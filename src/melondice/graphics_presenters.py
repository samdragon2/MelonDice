"""Protocol-specific presentation. Only the UI/lifecycle thread writes to the terminal.

Sixel conversion runs on Tasks' asyncio loop; its subprocess never inherits the
TUI streams. Sixel retains the displayed encoding and at most one replacement.
"""
from __future__ import annotations

import asyncio
import base64
from concurrent.futures import CancelledError
import re
import struct

ESC = "\x1b"
MAX_ENCODED = 128 * 1024 * 1024


class KittyPresenter:
    name = "kitty"

    def __init__(self, image_id):
        self.image_id = image_id
        self.uploaded = None
        self.placed = False
        self.rectangle = None
        self.placed_identity = None

    def prepare(self, tasks, png, identity, changed, failed):
        pass  # PNG is already the protocol's native format.

    def suspend(self, free=False):
        pass

    def ready(self, identity):
        return True  # PNG needs no asynchronous encoding.

    def hide(self, output, free=False):
        if self.placed or (free and self.uploaded is not None):
            action = "I" if free else "i"
            output.write_raw(f"{ESC}_Ga=d,d={action},i={self.image_id},q=2{ESC}\\")
            output.flush()
        self.placed = False
        self.placed_identity = None
        if free:
            self.uploaded = None
        return False  # Kitty deletion does not damage the text screen.

    def show(self, output, png, identity, rectangle):
        if self.placed and self.placed_identity == identity and self.rectangle == rectangle:
            return True
        x, y, columns, rows = rectangle
        if identity != self.uploaded:
            data = base64.b64encode(png).decode("ascii")
            for offset in range(0, len(data), 4096):
                chunk = data[offset:offset + 4096]
                more = int(offset + 4096 < len(data))
                header = f"a=t,t=d,f=100,i={self.image_id},q=1,m={more}" if offset == 0 else f"m={more},q=1"
                output.write_raw(f"{ESC}_G{header};{chunk}{ESC}\\")
            self.uploaded = identity
        output.write_raw(f"{ESC}7{ESC}[{y + 1};{x + 1}H{ESC}_Ga=p,i={self.image_id},p=1,c={columns},r={rows},C=1,q=1{ESC}\\{ESC}8")
        output.flush()
        self.placed, self.rectangle = True, rectangle
        self.placed_identity = identity
        return True


async def encode_sixel(executable, png):
    """Pipe a PNG through img2sixel with bounded time/output and reaped children."""
    process = None
    jobs = []

    async def read_limited(stream, limit):
        chunks, size = [], 0
        while True:
            chunk = await stream.read(65536)
            if not chunk:
                return b"".join(chunks)
            size += len(chunk)
            if size > limit:
                raise ValueError("img2sixel output exceeded its display buffer limit.")
            chunks.append(chunk)

    try:
        launch = asyncio.create_task(asyncio.create_subprocess_exec(
            executable, "-7", "-p", "256", "-d", "none", "-q", "low",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE))
        try:
            process = await asyncio.shield(launch)
        except asyncio.CancelledError:
            # Cancellation can arrive while the OS is creating the child. Get
            # ownership of that child before unwinding so it cannot be orphaned.
            process = await launch
            raise

        async def feed():
            try:
                process.stdin.write(png)
                await process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                pass  # Report the converter's diagnostic below.
            finally:
                process.stdin.close()

        jobs = [asyncio.create_task(feed()),
                asyncio.create_task(read_limited(process.stdout, MAX_ENCODED)),
                asyncio.create_task(read_limited(process.stderr, 65536))]
        _sent, encoded, diagnostic = await asyncio.wait_for(asyncio.gather(*jobs), timeout=30)
        await asyncio.wait_for(process.wait(), timeout=2)
        if process.returncode:
            detail = diagnostic.decode("utf-8", "replace")[-2000:]
            detail = "".join(c if c.isprintable() or c == "\n" else "?" for c in detail)
            raise ValueError(f"img2sixel exited with status {process.returncode}: {detail}")
        # Accept a single 7-bit DCS only. No converter cursor/mode commands enter
        # the terminal, and no resizing options alter the renderer's geometry.
        match = re.fullmatch(rb'\x1bP[0-9;]*q("1;1;(\d+);(\d+)[ -~]*)\x1b\\', encoded)
        if not match or tuple(map(int, match.group(2, 3))) != struct.unpack("!II", png[16:24]):
            raise ValueError("img2sixel returned an unexpected Sixel envelope or raster size.")
        # Transparent DCS background prevents clearing outside the raster. The
        # viewport PNG itself is opaque, including its white page margins.
        return ESC + "P0;1;0q" + match[1].decode("ascii") + ESC + "\\"
    finally:
        # Kill synchronously before any cleanup await: shutdown can deliver a
        # second cancellation while reader tasks are being collected.
        if process is not None and process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        for job in jobs:
            job.cancel()
        try:
            if jobs:
                await asyncio.gather(*jobs, return_exceptions=True)
        finally:
            if process is not None:
                # Drain pipes after killing, including when a bounded reader
                # failed. wait() alone can deadlock with a full pipe.
                await process.communicate()


