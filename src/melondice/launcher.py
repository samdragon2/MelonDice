"""Installed launch context routing; no installation or update work at startup."""
from __future__ import annotations

import json
from importlib.util import find_spec
import os
from pathlib import Path
import stat
import subprocess
import sys

FB_MARKER = "MELONDICE_FB_SESSION"


def linux_ancestors():
    """Read real executable ancestry, never infer a terminal from TERM.

    Unreadable ancestry is harmless: without positive VT evidence we never
    start a framebuffer process. Remote indicators have precedence below.
    """
    ancestors = []
    pid = os.getppid()
    seen = set()
    for _ in range(128):
        if pid <= 1 or pid in seen:
            break
        seen.add(pid)
        directory = Path("/proc") / str(pid)
        try:
            fields = (directory / "stat").read_text().rsplit(")", 1)[1].split()
            parent = int(fields[1])  # state, ppid, ...; comm can contain spaces.
        except (OSError, ValueError, IndexError):
            break
        try:
            executable = (directory / "exe").resolve(strict=True)
        except OSError:
            executable = None  # comm remains useful for restricted sshd parents.
        try:
            name = (directory / "comm").read_text().strip()
        except OSError:
            name = ""
        ancestors.append((executable, name))
        pid = parent
    return ancestors


def remote_session(ancestors):
    if any(os.environ.get(key) for key in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY")):
        return True
    return any(name.startswith(("sshd", "mosh-server"))
               or (executable is not None and executable.name.startswith(("sshd", "mosh-server")))
               for executable, name in ancestors)


def linux_virtual_console():
    """Require matching real Linux VT devices on stdin, stdout and /dev/tty.

    Serial consoles and PTYs, including SSH and existing mlterm, do not qualify.
    Device identity is used instead of TERM or merely the tty pathname.
    """
    if not sys.platform.startswith("linux"):
        return False
    try:
        incoming, outgoing = os.fstat(0), os.fstat(1)
        if not (os.isatty(0) and os.isatty(1) and stat.S_ISCHR(incoming.st_mode)
                and incoming.st_rdev == outgoing.st_rdev
                and os.major(incoming.st_rdev) == 4 and 1 <= os.minor(incoming.st_rdev) <= 63):
            return False
        fields = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()
        if int(fields[4]) != incoming.st_rdev:  # tty_nr must be this actual VT.
            return False
        with open("/dev/tty", "rb", buffering=0) as terminal:
            # /proc confirmed the controlling device; /dev/tty is its alias.
            return os.isatty(terminal.fileno()) and os.tcgetpgrp(terminal.fileno()) == os.getpgrp()
    except (OSError, ValueError, IndexError):
        return False


def application():
    try:
        from .cli import main
        return main()
    except ImportError as error:
        print(f"Melon Dice: an installed Python dependency is missing: {error}\nRun python3 scripts/install.py from the project source to repair the environment.", file=sys.stderr)
        return 1


def main():
    try:
        root_value = os.environ.get("MELONDICE_INSTALL_ROOT")
        if not root_value:
            return application()  # Ordinary pip/module use remains terminal-native.
        root = Path(root_value)
        settings = json.loads((root / "launcher.json").read_text())
        if (not isinstance(settings, dict) or settings.get("format") != 1 or settings.get("profile") not in {"pi", "terminal"}
                or not isinstance(settings.get("installation_id"), str)):
            raise ValueError(f"Invalid installation settings in {root / 'launcher.json'}")
        # Help/version never need a framebuffer session or an interactive TTY.
        if any(arg in {"-h", "--help", "--version"} for arg in sys.argv[1:]):
            return application()
        missing = [package for package in ("prompt_toolkit", "httpx", "jwt", "PIL", "pymupdf")
                   if find_spec(package) is None]
        if missing:
            raise OSError("Missing installed Python dependencies: " + ", ".join(missing))
        ancestors = linux_ancestors() if sys.platform.startswith("linux") else []
        if remote_session(ancestors) or settings["profile"] != "pi":
            return application()
        if os.environ.get(FB_MARKER) == settings["installation_id"]:
            if linux_virtual_console():
                raise OSError("Launcher session marker reached a bare console; refusing recursive mlterm startup. Unset MELONDICE_FB_SESSION and retry.")
            return application()
        mlterm = Path(settings["mlterm_fb"])
        # Existing mlterm-fb can have TERM=xterm. A real ancestor executable
        # match is positive evidence; its PTY also excludes the bare-VT route.
        if any(executable == mlterm.resolve() for executable, _name in ancestors):
            return application()
        if not linux_virtual_console():
            return application()
        if os.environ.get("TMUX") or os.environ.get("STY"):
            raise OSError("Leave tmux/screen before starting a local framebuffer session.")
        if not mlterm.is_file() or not os.access(mlterm, os.X_OK):
            raise OSError(f"Existing mlterm-fb is missing or not executable: {mlterm}. Re-run the installer with --mlterm-fb PATH; no terminal is installed automatically.")
        environment = dict(os.environ)
        environment[FB_MARKER] = settings["installation_id"]
        # No shell, init-string, login shell or daemon: mlterm's sole PTY owns
        # this child. Closing Melon Dice closes that session and returns to the VT.
        command = [str(mlterm), "--aafont=true", "--fontsize=24", "--fg=white", "--bg=black",
                   "--initstr=", f"--working-directory={Path.cwd()}",
                   "-e", sys.executable, "-I", "-m", "melondice.launcher", *sys.argv[1:]]
        # The supervisor holds bootstrap's shared install lock throughout mlterm,
        # including child startup; updates cannot remove a running environment.
        result = subprocess.run(command, env=environment, check=False)
        if result.returncode:
            print(f"Melon Dice: mlterm-fb exited with status {result.returncode}. Check the installation path and its console diagnostics.", file=sys.stderr)
        return result.returncode if result.returncode >= 0 else 128 - result.returncode
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Melon Dice launcher: {error}\nRun python3 scripts/install.py from the project source to repair installation settings.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
