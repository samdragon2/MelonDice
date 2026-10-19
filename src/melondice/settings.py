"""Keyboard-operable terminal Options; authorization URLs are displayed, never launched."""
from __future__ import annotations

from concurrent.futures import CancelledError
import copy
import json
from pathlib import Path

from prompt_toolkit.document import Document
from prompt_toolkit.layout import HSplit
from prompt_toolkit.widgets import Label, TextArea

from .auth import PLAN_SCOPE, USAGE_URL
from .dialogs import Modal, choose, message, prompt
from .storage import atomic_bytes


def save_option(app, key, value):
    config = copy.deepcopy(app.store.config)
    config[key] = value
    app.apply_config(config)


def settings(app):
    config = app.store.config
    def set_directory():
        def apply(text):
            path = Path(text).expanduser()
            if not path.is_dir():
                app.notify("Default document directory must already exist.")
                return
            save_option(app, "document_directory", str(path.absolute()))
        prompt(app, "Default document directory", "Directory:", apply, config["document_directory"])
    def number(key, label):
        def apply(text):
            try:
                save_option(app, key, int(text))
            except (OSError, ValueError) as error:
                app.error("Cannot save option", error)
        prompt(app, label, "Value:", apply, str(config[key]))
    def graphics_mode():
        modes = ["auto", "kitty", "sixel", "off"]
        choose(app, "PDF graphics — restart applies", modes,
               lambda i: save_option(app, "pdf_graphics", modes[i]))
    def cell_pixels():
        def apply(text):
            try:
                save_option(app, "pdf_cell_pixels", text.strip())
            except (OSError, ValueError) as error:
                app.error("Cannot save cell geometry", error)
        prompt(app, "PDF cell pixels — restart applies", "Measured WIDTHxHEIGHT; empty queries terminal. Font size is not cell geometry:",
               apply, config["pdf_cell_pixels"])
    choices = [
        ("ChatGPT account: " + app.accounts.status, lambda: account_menu(app)),
        ("Model: " + (config["model"] or "None selected"), lambda: models(app)),
        ("Default directory: " + config["document_directory"], set_directory),
        ("Theme: " + config["theme"], lambda: save_option(app, "theme", "light" if config["theme"] == "dark" else "dark")),
        (f"Mouse reporting: {config['mouse_support']}", lambda: save_option(app, "mouse_support", not config["mouse_support"])),
        ("PDF graphics: " + config["pdf_graphics"] + " (restart applies)", graphics_mode),
        ("PDF cell pixels: " + (config["pdf_cell_pixels"] or "Query terminal") + " (restart applies)", cell_pixels),
        ("Keyboard shortcuts", lambda: shortcuts(app)),
        (f"Escape timeout: {config['escape_timeout_ms']} ms", lambda: number("escape_timeout_ms", "Escape timeout (50–2000 ms)")),
        (f"Persist chat history: {config['history_persistence']}", lambda: save_option(app, "history_persistence", not config["history_persistence"])),
        (f"Editor recovery autosave: {config['editor_autosave_seconds']} seconds", lambda: number("editor_autosave_seconds", "Recovery autosave (0 disables; 1–3600 seconds)")),
        (f"OAuth callback port: {config['callback_port']}", lambda: number("callback_port", "Loopback callback port (1024–65535)")),
        ("Font size / Korean input (terminal-controlled)", lambda: message(app, "Terminal font and input", "Font family, size, and IME are controlled by your terminal/client environment. Melon Dice does not change them. Use UTF-8, Korean-capable client fonts, and a client input method. Bare Linux consoles have no image protocol; run inside a compatible terminal such as mlterm-fb for Sixel PDF images.")),
    ]
    choose(app, "Melon Dice Options — changes save immediately", [label for label, _ in choices], lambda i: choices[i][1]())


def shortcuts(app):
    entry = TextArea(text=json.dumps(app.store.config["shortcuts"], indent=2), multiline=True, scrollbar=True, height=12)
    note = Label(text="Use lists of terminal key sequences: f6, c-o, escape tab. Reserved/conflicting bindings are rejected.")
    def save():
        try:
            save_option(app, "shortcuts", json.loads(entry.text))
            dialog.close()
        except (OSError, ValueError, TypeError) as error:
            note.text = f"Cannot save: {error}"
    dialog = Modal(app, "Keyboard shortcuts", HSplit([note, entry], padding=1),
                   [("Save", save), ("Cancel", lambda: dialog.dismiss())], focus=entry)


def models(app):
    values = list(app.accounts.catalog)
    if app.accounts.catalog_account != app.accounts.data.get("active") or not values:
        app.refresh_models(show_picker=True)
        return
    choose(app, "Available ChatGPT models", [f"{m['display_name']} [{m['slug']}]" for m in values],
           lambda index: save_option(app, "model", values[index]["slug"]), extra=[("Refresh", lambda: app.refresh_models(show_picker=True))])


