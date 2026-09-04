"""Command-line interface for explain-repo."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from . import __version__
from .graph import build_dependency_graph, rank_files
from .parser import FileInfo, parse_repository


def _import_label(info: FileInfo) -> list[str]:
    labels = []
    for imported in info.imports:
        prefix = "." * imported.level + (imported.module or "")
        labels.append(prefix or ", ".join(imported.names))
    return labels


def _build_report(
    root: Path, top: int, rank_method: str, include_llm: bool
) -> dict[str, Any]:
    files = parse_repository(root)
    graph = build_dependency_graph(files)
    ranked = rank_files(graph, rank_method)[:top]
    entries = []
    for path, score in ranked:
        info = files[path]
        imported_by = sorted(source.as_posix() for source in graph.predecessors(path))
        dependencies = sorted(target.as_posix() for target in graph.successors(path))
        entry: dict[str, Any] = {
            "path": path.as_posix(),
            "score": score,
            "why_central": f"imported by {len(imported_by)} other file{'s' if len(imported_by) != 1 else ''}",
            "imported_by": imported_by,
            "dependencies": dependencies,
            "imports": _import_label(info),
            "functions": info.functions,
            "classes": [
                {"name": name, "methods": info.class_methods.get(name, [])}
                for name in info.classes
            ],
        }
        if include_llm:
            from .llm import describe_file

            entry["description"] = describe_file(info)
        entries.append(entry)
    return {
        "repository": str(root),
        "rank_method": rank_method,
        "python_file_count": len(files),
        "syntax_errors": [
            {"path": path.as_posix(), "error": info.syntax_error}
            for path, info in files.items()
            if info.syntax_error
        ],
        "reading_order": entries,
    }


def _render_text(report: dict[str, Any], console: Console) -> None:
    console.print("[bold]Suggested Reading Order[/bold]")
    reading_table = Table(show_header=True, header_style="bold cyan")
    reading_table.add_column("#", justify="right")
    reading_table.add_column("File")
    reading_table.add_column("Why central")
    reading_table.add_column("Dependencies")
    for index, entry in enumerate(report["reading_order"], start=1):
        reading_table.add_row(
            str(index),
            entry["path"],
            entry["why_central"],
            ", ".join(entry["dependencies"]) or "None",
        )
        if entry.get("description"):
            reading_table.add_row("", "[dim]Description[/dim]", entry["description"], "")
    console.print(reading_table)

    console.print("\n[bold]Core Abstractions[/bold]")
    abstraction_table = Table(show_header=True, header_style="bold cyan")
    abstraction_table.add_column("File")
    abstraction_table.add_column("Classes")
    abstraction_table.add_column("Functions")
    for entry in report["reading_order"]:
        classes = []
        for class_info in entry["classes"]:
            methods = ", ".join(class_info["methods"])
            classes.append(f"{class_info['name']} ({methods})" if methods else class_info["name"])
        abstraction_table.add_row(
            entry["path"],
            "\n".join(classes) or "None",
            ", ".join(entry["functions"]) or "None",
        )
    console.print(abstraction_table)


@click.command()
@click.version_option(version=__version__, prog_name="explain-repo")
@click.argument(
    "path",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
)
@click.option("--top", type=click.IntRange(min=1), default=10, show_default=True)
@click.option("--json", "as_json", is_flag=True, help="Output structured JSON.")
@click.option(
    "--rank-method",
    type=click.Choice(["indegree", "pagerank"]),
    default="pagerank",
    show_default=True,
)
@click.option("--llm", is_flag=True, help="Add Anthropic descriptions from extracted structure.")
def main(path: Path, top: int, as_json: bool, rank_method: str, llm: bool) -> None:
    """Analyze the Python repository at PATH and suggest a reading order."""
    root = path.resolve()
    try:
        report = _build_report(root, top, rank_method, llm)
    except RuntimeError as error:
        raise click.ClickException(str(error)) from error
    except Exception as error:
        if llm:
            raise click.ClickException(f"LLM request failed: {error}") from error
        raise

    for syntax_error in report["syntax_errors"]:
        click.echo(
            f"Warning: skipped {syntax_error['path']}: {syntax_error['error']}",
            err=True,
        )
    if as_json:
        click.echo(json.dumps(report, indent=2))
    else:
        _render_text(report, Console())


if __name__ == "__main__":
    main()