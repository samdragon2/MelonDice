"""Retained terminal chat buffers and background subscription inference."""
from __future__ import annotations

from concurrent.futures import CancelledError
from dataclasses import asdict

import httpx
from prompt_toolkit.document import Document
from prompt_toolkit.layout import HSplit
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.widgets import Label, TextArea

from .auth import ServiceError, stream_response
from .conversations import Attachment, Conversation, MAX_ATTACHMENTS_BYTES
from .dialogs import FilePicker, choose, confirm, prompt


class Chat:
    def __init__(self, app):
        self.app = app
        self.conversation = Conversation()
        self.input = TextArea(multiline=True, height=Dimension(min=2, preferred=4, max=7), scrollbar=True, focus_on_click=True)
        self.output = TextArea(read_only=True, scrollbar=True, wrap_lines=True, focus_on_click=True)
        self.input.buffer.on_text_changed += self.edited
        self.container = HSplit([Label(text=self.heading), self.output, Label(text=self.attachment_label),
                                Label(text="Message:"), self.input,
                                Label(text="Enter Send  ^J Newline  ^N New  F3 History  F4 Attach  F5 Remove\n"
                                           "PgUp/PgDn Scroll  Esc Stop  F9 Retry  Alt+U Manage usage  Tab Change focus")])
        self.future = None
        self.generation = 0
        self.alive = True
        self.snapshot_ids = set()
        self.cancelled_snapshots = set()
        self.follow = True
        self.updating_output = False
        self.output.buffer.on_cursor_position_changed += self.cursor_moved
        self.render_needed = True
        self.last_save = 0.0

    def focus(self):
        return self.input

    def heading(self):
        return f"Session: {self.conversation.title} | Status: {self.conversation.status}\n{self.app.accounts.status} | Model: {self.app.store.config['model'] or 'Choose in Options'}"

    def attachment_label(self):
        names = ", ".join(a.name for a in self.conversation.attachments) or "None"
        return "Attachments: " + names + (" (snapshot loading…)" if self.snapshot_ids - self.cancelled_snapshots else "")

    def edited(self, _buffer):
        self.conversation.draft = self.input.text
        self.conversation.dirty = True

    def touch(self):
        self.conversation.dirty = True
        self.render_needed = True

    def cursor_moved(self, _buffer):
        if not self.updating_output:
            self.follow = False

    def render_transcript(self):
        parts = []
        for item in self.conversation.messages:
            parts.append(("You" if item["role"] == "user" else "Assistant") + ":\n" + item["text"] + "\n")
            parts.extend("[Image: " + a["name"] + "]\n" for a in item.get("attachments", []))
            if item.get("state") not in {None, "complete", "generating"}:
                parts.append("[" + item["state"] + "]\n")
            parts.append("\n")
        text = "".join(parts)
        old = self.output.buffer.document
        selection = old.selection
        if selection is not None and selection.original_cursor_position > len(text):
            selection = None
        follow = self.follow and self.app.active == "chat" and selection is None
        cursor = len(text) if follow else min(old.cursor_position, len(text))
        self.updating_output = True
        try:
            self.output.buffer.set_document(Document(text, cursor, selection=selection), bypass_readonly=True)
        finally:
            self.updating_output = False
        self.render_needed = False

    def replace(self, conversation):
        self.conversation = conversation
        self.input.buffer.reset(document=Document(conversation.draft, len(conversation.draft)))
        self.conversation.dirty = False
        self.output.buffer.reset()
        self.output.window.vertical_scroll = 0
        self.follow = True
        self.render_transcript()

    def save_history(self, force=False, silent=False):
        try:
            self.conversation.draft = self.input.text
            self.app.history.save(self.conversation, force)
            return True
        except (OSError, ValueError) as error:
            if silent:
                self.app.notify(f"Cannot save conversation: {error}")
            else:
                self.app.error("Cannot save conversation", error)
            return False

    def guard(self, continuation):
        if self.snapshot_ids - self.cancelled_snapshots:
            self.app.notify("Wait for image snapshots, or press Esc to cancel attachment loading.")
        elif self.future:
            confirm(self.app, "Generation in progress", "Stop generation before continuing?", [
                ("Stop", lambda: (self.stop(), self.guard(continuation)))])
        elif self.conversation.dirty:
            def save():
                if self.save_history(force=True):
                    continuation()
            confirm(self.app, "Unsaved conversation", "Save the conversation, draft, and images locally?", [
                ("Save", save), ("Discard", continuation)])
        else:
            continuation()

    def new(self):
        self.guard(lambda: self.replace(Conversation()))

    def history(self):
        entries = self.app.history.entries()
        def load(index):
            def apply():
                try:
                    self.replace(self.app.history.load(entries[index][0]))
                except (OSError, ValueError, TypeError) as error:
                    self.app.error("Cannot open conversation", error)
            self.guard(apply)
        def rename(index):
            key, value = entries[index]
            def apply(title):
                if not title.strip():
                    return
                try:
                    conversation = self.conversation if key == self.conversation.id else self.app.history.load(key)
                    conversation.title = title.strip()[:120]
                    self.app.history.save(conversation, force=True)
                except (OSError, ValueError, TypeError) as error:
                    self.app.error("Cannot rename conversation", error)
            prompt(self.app, "Rename conversation", "Title:", apply, value["title"])
        def delete(index):
            key, value = entries[index]
            if key == self.conversation.id and self.future:
                self.app.notify("Stop generation before deleting its conversation.")
                return
            def apply():
                try:
                    self.app.history.delete(key)
                    if key == self.conversation.id:
                        self.replace(Conversation())
                except (OSError, ValueError) as error:
                    self.app.error("Cannot delete conversation", error)
            confirm(self.app, "Delete conversation", f"Permanently delete {value['title']} and its saved images/draft?",
                    [("Delete", apply)])
        choose(self.app, "Local conversation history", [value["title"] for _, value in entries], load,
               [("Rename", rename), ("Delete", delete)], extra=[("New", self.new)])

    def attach(self):
        if not self.app.accounts.image_allowed(self.app.store.config["model"]):
            self.app.notify("Images require authorized ChatGPT plan usage and a current catalog with an explicitly verified image model (gpt-6.1-sol).")
            return
        FilePicker(self.app, "Attach an existing local image (does not send)", self.snapshot)

    def snapshot(self, path):
        conversation, token = self.conversation, object()
        self.snapshot_ids.add(token)
        def finish(attachment=None, error=None):
            self.snapshot_ids.discard(token)
            cancelled = token in self.cancelled_snapshots
            self.cancelled_snapshots.discard(token)
            if not self.alive or self.conversation is not conversation or cancelled:
                return
            if error:
                self.app.error("Cannot attach image", error)
                return
            if len(conversation.attachments) >= 4 or sum(a.size for a in conversation.attachments) + attachment.size > MAX_ATTACHMENTS_BYTES:
                self.app.notify("Pending attachments exceed four images or 16 MiB combined.")
                return
            conversation.attachments.append(attachment)
            self.touch()
        self.app.io(lambda: Attachment.snapshot(path), finish, on_error=lambda error: finish(error=error))

    def remove_attachment(self):
        values = self.conversation.attachments
        def remove(index):
            values.pop(index)
            self.touch()
        choose(self.app, "Remove pending attachment", [a.name for a in values], remove)

    def retry(self):
        values = self.conversation.messages
        if self.future or not values or values[-1].get("state") not in {"stopped", "failed", "incomplete", "interrupted", "network error"}:
            self.app.notify("No failed/stopped response is available to retry.")
            return
        confirm(self.app, "Retry response", "Retry replaces the last partial response and may use additional ChatGPT plan allowance. Your next draft is retained.",
                [("Retry", lambda: self.send(retry=True))])

    def send(self, retry=False):
        conversation = self.conversation
        if self.future or self.snapshot_ids - self.cancelled_snapshots:
            self.app.notify("Wait for the operation, or press Esc to stop/cancel it.")
            return
        if self.app.account_busy:
            self.app.notify("An account operation is in progress.")
            return
        if not retry and not self.input.text.strip() and not conversation.attachments:
            return
        accounts, model = self.app.accounts, self.app.store.config["model"]
        if accounts.catalog_account != accounts.data.get("active") or not any(m["slug"] == model for m in accounts.catalog):
            self.app.notify("Connect, refresh the account model catalog, and select a model in Options.")
            return
        if accounts.data.get("active") in accounts.usage_blocks:
            self.app.notify("Usage limit reached. Manage usage, then explicitly resume requests in Options.")
            return
        images = conversation.attachments or any(m.get("attachments") for m in conversation.messages)
        if images and not accounts.image_allowed(model):
            self.app.notify("This conversation includes images; choose an authorized image-capable model.")
            return
        if retry:
            conversation.messages.pop()
        else:
            conversation.messages.append({"role": "user", "text": self.input.text,
                                          "attachments": [asdict(a) for a in conversation.attachments]})
            if conversation.title == "New conversation":
                conversation.title = self.input.text.strip().split("\n")[0][:60] or "Image conversation"
            self.input.buffer.reset()
            conversation.draft, conversation.attachments = "", []
        payload = conversation.payload()
        assistant = {"role": "assistant", "text": "", "state": "generating"}
        conversation.messages.append(assistant)
        conversation.status = "Generating…"
        self.generation += 1
        generation = self.generation
        self.follow = True
        self.touch()
        def delta(text):
            if self.alive and generation == self.generation:
                assistant["text"] += text
                self.touch()
        async def run():
            await stream_response(accounts, model, payload, lambda text: self.app.tasks.post(delta, text))
        def done(future):
            if not self.alive or generation != self.generation:
                return
            self.future = None
            try:
                future.result()
                assistant["state"], conversation.status = "complete", "Ready"
            except CancelledError:
                assistant["state"], conversation.status = "stopped", "Stopped"
            except httpx.HTTPError:
                assistant["state"], conversation.status = "network error", "Network error; F9 retries explicitly"
            except Exception as error:
                assistant["state"], conversation.status = "failed", str(error)
                self.app.notify(str(error))
                if isinstance(error, ServiceError):
                    assistant["state"] = {"response_incomplete": "incomplete", "stream_interrupted": "interrupted"}.get(error.code, "failed")
                    accounts.connection_note = str(error)
                    if error.code == "subscription_sharing_usage_limit_exceeded":
                        accounts.usage_blocks.add(accounts.data.get("active"))
            self.touch()
        self.future = self.app.tasks.submit(run(), done)

    def stop(self):
        self.cancelled_snapshots.update(self.snapshot_ids)
        if self.future:
            self.generation += 1
            self.future.cancel()
            self.future = None
            self.conversation.messages[-1]["state"] = "stopped"
            self.conversation.status = "Stopped"
            self.touch()

    def scroll(self, direction):
        buffer = self.output.buffer
        lines = max(1, (self.output.window.render_info.window_height if self.output.window.render_info else 12) - 2)
        offset = buffer.document.get_cursor_up_position(lines) if direction < 0 else buffer.document.get_cursor_down_position(lines)
        buffer.cursor_position += offset
        self.follow = direction > 0 and buffer.document.cursor_position_row >= buffer.document.line_count - 1

    def tick(self, now):
        if self.render_needed:
            self.render_transcript()
        if (self.app.store.config["history_persistence"] and self.conversation.dirty and now - self.last_save >= 3
                and not (self.app.dialog and self.app.dialog.protected)):
            self.last_save = now
            self.save_history(silent=True)

    def close(self):
        self.stop()
        self.alive = False
