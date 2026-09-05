"""Build and rank a file-level Python dependency graph."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path, PurePosixPath

import networkx as nx

from .parser import FileInfo, ImportInfo


DEGREE_DOMINANCE_RATIO = 2.0
MIN_SIGNAL_DEGREE = 2


def _module_name(path: Path) -> str:
    pure_path = PurePosixPath(path.as_posix())
    if pure_path.name == "__init__.py":
        return ".".join(pure_path.parent.parts)
    return ".".join(pure_path.with_suffix("").parts)


def _module_index(paths: Iterable[Path]) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for path in paths:
        module = _module_name(path)
        if module:
            index[module] = path
            if module.startswith("src."):
                index[module.removeprefix("src.")] = path
        elif path.name == "__init__.py":
            index["__root__"] = path
    return index


def _package_parts(importer: Path) -> list[str]:
    module_parts = _module_name(importer).split(".") if _module_name(importer) else []
    if importer.name != "__init__.py":
        module_parts = module_parts[:-1]
    return module_parts


def _import_candidates(importer: Path, imported: ImportInfo) -> list[str]:
    if imported.level:
        package = _package_parts(importer)
        keep = max(0, len(package) - imported.level + 1)
        base_parts = package[:keep]
        if imported.module:
            base_parts.extend(imported.module.split("."))
        base = ".".join(base_parts)
        if imported.module:
            return [*(f"{base}.{name}" for name in imported.names), base]
        return [".".join([*base_parts, name]) for name in imported.names]

    if imported.module:
        return [
            *(f"{imported.module}.{name}" for name in imported.names),
            imported.module,
        ]
    return list(imported.names)


def resolve_import(
    importer: Path, imported: ImportInfo, module_index: dict[str, Path]
) -> set[Path]:
    """Resolve an import to files indexed inside the analyzed repository."""
    resolved: set[Path] = set()
    for candidate in _import_candidates(importer, imported):
        if candidate in module_index:
            resolved.add(module_index[candidate])
            continue

        parts = candidate.split(".")
        while len(parts) > 1:
            parts.pop()
            parent = ".".join(parts)
            if parent in module_index:
                resolved.add(module_index[parent])
                break
    return resolved


def build_dependency_graph(files: dict[Path, FileInfo]) -> nx.DiGraph:
    """Build a graph whose edges point from importers to imported files."""
    graph = nx.DiGraph()
    graph.add_nodes_from(files)
    index = _module_index(files)
    for path, info in files.items():
        for imported in info.imports:
            for dependency in resolve_import(path, imported, index):
                if dependency != path:
                    graph.add_edge(path, dependency)
    return graph


def classify_node(graph: nx.DiGraph, node: Path) -> str:
    """Classify a file by whether incoming or outgoing imports dominate.

    Adding one to each degree avoids division by zero. A 2:1 threshold requires
    one direction to be meaningfully stronger, and requiring at least two edges
    prevents a one-import package shim from being treated as an entry point.
    """
    in_degree = graph.in_degree(node)
    out_degree = graph.out_degree(node)
    outgoing_ratio = (out_degree + 1) / (in_degree + 1)
    incoming_ratio = (in_degree + 1) / (out_degree + 1)

    if (
        out_degree >= MIN_SIGNAL_DEGREE
        and outgoing_ratio >= DEGREE_DOMINANCE_RATIO
    ):
        return "entry_point"
    if in_degree >= MIN_SIGNAL_DEGREE and incoming_ratio >= DEGREE_DOMINANCE_RATIO:
        return "core_dependency"
    return "leaf"


def _pagerank(graph: nx.DiGraph, damping: float = 0.85) -> dict[Path, float]:
    if not graph:
        return {}
    node_count = len(graph)
    scores = {node: 1.0 / node_count for node in graph}
    base_score = (1.0 - damping) / node_count
    for _ in range(100):
        dangling_score = sum(scores[node] for node in graph if graph.out_degree(node) == 0)
        updated = {}
        for node in graph:
            inbound_score = sum(
                scores[source] / graph.out_degree(source)
                for source in graph.predecessors(node)
            )
            updated[node] = base_score + damping * (
                inbound_score + dangling_score / node_count
            )
        if sum(abs(updated[node] - scores[node]) for node in graph) < node_count * 1e-6:
            return updated
        scores = updated
    return scores


def rank_files(graph: nx.DiGraph, method: str = "pagerank") -> list[tuple[Path, float]]:
    """Rank files by PageRank or in-degree centrality."""
    if method == "pagerank":
        scores = _pagerank(graph)
    elif method == "indegree":
        scores = nx.in_degree_centrality(graph) if len(graph) > 1 else {node: 0.0 for node in graph}
    else:
        raise ValueError(f"Unsupported rank method: {method}")
    return sorted(scores.items(), key=lambda item: (-item[1], item[0].as_posix()))