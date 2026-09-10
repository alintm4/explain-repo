"""Command-line interface for explain-repo."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from . import __version__
from .analysis import analyze_repository
from .graph import rank_files
from .parser import FileInfo
from .repository import repository_source


def _import_label(info: FileInfo) -> list[str]:
    labels = []
    for imported in info.imports:
        prefix = "." * imported.level + (imported.module or "")
        labels.append(prefix or ", ".join(imported.names))
    return labels


def _build_report(
    root: Path,
    top: int,
    rank_method: str,
    include_llm: bool,
    llm_provider: str = "ollama",
    repository_name: str | None = None,
    include_categories: tuple[str, ...] = (),
) -> dict[str, Any]:
    analysis = analyze_repository(root, include_categories)
    files = analysis.files
    graph = analysis.graph
    dependency_scores = dict(rank_files(graph, rank_method))

    def enrich(entry: dict[str, Any], classification: str) -> dict[str, Any]:
        path = Path(entry["path"])
        info = files[path]
        imported_by = sorted(source.as_posix() for source in graph.predecessors(path))
        dependencies = sorted(target.as_posix() for target in graph.successors(path))
        return {
            **entry,
            "score": entry.get("score", dependency_scores.get(path, 0.0)),
            "classification": classification,
            "in_degree": len(imported_by),
            "out_degree": len(dependencies),
            "imported_by": imported_by,
            "dependencies": dependencies,
            "imports": _import_label(info),
            "functions": info.functions,
            "classes": [
                {"name": name, "methods": info.class_methods.get(name, [])}
                for name in info.classes
            ],
        }

    entry_points = [enrich(dict(entry), "entry_point") for entry in analysis.entry_points[:top]]
    core_dependencies = [
        enrich(dict(entry), "core_dependency")
        for entry in analysis.architectural_core[:top]
    ]
    if include_llm:
        for entry in [*entry_points, *core_dependencies]:
            from .llm import describe_file

            entry["description"] = describe_file(
                files[Path(entry["path"])], llm_provider
            )
    package_results = [
        {
            "path": package,
            "entry_points": [entry for entry in entry_points if entry.get("package") == package],
            "architectural_core": [entry for entry in core_dependencies if entry.get("package") == package],
            "recommended_reading_order": [
                item
                for item in analysis.recommended_reading_order
                if item.get("package") == package
            ][:top],
        }
        for package in analysis.packages
    ]
    return {
        "repository": repository_name or str(root),
        "repository_type": analysis.repository_type,
        "languages": analysis.languages,
        "coverage": {
            "total_source_files": analysis.coverage.total_source_files,
            "supported_source_files": analysis.coverage.supported_source_files,
            "unsupported_source_files": analysis.coverage.unsupported_source_files,
            "parsed_files": analysis.coverage.parsed_files,
            "parse_failures": analysis.coverage.parse_failures,
            "analyzed_percentage": analysis.coverage.analyzed_percentage,
            "status": analysis.coverage.status,
            "unsupported_extensions": analysis.coverage.unsupported_extensions,
        },
        "source_categories": analysis.source_categories,
        "packages": analysis.packages,
        "package_results": package_results,
        "included_source_categories": ("production", *include_categories),
        "rank_method": rank_method,
        # Retained for 0.4.x JSON consumers; this counts all supported files.
        "python_file_count": len(files),
        "syntax_errors": [
            {
                "path": path.as_posix(),
                "error": info.syntax_error,
                "recovered": info.syntax_recovered,
            }
            for path, info in files.items()
            if info.syntax_error
        ],
        "entry_points": entry_points,
        "core_dependencies": core_dependencies,
        "architectural_core": core_dependencies,
        "recommended_reading_order": list(analysis.recommended_reading_order[:top]),
        "analysis_warnings": analysis.warnings,
    }


def _render_ranked_table(
    title: str, entries: list[dict[str, Any]], console: Console
) -> None:
    console.print(f"[bold]{title}[/bold]")
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right")
    table.add_column("File")
    table.add_column("Imported by", justify="right")
    table.add_column("Imports", justify="right")
    table.add_column("Dependencies")
    for index, entry in enumerate(entries, start=1):
        table.add_row(
            str(index),
            entry["path"],
            str(entry["in_degree"]),
            str(entry["out_degree"]),
            ", ".join(entry["dependencies"]) or "None",
        )
        if entry.get("description"):
            table.add_row("", "[dim]Description[/dim]", "", "", entry["description"])
    console.print(table)


def _render_text(report: dict[str, Any], console: Console) -> None:
    console.print(f"[bold]Repository[/bold] {report['repository']}")
    console.print(
        f"[bold]Languages[/bold] {', '.join(report['languages']) or 'None'}  "
        f"[bold]Type[/bold] {report['repository_type']}  "
        f"[bold]Coverage[/bold] {report['coverage']['analyzed_percentage']:.1f}%"
    )
    for warning in report["analysis_warnings"]:
        console.print(f"[yellow]Warning:[/yellow] {warning}")
    console.print()

    console.print("[bold]Execution Entry Points[/bold]")
    entry_table = Table(show_header=True, header_style="bold cyan")
    entry_table.add_column("File")
    entry_table.add_column("Confidence", justify="right")
    entry_table.add_column("Evidence")
    for entry in report["entry_points"]:
        entry_table.add_row(
            entry["path"],
            f"{entry['confidence']:.2f}",
            "; ".join(entry["evidence"]),
        )
    console.print(entry_table)
    console.print()
    _render_ranked_table(
        "Architectural Core (Core Dependencies)", report["architectural_core"], console
    )

    console.print("\n[bold]Recommended Reading Order[/bold]")
    reading_table = Table(show_header=True, header_style="bold cyan")
    reading_table.add_column("#", justify="right")
    reading_table.add_column("File")
    reading_table.add_column("Reason")
    for index, item in enumerate(report["recommended_reading_order"], start=1):
        reading_table.add_row(str(index), item["path"], item["reason"])
    console.print(reading_table)

    console.print("\n[bold]Core Abstractions[/bold]")
    abstraction_table = Table(show_header=True, header_style="bold cyan")
    abstraction_table.add_column("File")
    abstraction_table.add_column("Classes")
    abstraction_table.add_column("Functions")
    entries = [*report["entry_points"], *report["core_dependencies"]]
    for entry in entries:
        if not entry["classes"] and not entry["functions"]:
            continue
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
@click.argument("source")
@click.option("--top", type=click.IntRange(min=1), default=10, show_default=True)
@click.option("--json", "as_json", is_flag=True, help="Output structured JSON.")
@click.option("--ref", help="Branch, tag, or commit to analyze for a Git URL.")
@click.option(
    "--rank-method",
    type=click.Choice(["indegree", "pagerank"]),
    default="pagerank",
    show_default=True,
)
@click.option("--llm", is_flag=True, help="Add LLM descriptions from extracted structure.")
@click.option(
    "--include-category",
    "include_categories",
    multiple=True,
    type=click.Choice(["test", "example", "documentation", "fixture", "generated", "vendor"]),
    help="Include a non-production source category in architecture analysis.",
)
@click.option(
    "--llm-provider",
    type=click.Choice(["ollama", "anthropic"]),
    default="ollama",
    show_default=True,
    help="Provider used with --llm.",
)
def main(
    source: str,
    top: int,
    as_json: bool,
    ref: str | None,
    rank_method: str,
    llm: bool,
    include_categories: tuple[str, ...],
    llm_provider: str,
) -> None:
    """Analyze a local directory or Git repository URL in SOURCE."""
    try:
        with repository_source(source, ref) as root:
            report = _build_report(
                root,
                top,
                rank_method,
                llm,
                llm_provider,
                repository_name=source,
                include_categories=include_categories,
            )
    except RuntimeError as error:
        raise click.ClickException(str(error)) from error
    except Exception as error:
        if llm:
            raise click.ClickException(f"LLM request failed: {error}") from error
        raise

    for syntax_error in report["syntax_errors"]:
        action = (
            "parsed with recoverable syntax errors"
            if syntax_error["recovered"]
            else "skipped"
        )
        click.echo(
            f"Warning: {action} {syntax_error['path']}: {syntax_error['error']}",
            err=True,
        )
    if as_json:
        click.echo(json.dumps(report, indent=2))
    else:
        _render_text(report, Console())


if __name__ == "__main__":
    main()