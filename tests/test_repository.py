import subprocess
from pathlib import Path

import pytest

from explain_repo.repository import repository_source


def _git(root: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )


def test_repository_source_clones_refs_and_cleans_up(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init")
    _git(source, "config", "user.name", "Test User")
    _git(source, "config", "user.email", "test@example.com")
    (source / "version.py").write_text("VERSION = 1\n", encoding="utf-8")
    _git(source, "add", "version.py")
    _git(source, "commit", "-m", "version one")
    first_commit = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _git(source, "tag", "v1.0.0", first_commit)
    (source / "version.py").write_text("VERSION = 2\n", encoding="utf-8")
    _git(source, "commit", "-am", "version two")
    _git(source, "branch", "feature")

    refs = [
        (first_commit, "VERSION = 1\n"),
        ("v1.0.0", "VERSION = 1\n"),
        ("feature", "VERSION = 2\n"),
    ]
    for ref, expected_content in refs:
        with repository_source(source.as_uri(), ref) as checkout:
            checkout_path = checkout
            assert (checkout / "version.py").read_text(encoding="utf-8") == expected_content

        assert not checkout_path.exists()


def test_repository_source_rejects_ref_for_local_directory(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="only be used with a Git repository URL"):
        with repository_source(str(tmp_path), "main"):
            pass