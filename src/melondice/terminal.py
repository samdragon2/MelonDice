"""POSIX terminal restoration and Kitty presentation, independent of PDF rendering.

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
import struct
import sys
import termios
import time
import zlib

from prompt_toolkit.input.vt100 import Vt100Input

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
    def __init__(self, mode="auto"):
        self.probe_id = secrets.randbelow(1_000_000_000) + 1
        self.image_id = self.probe_id + 1
        self.mode = mode
        self.started = False
        self.deadline = 0.0
        self.acknowledged = False
        self.cell = None
        self.uploaded = None
        self.placed = False
        self.reason = "Checking terminal graphics capability…"
        self.revision = 0
        self.grid = None
        if mode == "off":
            self.reason = "Terminal PDF images disabled in Options."
        elif os.environ.get("TMUX") or os.environ.get("STY"):
            self.mode = "off"
            self.reason = "PDF images are disabled inside tmux/screen; use a direct SSH terminal."
        elif os.environ.get("TERM", "") in {"linux", "dumb", "cons25"}:
            self.mode = "off"
            self.reason = "This console has no implemented Kitty graphics backend."

    @property
    def supported(self):
        return self.mode == "auto" and self.acknowledged and self.cell is not None

    @property
    def description(self):
        if self.mode == "off":
            return self.reason
        if self.supported:
            return "Kitty graphics confirmed (in-band PNG over the terminal connection)."
        if self.started and time.monotonic() > self.deadline:
            if self.acknowledged:
                return "Kitty responded, but terminal cell pixel geometry is unavailable."
            return "No Kitty graphics acknowledgement received. Use a compatible terminal for PDF images."
        return self.reason

    def begin(self, output):
        if self.mode == "off":
            return
        size = output.get_size()
        grid = size.columns, size.rows
        if self.started:
            if grid != self.grid:
                self.grid = grid
                output.write_raw(ESC + "[16t")
                output.flush()
            return
        self.grid = grid
        self.started = True
        self.deadline = time.monotonic() + 1.5
        # Query the exact PNG transmission format we use, without displaying it.
        png = b"\x89PNG\r\n\x1a\n"
        for kind, payload in [(b"IHDR", struct.pack("!IIBBBBB", 1, 1, 8, 2, 0, 0, 0)),
                              (b"IDAT", zlib.compress(b"\x00\xff\xff\xff")), (b"IEND", b"")]:
            png += struct.pack("!I", len(payload)) + kind + payload + struct.pack("!I", binascii.crc32(kind + payload))
        data = base64.b64encode(png).decode("ascii")
        output.write_raw(f"{ESC}_Ga=q,i={self.probe_id},t=d,f=100;{data}{ESC}\\{ESC}[16t")
        output.flush()
        try:
            rows, cols, width, height = struct.unpack("HHHH", fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, b"\0" * 8))
            if rows and cols and width and height:
                self.cell = (max(1, width // cols), max(1, height // rows))
        except (OSError, ValueError):
            pass

    def reply(self, text):
        if text.startswith(ESC + "_G"):
            header, separator, payload = text[3:-2].partition(";")
            match = re.search(r"(?:^|,)i=(\d+)(?:,|$)", header)
            if match and separator:
                identifier = int(match[1])
                if identifier == self.probe_id:
                    if payload == "OK":
                        self.acknowledged = True
                    else:
                        self.mode = "off"
                        self.reason = "Terminal rejected the Kitty PNG capability query: " + payload
                    self.revision += 1
                elif identifier == self.image_id and payload != "OK":
                    self.mode = "off"
                    self.reason = "Terminal rejected PDF image presentation: " + payload
                    self.uploaded = None
                    self.revision += 1
        else:
            match = re.fullmatch(r"\x1b\[6;(\d+);(\d+)t", text)
            if match:
                height, width = map(int, match.groups())
                if 1 <= width <= 256 and 1 <= height <= 512:
                    self.cell = width, height
                    self.revision += 1

    def hide(self, output, free=False):
        if self.placed or (free and self.started and self.acknowledged):
            action = "I" if free else "i"
            output.write_raw(f"{ESC}_Ga=d,d={action},i={self.image_id},q=2{ESC}\\")
            output.flush()
        self.placed = False
        if free:
            self.uploaded = None

    def show(self, output, png, identity, rectangle):
        if not self.supported:
            return
        x, y, columns, rows = rectangle
        if min(columns, rows) <= 0:
            return
        if identity != self.uploaded:
            data = base64.b64encode(png).decode("ascii")
            for offset in range(0, len(data), 4096):
                chunk = data[offset:offset + 4096]
                more = int(offset + 4096 < len(data))
                header = f"a=t,t=d,f=100,i={self.image_id},q=1,m={more}" if offset == 0 else f"m={more},q=1"
                output.write_raw(f"{ESC}_G{header};{chunk}{ESC}\\")
            self.uploaded = identity
        # Save/restore the cursor so prompt_toolkit's renderer stays synchronized.
        output.write_raw(f"{ESC}7{ESC}[{y + 1};{x + 1}H{ESC}_Ga=p,i={self.image_id},p=1,c={columns},r={rows},C=1,q=1{ESC}\\{ESC}8")
        output.flush()
        self.placed = True


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
            match = re.match(r"\x1b\[6;\d+;\d+t", data)
            if match:
                self.graphics.reply(match.group())
                data = data[match.end():]
                continue
            if any(prefix.startswith(data) for prefix in (ESC + "_G", ESC + "[6;")) or re.fullmatch(r"\x1b\[6;[\d;]*", data):
                self.pending = data
                break
            result.append(data[0])
            data = data[1:]
        return "".join(result)

    def flush_escape(self):
        # A user's bare Escape must still reach the key decoder after its normal timeout.
        if self.pending and not self.pending.startswith(ESC + "_G") and not self.pending.startswith(ESC + "[6;"):
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
