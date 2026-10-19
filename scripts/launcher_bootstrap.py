"""Installed bootstrap: lock the managed installation before loading its packages.

This file is copied by install.py. Startup never installs or updates anything.
"""
from __future__ import annotations

import fcntl
import os
from pathlib import Path
import sys


def main():
    root = Path(__file__).resolve().parent
    try:
        # The installer holds an exclusive lock. Keep this shared descriptor
        # across exec; the launcher also retains it while supervising mlterm.
        lock = open(root / "install.lock", "rb")
        try:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise OSError("Installation/update in progress; retry melondice when it finishes.") from None
        current = (root / "current").resolve(strict=True)
        if current.parent != root / "environments" or not (current / ".melondice-environment").is_file():
            raise OSError(f"Invalid managed environment: {current}")
        python = current / "bin" / "python"
        if not python.is_file() or not os.access(python, os.X_OK):
            raise OSError(f"Installed Python is missing or not executable: {python}")
        os.set_inheritable(lock.fileno(), True)
        os.environ["MELONDICE_INSTALL_ROOT"] = str(root)
        os.execv(str(python), [str(python), "-I", "-m", "melondice.launcher", *sys.argv[1:]])
    except OSError as error:
        print(f"Melon Dice launcher: {error}\nRun python3 scripts/install.py from the project source to repair the installation.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
