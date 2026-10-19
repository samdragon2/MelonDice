#!/usr/bin/env python3
"""User-local installation/update. Never invoked by ordinary application startup."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid

PATH_START = "# >>> Melon Dice PATH >>>"
PATH_END = "# <<< Melon Dice PATH <<<"
PATH_BLOCK = '''# >>> Melon Dice PATH >>>
case "${PATH-}" in
    "$HOME/.local/bin"|"$HOME/.local/bin":*) ;;
    *) export PATH="$HOME/.local/bin${PATH:+:$PATH}" ;;
esac
# <<< Melon Dice PATH <<<
'''


def regular_owned(path):
    if path.is_symlink():
        raise OSError(f"Refusing to replace a symbolic link: {path}")
    if path.exists():
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise OSError(f"Expected an owned regular file: {path}")


def private_directory(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise OSError(f"Expected an owned, non-symlink directory: {path}")
    path.chmod(0o700)


def atomic_write(path, data, mode=0o600):
    regular_owned(path)
    fd, temporary = tempfile.mkstemp(prefix=".melondice-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            os.fchmod(output.fileno(), mode)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def json_bytes(value):
    return (json.dumps(value, indent=2) + "\n").encode()


def lock_file(path):
    regular_owned(path)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    handle = os.fdopen(fd, "a+b")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise OSError(f"Melon Dice or another installer is running. Close it before installation/update ({path}).") from None
    return handle


def raspberry_pi():
    if not sys.platform.startswith("linux"):
        return False
    for name in ("/proc/device-tree/model", "/sys/firmware/devicetree/base/model"):
        try:
            if b"Raspberry Pi" in Path(name).read_bytes():
                return True
        except OSError:
            pass
    return False


def path_updates(home, disabled):
    """Prepare bounded, repeatable edits without sourcing any shell startup file."""
    if disabled:
        return []
    shell = Path(os.environ.get("SHELL", "/bin/sh")).name
    if shell == "bash":
        login = next((home / name for name in (".bash_profile", ".bash_login")
                      if (home / name).exists() or (home / name).is_symlink()), home / ".profile")
        files = [login, home / ".bashrc"]
    elif shell == "zsh":
        directory = Path(os.environ.get("ZDOTDIR") or str(home)).expanduser().absolute()
        files = [directory / ".zprofile", directory / ".zshrc"]
    elif shell in {"sh", "dash", "ksh"}:
        files = [home / ".profile"]
    else:
        raise OSError(f"Automatic PATH setup supports bash/zsh/sh/dash/ksh, not {shell}. Set ~/.local/bin on PATH in your shell, then use --no-path-setup.")
    updates = []
    for path in dict.fromkeys(files):
        if path.is_symlink():
            raise OSError(f"PATH startup file is a symbolic link: {path}. Manage PATH in your dotfiles and rerun with --no-path-setup.")
        regular_owned(path)
        content = path.read_text() if path.exists() else ""
        if content.count(PATH_START) != content.count(PATH_END) or content.count(PATH_START) > 1:
            raise ValueError(f"Malformed managed PATH block in {path}; repair it or use --no-path-setup.")
        if PATH_START in content:
            start = content.index(PATH_START)
            end = content.index(PATH_END) + len(PATH_END)
            if start > end:
                raise ValueError(f"Reversed PATH block in {path}.")
            replacement = content[:start] + PATH_BLOCK.rstrip("\n") + content[end:]
        else:
            replacement = content + ("\n" if content and not content.endswith("\n") else "") + "\n" + PATH_BLOCK
        if replacement != content:
            mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
            updates.append((path, replacement.encode(), mode))
    return updates


def main():
    parser = argparse.ArgumentParser(description="Install/update Melon Dice for the current user; no sudo.")
    parser.add_argument("--profile", choices=["auto", "pi", "terminal"], default="auto",
                        help="auto detects Raspberry Pi via device tree; pi enables local VT → mlterm-fb")
    parser.add_argument("--mlterm-fb", type=Path, help="Existing framebuffer mlterm executable (default ~/.local/bin/mlterm-fb)")
    parser.add_argument("--pdf-graphics", choices=["auto", "kitty", "sixel", "off"],
                        help="Explicitly save this preference; otherwise preserve existing values, default new Pi installs to sixel")
    parser.add_argument("--no-path-setup", action="store_true", help="Leave shell files untouched; manage PATH yourself")
    args = parser.parse_args()
    candidate = None
    activated = False
    try:
        if os.getuid() == 0:
            raise OSError("Run this installer as your regular user, without sudo.")
        if sys.version_info < (3, 10):
            raise OSError("Python 3.10+ with venv/pip support is required.")
        source = Path(__file__).resolve().parent.parent
        if not (source / "pyproject.toml").is_file() or not (source / "src/melondice/launcher.py").is_file():
            raise OSError(f"Project source is incomplete: {source}")
        home = Path.home()
        root = home / ".local/share/melondice"
        launcher = home / ".local/bin/melondice"
        config_root = Path(os.environ.get("XDG_CONFIG_HOME") or str(home / ".config")).expanduser().absolute() / "melondice"
        config_path = config_root / "config.json"
        base_python = Path(getattr(sys, "_base_executable", sys.executable)).resolve(strict=True)
        if root.is_symlink() or (root.exists() and not (root / "managed.json").is_file()):
            raise OSError(f"Refusing to reuse an unrecognized installation directory: {root}")
        regular_owned(launcher)
        if launcher.exists() and not (root / "managed.json").is_file():
            raise OSError(f"Refusing to overwrite an unrelated executable: {launcher}. Move/rename it yourself before installing.")
        private_directory(root)
        with lock_file(root / "install.lock"):
            manifest_path = root / "managed.json"
            regular_owned(manifest_path)
            if manifest_path.exists():
                manifest = json.loads(manifest_path.read_text())
                if (not isinstance(manifest, dict) or manifest.get("format") != 1 or manifest.get("uid") != os.getuid()
                        or not isinstance(manifest.get("installation_id"), str)):
                    raise ValueError(f"Unrecognized installation ownership record: {manifest_path}")
            else:
                manifest = {"format": 1, "uid": os.getuid(), "installation_id": uuid.uuid4().hex}
                # Establish ownership before dependency/PATH preflights, so a
                # first attempt stopped by a missing prerequisite is repairable.
                atomic_write(manifest_path, json_bytes(manifest))
            settings_path = root / "launcher.json"
            regular_owned(settings_path)
            previous_settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
            if not isinstance(previous_settings, dict):
                raise ValueError(f"Expected a JSON object: {settings_path}")
            profile = args.profile
            if profile == "auto":
                profile = previous_settings.get("profile") or ("pi" if raspberry_pi() else "terminal")
            if profile not in {"pi", "terminal"}:
                raise ValueError(f"Invalid saved installation profile: {profile}")
            mlterm = Path(args.mlterm_fb or previous_settings.get("mlterm_fb") or home / ".local/bin/mlterm-fb").expanduser().absolute()
            if profile == "pi" and (not mlterm.is_file() or not os.access(mlterm, os.X_OK)):
                raise OSError(f"Existing mlterm-fb is missing or not executable: {mlterm}. Supply --mlterm-fb PATH. The installer does not install mlterm or alter OS display settings.")
            if launcher.exists():
                digest = hashlib.sha256(launcher.read_bytes()).hexdigest()
                if digest not in manifest.get("launcher_hashes", []):
                    raise OSError(f"Refusing to overwrite an unrelated or modified executable: {launcher}. Move/rename it yourself if you want this launcher installed there.")
            # Record ownership even if a first installation later fails, allowing
            # a repair to recognize its own environment directory.
            atomic_write(manifest_path, json_bytes(manifest))
            updates = path_updates(home, args.no_path_setup)
            regular_owned(config_path)
            private_directory(config_root)
            with lock_file(config_root / "instance.lock"):
                config = json.loads(config_path.read_text()) if config_path.exists() else {}
                if not isinstance(config, dict):
                    raise ValueError(f"Expected a JSON object: {config_path}")
                previous_config = dict(config)
                if args.pdf_graphics is not None:
                    config["pdf_graphics"] = args.pdf_graphics
                elif profile == "pi":
                    config.setdefault("pdf_graphics", "sixel")
                if config.get("pdf_graphics", "auto") not in {"auto", "kitty", "sixel", "off"}:
                    raise ValueError(f"Invalid pdf_graphics in {config_path}; correct the saved value.")
                if profile == "pi" and config["pdf_graphics"] in {"sixel", "auto"} and not shutil.which("img2sixel"):
                    raise OSError("img2sixel is missing from PATH (Debian package libsixel-bin). Make the existing executable available, then retry. System packages are not installed automatically.")
                current = root / "current"
                if current.exists() and not current.is_symlink():
                    raise OSError(f"Expected the installer's managed symlink: {current}")
                private_directory(root / "environments")
                candidate = root / "environments" / uuid.uuid4().hex
                candidate.mkdir(mode=0o700)
                atomic_write(candidate / ".melondice-environment", manifest["installation_id"].encode())
                print("Preparing the private application environment. Package downloads occur only during installation/update.")
                subprocess.run([str(base_python), "-I", "-m", "venv", str(candidate)], check=True)
                python = candidate / "bin/python"
                subprocess.run([str(python), "-I", "-m", "pip", "--isolated", "--disable-pip-version-check", "install", "--upgrade", str(source)], check=True)
                subprocess.run([str(python), "-I", "-m", "pip", "--isolated", "--disable-pip-version-check", "check"], check=True)
                settings = {"format": 1, "installation_id": manifest["installation_id"],
                            "profile": profile, "mlterm_fb": str(mlterm)}
                wrapper = (source / "scripts/melondice-launcher.sh").read_text()
                wrapper = wrapper.replace("@PYTHON@", shlex.quote(str(base_python)))
                wrapper = wrapper.replace("@ROOT@", shlex.quote(str(root)))
                wrapper_bytes = wrapper.encode()
                new_digest = hashlib.sha256(wrapper_bytes).hexdigest()
                manifest["launcher_hashes"] = list(dict.fromkeys([new_digest, *manifest.get("launcher_hashes", [])]))[:2]
                atomic_write(root / "bootstrap.py", (source / "scripts/launcher_bootstrap.py").read_bytes())
                atomic_write(root / "launcher.json", json_bytes(settings))
                if config != previous_config:
                    atomic_write(config_path, json_bytes(config))
                for path, content, mode in updates:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    atomic_write(path, content, mode)
                launcher.parent.mkdir(parents=True, exist_ok=True)
                atomic_write(manifest_path, json_bytes(manifest))
                atomic_write(launcher, wrapper_bytes, 0o755)
                link = root / (".current-" + uuid.uuid4().hex)
                try:
                    link.symlink_to(candidate.relative_to(root))
                    os.replace(link, current)
                finally:
                    link.unlink(missing_ok=True)
                activated = True
                # Exclusive installation lock excludes all managed app sessions.
                # Prune only directories carrying this installation's ownership.
                for old in (root / "environments").iterdir():
                    marker = old / ".melondice-environment"
                    if (old != candidate and not old.is_symlink() and old.is_dir()
                            and marker.is_file() and marker.read_text() == manifest["installation_id"]):
                        try:
                            shutil.rmtree(old)
                        except OSError as error:
                            print(f"Installed environment is active; could not remove old owned environment {old}: {error}", file=sys.stderr)
                print(f"Installed {launcher}\nProfile: {profile}; saved PDF graphics: {config.get('pdf_graphics', 'auto')}. Existing explicit preferences are preserved unless --pdf-graphics is given.")
                print("Launch from a new terminal/login with: melondice")
                print('For this shell now (bash/zsh/sh): export PATH="$HOME/.local/bin:$PATH"')
                if args.no_path_setup:
                    print("Shell files were not changed (--no-path-setup). Ensure ~/.local/bin is on PATH.")
                else:
                    print("Managed PATH blocks are idempotent; rerun this installer after copying updated source.")
        return 0
    except subprocess.CalledProcessError as error:
        print(f"Installation failed (command status {error.returncode}). Check Python venv/pip support, network/CA certificates and the package diagnostics above. Debian's python3-venv may be required. PyMuPDF needs an aarch64 wheel or build prerequisites. An existing active environment was not switched.", file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError) as error:
        print(f"Installation failed: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Installation cancelled. Re-run the installer when ready.", file=sys.stderr)
        return 130
    finally:
        if candidate is not None and not activated and candidate.is_dir():
            try:
                # An interrupt can land between replace(current) and setting
                # activated. Never remove the environment actually selected.
                if (candidate.parent.parent / "current").resolve() != candidate.resolve():
                    shutil.rmtree(candidate)
            except OSError as error:
                print(f"Could not remove incomplete owned environment {candidate}: {error}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
