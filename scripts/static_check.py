"""Source/metadata audit only. Does not import, launch, or exercise Melon Dice."""
from __future__ import annotations

import ast
import builtins
import json
from pathlib import Path
import symtable
import tomllib

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src" / "melondice"


def main():
    failures = []
    paths = sorted(PACKAGE.glob("*.py"))
    builtin_names = set(dir(builtins)) | {"__file__", "__name__", "__package__", "__spec__"}
    for path in paths:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path), feature_version=(3, 10))
        compile(tree, str(path), "exec")  # Generate a code object; never execute it.
        table = symtable.symtable(source, str(path), "exec")
        bound = {s.get_name() for s in table.get_symbols() if s.is_assigned() or s.is_imported()}

        def globals_in(scope):
            for symbol in scope.get_symbols():
                if symbol.is_global() and symbol.is_referenced() and symbol.get_name() not in bound | builtin_names:
                    failures.append(f"{path.name}: unresolved global {symbol.get_name()}")
            for child in scope.get_children():
                globals_in(child)

        globals_in(table)
        loaded = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [(node.module or "").split(".")[0]]
            else:
                modules = []
            if set(modules) & {"tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6", "gi", "webbrowser"}:
                failures.append(f"{path.name}: forbidden GUI/browser import")
            if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
                name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
                if name in {"bind", "add", "bind_class", "bind_all"} and node.args[0].value in {"c-p", "<Control-p>", "<Control-P>"}:
                    failures.append(f"{path.name}: forbidden explicit Ctrl+P binding")
            if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
                target = PACKAGE.joinpath(*node.module.split("."))
                if not target.with_suffix(".py").is_file() and not (target / "__init__.py").is_file():
                    failures.append(f"{path.name}: missing local import {node.module}")
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.ImportFrom) and node.module == "__future__":
                    continue
                for alias in node.names:
                    name = alias.asname or alias.name.split(".")[0]
                    if name not in loaded:
                        failures.append(f"{path.name}: possibly unused import {name}")
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())
    requirements = [line.strip() for line in (ROOT / "requirements.txt").read_text().splitlines()
                    if line.strip() and not line.startswith("#")]
    if metadata["project"]["dependencies"] != requirements:
        failures.append("Runtime dependencies differ between metadata and requirements.txt")
    target = metadata["project"]["scripts"]["melondice"]
    module, function = target.split(":")
    target_tree = ast.parse((ROOT / "src" / (module.replace(".", "/") + ".py")).read_text())
    if not any(isinstance(n, ast.FunctionDef) and n.name == function for n in target_tree.body):
        failures.append("Launch entry point is not a top-level function")
    config = json.loads((ROOT / "config.example.json").read_text())
    defaults_tree = ast.parse((PACKAGE / "storage.py").read_text())
    defaults = next(node.value for node in defaults_tree.body if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == "DEFAULTS" for target in node.targets))
    if set(config) != {node.value for node in defaults.keys}:
        failures.append("Configuration example fields differ from declared defaults")
    for name in ("README.md", "SPEC.md", "DEVELOPMENT_REPORT.md", "THIRD_PARTY_NOTICES.md", "LICENSE"):
        if not (ROOT / name).is_file():
            failures.append("Required artifact missing: " + name)
    text_files = paths + list((ROOT / "scripts").glob("*.py")) + [
        ROOT / name for name in ("pyproject.toml", "requirements.txt", "config.example.json",
                                "README.md", "SPEC.md", "DEVELOPMENT_REPORT.md", "THIRD_PARTY_NOTICES.md")]
    for path in text_files:
        text = path.read_text(encoding="utf-8")
        if not text.endswith("\n"):
            failures.append(f"{path.name}: missing final newline")
        for number, line in enumerate(text.splitlines(), 1):
            if line.rstrip() != line:
                failures.append(f"{path.name}:{number}: trailing whitespace")
    if failures:
        raise SystemExit("\n".join(failures))
    print(f"Static audit passed: {len(paths)} source modules; Python 3.10 grammar; code-object compilation; "
          "global symbols/local import paths; metadata/dependency consistency; entry point; JSON fields; no GUI imports or Ctrl+P binding; required documents; whitespace.")
    print("No application module was imported or executed. No runtime tests were performed.")


if __name__ == "__main__":
    main()
