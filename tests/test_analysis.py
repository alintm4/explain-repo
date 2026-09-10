from pathlib import Path

from explain_repo.analysis import (
    analyze_repository,
    classify_source_path,
    source_inventory,
    summarize_coverage,
)
from explain_repo.parser import parse_repository


def _write(root: Path, relative_path: str, content: str = "") -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_source_categories_and_partial_language_coverage(tmp_path: Path) -> None:
    _write(tmp_path, "src/app.py", "def main(): pass\n")
    _write(tmp_path, "tests/test_app.py", "from src import app\n")
    _write(tmp_path, "examples/demo.ts", "export function demo() {}\n")
    _write(tmp_path, "vendor/runtime.go", "package runtime\n")
    _write(tmp_path, "engine/main.rs", "fn main() {}\n")

    assert classify_source_path(Path("src/app.py")) == "production"
    assert classify_source_path(Path("tests/test_app.py")) == "test"
    assert classify_source_path(Path("examples/demo.ts")) == "example"
    assert classify_source_path(Path("vendor/runtime.go")) == "vendor"
    assert len(source_inventory(tmp_path)) == 5

    coverage = summarize_coverage(tmp_path, parse_repository(tmp_path))
    assert coverage.total_source_files == 5
    assert coverage.supported_source_files == 3
    assert coverage.unsupported_source_files == 2
    assert coverage.analyzed_percentage == 60.0
    assert coverage.status == "partial"
    assert coverage.unsupported_extensions == (".go", ".rs")


def test_source_category_filename_and_directory_variants() -> None:
    assert classify_source_path(Path("src/widget_test.py")) == "test"
    assert classify_source_path(Path("integration_tests/widget.py")) == "test"
    assert classify_source_path(Path("src/widget.spec.ts")) == "test"
    assert classify_source_path(Path("assets/bundle.min.js")) == "generated"


def test_declared_and_thin_python_entries_are_detected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "pyproject.toml",
        '[project]\nname = "demo"\nversion = "1"\n[project.scripts]\ndemo = "demo.cli:main"\n',
    )
    _write(tmp_path, "src/demo/cli.py", "from .service import run\ndef main(): run()\n")
    _write(tmp_path, "src/demo/service.py", "def run(): pass\n")

    analysis = analyze_repository(tmp_path)

    assert analysis.repository_type == "cli"
    assert analysis.entry_points[0]["path"] == "src/demo/cli.py"
    assert "declared in pyproject.toml" in analysis.entry_points[0]["evidence"][0]
    assert analysis.recommended_reading_order[0]["path"] == "src/demo/cli.py"


def test_main_guard_is_strong_entry_evidence(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "runner.py",
        'from service import run\nif __name__ == "__main__":\n    run()\n',
    )
    _write(tmp_path, "service.py", "def run(): pass\n")

    analysis = analyze_repository(tmp_path)

    assert analysis.entry_points[0]["path"] == "runner.py"
    assert "Python main guard" in analysis.entry_points[0]["evidence"]


