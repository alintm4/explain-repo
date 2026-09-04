import json
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

from click.testing import CliRunner

from explain_repo.cli import main


def _make_repo(root: Path) -> None:
    (root / "core.py").write_text("class Engine:\n    def run(self): pass\n", encoding="utf-8")
    (root / "app.py").write_text("from core import Engine\ndef main(): pass\n", encoding="utf-8")


def test_cli_reports_package_version() -> None:
    result = CliRunner().invoke(main, ["--version"])

    assert result.exit_code == 0
    assert result.output == "explain-repo, version 0.2.0\n"


def test_cli_renders_expected_sections(tmp_path: Path) -> None:
    _make_repo(tmp_path)

    result = CliRunner().invoke(main, [str(tmp_path), "--top", "1"])

    assert result.exit_code == 0
    assert "Suggested Reading Order" in result.output
    assert "Core Abstractions" in result.output
    assert "core.py" in result.output
    assert "Engine" in result.output


def test_cli_json_is_structured_and_honors_rank_method(tmp_path: Path) -> None:
    _make_repo(tmp_path)

    result = CliRunner().invoke(
        main, [str(tmp_path), "--json", "--rank-method", "indegree"]
    )

    assert result.exit_code == 0
    report = json.loads(result.output)
    assert report["rank_method"] == "indegree"
    assert report["reading_order"][0]["path"] == "core.py"
    assert report["reading_order"][0]["classes"] == [
        {"name": "Engine", "methods": ["run"]}
    ]


def test_cli_uses_selected_llm_provider(tmp_path: Path) -> None:
    _make_repo(tmp_path)

    with patch(
        "explain_repo.llm.describe_file", return_value="Defines the core engine."
    ) as describe_file:
        result = CliRunner().invoke(
            main,
            [
                str(tmp_path),
                "--json",
                "--top",
                "1",
                "--llm",
                "--llm-provider",
                "ollama",
            ],
        )

    assert result.exit_code == 0
    assert json.loads(result.output)["reading_order"][0]["description"] == (
        "Defines the core engine."
    )
    assert describe_file.call_args.args[1] == "ollama"


def test_cli_analyzes_git_url_at_ref(tmp_path: Path) -> None:
    _make_repo(tmp_path)

    @contextmanager
    def cloned_source(source: str, ref: str | None) -> Iterator[Path]:
        assert source == "https://github.com/example/project.git"
        assert ref == "v1.2.3"
        yield tmp_path

    with patch("explain_repo.cli.repository_source", side_effect=cloned_source):
        result = CliRunner().invoke(
            main,
            [
                "https://github.com/example/project.git",
                "--ref",
                "v1.2.3",
                "--json",
            ],
        )

    assert result.exit_code == 0
    assert json.loads(result.output)["repository"] == (
        "https://github.com/example/project.git"
    )


def test_cli_warns_and_continues_for_syntax_errors(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    (tmp_path / "broken.py").write_text("def nope(:\n", encoding="utf-8")

    result = CliRunner().invoke(main, [str(tmp_path), "--json"])

    assert result.exit_code == 0
    assert "Warning: skipped broken.py" in result.stderr
    assert len(json.loads(result.stdout)["syntax_errors"]) == 1


def test_cli_rejects_non_directory(tmp_path: Path) -> None:
    source = tmp_path / "file.py"
    source.write_text("pass\n", encoding="utf-8")

    result = CliRunner().invoke(main, [str(source)])

    assert result.exit_code != 0
    assert "not a directory" in result.output