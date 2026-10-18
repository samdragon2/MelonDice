"""Private persistence, atomic writes, configuration, and single-host ownership."""
from __future__ import annotations

import fcntl
from contextlib import contextmanager
import json
import os
import re
from pathlib import Path
import stat
import tempfile
import uuid


DEFAULTS = {
    "document_directory": str(Path.home() / "Documents" if (Path.home() / "Documents").is_dir() else Path.home()),
    "theme": "dark",
    "mouse_support": True,
    "pdf_graphics": "auto",
    "escape_timeout_ms": 200,
    "history_persistence": True,
    "editor_autosave_seconds": 30,
    "model": "",
    "callback_port": 1455,
    "shortcuts": {
        "cycle": ["escape tab", "f6"],
        "home": ["f1"],
        "information": ["f2"],
        "settings": ["c-o"],
        "close": ["c-q", "f10"],
        "save": ["c-s", "f8"],
    },
}


@contextmanager
def open_regular(path):
    """Reject devices/FIFOs before a potentially blocking read, including path races."""
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOCTTY)
    with os.fdopen(fd, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise OSError("Only regular files are supported.")
        yield handle


def atomic_bytes(path: Path, data: bytes, mode: int = 0o600) -> None:
    """Replace a regular file without following a final symlink; retain original on failure."""
    path = path.expanduser().absolute()
    if path.is_symlink():
        raise OSError("Refusing to replace a symbolic link; choose its actual file path.")
    if path.exists() and not path.is_file():
        raise OSError("Destination is not a regular file.")
    fd, name = tempfile.mkstemp(prefix=".melondice-", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def atomic_json(path: Path, value: object) -> None:
    atomic_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise OSError(f"Private storage must be an owned, non-symlink directory: {path}")
    path.chmod(0o700)


class Store:
    def __init__(self, root: Path):
        self.root = root.expanduser().absolute()
        private_directory(self.root)
        self.lock = open(self.root / "instance.lock", "a+b")
        os.chmod(self.root / "instance.lock", 0o600)
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close()
            raise OSError("Another Melon Dice process owns this data directory.") from None
        self.config = json.loads(json.dumps(DEFAULTS))
        loaded = read_json(self.root / "config.json", {})
        if not isinstance(loaded, dict):
            raise ValueError("config.json must contain an object.")
        for key in DEFAULTS:
            if key in loaded:
                if key == "shortcuts":
                    for action, keys in loaded[key].items():
                        self.config[key][action] = [legacy_key(k) for k in keys]
                else:
                    self.config[key] = loaded[key]
        self.validate(self.config)
        self.history = self.root / "conversations"
        private_directory(self.history)
        host = read_json(self.root / "host.json", {})
        self.host_id = host.get("ext_agent_host_id")
        if not self.host_id:
            self.host_id = "urn:uuid:" + str(uuid.uuid4())
            atomic_json(self.root / "host.json", {"ext_agent_host_id": self.host_id})

    @staticmethod
    def validate(config):
        if config["theme"] not in {"dark", "light"}:
            raise ValueError("theme must be dark or light")
        if config["pdf_graphics"] not in {"auto", "off"}:
            raise ValueError("pdf_graphics must be auto or off")
        for key, low, high in [("escape_timeout_ms", 50, 2000), ("callback_port", 1024, 65535),
                               ("editor_autosave_seconds", 0, 3600)]:
            if type(config[key]) is not int or not low <= config[key] <= high:
                raise ValueError(f"{key} must be an integer from {low} to {high}")
        for key in ("history_persistence", "mouse_support"):
            if type(config[key]) is not bool:
                raise ValueError(f"{key} must be a boolean")
        for key in ("document_directory", "model"):
            if not isinstance(config[key], str):
                raise ValueError(f"{key} must be text")
        if set(config["shortcuts"]) != set(DEFAULTS["shortcuts"]):
            raise ValueError("Unknown shortcut action")
        seen = set()
        reserved = {"c-p", "c-c", "c-v", "c-x", "c-i", "tab", "enter", "c-m", "escape",
                    "c-j", "c-n", "c-f", "c-z", "c-y", "c-space", "f3", "f4", "f5",
                    "f7", "f9", "f12", "escape s", "escape r", "escape u", "escape a", "escape e"}
        for keys in config["shortcuts"].values():
            if not isinstance(keys, list) or not keys:
                raise ValueError("Each shortcut action needs a nonempty list")
            for key in keys:
                if not isinstance(key, str) or not re.fullmatch(r"(?:f(?:[1-9]|1[0-9]|2[0-4])|c-[a-z]|escape (?:[a-z]|tab))", key):
                    raise ValueError("Use terminal key names: f6, c-o, or escape tab")
                if key in reserved or key in seen:
                    raise ValueError(f"Reserved or duplicate shortcut: {key}")
                seen.add(key)

    def save_config(self):
        self.validate(self.config)
        atomic_json(self.root / "config.json", self.config)

    def recent(self, path=None):
        values = read_json(self.root / "recent-pdfs.json", [])
        if path:
            values = [str(path)] + [v for v in values if v != str(path)]
            atomic_json(self.root / "recent-pdfs.json", values[:20])
        return values[:20]

    def close(self):
        if not self.lock.closed:
            self.lock.close()


def legacy_key(value):
    """Migrate the previous release's global bindings; GUI font preferences are ignored."""
    if not isinstance(value, str):
        raise ValueError("Shortcut must be text")
    replacements = {"<Alt-Tab>": "escape tab", "<Control-o>": "c-o",
                    "<Control-q>": "c-q", "<Control-s>": "c-s"}
    if value in replacements:
        return replacements[value]
    if re.fullmatch(r"<F\d+>", value):
        return value[1:-1].lower()
    return value
