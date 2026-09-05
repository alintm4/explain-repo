"""Parse supported source files into lightweight structural metadata."""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter import Language, Node, Parser, Query, QueryCursor
import tree_sitter_javascript
import tree_sitter_typescript


@dataclass(frozen=True)
class ImportInfo:
    """An import encountered in a supported source file."""

    module: str | None
    names: tuple[str, ...]
    level: int = 0
    aliases: tuple[tuple[str, str | None], ...] = ()


@dataclass
class FileInfo:
    """Structural information extracted from one source file."""

    path: Path
    imports: list[ImportInfo] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    class_methods: dict[str, list[str]] = field(default_factory=dict)
    syntax_error: str | None = None
    syntax_recovered: bool = False


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

PYTHON_EXTENSIONS = {".py"}
JAVASCRIPT_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx"}
SUPPORTED_EXTENSIONS = PYTHON_EXTENSIONS | JAVASCRIPT_EXTENSIONS

JAVASCRIPT_QUERY = """
(import_statement
    source: (string) @import.source)

(call_expression
    function: (identifier) @require.function
    arguments: (arguments (string) @require.source))

(export_statement
    declaration: (function_declaration
        name: (identifier) @function.name))

(export_statement
    declaration: (generator_function_declaration
        name: (identifier) @function.name))

(export_statement
    declaration: (class_declaration
        name: (identifier) @class.name) @class.declaration)

(export_statement
    declaration: (lexical_declaration
        (variable_declarator
            name: (identifier) @function.name
            value: [(arrow_function) (function_expression)])))
"""

TYPESCRIPT_QUERY = JAVASCRIPT_QUERY.replace(
    "name: (identifier) @class.name",
    "name: (type_identifier) @class.name",
)


def find_source_files(root: Path) -> list[Path]:
    """Find supported files while pruning common generated directories."""
    files: list[Path] = []
    for directory, directories, filenames in os.walk(root):
        directories[:] = sorted(
            name
            for name in directories
            if name not in IGNORED_DIRECTORIES and not name.startswith(".")
        )
        files.extend(
            Path(directory) / name
            for name in sorted(filenames)
            if Path(name).suffix.lower() in SUPPORTED_EXTENSIONS
        )
    return files


def find_python_files(root: Path) -> list[Path]:
    """Find Python files below root for backwards compatibility."""
    return [path for path in find_source_files(root) if path.suffix == ".py"]


def parse_repository(root: Path) -> dict[Path, FileInfo]:
    """Parse all supported files below root, keyed by paths relative to root."""
    return {
        path.relative_to(root): parse_file(path, root)
        for path in find_source_files(root)
    }


def parse_file(path: Path, root: Path | None = None) -> FileInfo:
    """Dispatch one source file to its language-specific parser."""
    extension = path.suffix.lower()
    if extension in PYTHON_EXTENSIONS:
        return _parse_python_file(path)
    if extension in JAVASCRIPT_EXTENSIONS:
        return _parse_javascript_file(path, root or path.parent)
    raise ValueError(f"Unsupported source file extension: {extension}")


def _parse_python_file(path: Path) -> FileInfo:
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


def _javascript_language(extension: str) -> Language:
    if extension == ".ts":
        return Language(tree_sitter_typescript.language_typescript())
    if extension == ".tsx":
        return Language(tree_sitter_typescript.language_tsx())
    return Language(tree_sitter_javascript.language())


def _node_text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8")


def _string_value(node: Node, source: bytes) -> str:
    value = _node_text(node, source)
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _extension_order(importer: Path) -> tuple[str, ...]:
    if importer.suffix in {".ts", ".tsx"}:
        return ".ts", ".tsx", ".js", ".jsx"
    return ".js", ".jsx", ".ts", ".tsx"


def _resolve_javascript_import(
    importer: Path, root: Path, specifier: str
) -> Path | None:
    if not specifier.startswith("."):
        return None

    base = importer.parent / specifier
    candidates = [base]
    candidates.extend(base.with_suffix(extension) for extension in _extension_order(importer))
    candidates.extend(base / f"index{extension}" for extension in _extension_order(importer))
    root = root.resolve()
    for candidate in candidates:
        if not candidate.is_file():
            continue
        resolved = candidate.resolve()
        if resolved.is_relative_to(root) and resolved.suffix in JAVASCRIPT_EXTENSIONS:
            return resolved
    return None


def _javascript_import_info(
    importer: Path, root: Path, specifier: str
) -> ImportInfo:
    target = _resolve_javascript_import(importer, root, specifier)
    if target is None:
        return ImportInfo(module=specifier, names=())
    relative_target = target.relative_to(root.resolve())
    module = ".".join(relative_target.with_suffix("").parts)
    return ImportInfo(module=module, names=())


def _class_methods(class_node: Node, source: bytes) -> list[str]:
    body = class_node.child_by_field_name("body")
    if body is None:
        return []
    methods = []
    for child in body.named_children:
        if child.type != "method_definition":
            continue
        name = child.child_by_field_name("name")
        if name is not None:
            methods.append(_node_text(name, source))
    return methods


def _parse_javascript_file(path: Path, root: Path) -> FileInfo:
    """Parse JavaScript or TypeScript structure with tree-sitter."""
    info = FileInfo(path=path)
    try:
        source = path.read_text(encoding="utf-8").encode("utf-8")
        language = _javascript_language(path.suffix.lower())
        tree = Parser(language).parse(source)
    except UnicodeDecodeError as error:
        info.syntax_error = str(error)
        return info

    if tree.root_node.has_error:
        info.syntax_error = f"syntax error in {path}"
        info.syntax_recovered = True

    query_source = (
        TYPESCRIPT_QUERY
        if path.suffix.lower() in {".ts", ".tsx"}
        else JAVASCRIPT_QUERY
    )
    query = Query(language, query_source)
    for _, captures in QueryCursor(query).matches(tree.root_node):
        import_nodes = captures.get("import.source", [])
        require_nodes = captures.get("require.source", [])
        require_functions = captures.get("require.function", [])
        if require_functions and _node_text(require_functions[0], source) != "require":
            require_nodes = []
        for node in [*import_nodes, *require_nodes]:
            imported = _javascript_import_info(path, root, _string_value(node, source))
            info.imports.append(imported)

        for node in captures.get("function.name", []):
            info.functions.append(_node_text(node, source))

        class_names = captures.get("class.name", [])
        class_nodes = captures.get("class.declaration", [])
        if class_names and class_nodes:
            class_name = _node_text(class_names[0], source)
            info.classes.append(class_name)
            info.class_methods[class_name] = _class_methods(class_nodes[0], source)
    return info