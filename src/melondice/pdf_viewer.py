"""PDF state/controller; MuPDF rasterization and Kitty presentation remain separate."""
from __future__ import annotations

from pathlib import Path

from prompt_toolkit.layout import DynamicContainer, HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Label, RadioList

from .dialogs import FilePicker, choose, prompt, selected_value
from .pdf_backend import PDFBackend


class Viewport(Window):
    def __init__(self, owner):
        self.owner = owner
        super().__init__(content=FormattedTextControl(owner.viewport_text, focusable=True),
                         wrap_lines=True, always_hide_cursor=True)

    def write_to_screen(self, screen, mouse_handlers, write_position, parent_style, erase_bg, z_index):
        self.owner.bounds = (write_position.xpos, write_position.ypos,
                             write_position.width, write_position.height)
        super().write_to_screen(screen, mouse_handlers, write_position, parent_style, erase_bg, z_index)


class PDFViewer:
    def __init__(self, app):
        self.app = app
        self.backend = None  # No native dependency/process is needed just to show a capability error.
        self.path = None
        self.pages = 0
        self.page = 0
        self.zoom = 1.0
        self.pan_x = self.pan_y = 0
        self.full = (0, 0)
        self.outline = []
        self.bounds = (0, 0, 0, 0)
        self.open_request = None
        self.open_path = None
        self.render_request = None
        self.inflight = None
        self.image = None
        self.image_key = None
        self.failed_key = None
        self.error = ""
        self.failed = False
        self.document_id = 0
        self.password_path = None
        self.cancelled_render = False
        self.recent_paths = app.store.recent()
        self.recents = RadioList(values=[(i, path) for i, path in enumerate(self.recent_paths)] or
                                [(-1, "No recent documents. Press F3 to open a PDF.")], select_on_focus=True)
        self.viewport = Viewport(self)
        recent = HSplit([Label(text="Recent files — Up/Down select, Enter open"), self.recents,
                         Label(text=lambda: "\n" + app.graphics.description + "\nThe rest of Melon Dice remains usable.")])
        self.container = HSplit([Label(text=self.heading),
                                DynamicContainer(lambda: self.viewport if self.pages else recent),
                                Label(text="F3 Open  F4 Outline  PgUp/PgDn Pages  G Go to page  +/- Zoom  Arrows Pan\n"
                                           "Esc Cancel pending operation  PDF is read-only; text copy/paste unavailable")])

    def focus(self):
        return self.viewport if self.pages else self.recents

    def heading(self):
        return f"pdfViewer | {self.path or 'No document'} | Page {self.page + 1 if self.pages else 0}/{self.pages} | {self.zoom:.0%} | Pan {self.pan_x},{self.pan_y}" + (" | Working…" if self.open_request or self.render_request else "")

    def desired(self):
        if not self.pages or not self.app.graphics.supported:
            return None
        _x, _y, columns, rows = self.bounds
        if min(columns, rows) <= 0:
            return None
        cell_width, cell_height = self.app.graphics.cell
        return (self.page, self.zoom, self.pan_x, self.pan_y, columns * cell_width, rows * cell_height)

    def viewport_text(self):
        if self.failed:
            return "PDF renderer unavailable. Close and reopen pdfViewer.\n" + self.error
        if not self.app.graphics.supported:
            return ("Original-layout PDF images unavailable in this terminal.\n\n" + self.app.graphics.description +
                    "\n\nUse a direct Kitty-graphics-compatible terminal with pixel geometry reporting.\n"
                    "No GUI will be opened and no extracted-text imitation will be shown.\n"
                    "Home, ChatGPT, the text editor, file metadata, and outline remain available.")
        if self.error:
            return "PDF rendering error: " + self.error
        if self.image is not None and self.image_key == self.desired():
            return ""
        return "Rendering PDF viewport…"

    def open(self):
        if self.open_request:
            self.app.notify("A PDF is opening. Esc cancels acceptance of that open.")
        else:
            FilePicker(self.app, "Open PDF", self.load)

    def open_selected_recent(self):
        index = selected_value(self.recents)
        if index is not None and index >= 0:
            self.load(Path(self.recent_paths[index]))

    def load(self, path, password=""):
        if self.open_request or self.failed:
            self.app.notify("Wait for/cancel the PDF operation, or close and reopen a failed viewer.")
            return
        try:
            if self.backend is None:
                self.backend = PDFBackend()
            self.open_path = path
            self.open_request = self.backend.send("open", str(path), password)
        except Exception as error:
            self.app.error("Cannot start PDF renderer", error)

    def poll(self):
        if self.failed or self.backend is None:
            return
        try:
            for sequence, kind, value in self.backend.receive():
                if kind == "startup_error":
                    self.failed, self.error = True, value
                    self.app.notify(value)
                    return
                if sequence == self.open_request:
                    self.open_request = None
                    if kind == "password":
                        self.password_path = self.open_path
                    elif kind == "opened":
                        self.backend.send("commit")
                        self.document_id += 1
                        self.path, self.pages, self.outline = self.open_path, value["pages"], value["outline"]
                        self.page, self.zoom, self.pan_x, self.pan_y = 0, 1.0, 0, 0
                        self.image, self.image_key, self.failed_key, self.error = None, None, None, ""
                        try:
                            self.app.store.recent(self.path)
                        except OSError as error:
                            self.app.notify(f"PDF opened; recent-file persistence failed: {error}")
                        if self.app.active == "pdf" and not self.app.dialog:
                            self.app.ui.layout.focus(self.viewport)
                    else:
                        self.app.notify("Cannot open PDF: " + str(value))
                elif sequence == self.render_request:
                    self.render_request = None
                    if self.cancelled_render:
                        self.cancelled_render = False
                        continue
                    if self.inflight != self.desired():
                        continue
                    if kind == "rendered":
                        self.pan_x, self.pan_y = value["pan"]
                        self.full = value["full"]
                        self.image, self.image_key = value["png"], self.desired()
                        self.error, self.failed_key = "", None
                    else:
                        self.error, self.failed_key = str(value), self.inflight
            if self.password_path and self.app.active == "pdf" and not self.app.dialog:
                path, self.password_path = self.password_path, None
                prompt(self.app, "PDF password", "Enter password (also shown after an incorrect password):",
                       lambda password: self.load(path, password), secret=True)
            desired = self.desired()
            if (self.app.active == "pdf" and not self.app.dialog and not self.open_request and not self.render_request
                    and desired is not None and desired != self.image_key and desired != self.failed_key):
                self.error = ""
                self.inflight = desired
                self.render_request = self.backend.send("render", *desired)
        except Exception as error:
            self.failed, self.error = True, str(error)
            self.app.notify(f"PDF renderer error: {error}")

    def turn(self, amount):
        if self.pages and not self.open_request:
            self.page = max(0, min(self.pages - 1, self.page + amount))
            self.pan_x = self.pan_y = 0
            self.error = ""

    def goto(self):
        if not self.pages:
            return
        def apply(text):
            try:
                number = int(text)
                if not 1 <= number <= self.pages:
                    raise ValueError(f"Enter 1–{self.pages}.")
                self.turn(number - 1 - self.page)
            except ValueError as error:
                self.app.error("Invalid page", error)
        prompt(self.app, "Go to page", f"Page (1–{self.pages}):", apply, str(self.page + 1))

    def magnify(self, factor):
        if self.pages and not self.open_request:
            self.zoom = max(0.25, min(4.0, self.zoom * factor))
            self.error = ""

    def pan(self, x, y):
        if self.pages and not self.open_request:
            self.pan_x = max(0, self.pan_x + x * 32)
            self.pan_y = max(0, self.pan_y + y * 32)
            self.error = ""

    def show_outline(self):
        entries = [(level, title, page) for level, title, page in self.outline if page > 0]
        choose(self.app, "PDF outline", ["  " * min(level - 1, 10) + title for level, title, _ in entries],
               lambda index: self.turn(entries[index][2] - 1 - self.page))

    def cancel(self):
        if self.open_request:
            self.backend.send("discard")
            self.open_request = None
            self.app.notify("Pending PDF open cancelled; previous committed document preserved.")
        elif self.render_request:
            self.cancelled_render = True
            if self.image_key:
                self.page, self.zoom, self.pan_x, self.pan_y = self.image_key[:4]
            else:
                self.failed_key = self.desired()
                self.error = "Display update cancelled. Change zoom/page to request another render."
            self.app.notify("Pending display cancelled. The native renderer may finish its call in the background.")

    def present(self):
        if self.image is not None and self.image_key == self.desired() and not self.error:
            self.app.graphics.show(self.app.ui.output, self.image, (id(self), self.document_id, self.image_key), self.bounds)

    def close(self):
        if self.backend:
            self.backend.close()
        self.app.graphics.hide(self.app.ui.output, free=True)
