"""Parse Python files into lightweight structural metadata."""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ImportInfo:
    """An import encountered in a Python source file."""

    module: str | None
    names: tuple[str, ...]
    level: int = 0
    aliases: tuple[tuple[str, str | None], ...] = ()


@dataclass
class FileInfo:
    """Structural information extracted from one Python file."""

    path: Path
    imports: list[ImportInfo] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    class_methods: dict[str, list[str]] = field(default_factory=dict)
    syntax_error: str | None = None


IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "env",
    "node_modules",
    "venv",
}


def find_python_files(root: Path) -> list[Path]:
    """Find Python files under root while pruning common generated directories."""
    files: list[Path] = []
    for directory, directories, filenames in os.walk(root):
        directories[:] = sorted(
            name
            for name in directories
            if name not in IGNORED_DIRECTORIES and not name.startswith(".")
        )
        files.extend(
            Path(directory) / name for name in sorted(filenames) if name.endswith(".py")
        )
    return files


def parse_repository(root: Path) -> dict[Path, FileInfo]:
    """Parse all Python files below root, keyed by paths relative to root."""
    return {path.relative_to(root): parse_file(path) for path in find_python_files(root)}


def parse_file(path: Path) -> FileInfo:
    """Parse one Python file without raising for invalid syntax."""
    info = FileInfo(path=path)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as error:
        info.syntax_error = str(error)
        return info

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            info.functions.append(node.name)
        elif isinstance(node, ast.ClassDef):
            info.classes.append(node.name)
            info.class_methods[node.name] = [
                child.name
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
        elif isinstance(node, ast.Import):
            info.imports.append(
                ImportInfo(
                    module=None,
                    names=tuple(alias.name for alias in node.names),
                    aliases=tuple((alias.name, alias.asname) for alias in node.names),
                )
            )
        elif isinstance(node, ast.ImportFrom):
            info.imports.append(
                ImportInfo(
                    module=node.module,
                    names=tuple(alias.name for alias in node.names),
                    level=node.level,
                    aliases=tuple((alias.name, alias.asname) for alias in node.names),
                )
            )
    return info