def test_dunder_main_is_strong_entry_evidence(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__main__.py", "from .cli import main\n")
    _write(tmp_path, "pkg/cli.py", "def main(): pass\n")

    analysis = analyze_repository(tmp_path)

    assert analysis.entry_points[0]["path"] == "pkg/__main__.py"
    assert "Python __main__.py module" in analysis.entry_points[0]["evidence"]


def test_legacy_console_script_metadata_is_resolved(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "setup.py",
        "from setuptools import setup\nsetup(entry_points={'console_scripts': ['demo = pkg.cli:main']})\n",
    )
    _write(tmp_path, "pkg/cli.py", "def main(): pass\n")

    analysis = analyze_repository(tmp_path)

    assert analysis.entry_points[0]["path"] == "pkg/cli.py"
    assert "setup.py console script" in analysis.entry_points[0]["evidence"][0]


def test_setup_cfg_console_script_is_resolved(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "setup.cfg",
        "[options.entry_points]\nconsole_scripts =\n    demo = pkg.cli:main\n",
    )
    _write(tmp_path, "pkg/cli.py", "def main(): pass\n")

    analysis = analyze_repository(tmp_path)

    assert analysis.entry_points[0]["path"] == "pkg/cli.py"
    assert "setup.cfg console script" in analysis.entry_points[0]["evidence"][0]


def test_reexport_config_and_tests_are_not_execution_entries(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .api import Client\nfrom .model import Result\n")
    _write(tmp_path, "pkg/api.py", "from .model import Result\nclass Client: pass\n")
    _write(tmp_path, "pkg/model.py", "class Result: pass\n")
    _write(tmp_path, "settings.py", "from pkg.api import Client\nfrom pkg.model import Result\n")
    _write(tmp_path, "tests/main.py", "from pkg.api import Client\nfrom pkg.model import Result\n")

    analysis = analyze_repository(tmp_path)

    assert analysis.entry_points == ()
    assert "tests/main.py" not in analysis.graph
    assert analysis.source_categories["test"] == 1
    assert analysis.architectural_core[0]["path"] == "pkg/model.py"


def test_package_json_bin_and_monorepo_boundaries(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "package.json",
        '{"private":true,"workspaces":["apps/*","packages/*"]}',
    )
    _write(tmp_path, "apps/cli/package.json", '{"bin":{"demo":"./src/cli.ts"}}')
    _write(tmp_path, "apps/cli/src/cli.ts", "import '../../../packages/core/src/index';\n")
    _write(tmp_path, "packages/core/package.json", '{"main":"./src/index.ts"}')
    _write(tmp_path, "packages/core/src/index.ts", "export function run() {}\n")

    analysis = analyze_repository(tmp_path)

    assert analysis.repository_type == "monorepo"
    assert analysis.packages == ("apps/cli", "packages/core")
    assert analysis.entry_points[0]["path"] == "apps/cli/src/cli.ts"
    assert "package.json bin" in analysis.entry_points[0]["evidence"][0]
    assert analysis.entry_points[0]["package"] == "apps/cli"


def test_parse_failures_are_excluded_from_architecture(tmp_path: Path) -> None:
    _write(tmp_path, "broken.py", "def nope(:\n")
    _write(tmp_path, "a.py", "from broken import value\n")
    _write(tmp_path, "b.py", "from broken import value\n")

    analysis = analyze_repository(tmp_path)

    assert analysis.coverage.parse_failures == 1
    assert Path("broken.py") not in analysis.graph
    assert analysis.warnings == ("1 supported source file(s) failed parsing",)


def test_nonproduction_sources_require_explicit_opt_in(tmp_path: Path) -> None:
    _write(tmp_path, "src/core.py", "def run(): pass\n")
    _write(tmp_path, "tests/main.py", "from src.core import run\n")

    default = analyze_repository(tmp_path)
    with_tests = analyze_repository(tmp_path, ("test",))

    assert Path("tests/main.py") not in default.graph
    assert Path("tests/main.py") in with_tests.graph
    assert with_tests.entry_points[0]["path"] == "tests/main.py"


def test_package_main_is_a_library_reading_surface_not_execution(tmp_path: Path) -> None:
    _write(tmp_path, "package.json", '{"name":"client","main":"./src/index.js","exports":"./src/index.js"}')
    _write(tmp_path, "src/index.js", "import './client.js';\nexport function create() {}\n")
    _write(tmp_path, "src/client.js", "export class Client {}\n")

    analysis = analyze_repository(tmp_path)

    assert analysis.repository_type == "library"
    assert analysis.entry_points == ()
    assert analysis.recommended_reading_order[0]["path"] == "src/index.js"


def test_unrelated_tests_do_not_change_production_architecture(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", "from service import run\n")
    _write(tmp_path, "service.py", "def run(): pass\n")
    before = analyze_repository(tmp_path)

    _write(tmp_path, "tests/test_everything.py", "from main import main\nfrom service import run\n")
    _write(tmp_path, "fixtures/generated_test.py", "from service import run\n")
    after = analyze_repository(tmp_path)

    assert after.entry_points == before.entry_points
    assert after.architectural_core == before.architectural_core
    assert after.recommended_reading_order == before.recommended_reading_order


def test_mixed_repository_reports_partial_coverage(tmp_path: Path) -> None:
    _write(tmp_path, "web/app.ts", "export function App() {}\n")
    for index in range(4):
        _write(tmp_path, f"server/module{index}.go", "package server\n")

    analysis = analyze_repository(tmp_path)

    assert analysis.coverage.status == "partial"
    assert analysis.coverage.analyzed_percentage == 20.0
    assert analysis.languages == ("Go", "TypeScript")
    assert "Partial/unsupported language coverage" in analysis.warnings[0]