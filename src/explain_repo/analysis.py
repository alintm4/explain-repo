"""Evidence-backed repository architecture analysis."""

from __future__ import annotations

import ast
import json
import tomllib
from collections import deque
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import networkx as nx

from .graph import build_dependency_graph, rank_files
from .parser import FileInfo, SUPPORTED_EXTENSIONS, parse_repository


SOURCE_EXTENSIONS = SUPPORTED_EXTENSIONS | {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".kt",
    ".kts",
    ".php",
    ".rb",
    ".rs",
    ".scala",
    ".swift",
}

CATEGORY_PARTS = {
    "test": {"test", "tests", "testing", "spec", "specs", "__tests__"},
    "example": {"example", "examples", "sample", "samples", "playground"},
    "documentation": {"doc", "docs", "documentation"},
    "fixture": {"fixture", "fixtures", "testdata", "test_data"},
    "generated": {"generated", "gen", "build", "dist", "coverage"},
    "vendor": {"vendor", "vendored", "third_party", "third-party", "deps"},
}


@dataclass(frozen=True)
class CoverageSummary:
    total_source_files: int
    supported_source_files: int
    unsupported_source_files: int
    parsed_files: int
    parse_failures: int
    analyzed_percentage: float
    status: str
    unsupported_extensions: tuple[str, ...]


@dataclass(frozen=True)
class ArchitectureAnalysis:
    repository_type: str
    languages: tuple[str, ...]
    coverage: CoverageSummary
    source_categories: dict[str, int]
    packages: tuple[str, ...]
    entry_points: tuple[dict[str, Any], ...]
    architectural_core: tuple[dict[str, Any], ...]
    recommended_reading_order: tuple[dict[str, Any], ...]
    warnings: tuple[str, ...]
    files: dict[Path, FileInfo]
    graph: nx.DiGraph


def classify_source_path(path: Path) -> str:
    """Classify a source path by its architectural role."""
    pure_path = PurePosixPath(path.as_posix())
    parts = {part.lower() for part in pure_path.parts[:-1]}
    filename = pure_path.name.lower()
    if (
        filename.startswith(("test_", "tests_"))
        or ".test." in filename
        or ".spec." in filename
        or filename.endswith(("_test.py", "_tests.py"))
    ):
        return "test"
    if filename.endswith((".min.js", ".min.css")) or filename.startswith("generated_"):
        return "generated"
    for category, names in CATEGORY_PARTS.items():
        if parts & names or any(
            category == "test" and (part.startswith("test") or part.endswith("tests"))
            for part in parts
        ):
            return category
    return "production"


def source_inventory(root: Path) -> list[Path]:
    """Return supported and common unsupported source files below a repository."""
    return sorted(
        (
            path.relative_to(root)
            for path in root.rglob("*")
            if path.is_file()
            and path.suffix.lower() in SOURCE_EXTENSIONS
            and not any(part.startswith(".") for part in path.relative_to(root).parts)
            and not any(
                part in {"node_modules", ".venv", "venv", "env", "__pycache__"}
                for part in path.relative_to(root).parts[:-1]
            )
        ),
        key=Path.as_posix,
    )


def summarize_coverage(root: Path, parsed_files: dict[Path, object]) -> CoverageSummary:
    """Summarize how much source-like content received supported parsing."""
    inventory = source_inventory(root)
    supported = [path for path in inventory if path.suffix.lower() in SUPPORTED_EXTENSIONS]
    parse_failures = sum(
        bool(getattr(info, "syntax_error", None)) and not getattr(info, "syntax_recovered", False)
        for info in parsed_files.values()
    )
    parsed_count = sum(
        not getattr(info, "syntax_error", None) or getattr(info, "syntax_recovered", False)
        for info in parsed_files.values()
    )
    analyzed_percentage = (
        round(100.0 * parsed_count / len(inventory), 1) if inventory else 100.0
    )
    status = "complete"
    if inventory and not supported:
        status = "unsupported"
    elif len(supported) < len(inventory) and analyzed_percentage < 80.0:
        status = "partial"
    elif parse_failures:
        status = "parse_failures"
    return CoverageSummary(
        total_source_files=len(inventory),
        supported_source_files=len(supported),
        unsupported_source_files=len(inventory) - len(supported),
        parsed_files=parsed_count,
        parse_failures=parse_failures,
        analyzed_percentage=analyzed_percentage,
        status=status,
        unsupported_extensions=tuple(
            sorted({path.suffix.lower() for path in inventory if path not in supported})
        ),
    )