class SixelPresenter:
    name = "sixel"

    def __init__(self, executable):
        self.executable = executable
        self.ready_identity = None
        self.ready_encoded = None
        self.placed = False
        self.rectangle = None
        self.placed_identity = None
        self.displayed_encoded = None
        self.displayed_identity = None
        self.future = None
        self.requested = None
        self.generation = 0

    def prepare(self, tasks, png, identity, changed, failed):
        if self.ready(identity) or (self.future is not None and identity == self.requested):
            return
        self.suspend()
        generation = self.generation
        self.requested = identity

        def done(future):
            if generation != self.generation:
                return  # Cancellation may race completion; never accept stale output.
            self.future = None
            self.requested = None
            try:
                encoded = future.result()
            except CancelledError:
                return
            except Exception as error:
                failed(f"Sixel encoding failed: {type(error).__name__}: {error}. Previous image retained where safe. Check img2sixel on PATH; change page/zoom/pan to retry.")
            else:
                self.ready_identity, self.ready_encoded = identity, encoded
            changed()

        self.future = tasks.submit(encode_sixel(self.executable, png), done)

    def ready(self, identity):
        return ((identity == self.ready_identity and self.ready_encoded is not None)
                or (identity == self.displayed_identity and self.displayed_encoded is not None))

    def suspend(self, free=False):
        self.generation += 1
        if self.future is not None:
            self.future.cancel()
            self.future = None
        self.requested = None
        # A completed replacement is still pending until show() actually sends it.
        self.ready_identity = self.ready_encoded = None
        if free:
            self.displayed_identity = self.displayed_encoded = None

    def _erase(self, output):
        damaged = self.placed
        if damaged:
            x, y, columns, rows = self.rectangle
            size = output.get_size()
            columns = max(0, min(columns, size.columns - x))
            output.write_raw(ESC + "7" + ESC + "[0m")
            # ECH replaces mlterm's picture cells and erases intersecting Sixel
            # pixels in terminals with text/graphics erasure semantics.
            if columns:
                for row in range(max(0, y), min(y + rows, size.rows)):
                    output.write_raw(f"{ESC}[{row + 1};{x + 1}H{ESC}[{columns}X")
            output.write_raw(ESC + "8")
        return damaged

    def hide(self, output, free=False):
        damaged = self._erase(output)
        if damaged:
            output.flush()
        self.placed = False
        self.placed_identity = None
        if free:
            self.suspend(free=True)
        return damaged  # Caller must repaint the text screen after erasure.

    def show(self, output, png, identity, rectangle):
        if not self.ready(identity):
            return False
        if self.placed and identity == self.placed_identity and rectangle == self.rectangle:
            return True
        encoded = self.ready_encoded if identity == self.ready_identity else self.displayed_encoded
        if self.placed:
            # Same-bounds replacement: erase picture cells and send the finished
            # DCS in ONE flush. Never expose an empty region while encoding.
            self._erase(output)
        x, y, _columns, _rows = rectangle
        # DECSDM reset uses the cursor origin (setting it puts images at home in
        # mlterm). The bounded raster ends above the footer, leaving room for
        # mlterm's post-image line feed, so no screen scrolling is needed.
        # Save/restore both this private mode and the terminal cursor.
        output.write_raw(f"{ESC}7{ESC}[?80s{ESC}[?80l{ESC}[{y + 1};{x + 1}H" +
                         encoded + f"{ESC}[?80r{ESC}8")
        output.flush()
        self.placed, self.placed_identity, self.rectangle = True, identity, rectangle
        self.displayed_identity, self.displayed_encoded = identity, encoded
        if self.ready_identity == identity:
            self.ready_identity = self.ready_encoded = None
        return True
