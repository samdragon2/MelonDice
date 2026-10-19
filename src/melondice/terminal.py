"""POSIX terminal restoration, capability detection and coordinated presentation, independent of PDF rendering.

Graphics support is actively queried while prompt_toolkit owns raw input. The input
reader removes protocol replies before they can become composer/editor keystrokes.
"""
from __future__ import annotations

import base64
import binascii
import fcntl
import os
import re
import secrets
import shutil
import struct
import sys
import termios
import time
import zlib

from prompt_toolkit.input.vt100 import Vt100Input

from .graphics_presenters import KittyPresenter, SixelPresenter
from .storage import parse_cell_pixels

ESC = "\x1b"


class TerminalGuard:
    def __enter__(self):
        self.fd = sys.stdin.fileno()
        self.attributes = termios.tcgetattr(self.fd)
        self.flags = fcntl.fcntl(self.fd, fcntl.F_GETFL)
        return self

    def __exit__(self, *_args):
        try:
            termios.tcsetattr(self.fd, termios.TCSANOW, self.attributes)
        finally:
            fcntl.fcntl(self.fd, fcntl.F_SETFL, self.flags)


class Graphics:
    """Small shared controller over Kitty/Sixel presenters, with bounded probing."""
    def __init__(self, mode="auto", cell_pixels=""):
        self.probe_id = secrets.randbelow(1_000_000_000) + 1
        self.image_id = self.probe_id + 1
        self.mode = mode
        self.override = parse_cell_pixels(cell_pixels)
        self.started = False
        self.deadline = 0.0
        self.geometry_deadline = 0.0
        self.geometry_expired = False
        self.settled = False
        self.acknowledged = False
        self.sixel_advertised = False
        self.kitty_error = ""
        self.cell = self.override
        self.cell_source = 3 if self.override else 0
        self.converter = shutil.which("img2sixel")
        self.presenter = None
        self.reason = "Checking terminal graphics capability…"
        self.revision = 0
        self.grid = None
        self.text_dirty = False
        if mode == "off":
            self.reason = "Terminal PDF images disabled. Select auto, kitty or sixel in Options and restart."
        elif os.environ.get("TMUX") or os.environ.get("STY"):
            self.disable("PDF images inside tmux/screen are unsupported. Run in the terminal directly; text apps remain usable.")
        elif mode == "sixel" and not self.converter:
            self.disable("Sixel requires img2sixel (Debian package libsixel-bin) on PATH. Install it or correct PATH, then restart.")

    @property
    def placed(self):
        return bool(self.presenter and self.presenter.placed)

    @property
    def protocol(self):
        return self.presenter.name if self.presenter else None

    @property
    def supported(self):
        return self.mode != "off" and self.presenter is not None and self.cell is not None

    @property
    def encoding(self):
        return self.protocol == "sixel" and self.presenter.future is not None

    def viewport_pixels(self, columns, rows):
        width, height = columns * self.cell[0], rows * self.cell[1]
        if self.protocol == "sixel":
            # Contain the final six-pixel band inside the reserved text region.
            height -= height % 6
        return width, height

    @property
    def description(self):
        if self.mode == "off":
            return self.reason
        if self.supported:
            prefix = "Kitty PNG graphics confirmed" if self.protocol == "kitty" else "Sixel graphics selected (img2sixel, 256 colors)"
            return f"{prefix}; cell {self.cell[0]}×{self.cell[1]} pixels."
        if self.settled and self.presenter is None:
            return self.reason
        if self.started and self.cell is None and time.monotonic() >= self.geometry_deadline:
            return "Terminal pixel geometry unavailable. Supply measured --pdf-cell-pixels WIDTHxHEIGHT (or pdf_cell_pixels in config), then restart. Font size alone is not cell geometry."
        return self.reason

    def disable(self, reason):
        self.mode, self.reason = "off", reason
        self.suspend()
        self.revision += 1

    def _set_cell(self, width, height, source):
        if 1 <= width <= 256 and 1 <= height <= 512 and source >= self.cell_source:
            if self.cell != (width, height):
                self.cell = width, height
                self.revision += 1
            self.cell_source = source

    def _area_geometry(self, width, height):
        if self.grid:
            columns, rows = self.grid
            # Whole text area only, never physical monitor/window dimensions.
            # Reject non-integral geometry instead of accumulating placement drift.
            if columns and rows and width % columns == 0 and height % rows == 0:
                self._set_cell(width // columns, height // rows, 1)

    def begin(self, output):
        if self.mode == "off":
            return
        size = output.get_size()
        grid = size.columns, size.rows
        if self.started and grid == self.grid:
            return
        first = not self.started
        self.grid, self.started = grid, True
        self.cell, self.cell_source = self.override, 3 if self.override else 0
        self.geometry_deadline = time.monotonic() + 1.5
        self.geometry_expired = False
        self.revision += 1
        # Queries only on PDF entry and grid resize, never on the 50ms pump.
        if not self.override:
            output.write_raw(ESC + "[16t" + ESC + "[14t")
            try:
                rows, cols, width, height = struct.unpack("HHHH", fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, b"\0" * 8))
                if (cols, rows) == grid and width and height:
                    self._area_geometry(width, height)
            except (OSError, ValueError):
                pass
        if first:
            self.deadline = time.monotonic() + 1.5
            if self.mode == "sixel":
                self.presenter = SixelPresenter(self.converter)
                self.settled = True  # Explicit choice trusts the user's known terminal.
            else:
                # Query the exact PNG transmission format, without displaying it.
                png = b"\x89PNG\r\n\x1a\n"
                for kind, payload in [(b"IHDR", struct.pack("!IIBBBBB", 1, 1, 8, 2, 0, 0, 0)),
                                      (b"IDAT", zlib.compress(b"\x00\xff\xff\xff")), (b"IEND", b"")]:
                    png += struct.pack("!I", len(payload)) + kind + payload + struct.pack("!I", binascii.crc32(kind + payload))
                data = base64.b64encode(png).decode("ascii")
                output.write_raw(f"{ESC}_Ga=q,i={self.probe_id},t=d,f=100;{data}{ESC}\\")
                if self.mode == "auto":
                    output.write_raw(ESC + "[c")  # Primary DA: feature 4 advertises Sixel.
        output.flush()

    def tick(self):
        if self.mode == "off" or not self.started:
            return
        if not self.geometry_expired and time.monotonic() >= self.geometry_deadline:
            self.geometry_expired = True
            self.revision += 1
        if self.settled:
            return
        if self.acknowledged:
            self.presenter = KittyPresenter(self.image_id)
        elif time.monotonic() < self.deadline:
            return
        elif self.mode == "auto" and self.sixel_advertised and self.converter:
            self.presenter = SixelPresenter(self.converter)
        else:
            if self.mode == "auto" and self.sixel_advertised and not self.converter:
                self.reason = "Terminal advertises Sixel, but img2sixel is missing from PATH (Debian: libsixel-bin). Restart after installing it."
            else:
                self.reason = ("No positive Kitty PNG acknowledgement" + (f" ({self.kitty_error})" if self.kitty_error else "") +
                               (" or Sixel advertisement" if self.mode == "auto" else "") +
                               ". For a known Sixel terminal such as mlterm-fb, use --pdf-graphics sixel; otherwise use a compatible terminal or off.")
            # Keep filtering late replies, but never switch the chosen backend later.
            self.settled = True
            self.revision += 1
            return
        self.settled = True
        self.revision += 1

    def reply(self, text):
        if text.startswith(ESC + "_G"):
            header, separator, payload = text[3:-2].partition(";")
            match = re.search(r"(?:^|,)i=(\d+)(?:,|$)", header)
            if match and separator:
                identifier = int(match[1])
                if identifier == self.probe_id and not self.settled and time.monotonic() <= self.deadline:
                    self.acknowledged = payload == "OK"
                    self.kitty_error = payload if payload != "OK" else ""
                    self.tick()
                elif identifier == self.image_id and self.protocol == "kitty" and payload != "OK":
                    self.disable("Terminal rejected PDF image presentation: " + payload)
        else:
            match = re.fullmatch(r"\x1b\[([46]);(\d+);(\d+)t", text)
            if match and self.started and time.monotonic() <= self.geometry_deadline:
                kind, height, width = map(int, match.groups())
                if kind == 6:
                    self._set_cell(width, height, 2)
                else:
                    self._area_geometry(width, height)
            match = re.fullmatch(r"\x1b\[\?([\d;]+)c", text)
            if match and not self.settled and time.monotonic() <= self.deadline:
                self.sixel_advertised = "4" in match[1].split(";")[1:]

    def prepare(self, tasks, png, identity, changed):
        if self.supported:
            self.presenter.prepare(tasks, png, identity, changed, self.disable)

    def suspend(self, free=False):
        if self.presenter:
            self.presenter.suspend(free=free)

    def hide(self, output, free=False):
        if self.presenter:
            self.text_dirty |= self.presenter.hide(output, free=free)

    def show(self, output, png, identity, rectangle):
        if not self.supported:
            return
        x, y, columns, rows = rectangle
        size = output.get_size()
        # Sixel has no portable clipping rectangle. Never send an out-of-bounds
        # raster, and retain one text row below for cursor-origin Sixel terminals.
        if min(columns, rows) <= 0 or min(x, y) < 0 or x + columns > size.columns or y + rows >= size.rows:
            return
        self.presenter.show(output, png, identity, rectangle)


