"""Single in-memory prompt_toolkit clipboard; never accesses OSC52 or OS clipboards."""
from prompt_toolkit.clipboard import Clipboard, ClipboardData


class SharedClipboard(Clipboard):
    def __init__(self):
        self.data = ClipboardData("")
        self.allow_write = lambda: True

    def set_data(self, data):
        if data.text and self.allow_write():
            self.data = data

    def get_data(self):
        return self.data

    @property
    def label(self):
        return "Clipboard: Text" if self.data.text else "Clipboard: Empty"

    def clear(self):
        self.data = ClipboardData("")


def insert_text(buffer, text):
    buffer.save_to_undo_stack()
    if buffer.selection_state:
        document, _selection = buffer.document.cut_selection()
        buffer.document = document
    buffer.insert_text(text)
