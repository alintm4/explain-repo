"""Resolve local paths and remote Git repositories for analysis."""

from __future__ import annotations

import subprocess
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator


def _is_git_url(source: str) -> bool:
    return source.startswith(("https://", "http://", "ssh://", "git@", "file://"))


def _run_git(arguments: list[str]) -> None:
    try:
        subprocess.run(
            ["git", *arguments],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        raise RuntimeError("Git is required to analyze a repository URL") from error
    except subprocess.CalledProcessError as error:
        message = error.stderr.strip() or error.stdout.strip() or "unknown Git error"
        raise RuntimeError(f"Git operation failed: {message}") from error


@contextmanager
def repository_source(source: str, ref: str | None = None) -> Iterator[Path]:
    """Yield a local repository path, cloning remote sources temporarily."""
    local_path = Path(source).expanduser()
    if local_path.exists():
        if not local_path.is_dir():
            raise RuntimeError(f"Repository path is not a directory: {source}")
        if ref:
            raise RuntimeError("--ref can only be used with a Git repository URL")
        yield local_path.resolve()
        return

    if not _is_git_url(source):
        raise RuntimeError(f"Repository path does not exist: {source}")

    with TemporaryDirectory(prefix="explain-repo-") as temporary_directory:
        checkout = Path(temporary_directory) / "repository"
        _run_git(["clone", "--filter=blob:none", "--no-checkout", source, str(checkout)])
        _run_git(["-C", str(checkout), "checkout", ref or "HEAD"])
        yield checkout