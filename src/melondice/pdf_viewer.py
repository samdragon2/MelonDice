"""Shared PDF state/controller; rasterization and terminal protocols stay separate."""
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
        self.inflight_document = None
        self.replacement_png = None
        self.replacement_key = None
        # A native raster/encoded replacement is not the terminal's display.
        self.displayed_image = None
        self.displayed_key = None
        self.displayed_bounds = None
        self.revision = 0
        self.inflight_revision = None
        self.failed_key = None
        self.error = ""
        self.failed = False
        self.document_id = 0
        self.password_path = None
        self.recent_paths = app.store.recent()
        self.recents = RadioList(values=[(i, path) for i, path in enumerate(self.recent_paths)] or
                                [(-1, "No recent documents. Press F3 to open a PDF.")], select_on_focus=True)
        self.viewport = Viewport(self)
        recent = HSplit([Label(text="Recent files — Up/Down select, Enter open"), self.recents,
                         Label(text=lambda: "\n" + app.graphics.description + "\nThe rest of Melon Dice remains usable.")])
        # Busy/encoding status must not grow/shrink the raster's cell region.
        self.container = HSplit([Window(content=FormattedTextControl(self.heading), height=2,
                                       wrap_lines=False, always_hide_cursor=True),
                                DynamicContainer(lambda: self.viewport if self.pages else recent),
                                Label(text="< Previous / > Next  (PgUp/PgDn)  G Page  +/- Zoom  Arrows Pan\n"
                                           "F3 Open  F4 Outline  Esc Cancel update  PDF read-only; no text copy/paste")])

    def focus(self):
        return self.viewport if self.pages else self.recents

    def heading(self):
        shown = self.displayed_key if self.display_identity() is not None else None
        displayed = (f"Displayed {shown[0] + 1}/{self.pages} {shown[1]:.0%} Pan {shown[2]},{shown[3]}"
                     if shown else "Displayed: none")
        requested = f"Requested {self.page + 1 if self.pages else 0}/{self.pages} {self.zoom:.0%} Pan {self.pan_x},{self.pan_y}"
        if self.open_request:
            status = "Opening PDF…"
        elif self.error:
            status = " ".join(self.error.splitlines())
        elif self.app.graphics.encoding:
            status = "Encoding Sixel…"
        elif self.desired() is not None and (shown != self.desired() or self.render_request):
            status = "Loading…"
        else:
            status = "Ready" if shown else "Waiting for display"
        # Explicit rows, clipped horizontally: no status/path wrapping can move
        # the image, and even long errors remain outside the reserved viewport.
        path = " ".join(str(self.path or "No document").splitlines())
        return (f"pdfViewer | {displayed} | {path}\n" +
                f"{requested} | {status}")

    def desired(self):
        if not self.pages or not self.app.graphics.supported:
            return None
        _x, _y, columns, rows = self.bounds
        if min(columns, rows) <= 0:
            return None
        width, height = self.app.graphics.viewport_pixels(columns, rows)
        if height < 1:
            return None
        return (self.page, self.zoom, self.pan_x, self.pan_y, width, height)

    def visible(self):
        size = self.app.ui.output.get_size()
        return (self.app.active == "pdf" and not self.app.dialog and size.columns >= 80 and size.rows >= 24
                and self.viewport in self.app.ui.layout.find_all_windows())

    def display_identity(self):
        identity = self.identity(self.displayed_key)
        if (self.display_safe() and self.app.graphics.placed
                and self.app.graphics.presenter.placed_identity == identity):
            return identity
        return None

    def identity(self, key):
        return (id(self), self.document_id, key) if key is not None else None

    def display_safe(self):
        desired = self.desired()
        return (self.displayed_image is not None and desired is not None
                and self.displayed_key[4:] == desired[4:] and self.displayed_bounds == self.bounds)

    def viewport_text(self):
        if not self.app.graphics.supported:
            return ("Original-layout PDF images unavailable in this terminal.\n\n" + self.app.graphics.description +
                    "\n\nUse a compatible Kitty or Sixel terminal; mlterm-fb: --pdf-graphics sixel.\n"
                    "No GUI will be opened and no extracted-text imitation will be shown.\n"
                    "Home, ChatGPT, the text editor, file metadata, and outline remain available.")
        # Keep the text diff over image cells invariant, including initial load,
        # failure and cancellation. A changing placeholder would erase Sixel
        # picture cells even if before_render retained the image. Status lives
        # in the fixed heading; full-screen damage is handled by render hooks.
        return ""

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
        changed = False
        if self.failed or self.backend is None:
            return changed
        try:
            for sequence, kind, value in self.backend.receive():
                changed = True
                if kind == "startup_error":
                    self.failed, self.error = True, value
                    self.app.notify(value)
                    return True
                if sequence == self.open_request:
                    self.open_request = None
                    if kind == "password":
                        self.password_path = self.open_path
                    elif kind == "opened":
                        self.backend.send("commit")
                        self.suspend_updates()
                        self.app.graphics.hide(self.app.ui.output, free=True)
                        self.document_id += 1
                        self.path, self.pages, self.outline = self.open_path, value["pages"], value["outline"]
                        self.page, self.zoom, self.pan_x, self.pan_y = 0, 1.0, 0, 0
                        self.replacement_png, self.replacement_key, self.failed_key, self.error = None, None, None, ""
                        self.displayed_image = self.displayed_key = self.displayed_bounds = None
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
                    if (self.inflight_document != self.document_id or self.inflight != self.desired()
                            or self.inflight_revision != self.revision):
                        continue
                    if kind == "rendered":
                        self.pan_x, self.pan_y = value["pan"]
                        self.full = value["full"]
                        self.replacement_png, self.replacement_key = value["png"], self.desired()
                        self.error, self.failed_key = "", None
                    else:
                        self.error, self.failed_key = str(value), self.inflight
                        self.app.notify("PDF rendering failed: " + self.error)
            if self.password_path and self.app.active == "pdf" and not self.app.dialog:
                path, self.password_path = self.password_path, None
                prompt(self.app, "PDF password", "Enter password (also shown after an incorrect password):",
                       lambda password: self.load(path, password), secret=True)
            desired = self.desired()
            if self.replacement_key is not None and self.replacement_key != desired:
                self.drop_replacement()
            if (self.visible() and not self.open_request and not self.render_request
                    and desired is not None and desired != self.replacement_key and desired != self.failed_key
                    and not (self.display_safe() and desired == self.displayed_key)):
                self.error = ""
                self.inflight = desired
                self.inflight_document = self.document_id
                self.inflight_revision = self.revision
                self.render_request = self.backend.send("render", *desired)
                changed = True
            if self.visible():
                if self.replacement_png is not None and self.replacement_key == desired:
                    self.prepare(self.replacement_png, self.replacement_key)
                elif self.display_safe() and not self.app.graphics.placed:
                    self.prepare(self.displayed_image, self.displayed_key)
        except Exception as error:
            self.failed = True
            self.error = f"PDF renderer unavailable: {error}. Close and reopen pdfViewer."
            self.drop_replacement()
            self.app.notify(self.error)
            changed = True
        return changed

    def prepare(self, png, key):
        identity = self.identity(key)
        revision = self.revision

        def failed(detail):
            if (revision == self.revision and identity == self.identity(key)
                    and key == self.desired()):
                self.error, self.failed_key = detail, self.desired()
                self.replacement_png = self.replacement_key = None
                self.app.notify(detail)

        self.app.graphics.prepare(self.app.tasks, png, identity, self.app.ui.invalidate, failed)

    def drop_replacement(self):
        self.app.graphics.suspend()
        self.replacement_png = self.replacement_key = None

    def suspend_updates(self):
        # Native calls cannot be interrupted individually. Keep the one in-flight
        # sequence until drained, but reject it even if the user returns to its key.
        self.revision += 1
        self.drop_replacement()

    def leave_surface(self):
        self.suspend_updates()
        self.displayed_image = self.displayed_key = self.displayed_bounds = None
        self.app.graphics.suspend(free=True)

    def request_changed(self, previous):
        if previous != (self.page, self.zoom, self.pan_x, self.pan_y):
            self.suspend_updates()
            self.failed_key = None
            if not self.failed:
                self.error = ""

    def turn(self, amount):
        if self.pages and not self.open_request:
            previous = self.page, self.zoom, self.pan_x, self.pan_y
            self.page = max(0, min(self.pages - 1, self.page + amount))
            if self.page != previous[0]:
                self.pan_x = self.pan_y = 0
            self.request_changed(previous)

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
            previous = self.page, self.zoom, self.pan_x, self.pan_y
            self.zoom = max(0.25, min(4.0, self.zoom * factor))
            self.request_changed(previous)

    def pan(self, x, y):
        if self.pages and not self.open_request:
            previous = self.page, self.zoom, self.pan_x, self.pan_y
            self.pan_x = max(0, self.pan_x + x * 32)
            self.pan_y = max(0, self.pan_y + y * 32)
            self.request_changed(previous)

    def show_outline(self):
        entries = [(level, title, page) for level, title, page in self.outline if page > 0]
        choose(self.app, "PDF outline", ["  " * min(level - 1, 10) + title for level, title, _ in entries],
               lambda index: self.turn(entries[index][2] - 1 - self.page))

    def cancel(self):
        if self.open_request:
            self.backend.send("discard")
            self.open_request = None
            self.app.notify("Pending PDF open cancelled; previous committed document preserved.")
        elif self.failed:
            self.app.notify(self.error)
        elif (self.render_request or self.replacement_png is not None or self.app.graphics.encoding
              or self.desired() != self.displayed_key):
            self.suspend_updates()
            self.failed_key = self.desired()
            self.error = "Update cancelled. Change page/zoom/pan to retry."
            self.app.notify(self.error)

    def present(self):
        if self.replacement_png is not None and self.replacement_key == self.desired():
            png, key = self.replacement_png, self.replacement_key
        elif self.display_safe():
            png, key = self.displayed_image, self.displayed_key
        else:
            return
        identity = self.identity(key)
        if self.app.graphics.ready(identity):
            previous = self.display_identity()
            if self.app.graphics.show(self.app.ui.output, png, identity, self.bounds):
                self.displayed_image, self.displayed_key, self.displayed_bounds = png, key, self.bounds
                if self.replacement_key == key:
                    self.replacement_png = self.replacement_key = None
                if previous != identity:
                    self.app.ui.invalidate()  # Metadata now describes a sent frame.

    def close(self):
        self.leave_surface()
        if self.backend:
            self.backend.close()
        self.app.graphics.hide(self.app.ui.output, free=True)
