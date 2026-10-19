"""Full-screen terminal application: navigation, input, retained sessions, lifecycle."""
from __future__ import annotations

import asyncio
from concurrent.futures import CancelledError
import signal
import time

import httpx
from prompt_toolkit import Application as TerminalApplication
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings, DynamicKeyBindings
from prompt_toolkit.layout import DynamicContainer, Float, FloatContainer, HSplit, Layout, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.styles import Style, DynamicStyle
from prompt_toolkit.widgets import Label

from . import __version__
from .auth import Accounts
from .chat import Chat
from .clipboard import SharedClipboard, insert_text
from .conversations import History
from .dialogs import confirm, message
from .editor import Editor
from .pdf_viewer import PDFViewer
from .settings import settings
from .tasks import Tasks

NAMES = {"chat": "ChatGPT", "pdf": "pdfViewer", "editor": "Text editor"}
ORDER = tuple(NAMES)


class Application:
    def __init__(self, store, graphics, terminal_input):
        self.store, self.graphics = store, graphics
        self.accounts, self.history = Accounts(store), History(store)
        self.active, self.last_active, self.selected = "home", None, None
        self.sessions = {}
        self.dialog = None
        self.dialog_focus = None
        self.account_job = None
        self.pending_ui = []
        self.notification = "Ready"
        self.closed = False
        self.exiting = False
        self.signals = {}
        self.graphics_context = None
        self.graphics_revision = graphics.revision
        self.clipboard = SharedClipboard()
        self.home_window = Window(content=FormattedTextControl(self.home_text, focusable=True),
                                  wrap_lines=True, always_hide_cursor=True)
        self.small_window = Window(content=FormattedTextControl("Resize terminal to at least 80 columns × 24 rows. F10/^Q still closes.", focusable=True), wrap_lines=True)
        body = HSplit([Label(text=self.navigation), DynamicContainer(self.current_container),
                       Window(content=FormattedTextControl(lambda: self.notification), height=2, wrap_lines=True, style="class:notification"),
                       Label(text=self.footer, style="class:footer")])
        self.root = FloatContainer(content=body, floats=[])
        self.bindings = self.make_bindings()
        self.style = self.make_style()
        self.ui = TerminalApplication(layout=Layout(self.root, focused_element=self.home_window),
            key_bindings=DynamicKeyBindings(lambda: self.bindings), full_screen=True,
            mouse_support=Condition(lambda: self.store.config["mouse_support"]), clipboard=self.clipboard,
            style=DynamicStyle(lambda: self.style), input=terminal_input,
            before_render=self.before_render, after_render=self.after_render)
        self.clipboard.allow_write = lambda: not self.secret()
        self.ui.ttimeoutlen = self.store.config["escape_timeout_ms"] / 1000
        self.ui.timeoutlen = self.ui.ttimeoutlen
        self.tasks = Tasks()

    @property
    def account_busy(self):
        return self.account_job is not None and not self.account_job.done()

    def current_container(self):
        if hasattr(self, "ui"):
            size = self.ui.output.get_size()
            if size.columns < 80 or size.rows < 24:
                return self.small_window
        return self.home_window if self.active == "home" else self.sessions[self.active].container

    def home_text(self):
        return ("=" * 50 + "\nMelon Dice\nmade by SamRyong\n" + "=" * 50 +
                "\n\n1. ChatGPT\n2. pdfViewer\n3. Text editor\n\nEnter: [" +
                (NAMES[self.selected] if self.selected else "No selection") + "]\n\n" +
                "Press 1, 2, or 3, then Enter.\nSessions resume when you return.")

    def navigation(self):
        if self.active == "home":
            return "Melon Dice"
        return "Melon Dice | " + "  ".join(("[" if self.active == key else "") +
                      f"{index}.{NAMES[key]}" + ("]" if self.active == key else "") for index, key in enumerate(ORDER, 1))

    def footer(self):
        return "F1 Home  F2 Info  ^O Options  Alt+Tab/F6 Switch  ^Q/F10 " + ("Exit" if self.active == "home" else "Close") + "\n" + self.clipboard.label

    def make_style(self):
        dark = self.store.config["theme"] == "dark"
        return Style.from_dict({
            "": "bg:#17231d #e4eee7" if dark else "bg:#eff5eb #16251a",
            "footer": "reverse", "notification": "#87af87" if dark else "#005f00",
            "dialog": "bg:#263c2e #ffffff" if dark else "bg:#ddebd5 #16251a",
            "dialog frame.label": "bold", "button.focused": "bg:#5f875f #ffffff bold",
            "selected": "bg:#4e7651 #ffffff", "radio-selected": "reverse",
            "text-area": "", "line-number": "#808080", "scrollbar.button": "bg:#87af87",
        })

    def apply_config(self, config):
        self.store.validate(config)
        previous = self.store.config
        self.store.config = config
        try:
            bindings = self.make_bindings()  # Also asks the framework to validate key names.
            self.store.save_config()
        except Exception:
            self.store.config = previous
            raise
        self.bindings, self.style = bindings, self.make_style()
        self.ui.ttimeoutlen = self.ui.timeoutlen = config["escape_timeout_ms"] / 1000
        self.notify("Option saved. PDF graphics mode and cell geometry changes apply after restart.")

    def make_bindings(self):
        bindings = KeyBindings()
        def bind(keys, callback, condition=lambda: True, eager=True):
            @bindings.add(*keys.split(), filter=Condition(condition), eager=eager, is_global=True,
                          save_before=lambda _e: False)
            def invoke(event):
                try:
                    callback(event)
                except Exception as error:
                    self.notify(f"Operation failed: {type(error).__name__}: {error}")
        actions = {"cycle": self.cycle, "home": self.home, "information": self.information,
                   "settings": self.options, "close": self.close_current,
                   "save": lambda: self.sessions["editor"].save() if self.active == "editor" and not self.dialog else None}
        for action, sequences in self.store.config["shortcuts"].items():
            for sequence in sequences:
                bind(sequence, lambda _e, action=action: actions[action]())
        bind("c-c", lambda _e: self.copy())
        bind("c-v", lambda _e: self.paste())
        bind("c-x", lambda _e: self.cut())
        bind("c-d", lambda _e: self.notify("Use Ctrl+Q/F10 to close with unsaved-work handling."))
        bind("c-space", lambda e: e.current_buffer.exit_selection() if e.current_buffer.selection_state else e.current_buffer.start_selection(),
             lambda: isinstance(self.ui.layout.current_control, BufferControl))
        bind("escape a", lambda e: e.current_buffer.exit_selection() if e.current_buffer.selection_state else e.current_buffer.start_selection(),
             lambda: isinstance(self.ui.layout.current_control, BufferControl))
        bind("escape", lambda _e: self.escape(), eager=False)
        plain = lambda: self.dialog is None
        home = lambda: plain() and self.active == "home"
        chat = lambda: plain() and self.active == "chat"
        editor = lambda: plain() and self.active == "editor"
        pdf = lambda: plain() and self.active == "pdf"
        for number in ("1", "2", "3"):
            bind(number, lambda _e, n=number: setattr(self, "selected", ORDER[int(n) - 1]), home)
        bind("enter", lambda _e: self.navigate(self.selected) if self.selected else None, home)
        bind("tab", lambda _e: self.ui.layout.focus(self.sessions["chat"].output if self.ui.layout.has_focus(self.sessions["chat"].input) else self.sessions["chat"].input), chat)
        bind("tab", lambda e: insert_text(e.current_buffer, "    "), editor)
        bind("enter", lambda _e: self.sessions["chat"].send(), lambda: chat() and self.ui.layout.has_focus(self.sessions["chat"].input))
        bind("f12", lambda _e: self.sessions["chat"].send(), chat)
        bind("c-j", lambda e: insert_text(e.current_buffer, "\n"), lambda: chat() and self.ui.layout.has_focus(self.sessions["chat"].input))
        bind("c-n", lambda _e: self.sessions[self.active].new(), lambda: chat() or editor())
        bind("f3", lambda _e: self.sessions["chat"].history() if self.active == "chat" else self.sessions[self.active].open(), lambda: plain() and self.active in ORDER)
        bind("f4", lambda _e: self.sessions["chat"].attach() if self.active == "chat" else self.sessions["pdf"].show_outline(), lambda: chat() or pdf())
        bind("f5", lambda _e: self.sessions["chat"].remove_attachment(), chat)
        bind("f7", lambda _e: self.sessions["editor"].save(force_as=True), editor)
        bind("escape s", lambda _e: self.sessions["editor"].save(force_as=True), editor)
        bind("f9", lambda _e: self.sessions["chat"].retry() if self.active == "chat" else self.sessions["editor"].guard(self.sessions["editor"].offer_recovery), lambda: chat() or editor())
        bind("escape u", lambda _e: self.manage_usage(), chat)
        bind("c-f", lambda _e: self.sessions["editor"].find(), editor)
        bind("c-z", lambda e: e.current_buffer.undo() if not e.current_buffer.read_only() else None)
        bind("c-y", lambda e: e.current_buffer.redo() if not e.current_buffer.read_only() else None, editor)
        bind("pageup", lambda _e: self.sessions["chat"].scroll(-1) if self.active == "chat" else self.sessions["pdf"].turn(-1), lambda: chat() or pdf())
        bind("pagedown", lambda _e: self.sessions["chat"].scroll(1) if self.active == "chat" else self.sessions["pdf"].turn(1), lambda: chat() or pdf())
        bind("enter", lambda _e: self.sessions["pdf"].open_selected_recent(), lambda: pdf() and not self.sessions["pdf"].pages)
        for key in ("g", "G"):
            bind(key, lambda _e: self.sessions["pdf"].goto(), pdf)
        for key in ("+", "="):
            bind(key, lambda _e: self.sessions["pdf"].magnify(1.25), pdf)
        bind("-", lambda _e: self.sessions["pdf"].magnify(0.8), pdf)
        for key, x, y in [("left", -1, 0), ("right", 1, 0), ("up", 0, -1), ("down", 0, 1)]:
            bind(key, lambda _e, x=x, y=y: self.sessions["pdf"].pan(x, y), lambda: pdf() and bool(self.sessions["pdf"].pages))
        return bindings

    def show_dialog(self, dialog):
        if self.dialog:
            if self.dialog.protected:
                self.pending_ui.append(lambda: self.show_dialog(dialog))
                return
            self.dialog.dismiss()
        self.dialog_focus = self.ui.layout.current_control
        self.dialog = dialog
        self.root.floats[:] = [Float(content=dialog.container)]
        if dialog.focus:
            self.ui.layout.focus(dialog.focus)
        self.ui.invalidate()

    def close_dialog(self, dialog):
        if self.dialog is not dialog:
            return
        self.root.floats.clear()
        self.dialog = None
        try:
            if self.dialog_focus:
                self.ui.layout.focus(self.dialog_focus)
            else:
                self.focus_active()
        except ValueError:
            self.focus_active()
        self.dialog_focus = None
        self.ui.invalidate()

    def defer(self, callback):
        if self.dialog:
            self.pending_ui.append(callback)
        else:
            callback()

    def allow_navigation(self):
        if self.exiting:
            return False
        if self.dialog:
            if self.dialog.protected:
                self.notify("Resolve Save / Discard / Cancel before navigating.")
                return False
            self.dialog.dismiss()
        return True

    def focus_active(self):
        target = self.home_window if self.active == "home" else self.sessions[self.active].focus()
        size = self.ui.output.get_size()
        self.ui.layout.focus(self.small_window if size.columns < 80 or size.rows < 24 else target)

    def navigate(self, key):
        if key is None or not self.allow_navigation():
            return
        if key not in self.sessions:
            try:
                self.sessions[key] = {"chat": Chat, "pdf": PDFViewer, "editor": Editor}[key](self)
            except Exception as error:
                self.error("Cannot start " + NAMES[key], error)
                return
        if self.active == "chat" and key != "chat":
            self.sessions["chat"].follow = False
        self.active, self.last_active = key, key
        self.focus_active()
        if key == "editor" and not getattr(self.sessions[key], "recovery_offered", False):
            self.sessions[key].recovery_offered = True
            self.sessions[key].offer_recovery()

    def cycle(self):
        target = (self.last_active or "chat") if self.active == "home" else ORDER[(ORDER.index(self.active) + 1) % 3]
        self.navigate(target)

    def home(self):
        if self.allow_navigation():
            if self.active == "chat":
                self.sessions["chat"].follow = False
            self.active = "home"
            self.focus_active()

    def close_current(self):
        if not self.allow_navigation():
            return
        if self.active == "home":
            self.exit()
            return
        key, session = self.active, self.sessions[self.active]
        def close():
            session.close()
            self.sessions.pop(key)
            self.active = "home"
            self.focus_active()
        if key in {"chat", "editor"}:
            session.guard(close)
        else:
            close()

    def exit(self):
        if not self.allow_navigation():
            return
        if self.account_busy:
            def cancel_then_exit():
                self.account_job.cancel()
                self.exit()
            confirm(self, "Account operation in progress", "Exit cancels the pending account operation. If sign-out revocation is unconfirmed, disconnect Melon Dice in ChatGPT Settings.",
                    [("Cancel operation and exit", cancel_then_exit)])
            return
        keys = [key for key in ("editor", "chat") if key in self.sessions]
        def next_guard(index=0):
            if index == len(keys):
                self.exiting = True
                self.ui.exit()
            else:
                self.sessions[keys[index]].guard(lambda: next_guard(index + 1))
        next_guard()

    def secret(self):
        return bool(self.dialog and self.ui.current_buffer in self.dialog.secret_buffers)

    def copy(self):
        buffer = self.ui.current_buffer
        if isinstance(self.ui.layout.current_control, BufferControl) and not self.secret() and buffer.selection_state:
            _document, data = buffer.document.cut_selection()
            if data.text:
                self.clipboard.set_data(data)
                self.notify("Copied selected text.")
                return
        self.notify("No copyable text selected; clipboard preserved.")

    def paste(self):
        buffer = self.ui.current_buffer
        if not isinstance(self.ui.layout.current_control, BufferControl) or buffer.read_only() or not self.clipboard.get_data().text or (self.active == "pdf" and not self.dialog):
            self.notify("Paste unavailable here or clipboard empty. PDFs are read-only.")
        else:
            insert_text(buffer, self.clipboard.get_data().text)

    def cut(self):
        buffer = self.ui.current_buffer
        if not isinstance(self.ui.layout.current_control, BufferControl) or self.secret() or buffer.read_only() or not buffer.selection_state:
            self.notify("No editable selection to cut; clipboard preserved.")
            return
        document, data = buffer.document.cut_selection()
        if data.text:
            buffer.save_to_undo_stack()
            self.clipboard.set_data(data)
            buffer.document = document

    def escape(self):
        if self.dialog:
            self.dialog.dismiss()
        elif self.active == "chat" and (self.sessions["chat"].future or self.sessions["chat"].snapshot_ids - self.sessions["chat"].cancelled_snapshots):
            self.sessions["chat"].stop()
        elif self.active == "pdf":
            self.sessions["pdf"].cancel()
        else:
            self.ui.current_buffer.exit_selection()

    def options(self):
        if self.allow_navigation():
            settings(self)

    def information(self):
        if self.allow_navigation():
            message(self, "Melon Dice Information", f"Melon Dice {__version__}\nAuthor: SamRyong\n\n"
                    "Python terminal UI powered by prompt_toolkit (BSD-3-Clause), HTTPX (BSD-3-Clause), "
                    "PyJWT (MIT), cryptography (Apache-2.0/BSD), Pillow (HPND), PyMuPDF/MuPDF (AGPL/commercial). "
                    "Melon Dice: AGPL-3.0-or-later. See THIRD_PARTY_NOTICES.md.\n\n"
                    "Shell/chat/editor/dialogs work in a POSIX UTF-8 VT100-compatible terminal, including ordinary SSH. "
                    "PDF images require Kitty or Sixel presentation and valid pixel cell geometry. Use --pdf-graphics sixel inside mlterm-fb. Bare Linux console PDF images "
                    "and tmux/screen graphics are unsupported; text apps remain usable.\n\n"
                    "F6 replaces intercepted Alt+Tab; F7 Save As, F8 Save, F10 Close. Ctrl+I is Tab, so F2 is Information. "
                    "Ctrl+Space provides selection when Shift+arrows are not transmitted. Mouse dragging depends on "
                    "terminal mouse reporting. Fonts/size/Korean input are configured in the terminal client.")

    def manage_usage(self):
        from .auth import USAGE_URL
        message(self, "Manage usage", "Open in your browser:\n" + USAGE_URL)

    def stop_generation(self):
        if "chat" in self.sessions:
            self.sessions["chat"].stop()

    def account_operation(self, coroutine, success=None, reset_model=True):
        if self.account_busy:
            coroutine.close()
            self.notify("An account operation is already running.")
            return
        self.stop_generation()
        def done(future):
            try:
                result = future.result()
                if reset_model:
                    self.store.config["model"] = ""
                    self.store.save_config()
                self.notify(success or result or "Account operation completed.")
            except CancelledError:
                self.notify("Account operation cancelled; unconfirmed sign-out revocation must be managed in ChatGPT Settings.")
            except Exception as error:
                self.error("Account operation failed", error)
        self.account_job = self.tasks.submit(coroutine, done)

    def refresh_models(self, show_picker=False):
        if self.account_busy:
            self.notify("An account operation is running.")
            return
        def done(future):
            try:
                values = future.result()
                if not any(m["slug"] == self.store.config["model"] for m in values):
                    self.store.config["model"] = values[0]["slug"] if values else ""
                    self.store.save_config()
                self.notify(f"Loaded {len(values)} account models.")
                if show_picker and values:
                    from .settings import models
                    self.defer(lambda: models(self))
            except CancelledError:
                pass
            except Exception as error:
                self.error("Cannot load models", error)
        self.account_job = self.tasks.submit(self.accounts.models(), done)

    def io(self, function, done, on_error=None):
        async def operation():
            return await asyncio.to_thread(function)
        def complete(future):
            if self.closed:
                return
            try:
                value = future.result()
            except CancelledError:
                return
            except Exception as error:
                (on_error or (lambda error: self.error("File operation failed", error)))(error)
            else:
                done(value)
        return self.tasks.submit(operation(), complete)

    def notify(self, text):
        self.notification = str(text)
        self.ui.invalidate()

    def error(self, title, error):
        detail = "Network request failed. Check connectivity and retry; local work is retained." if isinstance(error, httpx.HTTPError) else str(error)
        if self.dialog:
            self.notify(title + ": " + detail)
        else:
            message(self, title, detail)

    def before_render(self, _app):
        try:
            size = self.ui.output.get_size()
            viewer = self.sessions.get("pdf")
            visible = (not self.ui.is_done and not self.exiting and not self.dialog and self.active == "pdf"
                       and size.columns >= 80 and size.rows >= 24 and viewer is not None)
            identity = viewer.display_identity() if visible else None
            context = (size.columns, size.rows, self.style.invalidation_hash(), self.graphics.cell)
            if identity is None:
                self.graphics.suspend()
            presenter = self.graphics.presenter
            if self.graphics.protocol == "kitty":
                self.graphics.hide(self.ui.output)
            elif self.graphics.placed and (identity != presenter.placed_identity
                    or context != self.graphics_context or not self.graphics.supported
                    or self.ui.renderer.last_rendered_screen is None):
                self.graphics.hide(self.ui.output)
            self.graphics_context = context
            if self.graphics.text_dirty:
                # Sixel erasure changes real text cells behind the framework's
                # diff cache. Repaint once for damage, never once per pump tick.
                self.ui.renderer.erase(leave_alternate_screen=False)
                self.graphics.text_dirty = False
        except OSError as error:
            self.exiting = True
            if self.ui.future is not None and not self.ui.future.done():
                self.ui.exit(exception=error)

    def after_render(self, _app):
        try:
            if self.ui.is_done or self.exiting:
                return
            if not self.dialog and self.active == "pdf" and self.sessions["pdf"].viewport in self.ui.layout.find_all_windows():
                self.graphics.begin(self.ui.output)
                presenter = self.graphics.presenter
                if (self.graphics.protocol == "sixel" and self.graphics.placed
                        and presenter.rectangle != self.sessions["pdf"].bounds):
                    # Layout changes (e.g. a wrapped heading) are known only
                    # after layout. Repair text before presenting at new bounds.
                    self.graphics.hide(self.ui.output)
                    self.ui.renderer.erase(leave_alternate_screen=False)
                    self.graphics.text_dirty = False
                    self.ui.invalidate()
                    return
                self.sessions["pdf"].present()
            elif not self.dialog and self.active == "pdf":
                # Also probe on the recent-documents screen, which has no image window yet.
                self.graphics.begin(self.ui.output)
        except OSError as error:
            self.exiting = True
            if self.ui.future is not None and not self.ui.future.done():
                self.ui.exit(exception=error)
        except Exception as error:
            self.graphics.disable(f"Terminal image presentation failed: {type(error).__name__}: {error}")
            self.notify(self.graphics.reason)

    async def pump(self):
        while not self.exiting:
            try:
                changed = bool(self.tasks.drain(lambda: self.exiting))
                if self.exiting:
                    return
                if self.pending_ui and not self.dialog:
                    self.pending_ui.pop(0)()
                now = time.monotonic()
                if "chat" in self.sessions:
                    self.sessions["chat"].tick(now)
                if "editor" in self.sessions:
                    self.sessions["editor"].tick(now)
                if "pdf" in self.sessions:
                    self.graphics.tick()
                    changed |= self.sessions["pdf"].poll() or self.graphics_revision != self.graphics.revision
                    self.graphics_revision = self.graphics.revision
                # Restore focus after a resize that temporarily hid the active control.
                if not self.dialog and self.ui.layout.current_window not in self.ui.layout.find_all_windows():
                    self.focus_active()
                if changed:
                    self.ui.invalidate()
            except Exception as error:
                self.notify(f"Background operation failed: {type(error).__name__}: {error}")
            await asyncio.sleep(0.05)

    def run(self):
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            self.signals[sig] = signal.getsignal(sig)
        signal.signal(signal.SIGINT, lambda _s, _f: self.tasks.post(self.notify, "Ctrl+C copies text. Use Ctrl+Q/F10 to close."))
        signal.signal(signal.SIGTERM, lambda _s, _f: self.tasks.post(self.exit))
        signal.signal(signal.SIGHUP, lambda _s, _f: self.tasks.post(lambda: self.ui.exit(exception=EOFError())))
        # No nested event loops or GUI windows. prompt_toolkit owns the current TTY.
        return self.ui.run(pre_run=lambda: self.ui.create_background_task(self.pump()), set_exception_handler=False, handle_sigint=False)

    def cleanup(self, emergency=False):
        if self.closed:
            return
        if emergency:
            if "editor" in self.sessions:
                try:
                    self.sessions["editor"].emergency_save()
                except Exception:
                    pass
            if "chat" in self.sessions:
                self.sessions["chat"].stop()
                if self.store.config["history_persistence"]:
                    self.sessions["chat"].save_history(silent=True)
        self.closed = True
        self.graphics.suspend(free=True)
        try:
            for key, session in self.sessions.items():
                try:
                    if key == "editor" and emergency:
                        session.alive = False  # Keep the recovery journal.
                    else:
                        session.close()
                except Exception:
                    pass
        finally:
            try:
                try:
                    self.graphics.hide(self.ui.output, free=True)
                finally:
                    self.tasks.close()
            finally:
                self.clipboard.clear()
                try:
                    (self.store.root / "oauth-authorization-url.txt").unlink(missing_ok=True)
                except OSError:
                    pass
                for sig, previous in self.signals.items():
                    signal.signal(sig, previous)
