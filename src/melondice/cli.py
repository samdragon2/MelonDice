"""Launch the TUI in the current terminal, independent of graphical environments."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from . import __version__
from .storage import Store, parse_cell_pixels


def main():
    parser = argparse.ArgumentParser(description="Melon Dice terminal — ChatGPT, pdfViewer, Text editor")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--data-dir", type=Path, help="Private configuration/history directory")
    parser.add_argument("--pdf-graphics", choices=["auto", "kitty", "sixel", "off"],
                        help="PDF presentation: auto prefers confirmed Kitty, then advertised Sixel; sixel explicitly trusts the terminal")
    parser.add_argument("--pdf-cell-pixels", metavar="WIDTHxHEIGHT",
                        help="Measured terminal cell pixels; overrides geometry queries and config")
    args = parser.parse_args()
    try:
        if args.pdf_cell_pixels is not None:
            parse_cell_pixels(args.pdf_cell_pixels)
    except ValueError as error:
        parser.error(str(error))
    if not sys.stdin.isatty() or not sys.stdout.isatty() or os.environ.get("TERM") == "dumb":
        print("Melon Dice requires an interactive VT100-compatible terminal. For remote use, allocate a TTY with ssh -t USER@PI. No graphical display is needed.", file=sys.stderr)
        return 2
    store = None
    application = None
    normal = False
    try:
        from .terminal import Graphics, TerminalGuard, TerminalInput
        from .app import Application
        root = args.data_dir or Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "melondice"
        store = Store(root)
        graphics = Graphics(args.pdf_graphics or store.config["pdf_graphics"],
                            args.pdf_cell_pixels if args.pdf_cell_pixels is not None else store.config["pdf_cell_pixels"])
        with TerminalGuard():
            try:
                terminal_input = TerminalInput(sys.stdin, graphics)
                application = Application(store, graphics, terminal_input)
                application.run()
                normal = True
            finally:
                if application:
                    application.cleanup(emergency=not normal)
        return 0
    except (KeyboardInterrupt, EOFError):
        return 130
    except Exception as error:
        # Printed only after terminal modes/alternate screen have been restored.
        print(f"Melon Dice could not start or continue: {type(error).__name__}: {error}\nSee README.md.", file=sys.stderr)
        return 1
    finally:
        if store:
            store.close()
