"""One retained terminal text buffer with safe file operations and recovery."""
from __future__ import annotations

import os
import stat

from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.layout import HSplit
from prompt_toolkit.selection import SelectionState
from prompt_toolkit.widgets import Label, TextArea

from .dialogs import FilePicker, Modal, confirm
from .storage import atomic_bytes, atomic_json, open_regular, read_json

MAX_TEXT = 8 * 1024 * 1024


class Editor:
    def __init__(self, app):
        self.app = app
        self.path = None
        self.encoding = "utf-8"
        self.saved_text = ""
        self.stamp = None
        self.busy = False
        self.alive = True
        self.revision = 0
        self.epoch = 0
        self.recovery_pending = (app.store.root / "editor-recovery.json").exists()
        self.last_autosave = 0.0
        self.autosave_revision = -1
        self.recovery_future = None
        self.text = TextArea(multiline=True, scrollbar=True, line_numbers=True, wrap_lines=False,
                             read_only=Condition(lambda: self.busy), focus_on_click=True)
        self.text.buffer.on_text_changed += self.changed
        self.container = HSplit([Label(text=self.heading), self.text,
            Label(text="^S/F8 Save  F7 Save As  F3 Open  ^N New  ^F Find/Replace  F9 Recovery\n"
                       "^Z Undo  ^Y Redo  Shift+arrows / ^Space / Alt+A Select  ^C Copy  ^V Paste")])

    @property
    def dirty(self):
        return self.text.text != self.saved_text

    def heading(self):
        document = self.text.buffer.document
        return f"File: {self.path or 'Untitled'} {'*' if self.dirty else ''}  Ln {document.cursor_position_row + 1}, Col {document.cursor_position_col + 1}" + ("  Working…" if self.busy else "")

    def focus(self):
        return self.text

    def changed(self, _buffer):
        self.revision += 1

    def guard(self, continuation):
        if self.busy:
            self.app.notify("Wait for the file operation to finish.")
        elif self.dirty:
            confirm(self.app, "Unsaved document", "Save changes before continuing?", [
                ("Save", lambda: self.save(after=continuation, protected=True)),
                ("Discard", lambda: self.discard_then(continuation))])
        else:
            continuation()

    def discard_then(self, continuation):
        self.remove_recovery()
        continuation()

    def reset(self, value="", path=None, encoding="utf-8", stamp=None):
        self.text.buffer.reset(document=Document(value, 0))
        self.path, self.encoding, self.stamp = path, encoding, stamp
        self.saved_text = value
        self.text.window.vertical_scroll = 0
        self.text.window.horizontal_scroll = 0
        self.remove_recovery()

    def new(self):
        self.guard(self.reset)

    def open(self):
        self.guard(lambda: FilePicker(self.app, "Open UTF-8 document", self.load))

    def load(self, path):
        self.busy = True
        def read():
            with open_regular(path) as handle:
                data = handle.read(MAX_TEXT + 1)
                info = os.fstat(handle.fileno())
            if len(data) > MAX_TEXT or b"\x00" in data:
                raise ValueError("Use a plain-text file without NUL bytes, at most 8 MiB.")
            encoding = "utf-8-sig" if data.startswith(b"\xef\xbb\xbf") else "utf-8"
            return data.decode(encoding), encoding, (info.st_mtime_ns, info.st_size)
        def done(value):
            if self.alive:
                self.busy = False
                text, encoding, stamp = value
                self.reset(text, path, encoding, stamp)
        def error(error):
            self.busy = False
            self.app.error("Cannot open document", error)
        self.app.io(read, done, on_error=error)

    def save(self, after=None, protected=False, force_as=False):
        if self.busy:
            self.app.notify("Wait for the current file operation.")
        elif self.path is None or force_as:
            FilePicker(self.app, "Save document as", lambda path: self.write(path, after), save=True,
                       initial=self.path, protected=protected)
        else:
            self.write(self.path, after)

    def write(self, path, after=None):
        value = self.text.text
        encoding = self.encoding
        expected = self.stamp if path == self.path else None
        self.busy = True
        def write():
            if len(value.encode(encoding)) > MAX_TEXT:
                raise ValueError("Document exceeds the 8 MiB save limit.")
            if expected is not None:
                info = path.stat()
                if (info.st_mtime_ns, info.st_size) != expected:
                    raise OSError("File changed on disk. Use F7 Save As to preserve both versions.")
            mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
            atomic_bytes(path, value.encode(encoding), mode)
            info = path.stat()
            return info.st_mtime_ns, info.st_size
        def done(stamp):
            if self.alive:
                self.busy = False
                self.path, self.stamp, self.saved_text = path, stamp, value
                self.remove_recovery()
                self.app.notify("Document saved.")
                if after:
                    after()
        def error(error):
            self.busy = False
            self.app.error("Cannot save document", error)
        self.app.io(write, done, on_error=error)

    def find(self):
        if self.busy:
            return
        needle, replacement = TextArea(multiline=False, focus_on_click=True), TextArea(multiline=False, focus_on_click=True)
        note = Label(text="Literal, case-sensitive search; wraps at the end.")
        def next_match():
            query = needle.text
            if not query:
                return
            buffer = self.text.buffer
            start = max(buffer.document.selection_range()) if buffer.selection_state else buffer.cursor_position
            found = buffer.text.find(query, start)
            if found < 0:
                found = buffer.text.find(query, 0, start)
            if found < 0:
                note.text = "No match found."
            else:
                buffer.document = Document(buffer.text, found + len(query), selection=SelectionState(found))
                # Keep the document's cursor visible even while the dialog owns focus.
                self.text.window.vertical_scroll = max(0, buffer.document.cursor_position_row - 3)
                note.text = "Match selected in document."
        def replace_one():
            buffer = self.text.buffer
            if buffer.selection_state:
                document, selected = buffer.document.cut_selection()
                if selected.text == needle.text:
                    buffer.save_to_undo_stack()
                    buffer.document = document
                    buffer.insert_text(replacement.text)
            next_match()
        def replace_all():
            if not needle.text:
                return
            buffer = self.text.buffer
            count = buffer.text.count(needle.text)
            if count:
                buffer.save_to_undo_stack()
                buffer.document = Document(buffer.text.replace(needle.text, replacement.text), 0)
            note.text = f"Replaced {count} matches; Ctrl+Z in document undoes this change."
        dialog = Modal(self.app, "Find and replace", HSplit([Label(text="Find:"), needle,
                       Label(text="Replace with:"), replacement, note], padding=1),
                       [("Find next", next_match), ("Replace", replace_one),
                        ("Replace all", replace_all), ("Close", lambda: dialog.dismiss())], focus=needle)
        needle.buffer.accept_handler = lambda _b: (next_match(), True)[1]

    def remove_recovery(self):
        if self.recovery_pending:
            return
        # Invalidate a background recovery writer before removing its destination.
        self.revision += 1
        self.epoch += 1
        self.autosave_revision = -1
        try:
            (self.app.store.root / "editor-recovery.json").unlink(missing_ok=True)
        except OSError as error:
            self.app.notify(f"Recovery cleanup failed: {error}")

    def tick(self, now):
        interval = self.app.store.config["editor_autosave_seconds"]
        if (not interval or not self.dirty or self.busy or self.recovery_pending or
                self.recovery_future or now - self.last_autosave < interval or self.autosave_revision == self.revision):
            return
        self.last_autosave = now
        revision = self.revision
        epoch = self.epoch
        value = {"text": self.text.text, "path": str(self.path) if self.path else None,
                 "encoding": self.encoding, "cursor": self.text.buffer.cursor_position}
        # The background job prepares JSON; its main-thread callback commits only a current snapshot.
        def prepare():
            import json
            return (json.dumps(value, ensure_ascii=False) + "\n").encode()
        def done(data):
            self.recovery_future = None
            if self.alive and epoch == self.epoch and self.dirty:
                try:
                    atomic_bytes(self.app.store.root / "editor-recovery.json", data)
                    self.autosave_revision = revision
                except OSError as error:
                    self.app.notify(f"Recovery autosave failed: {error}")
        def error(error):
            self.recovery_future = None
            self.app.notify(f"Recovery autosave failed: {error}")
        self.recovery_future = self.app.io(prepare, done, on_error=error)

    def offer_recovery(self):
        path = self.app.store.root / "editor-recovery.json"
        try:
            saved = read_json(path, None)
            if saved is None:
                return
            if (not isinstance(saved, dict) or not isinstance(saved.get("text"), str)
                    or len(saved["text"].encode("utf-8")) > MAX_TEXT
                    or saved.get("encoding", "utf-8") not in {"utf-8", "utf-8-sig"}):
                raise ValueError("Invalid recovery record; it has been preserved.")
            self.recovery_pending = True
        except (OSError, ValueError) as error:
            self.app.error("Cannot read recovery", error)
            return
        def recover():
            self.recovery_pending = False
            self.path, self.stamp, self.saved_text = None, None, ""
            self.encoding = saved.get("encoding", "utf-8")
            cursor = saved.get("cursor", 0)
            # Previous GUI journals stored a line.column string; preserve text even if cursor cannot migrate.
            cursor = min(len(saved["text"]), cursor) if isinstance(cursor, int) else 0
            self.text.buffer.reset(document=Document(saved["text"], max(0, cursor)))
        def discard():
            self.recovery_pending = False
            self.remove_recovery()
        confirm(self.app, "Editor recovery", f"Recovery copy for {saved.get('path') or 'Untitled'}.",
                [("Recover as Untitled", recover), ("Discard recovery", discard)])

    def close(self):
        self.alive = False
        self.remove_recovery()

    def emergency_save(self):
        if self.dirty and not self.recovery_pending and self.app.store.config["editor_autosave_seconds"]:
            atomic_json(self.app.store.root / "editor-recovery.json", {
                "text": self.text.text, "path": str(self.path) if self.path else None,
                "encoding": self.encoding, "cursor": self.text.buffer.cursor_position})
