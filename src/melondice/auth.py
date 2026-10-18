"""Documented Sign in with ChatGPT public-client flow. No API-key fallback."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import secrets
import stat
import time
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import jwt

from .storage import atomic_json, read_json

ISSUER = "https://auth.openai.com"
AUTHORIZE = ISSUER + "/api/accounts/authorize"
TOKEN = ISSUER + "/api/accounts/oauth/token"
RESOURCE = "https://api.openai.com/v1"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
PLAN_SCOPE = "chatgpt.tokens.use.direct"
USAGE_URL = "https://chatgpt.com/settings/usage"
TERMINAL_REFRESH = {"invalid_grant", "invalid_refresh_token", "token_expired",
                    "refresh_token_expired", "refresh_token_invalidated", "refresh_token_reused"}


class ServiceError(Exception):
    def __init__(self, message, *, status=None, code="", request_id="", param="", shape=""):
        super().__init__(message)
        self.status, self.code, self.request_id = status, code, request_id
        self.param, self.shape = param, shape

    def __str__(self):
        parts = [super().__str__()]
        for key, value in [("HTTP", self.status), ("code", self.code), ("param", self.param),
                           ("request", self.request_id), ("shape", self.shape)]:
            if value:
                parts.append(f"{key}: {value}")
        return " | ".join(parts)


def error_from_body(body, status=None, request_id="", sensitive=False):
    if not isinstance(body, dict):
        body = {}
    error = body.get("error", body if "code" in body else {})
    if isinstance(error, str):
        error = {"code": error}
    if not isinstance(error, dict):
        error = {}
    code = str(error.get("code") or error.get("type") or "")[:150]
    messages = {
        "subscription_sharing_user_not_eligible": "This account/workspace is not eligible for ChatGPT plan usage.",
        "subscription_sharing_usage_limit_exceeded": "Usage limit reached. Pause requests and choose Manage usage.",
        "subscription_sharing_usage_unavailable": "Usage availability could not be checked. Retry later.",
        "subscription_sharing_unsupported_capability": "The selected model or input capability is unsupported.",
        "subscription_sharing_route_not_supported": "ChatGPT plan route is not supported for this request.",
        "subscription_sharing_invalid_user": "Subscriber identity could not be validated. Reconnect the account.",
        "subscription_sharing_user_unavailable": "Account/workspace is temporarily unavailable. Retry later.",
    }
    message = messages.get(code)
    if not message:
        message = {401: "Authentication was rejected; check account permissions or reconnect.",
                   403: "Access denied by eligibility, permission, region, or policy.",
                   429: "Usage/rate limit reached. Manage usage or retry later.",
                   503: "ChatGPT plan routing is unavailable. Retry later."}.get(status)
    if not message:
        message = "Authorization request failed." if sensitive else "OpenAI request failed."
    # Never include a token-endpoint response, URL, or request headers in diagnostics.
    if not sensitive:
        detail = error.get("message") or body.get("detail")
        if isinstance(detail, str):
            message += " " + detail[:800]
    return ServiceError(message, status=status, code=code, request_id=request_id,
                        param=str(error.get("param") or "")[:100],
                        shape=",".join(sorted(str(k) for k in body))[:150])


def checked(response, *, sensitive=False):
    if not response.is_success:
        try:
            body = response.json()
        except ValueError:
            body = {}
        raise error_from_body(body, response.status_code,
                              response.headers.get("openai-request-id") or response.headers.get("x-request-id", ""), sensitive)
    try:
        return response.json()
    except ValueError:
        raise ServiceError("Server returned invalid JSON.") from None


def http_client():
    return httpx.AsyncClient(timeout=httpx.Timeout(30, connect=15), follow_redirects=False)


class Accounts:
    def __init__(self, store):
        self.store = store
        self.path = store.root / "accounts.json"
        if self.path.exists():
            info = self.path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_mode & 0o077):
                raise OSError("accounts.json must be an owned regular file with mode 0600.")
        self.data = read_json(self.path, {"active": None, "accounts": {}})
        if not isinstance(self.data, dict) or not isinstance(self.data.get("accounts"), dict):
            raise ValueError("Invalid accounts.json: expected an accounts object. Original file was preserved.")
        for key, record in self.data["accounts"].items():
            if (not isinstance(record, dict) or record.get("client_id") != key or key == "dynamic_agent_client"
                    or record.get("issuer") != ISSUER or not isinstance(record.get("subject"), str)
                    or not record["subject"] or not isinstance(record.get("scopes"), list)
                    or any(not isinstance(scope, str) for scope in record["scopes"])
                    or not isinstance(record.get("expires_at", 0), (int, float))
                    or any(name in record and not isinstance(record[name], str)
                           for name in ("access_token", "refresh_token", "id_token"))):
                raise ValueError("Invalid accounts.json registration. Original file was preserved.")
        if self.data.get("active") is not None and self.data["active"] not in self.data["accounts"]:
            raise ValueError("Invalid accounts.json: active registration is missing. Original file was preserved.")
        self.lock = asyncio.Lock()  # Used only on the dedicated network loop.
        self.catalog = []
        self.catalog_account = None
        self.connection_note = ""
        self.pending_path = store.root / "pending-registration.json"
        self.usage_blocks = set()

    def persist(self):
        atomic_json(self.path, self.data)

    @property
    def active(self):
        return self.data["accounts"].get(self.data.get("active"))

    @property
    def status(self):
        record = self.active
        if not record or not record.get("id_token"):
            return "Signed out" if not record or not record.get("expired") else "Expired session"
        if PLAN_SCOPE not in record.get("scopes", []):
            if record.get("id_expires_at", 0) <= time.time():
                return "Expired identity-only session"
            return "Signed in (identity only; plan usage disabled)"
        if record.get("expires_at", 0) <= time.time():
            return "Expired access token (renewal required)"
        if record["client_id"] in self.usage_blocks:
            return "Usage limit reached (ChatGPT plan)"
        return "Using ChatGPT plan"

    async def select(self, key):
        async with self.lock:
            if key not in self.data["accounts"]:
                raise ServiceError("Unknown account registration.")
            updated = {"active": key, "accounts": dict(self.data["accounts"])}
            atomic_json(self.path, updated)
            self.data = updated
            self.catalog = []
            self.catalog_account = None
            self.connection_note = ""

    async def resume_usage(self):
        async with self.lock:
            self.usage_blocks.discard(self.data.get("active"))
            self.connection_note = ""
        return "Usage retry enabled by user. The server still enforces all account and app limits."

    async def discovery(self, client):
        doc = checked(await client.get(ISSUER + "/.well-known/openid-configuration"), sensitive=True)
        if doc.get("issuer") != ISSUER:
            raise ServiceError("OpenAI discovery issuer mismatch.")
        for key in ("jwks_uri", "revocation_endpoint"):
            address = urlsplit(doc.get(key, ""))
            if address.scheme != "https" or address.netloc != "auth.openai.com":
                raise ServiceError("Unexpected OpenAI discovery endpoint.")
        return doc

    async def validate_identity(self, client, token, client_id, nonce=None):
        try:
            doc = await self.discovery(client)
            header = jwt.get_unverified_header(token)
            if header.get("alg") not in {"RS256", "ES256"}:
                raise ValueError("Unsupported signature algorithm")
            keys = checked(await client.get(doc["jwks_uri"]), sensitive=True)
            key = next(k for k in keys["keys"] if k.get("kid") == header.get("kid"))
            public_key = jwt.PyJWK.from_dict(key, algorithm=header["alg"]).key
            claims = jwt.decode(token, public_key, algorithms=[header["alg"]],
                                issuer=ISSUER, audience=client_id, leeway=5,
                                options={"require": ["sub", "exp", "iat", "iss", "aud"]})
            if not isinstance(claims["sub"], str) or not claims["sub"]:
                raise ValueError("Missing subject")
            if nonce is not None and not secrets.compare_digest(claims.get("nonce", ""), nonce):
                raise ValueError("Nonce mismatch")
            if "azp" in claims and claims["azp"] != client_id:
                raise ValueError("Authorized party mismatch")
            if isinstance(claims["aud"], list) and len(claims["aud"]) > 1 and claims.get("azp") != client_id:
                raise ValueError("Multiple audiences without a matching authorized party")
            return claims
        except (jwt.PyJWTError, ValueError, KeyError, StopIteration, TypeError):
            raise ServiceError("ID token identity validation failed; credentials were not replaced.") from None

    async def signin(self, port, announce, key=None, consent=False):
        """Own the callback listener for exactly one expiring authorization attempt."""
        async with self.lock:
            old = dict(self.data["accounts"].get(key, {}))
            if not old and key is None:
                pending = read_json(self.pending_path, {})
                if pending.get("ext_agent_host_id") == self.store.host_id:
                    old = pending
        state, nonce, verifier = (secrets.token_urlsafe(40) for _ in range(3))
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        redirect = f"http://127.0.0.1:{port}/auth/callback"
        result = asyncio.get_running_loop().create_future()

        async def callback(reader, writer):
            try:
                raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5)
                first = raw.split(b"\r\n", 1)[0].decode("ascii")
                method, target, _version = first.split(" ", 2)
                address = urlsplit(target)
                query = parse_qs(address.query, strict_parsing=True)
                valid = (method == "GET" and address.path == "/auth/callback"
                         and len(query.get("state", [])) == 1
                         and secrets.compare_digest(query["state"][0], state)
                         and all(len(v) == 1 for v in query.values()))
                if not valid or result.done():
                    status, body = "400 Bad Request", b"Invalid or expired sign-in callback."
                else:
                    result.set_result({k: v[0] for k, v in query.items()})
                    status, body = "200 OK", b"Return to Melon Dice to see the authorization result."
                writer.write(f"HTTP/1.1 {status}\r\nContent-Type: text/plain\r\nCache-Control: no-store\r\nConnection: close\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body)
                await writer.drain()
            except (ValueError, UnicodeError, asyncio.TimeoutError, asyncio.IncompleteReadError,
                    asyncio.LimitOverrunError, ConnectionError):
                pass
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(callback, "127.0.0.1", port, limit=8192)
        params = {"client_id": old.get("client_id", "dynamic_agent_client"),
                  "ext_agent_host_id": self.store.host_id, "response_type": "code",
                  "redirect_uri": redirect, "scope": SCOPES, "resource": RESOURCE,
                  "state": state, "nonce": nonce, "code_challenge_method": "S256",
                  "code_challenge": challenge}
        if not old:
            params["agent_name_hint"] = "Melon Dice"
        elif old.get("email"):
            # The official flow permits omitting id_token_hint. Keep the retained
            # token in protected storage and use the account selector for manual
            # SSH browser authorization, avoiding a very long sensitive URL.
            params["login_hint"] = old["email"]
        if consent:
            params["prompt"] = "consent"
        try:
            async with server:
                announce(AUTHORIZE + "?" + urlencode(params))
                query = await asyncio.wait_for(result, timeout=600)
        except asyncio.TimeoutError:
            raise ServiceError("Authorization timed out. Choose Continue with ChatGPT again.") from None
        if query.get("error"):
            raise ServiceError("Authorization declined or cancelled. Existing account remains unchanged.")
        issued = query.get("client_id") or old.get("client_id")
        if not issued or issued == "dynamic_agent_client" or not query.get("code"):
            raise ServiceError("Registration incomplete: authorization code or issued client ID missing.")
        if old and issued != old["client_id"]:
            raise ServiceError("Callback changed the selected account's client ID.")
        if not old.get("subject"):
            # Retain the issued registration across cancelled/failed exchanges without trusting identity.
            atomic_json(self.pending_path, {"client_id": issued, "ext_agent_host_id": self.store.host_id})
        async with http_client() as client:
            tokens = checked(await client.post(TOKEN, data={
                "grant_type": "authorization_code", "client_id": issued,
                "code": query["code"], "code_verifier": verifier,
                "redirect_uri": redirect, "resource": RESOURCE}), sensitive=True)
            claims = await self.validate_identity(client, tokens.get("id_token", ""), issued, nonce)
        if old.get("subject") and claims["sub"] != old["subject"]:
            raise ServiceError("Signed-in identity differs from the selected account. Add another account instead.")
        record = {"client_id": issued, "subject": claims["sub"], "issuer": ISSUER,
                  "email": claims.get("email", ""), "ext_agent_host_id": self.store.host_id,
                  "welcomed": old.get("welcomed", False), "id_expires_at": claims["exp"]}
        self.apply_tokens(record, tokens, initial=True)
        async with self.lock:
            existing = self.data["accounts"].get(issued)
            if existing and existing["subject"] != record["subject"]:
                raise ServiceError("Registration identity collision; account not replaced.")
            record["welcomed"] = (existing or record).get("welcomed", False)
            updated = {"active": issued, "accounts": dict(self.data["accounts"])}
            updated["accounts"][issued] = record
            atomic_json(self.path, updated)
            self.data = updated
            self.catalog = []
            self.catalog_account = None
            self.connection_note = ""
            self.pending_path.unlink(missing_ok=True)
        return issued

    @staticmethod
    def apply_tokens(record, tokens, initial=False):
        if tokens.get("token_type", "Bearer").lower() != "bearer":
            raise ServiceError("Unsupported OAuth token type.")
        for field in ("access_token", "refresh_token", "id_token"):
            if tokens.get(field):
                record[field] = tokens[field]
        if initial or "scope" in tokens:
            record["scopes"] = tokens.get("scope", "").split()
        record["expires_at"] = time.time() + float(tokens.get("expires_in", 0))
        record["saved_at"] = time.time()
        record["earliest_refresh_at"] = tokens.get("earliest_refresh_at", 0)
        record["expired"] = False

    async def access(self):
        async with self.lock:
            record = self.active
            if not record or not record.get("id_token"):
                raise ServiceError("Signed out or expired. Continue with ChatGPT in Options.")
            if PLAN_SCOPE not in record.get("scopes", []):
                raise ServiceError("Identity-only sign-in. Authorize ChatGPT plan usage in Options.")
            if record["client_id"] in self.usage_blocks:
                raise ServiceError("Usage limit reached. Manage usage, then explicitly resume requests in Options.",
                                   code="subscription_sharing_usage_limit_exceeded")
            if record.get("expires_at", 0) < time.time() + 60:
                if not record.get("refresh_token"):
                    record["expired"] = True
                    self.persist()
                    raise ServiceError("Session expired. Continue with ChatGPT again.")
                earliest = record.get("earliest_refresh_at")
                if isinstance(earliest, (int, float)) and earliest > time.time():
                    if record.get("expires_at", 0) > time.time():
                        return record["client_id"], record["access_token"]
                    raise ServiceError("Token renewal is not available yet. Retry later.")
                async with http_client() as client:
                    try:
                        tokens = checked(await client.post(TOKEN, data={
                            "grant_type": "refresh_token", "client_id": record["client_id"],
                            "refresh_token": record["refresh_token"], "resource": RESOURCE}), sensitive=True)
                    except ServiceError as error:
                        if error.code in TERMINAL_REFRESH:
                            self.clear_tokens(record)
                            record["expired"] = True
                            self.persist()
                        raise
                    updated = dict(record)
                    self.apply_tokens(updated, tokens)
                    if tokens.get("id_token"):
                        claims = await self.validate_identity(client, tokens["id_token"], record["client_id"])
                        if claims["sub"] != record["subject"]:
                            raise ServiceError("Renewed identity differs; credentials not replaced.")
                        updated["id_expires_at"] = claims["exp"]
                    if not tokens.get("access_token") or not tokens.get("refresh_token"):
                        raise ServiceError("Token renewal omitted replacement credentials.")
                    record.update(updated)
                    self.persist()
            if not record.get("access_token"):
                raise ServiceError("Plan usage access token missing. Reauthorize in Options.")
            return record["client_id"], record["access_token"]

    @staticmethod
    def clear_tokens(record):
        for name in ("access_token", "refresh_token", "id_token"):
            record.pop(name, None)
        record["scopes"] = []
        record["expires_at"] = 0

    async def signout(self):
        async with self.lock:
            record = self.active
            if not record:
                return "Signed out."
            confirmed = not record.get("refresh_token")
            try:
                if record.get("refresh_token"):
                    async with http_client() as client:
                        doc = await self.discovery(client)
                        for delay in (0, 1, 2):
                            if delay:
                                await asyncio.sleep(delay)
                            try:
                                response = await client.post(doc["revocation_endpoint"], data={
                                    "token": record["refresh_token"], "token_type_hint": "refresh_token",
                                    "client_id": record["client_id"]})
                                if response.status_code == 200:
                                    confirmed = True
                                    break
                                if response.status_code < 500:
                                    break
                            except httpx.HTTPError:
                                continue
            except (httpx.HTTPError, ServiceError):
                confirmed = False
            finally:
                self.clear_tokens(record)
                self.catalog = []
                self.catalog_account = None
                try:
                    self.persist()
                except OSError:
                    raise ServiceError("Signed out in memory, but credentials could not be cleared on disk. "
                                       "Resolve storage permissions and disconnect this app in ChatGPT Settings.") from None
            return ("Signed out; renewable session revoked." if confirmed else
                    "Signed out locally. Remote revocation was not confirmed; disconnect Melon Dice in ChatGPT Settings.")

    async def models(self):
        key, token = await self.access()
        async with http_client() as client:
            body = checked(await client.get(RESOURCE + "/models", headers={"Authorization": "Bearer " + token}))
        models = body.get("models")
        if not isinstance(models, list):
            raise ServiceError("Unexpected model catalog; expected the ChatGPT models array.")
        values = [{"slug": m["slug"], "display_name": m.get("display_name", m["slug"])}
                  for m in models if m.get("visibility") == "list" and isinstance(m.get("slug"), str)]
        if self.data.get("active") == key:
            self.catalog, self.catalog_account = values, key
        return values

    def image_allowed(self, model):
        # Conservative allowlist from official model modalities, not guesses from a slug.
        return (self.status == "Using ChatGPT plan" and self.catalog_account == self.data.get("active")
                and model == "gpt-6.1-sol" and any(m["slug"] == model for m in self.catalog))


async def stream_response(accounts, model, messages, emit):
    _key, token = await accounts.access()
    payload = {"model": model, "input": messages, "store": False, "stream": True}
    completed = False
    async with http_client() as client:
        async with client.stream("POST", RESOURCE + "/responses", json=payload,
                                 headers={"Authorization": "Bearer " + token}) as response:
            if not response.is_success:
                await response.aread()
                checked(response)
            data = []
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    data.append(line[5:].lstrip())
                    continue
                if line or not data:
                    continue
                raw, data = "\n".join(data), []
                if raw == "[DONE]":
                    continue
                event = json.loads(raw)
                kind = event.get("type")
                if kind == "response.output_text.delta":
                    emit(event.get("delta", ""))
                elif kind == "response.refusal.delta":
                    emit(event.get("delta", ""))
                elif kind in {"response.failed", "error"}:
                    raise error_from_body(event.get("response", event), response.status_code,
                                          response.headers.get("openai-request-id") or response.headers.get("x-request-id", ""))
                elif kind == "response.incomplete":
                    raise ServiceError("Response incomplete; partial text has been retained.", code="response_incomplete")
                elif kind == "response.completed":
                    completed = True
                    break
    if not completed:
        raise ServiceError("Stream interrupted before completion; partial text has been retained.", code="stream_interrupted")