class ReplyReader:
    """Keep protocol replies (including split/late replies) out of editable text."""
    def __init__(self, reader, graphics):
        self.reader, self.graphics = reader, graphics
        self.pending = ""

    @property
    def closed(self):
        return self.reader.closed

    def read(self):
        data = self.pending + self.reader.read()
        self.pending = ""
        result = []
        while data:
            at = data.find(ESC)
            if at < 0:
                result.append(data)
                break
            result.append(data[:at])
            data = data[at:]
            if data.startswith(ESC + "_G"):
                end = data.find(ESC + "\\", 3)
                if end < 0:
                    self.pending = data[:8192]
                    break
                self.graphics.reply(data[:end + 2])
                data = data[end + 2:]
                continue
            match = re.match(r"\x1b\[(?:[46];\d+;\d+t|\?[\d;]+c)", data)
            if match:
                self.graphics.reply(match.group())
                data = data[match.end():]
                continue
            if (any(prefix.startswith(data) for prefix in (ESC + "_G", ESC + "[6;", ESC + "[4;", ESC + "[?"))
                    or re.fullmatch(r"\x1b\[(?:[46];[\d;]*|\?[\d;]*)", data)):
                if len(data) > 8192:
                    data = data[1:]
                    continue
                self.pending = data
                break
            result.append(data[0])
            data = data[1:]
        return "".join(result)

    def flush_escape(self):
        # A user's bare Escape must still reach the key decoder after its normal timeout.
        if self.pending and not self.pending.startswith(ESC + "_G") and not self.pending.startswith((ESC + "[6;", ESC + "[4;", ESC + "[?")):
            data, self.pending = self.pending, ""
            return data
        return ""


class TerminalInput(Vt100Input):
    def __init__(self, stdin, graphics):
        super().__init__(stdin)
        # A small, version-pinned extension of the upstream POSIX reader; the
        # original incremental UTF-8 decoder and terminal contexts are retained.
        self.stdin_reader = ReplyReader(self.stdin_reader, graphics)

    def flush_keys(self):
        self.vt100_parser.feed(self.stdin_reader.flush_escape())
        return super().flush_keys()
