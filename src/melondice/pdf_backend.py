"""MuPDF lives exclusively in a spawned process; PDF bytes and passwords stay in memory."""
from __future__ import annotations

import multiprocessing as mp
from io import BytesIO
import math
import os
from pathlib import Path
import queue

from .storage import open_regular

MAX_PDF = 128 * 1024 * 1024
MAX_PIXELS = 12_000_000


def worker(requests, results):
    # Native diagnostics must not overwrite the parent's full-screen terminal.
    with open(os.devnull, "wb") as sink:
        os.dup2(sink.fileno(), 1)
        os.dup2(sink.fileno(), 2)
    try:
        import pymupdf
        from PIL import Image
    except Exception as error:
        results.put((0, "startup_error", f"PDF dependencies could not be loaded: {type(error).__name__}: {error}"))
        return

    document = None
    pending_document = None
    try:
        while True:
            command = requests.get()
            if command is None:
                return
            sequence, kind, args = command
            try:
                if kind == "open":
                    if pending_document is not None:
                        pending_document.close()
                        pending_document = None
                    path, password = args
                    with open_regular(Path(path)) as source:
                        data = source.read(MAX_PDF + 1)
                    if len(data) > MAX_PDF:
                        raise ValueError("PDF documents are limited to 128 MiB.")
                    candidate = pymupdf.open(stream=data, filetype="pdf")
                    try:
                        if candidate.needs_pass and not candidate.authenticate(password):
                            results.put((sequence, "password", None))
                            continue
                        if not candidate.page_count:
                            raise ValueError("The PDF has no pages.")
                        outline = candidate.get_toc(simple=True)
                        metadata = {"pages": candidate.page_count, "outline": outline}
                        pending_document = candidate
                        candidate = None
                        results.put((sequence, "opened", metadata))
                    finally:
                        if candidate is not None:
                            candidate.close()
                elif kind == "commit":
                    if pending_document is not None:
                        if document is not None:
                            document.close()
                        document, pending_document = pending_document, None
                elif kind == "discard":
                    if pending_document is not None:
                        pending_document.close()
                        pending_document = None
                elif kind == "render":
                    if document is None:
                        raise ValueError("No PDF document is open.")
                    page_number, zoom, pan_x, pan_y, width, height = args
                    page = document.load_page(page_number)
                    rect = page.rect
                    if rect.width <= 0 or rect.height <= 0:
                        raise ValueError("PDF page has invalid dimensions.")
                    if width * height > MAX_PIXELS or max(width, height) > 16384:
                        raise ValueError("Terminal viewport exceeds the 12 megapixel/16384 pixel raster limit.")
                    if min(width, height) < 1:
                        raise ValueError("Terminal viewport is too small.")
                    full_width, full_height = math.ceil(rect.width * zoom), math.ceil(rect.height * zoom)
                    pan_x = max(0, min(int(pan_x), max(0, full_width - width)))
                    pan_y = max(0, min(int(pan_y), max(0, full_height - height)))
                    clip = pymupdf.Rect(pan_x / zoom, pan_y / zoom,
                                        min(rect.width, (pan_x + width) / zoom),
                                        min(rect.height, (pan_y + height) / zoom))
                    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom),
                                             clip=clip, colorspace=pymupdf.csRGB, alpha=False, annots=True)
                    raster = Image.new("RGB", (width, height), "white")
                    raster.paste(Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples), (0, 0))
                    encoded = BytesIO()
                    raster.save(encoded, format="PNG")
                    # A viewport display buffer, never a page export or clipboard image.
                    results.put((sequence, "rendered", {"png": encoded.getvalue(), "pan": (pan_x, pan_y),
                                                        "full": (full_width, full_height)}))
            except Exception as error:
                results.put((sequence, "error", f"{type(error).__name__}: {error}"))
    finally:
        if document:
            document.close()
        if pending_document is not None:
            pending_document.close()


class PDFBackend:
    def __init__(self):
        context = mp.get_context("spawn")
        self.requests = context.Queue(maxsize=8)
        self.results = context.Queue(maxsize=8)
        self.process = context.Process(target=worker, args=(self.requests, self.results),
                                       name="melondice-pdf", daemon=True)
        self.process.start()
        self.sequence = 0
        self.closed = False

    def send(self, kind, *args):
        self.sequence += 1
        self.requests.put_nowait((self.sequence, kind, args))
        return self.sequence

    def receive(self):
        values = []
        for _ in range(8):
            try:
                values.append(self.results.get_nowait())
            except queue.Empty:
                break
        if not self.process.is_alive() and not values:
            raise RuntimeError("PDF renderer exited. Close and reopen pdfViewer to restart it.")
        return values

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.process.is_alive():
            self.process.terminate()
        self.process.join(timeout=2)
        if self.process.is_alive():
            self.process.kill()
            self.process.join(timeout=1)
        for channel in (self.requests, self.results):
            channel.cancel_join_thread()
            channel.close()
        self.process.close()