def _language(path: Path) -> str:
    if path.suffix == ".py":
        return "Python"
    if path.suffix in {".cts", ".mts", ".ts", ".tsx"}:
        return "TypeScript"
    if path.suffix in {".cjs", ".js", ".jsx", ".mjs"}:
        return "JavaScript"
    common_languages = {
        ".c": "C",
        ".cc": "C++",
        ".cpp": "C++",
        ".cs": "C#",
        ".go": "Go",
        ".java": "Java",
        ".kt": "Kotlin",
        ".kts": "Kotlin",
        ".rb": "Ruby",
        ".rs": "Rust",
        ".swift": "Swift",
    }
    if path.suffix in common_languages:
        return common_languages[path.suffix]
    return path.suffix.removeprefix(".").upper()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _resolve_source_target(root: Path, target: str, files: dict[Path, FileInfo]) -> Path | None:
    target = target.split(":", 1)[0].strip().removeprefix("./")
    base = Path(target.replace(".", "/")) if "/" not in target else Path(target)
    candidates = [
        base,
        base.with_suffix(".py"),
        Path("src") / base.with_suffix(".py"),
        base / "__init__.py",
        Path("src") / base / "__init__.py",
    ]
    for extension in (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"):
        candidates.extend((base.with_suffix(extension), base / f"index{extension}"))
    for candidate in candidates:
        if candidate in files or (root / candidate).is_file() and candidate in files:
            return candidate
    return None


def _flatten_metadata_targets(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for child in value for item in _flatten_metadata_targets(child)]
    if isinstance(value, dict):
        return [item for child in value.values() for item in _flatten_metadata_targets(child)]
    return []


def _metadata_evidence(root: Path, files: dict[Path, FileInfo]) -> tuple[dict[Path, list[str]], set[Path], dict[str, Any]]:
    executable: dict[Path, list[str]] = {}
    public_api: set[Path] = set()
    metadata: dict[str, Any] = {}

    pyproject_path = root / "pyproject.toml"
    if pyproject_path.is_file():
        try:
            metadata["pyproject"] = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            metadata["pyproject"] = {}
        project = metadata["pyproject"].get("project", {})
        for group in ("scripts", "gui-scripts"):
            for target in project.get(group, {}).values():
                resolved = _resolve_source_target(root, str(target), files)
                if resolved:
                    executable.setdefault(resolved, []).append(f"declared in pyproject.toml [project.{group}]")

    for package_path in root.rglob("package.json"):
        if any(part in {"node_modules", "vendor", "vendored"} for part in package_path.parts):
            continue
        package = _load_json(package_path)
        relative_parent = package_path.parent.relative_to(root)
        metadata.setdefault("packages", []).append((relative_parent, package))
        for field in ("bin",):
            for target in _flatten_metadata_targets(package.get(field)):
                resolved = _resolve_source_target(root, (relative_parent / target).as_posix(), files)
                if resolved:
                    executable.setdefault(resolved, []).append(f"declared by package.json {field}")
        for field in ("main", "exports"):
            for target in _flatten_metadata_targets(package.get(field)):
                resolved = _resolve_source_target(root, (relative_parent / target).as_posix(), files)
                if resolved:
                    public_api.add(resolved)

    for path in files:
        if path.name == "__init__.py":
            public_api.add(path)
        if path.name == "__main__.py":
            executable.setdefault(path, []).append("Python __main__.py module")
        if path.suffix == ".py":
            try:
                tree = ast.parse((root / path).read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, SyntaxError):
                continue
            if any(_is_main_guard(node) for node in tree.body):
                executable.setdefault(path, []).append("Python main guard")

    for config_name in ("setup.cfg",):
        config_path = root / config_name
        if not config_path.is_file():
            continue
        lines = config_path.read_text(encoding="utf-8", errors="replace").splitlines()
        in_console_scripts = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("["):
                in_console_scripts = stripped.lower() == "[options.entry_points]"
                continue
            if in_console_scripts and "=" in stripped and "console_scripts" not in stripped:
                resolved = _resolve_source_target(root, stripped.split("=", 1)[1], files)
                if resolved:
                    executable.setdefault(resolved, []).append("declared setup.cfg console script")

    setup_path = root / "setup.py"
    if setup_path.is_file():
        try:
            setup_tree = ast.parse(setup_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, SyntaxError):
            setup_tree = ast.Module(body=[], type_ignores=[])
        for node in ast.walk(setup_tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg != "entry_points":
                    continue
                try:
                    entry_points = ast.literal_eval(keyword.value)
                except (ValueError, TypeError):
                    continue
                if not isinstance(entry_points, dict):
                    continue
                for declaration in entry_points.get("console_scripts", []):
                    if not isinstance(declaration, str) or "=" not in declaration:
                        continue
                    resolved = _resolve_source_target(root, declaration.split("=", 1)[1], files)
                    if resolved:
                        executable.setdefault(resolved, []).append("declared setup.py console script")
    return executable, public_api, metadata


def _is_main_guard(node: ast.stmt) -> bool:
    if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
        return False
    comparison = node.test
    if len(comparison.ops) != 1 or not isinstance(comparison.ops[0], ast.Eq):
        return False
    values = [comparison.left, *comparison.comparators]
    return any(isinstance(value, ast.Name) and value.id == "__name__" for value in values) and any(
        isinstance(value, ast.Constant) and value.value == "__main__" for value in values
    )


def _package_boundaries(root: Path, metadata: dict[str, Any]) -> tuple[str, ...]:
    boundaries: set[str] = set()
    packages = metadata.get("packages", [])
    for parent, _ in packages:
        if parent != Path("."):
            boundaries.add(parent.as_posix())
    for container in ("apps", "packages"):
        directory = root / container
        if directory.is_dir():
            boundaries.update(
                child.relative_to(root).as_posix() for child in directory.iterdir() if child.is_dir()
            )
    if len(boundaries) <= 1:
        return ()
    return tuple(sorted(boundaries))


def _package_for(path: Path, packages: tuple[str, ...]) -> str | None:
    matches = [package for package in packages if path == Path(package) or Path(package) in path.parents]
    return max(matches, key=len) if matches else None


def _repository_type(
    root: Path,
    metadata: dict[str, Any],
    executable: dict[Path, list[str]],
    packages: tuple[str, ...],
) -> str:
    if packages:
        return "monorepo"
    pyproject = metadata.get("pyproject", {}).get("project", {})
    package_values = [package for _, package in metadata.get("packages", [])]
    if executable:
        if pyproject.get("scripts") or any(package.get("bin") for package in package_values):
            return "cli"
        return "application"
    if pyproject or package_values:
        return "library"
    if (root / "apps").is_dir() or (root / "packages").is_dir():
        return "monorepo"
    return "unknown"


def _entry_points(
    graph: nx.DiGraph,
    files: dict[Path, FileInfo],
    declared: dict[Path, list[str]],
    analyzed_categories: set[str],
) -> tuple[dict[str, Any], ...]:
    entries = []
    for path in graph:
        if classify_source_path(path) not in analyzed_categories:
            continue
        evidence = list(declared.get(path, []))
        score = 0.85 if evidence else 0.0
        in_degree = graph.in_degree(path)
        out_degree = graph.out_degree(path)
        if path.stem in {"main", "cli", "server", "app"} and in_degree == 0:
            evidence.append("conventional bootstrap name with no internal importers")
            score += 0.45
        if in_degree == 0 and out_degree:
            evidence.append("root-like production dependency position")
            score += 0.1
        if out_degree:
            evidence.append(f"imports {out_degree} production module{'s' if out_degree != 1 else ''}")
            score += min(0.1, out_degree * 0.025)
        if path.name in {"__init__.py", "index.js", "index.ts", "index.jsx", "index.tsx"} and not declared.get(path):
            evidence.append("package export surface; not treated as execution evidence")
            score -= 0.5
        score = max(0.0, min(score, 1.0))
        if score >= 0.5:
            entries.append(
                {
                    "path": path.as_posix(),
                    "confidence": round(score, 3),
                    "evidence": evidence,
                    "in_degree": in_degree,
                    "out_degree": out_degree,
                }
            )
    return tuple(sorted(entries, key=lambda item: (-item["confidence"], item["path"])))


def _architectural_core(
    graph: nx.DiGraph,
    files: dict[Path, FileInfo],
    analyzed_categories: set[str],
) -> tuple[dict[str, Any], ...]:
    if not graph:
        return ()
    pagerank = dict(rank_files(graph, "pagerank"))
    maximum_rank = max(pagerank.values(), default=1.0)
    maximum_in = max((graph.in_degree(path) for path in graph), default=1) or 1
    maximum_reach = max((len(nx.ancestors(graph, path)) for path in graph), default=1) or 1
    entries = []
    for path, info in files.items():
        if path not in graph or classify_source_path(path) not in analyzed_categories:
            continue
        incoming = graph.in_degree(path)
        if incoming == 0:
            continue
        reach = len(nx.ancestors(graph, path))
        definition_signal = 1.0 if info.classes or info.functions else 0.0
        score = (
            0.45 * pagerank[path] / maximum_rank
            + 0.3 * incoming / maximum_in
            + 0.15 * reach / maximum_reach
            + 0.1 * definition_signal
        )
        evidence = [f"imported by {incoming} production module{'s' if incoming != 1 else ''}"]
        if pagerank[path] >= maximum_rank * 0.75:
            evidence.append("high dependency centrality")
        if reach > incoming:
            evidence.append(f"reachable from {reach} upstream production modules")
        if info.classes or info.functions:
            evidence.append("defines named abstractions")
        entries.append(
            {"path": path.as_posix(), "score": round(min(score, 1.0), 3), "evidence": evidence}
        )
    return tuple(sorted(entries, key=lambda item: (-item["score"], item["path"])))


def _reading_order(
    graph: nx.DiGraph,
    entries: tuple[dict[str, Any], ...],
    core: tuple[dict[str, Any], ...],
    public_api: set[Path],
    analyzed_categories: set[str],
) -> tuple[dict[str, Any], ...]:
    core_scores = {Path(item["path"]): item["score"] for item in core}
    starts = [Path(item["path"]) for item in entries]
    if not starts:
        starts = sorted(public_api, key=Path.as_posix)
    if not starts:
        starts = [Path(item["path"]) for item in core[:3]]
    queue = deque((path, 0) for path in starts if path in graph)
    seen: set[Path] = set()
    reading = []
    while queue:
        path, depth = queue.popleft()
        if path in seen:
            continue
        seen.add(path)
        if classify_source_path(path) not in analyzed_categories:
            continue
        reason = "execution entry point" if depth == 0 and entries else (
            "public package surface" if depth == 0 else f"production dependency at depth {depth}"
        )
        if path in core_scores:
            reason += f"; architectural score {core_scores[path]:.3f}"
        reading.append({"path": path.as_posix(), "reason": reason})
        successors = sorted(
            graph.successors(path),
            key=lambda child: (-core_scores.get(child, 0.0), child.as_posix()),
        )
        queue.extend((child, depth + 1) for child in successors)
    for item in core:
        path = Path(item["path"])
        if path not in seen:
            reading.append({"path": item["path"], "reason": "architecturally important production module"})
            seen.add(path)
    for path in sorted(public_api, key=Path.as_posix):
        if path not in seen and path in graph:
            reading.append({"path": path.as_posix(), "reason": "public package surface"})
    return tuple(reading)


def analyze_repository(
    root: Path, include_categories: tuple[str, ...] = ()
) -> ArchitectureAnalysis:
    """Analyze a repository using separate entry, core, and reading models."""
    files = parse_repository(root)
    coverage = summarize_coverage(root, files)
    categories: dict[str, int] = {}
    for path in source_inventory(root):
        category = classify_source_path(path)
        categories[category] = categories.get(category, 0) + 1
    analyzed_categories = {"production", *include_categories}
    production_files = {
        path: info
        for path, info in files.items()
        if classify_source_path(path) in analyzed_categories
        and (not info.syntax_error or info.syntax_recovered)
    }
    graph = build_dependency_graph(production_files)
    declared, public_api, metadata = _metadata_evidence(root, production_files)
    packages = _package_boundaries(root, metadata)
    entries = _entry_points(graph, production_files, declared, analyzed_categories)
    core = _architectural_core(graph, production_files, analyzed_categories)
    reading = _reading_order(graph, entries, core, public_api, analyzed_categories)
    entries = tuple({**item, "package": _package_for(Path(item["path"]), packages)} for item in entries)
    core = tuple({**item, "package": _package_for(Path(item["path"]), packages)} for item in core)
    reading = tuple({**item, "package": _package_for(Path(item["path"]), packages)} for item in reading)
    warnings = []
    if coverage.status in {"partial", "unsupported"}:
        warnings.append(
            f"Partial/unsupported language coverage: analyzed {coverage.analyzed_percentage:.1f}% of source files"
        )
    if coverage.parse_failures:
        warnings.append(f"{coverage.parse_failures} supported source file(s) failed parsing")
    if packages:
        warnings.append("Monorepo packages are ranked within a production-only repository graph")
    return ArchitectureAnalysis(
        repository_type=_repository_type(root, metadata, declared, packages),
        languages=tuple(sorted({_language(path) for path in source_inventory(root)})),
        coverage=coverage,
        source_categories=dict(sorted(categories.items())),
        packages=packages,
        entry_points=entries,
        architectural_core=core,
        recommended_reading_order=reading,
        warnings=tuple(warnings),
        files=files,
        graph=graph,
    )