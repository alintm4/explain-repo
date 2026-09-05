from pathlib import Path

from explain_repo.graph import build_dependency_graph, classify_node, rank_files
from explain_repo.parser import parse_repository


def _write(root: Path, relative_path: str, content: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_graph_resolves_internal_imports_and_ranks_shared_module(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from . import core\n")
    _write(tmp_path, "pkg/core.py", "from .cycle import loop\nclass Engine: pass\n")
    _write(tmp_path, "pkg/cycle.py", "from . import core\ndef loop(): pass\n")
    _write(tmp_path, "pkg/service.py", "import numpy as np\nfrom pkg.core import Engine\n")
    _write(tmp_path, "runner.py", "from pkg import core\n")

    files = parse_repository(tmp_path)
    graph = build_dependency_graph(files)

    core = Path("pkg/core.py")
    assert set(graph.predecessors(core)) == {
        Path("pkg/__init__.py"),
        Path("pkg/cycle.py"),
        Path("pkg/service.py"),
        Path("runner.py"),
    }
    assert all("numpy" not in path.as_posix() for path in graph)
    assert rank_files(graph, "indegree")[0][0] == core
    assert rank_files(graph, "pagerank")[0][0] == core


def test_repository_scan_ignores_generated_directories(tmp_path: Path) -> None:
    _write(tmp_path, "app.py", "def main(): pass\n")
    _write(tmp_path, "web.tsx", "export function App() { return null; }\n")
    _write(tmp_path, ".venv/ignored.py", "def hidden(): pass\n")
    _write(tmp_path, "node_modules/ignored.py", "def hidden(): pass\n")
    _write(tmp_path, "node_modules/ignored.js", "export function hidden() {}\n")
    _write(tmp_path, "dist/ignored.ts", "export function hidden() {}\n")
    _write(tmp_path, "build/ignored.jsx", "export function Hidden() {}\n")

    assert set(parse_repository(tmp_path)) == {Path("app.py"), Path("web.tsx")}


def test_javascript_imports_resolve_extensions_and_directory_indexes(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/utils/helpers.ts", "export function help() {}\n")
    _write(tmp_path, "src/config/index.js", "module.exports = {};\n")
    _write(
        tmp_path,
        "src/main.ts",
        """import { help } from './utils/helpers';
const config = require('./config');
import React from 'react';
export function main() {}
""",
    )

    files = parse_repository(tmp_path)
    graph = build_dependency_graph(files)

    main = Path("src/main.ts")
    assert [imported.module for imported in files[main].imports] == [
        "src.utils.helpers",
        "src.config.index",
        "react",
    ]
    assert set(graph.successors(main)) == {
        Path("src/utils/helpers.ts"),
        Path("src/config/index.js"),
    }


def test_classify_node_distinguishes_entry_core_and_reexport_shim(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .core import Engine\n")
    _write(tmp_path, "pkg/core.py", "class Engine: pass\n")
    _write(tmp_path, "pkg/service.py", "def serve(): pass\n")
    _write(
        tmp_path,
        "app.py",
        "from pkg.core import Engine\nfrom pkg.service import serve\ndef main(): pass\n",
    )
    _write(tmp_path, "worker.py", "from pkg.core import Engine\ndef work(): pass\n")

    graph = build_dependency_graph(parse_repository(tmp_path))

    assert classify_node(graph, Path("app.py")) == "entry_point"
    assert classify_node(graph, Path("pkg/core.py")) == "core_dependency"
    assert classify_node(graph, Path("pkg/service.py")) == "leaf"
    assert classify_node(graph, Path("pkg/__init__.py")) == "leaf"