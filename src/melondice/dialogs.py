"""Terminal-native non-blocking dialogs inside the current full-screen application."""
from __future__ import annotations

from pathlib import Path

from prompt_toolkit.filters import Condition, has_focus
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import DynamicContainer, HSplit
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.widgets import Button, Dialog as ToolkitDialog, Label, RadioList, TextArea


def selected_value(radio):
    # In the pinned widget version, page/typeahead moves the highlight before
    # current_value is committed. Activate the highlighted row, never an old row.
    return radio.values[radio._selected_index][0]


class Modal:
    def __init__(self, app, title, body, actions, *, focus=None, protected=False, cancel=None):
        self.app, self.protected, self.cancel = app, protected, cancel
        self.secret_buffers = set()
        self.buttons = [Button(text=label, handler=action) for label, action in actions]
        self.container = ToolkitDialog(title=title, body=body, buttons=self.buttons,
                                       width=Dimension(min=30, preferred=78), modal=True)
        self.focus = focus or (self.buttons[0] if self.buttons else None)
        app.show_dialog(self)

    def close(self):
        self.app.close_dialog(self)

    def dismiss(self):
        self.close()
        if self.cancel:
            self.cancel()


def message(app, title, text, callback=None):
    content = TextArea(text=str(text), read_only=True, scrollbar=True, wrap_lines=True,
                       height=Dimension(min=3, preferred=12, max=20), focus_on_click=True)
    def done():
        dialog.close()
        if callback:
            callback()
    keys = KeyBindings()
    @keys.add("enter", filter=has_focus(content), eager=True)
    def accept(_event):
        done()
    dialog = Modal(app, title, HSplit([content], key_bindings=keys), [("Got it", done)], focus=content)
    return dialog


def confirm(app, title, text, actions, *, cancel=None):
    dialog = None
    def invoke(callback):
        dialog.close()
        callback()
    buttons = [(label, lambda callback=callback: invoke(callback)) for label, callback in actions]
    buttons.append(("Cancel", lambda: dialog.dismiss()))
    dialog = Modal(app, title, Label(text=text), buttons, protected=True, cancel=cancel)
    return dialog


def prompt(app, title, label, callback, initial="", *, secret=False, protected=False, cancel=None):
    entry = TextArea(text=initial, multiline=False, password=secret, focus_on_click=True)
    note = Label(text="")
    def accept(_buffer=None):
        value = entry.text
        dialog.close()
        callback(value)
        return True
    entry.buffer.accept_handler = accept
    dialog = Modal(app, title, HSplit([Label(text=label), entry, note], padding=1),
                   [("OK", accept), ("Cancel", lambda: dialog.dismiss())],
                   focus=entry, protected=protected, cancel=cancel)
    if secret:
        dialog.secret_buffers.add(entry.buffer)
    return dialog


def choose(app, title, labels, callback, actions=(), extra=()):
    values = [(index, label) for index, label in enumerate(labels)]
    radio = RadioList(values=values or [(-1, "No entries")], select_on_focus=True)
    keys = KeyBindings()
    dialog = None
    def selected(action=callback):
        index = selected_value(radio)
        if index is not None and index >= 0:
            dialog.close()
            action(index)
    @keys.add("enter", filter=has_focus(radio), eager=True)
    def accept(_event):
        selected()
    body = HSplit([radio], key_bindings=keys, height=Dimension(min=3, preferred=12, max=18))
    buttons = [("Open", selected)] + [(label, lambda action=action: selected(action)) for label, action in actions]
    buttons += [(label, lambda action=action: (dialog.close(), action())) for label, action in extra]
    buttons += [("Cancel", lambda: dialog.dismiss())]
    dialog = Modal(app, title, body, buttons, focus=radio)
    return dialog


class FilePicker:
    def __init__(self, app, title, callback, *, save=False, initial=None, protected=False, cancel=None):
        self.app, self.callback, self.save = app, callback, save
        self.revision = 0
        self.items = []
        self.directory = Path(initial or app.store.config["document_directory"]).expanduser()
        value = str(self.directory)
        if self.directory.is_dir():
            value += "/"
        self.path = TextArea(text=value, multiline=False, focus_on_click=True)
        self.note = Label(text="Reading directory…")
        self.radio = RadioList(values=[(-1, "Reading…")], select_on_focus=True)
        self.keys = KeyBindings()
        @self.keys.add("enter", filter=Condition(lambda: app.ui.layout.has_focus(self.radio)), eager=True)
        def activate(_event):
            self.activate()
        self.path.buffer.accept_handler = lambda _b: self.accept()
        body = HSplit([Label(text="Path (type a file path, or select a directory/file below)"),
                       self.path, DynamicContainer(lambda: self.radio), self.note], padding=1,
                      key_bindings=self.keys, height=Dimension(min=8, preferred=18, max=24))
        self.modal = Modal(app, title, body,
                           [("Save" if save else "Open", self.accept), ("Up", self.up),
                            ("Cancel", lambda: self.modal.dismiss())],
                           focus=self.path, protected=protected, cancel=cancel)
        self.browse(self.directory if self.directory.is_dir() else self.directory.parent, preserve=True)

    def browse(self, directory, preserve=False):
        self.directory = directory
        self.revision += 1
        revision = self.revision
        if not preserve:
            self.path.text = str(directory) + "/"
        def read():
            return sorted(((p, p.is_dir()) for p in directory.iterdir()),
                          key=lambda item: (not item[1], item[0].name.casefold()))[:2000]
        def done(items):
            if self.app.dialog is not self.modal or revision != self.revision:
                return
            focus_list = self.app.ui.layout.has_focus(self.radio)
            self.items = items
            self.radio = RadioList(values=[(i, p.name + ("/" if directory else ""))
                                          for i, (p, directory) in enumerate(items)] or [(-1, "Empty directory")],
                                   select_on_focus=True)
            self.note.text = "Up/Down: select; Enter: open; Tab: move between controls. Up to 2000 entries."
            if focus_list:
                self.app.ui.layout.focus(self.radio)
        self.app.io(read, done, on_error=lambda error: setattr(self.note, "text", f"Directory error: {error}"))

    def up(self):
        self.browse(self.directory.parent)

    def activate(self):
        index = selected_value(self.radio)
        if index is None or index < 0:
            return
        path, directory = self.items[index]
        if directory:
            self.browse(path)
        else:
            self.path.text = str(path)
            self.accept()

    def accept(self):
        try:
            path = Path(self.path.text).expanduser().absolute()
            if path.is_dir():
                self.browse(path)
                return True
            if not self.save and not path.is_file():
                raise OSError("Select an existing regular file.")
            if self.save and not path.parent.is_dir():
                raise OSError("Parent directory does not exist.")
            if self.save and path.is_symlink():
                raise OSError("Save to the actual file path, not a symbolic link.")
            self.modal.close()
            if self.save and path.exists():
                confirm(self.app, "Confirm overwrite", f"Replace existing file {path}?",
                        [("Overwrite", lambda: self.callback(path))])
            else:
                self.callback(path)
        except OSError as error:
            self.note.text = str(error)
        return True