def account_menu(app):
    active = app.accounts.active
    label = f"{active.get('email') or active['subject']} [{active['client_id']}]" if active else "None"
    choices = [
        ("Continue with ChatGPT", lambda: signin(app)),
        ("Authorize ChatGPT plan usage", lambda: signin(app, consent=True)),
        ("Saved accounts / workspaces", lambda: accounts(app)),
        ("Add another ChatGPT account/workspace", lambda: signin(app, new=True)),
        ("Sign out selected account", lambda: app.account_operation(app.accounts.signout())),
        ("Manage usage", lambda: message(app, "Manage ChatGPT usage", "Open this official URL in your browser:\n\n" + USAGE_URL + "\n\nReview allowance and app access there. No unlimited usage is assumed.")),
        ("Resume requests after reviewing usage", lambda: app.account_operation(app.accounts.resume_usage(), reset_model=False)),
        ("Refresh available models", lambda: app.refresh_models(show_picker=True)),
    ]
    choose(app, "ChatGPT: " + app.accounts.status + " | " + label, [text for text, _ in choices], lambda index: choices[index][1]())


def accounts(app):
    values = list(app.accounts.data["accounts"].items())
    choose(app, "Saved ChatGPT registrations", [f"{record.get('email') or record['subject']} [{key}]" +
           (" (active)" if key == app.accounts.data.get("active") else "") for key, record in values],
           lambda index: app.account_operation(app.accounts.select(values[index][0]), success="Account selected; refresh its models."),
           extra=[("Add another", lambda: signin(app, new=True))])


def signin(app, *, new=False, consent=False):
    if app.account_busy:
        app.notify("An account operation is already running.")
        return
    app.stop_generation()
    url = TextArea(text="Starting loopback callback listener…", read_only=True, wrap_lines=True, scrollbar=True, height=8)
    holder = []
    link_value = []
    link_path = app.store.root / "oauth-authorization-url.txt"
    def remove_link():
        try:
            link_path.unlink(missing_ok=True)
        except OSError as error:
            app.notify(f"Could not remove the private authorization link file: {error}")
    def cancel():
        if holder:
            holder[0].cancel()
        remove_link()
    def save_link():
        if link_value:
            try:
                atomic_bytes(link_path, (link_value[0] + "\n").encode())
                app.notify(f"Private link saved at {link_path}; read via a second SSH session. It is deleted when the attempt ends.")
            except OSError as error:
                app.notify(f"Cannot save authorization link: {error}")
    dialog = Modal(app, "Continue with ChatGPT", HSplit([
        Label(text="Authenticate and grant permission in OpenAI's official browser flow.\n"
                   "SSH: first forward the callback port, e.g. ssh -L 1455:127.0.0.1:1455 USER@PI.\n"
                   "Open the URL below on the browser computer. No browser is launched by this TUI.\n"
                   "Keep the URL private. Tab/Shift+arrows or Ctrl+Space select; Ctrl+C copies internally."), url], padding=1),
        [("Save link to private file", save_link), ("Cancel", lambda: dialog.dismiss())], focus=url, cancel=cancel)
    def announce(link):
        if app.dialog is dialog:
            link_value[:] = [link]
            url.buffer.set_document(Document(link, 0), bypass_readonly=True)
    def done(future):
        remove_link()
        if app.dialog is dialog:
            dialog.close()
        try:
            future.result()
        except CancelledError:
            app.notify("Authorization cancelled; prior account unchanged.")
            return
        except Exception as error:
            app.error("ChatGPT authorization failed", error)
            return
        active = app.accounts.active
        def connected():
            if active and PLAN_SCOPE in active.get("scopes", []) and not active.get("welcomed"):
                active["welcomed"] = True
                try:
                    app.accounts.persist()
                except OSError as error:
                    app.notify(f"Could not save welcome preference: {error}")
                message(app, "You're using your ChatGPT plan", "Eligible requests in Melon Dice use your ChatGPT plan or available credits. Manage usage in ChatGPT Settings:\n" + USAGE_URL,
                        lambda: app.refresh_models(show_picker=True))
            elif active and PLAN_SCOPE in active.get("scopes", []):
                app.refresh_models(show_picker=True)
            else:
                message(app, "Identity-only sign-in", "Signed in, but ChatGPT plan usage was not authorized. Choose Authorize ChatGPT plan usage in Options before chatting.")
        app.defer(connected)
    key = None if new else app.accounts.data.get("active")
    app.account_job = app.tasks.submit(app.accounts.signin(app.store.config["callback_port"],
                       lambda link: app.tasks.post(announce, link), key, consent), done)
    holder.append(app.account_job)
