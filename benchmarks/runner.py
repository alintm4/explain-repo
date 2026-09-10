"""Run the explicit explain-repo architecture benchmark."""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from time import perf_counter
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from explain_repo.analysis import analyze_repository  # noqa: E402


def _metrics(true_positive: int, predicted: int, expected: int) -> dict[str, float]:
    precision = true_positive / predicted if predicted else 1.0 if not expected else 0.0
    recall = true_positive / expected if expected else 1.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0,
    }


def _matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def _is_contamination(path: str) -> bool:
    parts = set(Path(path).parts[:-1])
    return bool(
        parts
        & {
            "test",
            "tests",
            "integration",
            "example",
            "examples",
            "docs",
            "docs_src",
            "fixtures",
            "__fixtures__",
            "playground",
            "bench",
            "benchmarks",
            "scripts",
            "tools",
            "vendor",
            "deps",
        }
    )


def evaluate_real_results(results: list[dict[str, object]]) -> dict[str, object]:
    gold = json.loads((Path(__file__).parent / "gold" / "real-repositories.json").read_text())[
        "repositories"
    ]
    entry_tp = entry_count = entry_expected = top_1 = top_3 = 0
    core_hits = core_slots = core_repositories = reading_hits = contaminated = 0
    supported = 0
    unsupported_honest = 0
    type_hits = 0
    expected_entry_repositories = 0
    for result in results:
        name = str(result["name"])
        expected = gold[name]
        entries = [item["path"] for item in result["entry_points"]]
        core = [item["path"] for item in result["architectural_core"][:5]]
        reading = [item["path"] for item in result["recommended_reading_order"][:5]]
        if result["type"] in {"unsupported", "mixed"}:
            unsupported_honest += int(result["coverage"]["status"] in {"unsupported", "partial"})
            continue
        supported += 1
        entry_expected += len(expected["entries"])
        entry_tp += sum(
            any(fnmatch.fnmatch(path, pattern) for path in entries)
            for pattern in expected["entries"]
        )
        if expected["entries"]:
            expected_entry_repositories += 1
            top_1 += int(bool(entries) and _matches(entries[0], expected["entries"]))
            top_3 += int(any(_matches(path, expected["entries"]) for path in entries[:3]))
        entry_count += len(entries)
        contaminated += int(any(_is_contamination(path) for path in entries))
        core_repositories += int(any(_matches(path, expected["core"]) for path in core))
        core_hits += sum(_matches(path, expected["core"]) for path in core)
        core_slots += len(core)
        reading_hits += int(bool(reading) and _matches(reading[0], expected["read_first"]))
        type_hits += int(result["repository_type_actual"] == result["type"])
    return {
        "entry": {
            **_metrics(entry_tp, entry_count, entry_expected),
            "top_1_accuracy": round(
                top_1 / expected_entry_repositories,
                4,
            ) if expected_entry_repositories else 1.0,
            "top_3_recall": round(
                top_3 / expected_entry_repositories,
                4,
            ) if expected_entry_repositories else 1.0,
            "contaminated_repository_rate": round(contaminated / supported, 4) if supported else 0.0,
        },
        "core": {
            "repository_recall": round(core_repositories / supported, 4) if supported else 1.0,
            "top_5_precision": round(core_hits / core_slots, 4) if core_slots else 1.0,
        },
        "reading_top_1_accuracy": round(reading_hits / supported, 4) if supported else 1.0,
        "repository_type_accuracy": round(type_hits / supported, 4) if supported else 1.0,
        "unsupported_coverage_detection": round(
            unsupported_honest
            / sum(result["type"] in {"unsupported", "mixed"} for result in results),
            4,
        )
        if any(result["type"] in {"unsupported", "mixed"} for result in results)
        else 1.0,
    }


def run_fixtures() -> dict[str, object]:
    cases = json.loads((Path(__file__).parent / "fixtures" / "cases.json").read_text())
    results = []
    entry_tp = entry_predicted = entry_expected = 0
    top_1 = top_3 = core_hits = core_expected = reading_top_1 = 0
    for case in cases:
        with TemporaryDirectory(prefix=f"explain-repo-{case['name']}-") as temporary:
            root = Path(temporary)
            for relative, content in case["files"].items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            analysis = analyze_repository(root)
        actual_entries = [item["path"] for item in analysis.entry_points]
        actual_core = [item["path"] for item in analysis.architectural_core[:5]]
        actual_reading = [item["path"] for item in analysis.recommended_reading_order]
        expected_entries = set(case["entries"])
        expected_core = set(case["core"])
        hits = len(expected_entries & set(actual_entries))
        entry_tp += hits
        entry_predicted += len(actual_entries)
        entry_expected += len(expected_entries)
        top_1 += int(bool(expected_entries) and bool(actual_entries) and actual_entries[0] in expected_entries)
        top_3 += int(bool(expected_entries & set(actual_entries[:3])))
        core_hits += len(expected_core & set(actual_core))
        core_expected += len(expected_core)
        reading_top_1 += int(bool(case["read_first"]) and bool(actual_reading) and actual_reading[0] in case["read_first"])
        results.append({
            "repository": case["name"],
            "expected_entry_points": case["entries"],
            "actual_entry_points": actual_entries,
            "expected_core_modules": case["core"],
            "actual_core_modules": actual_core,
            "expected_reading_first": case["read_first"],
            "actual_reading_order": actual_reading,
            "coverage": analysis.coverage.analyzed_percentage,
            "failures": sorted(expected_entries - set(actual_entries)),
        })
    positive_cases = sum(bool(case["entries"]) for case in cases)
    reading_cases = sum(bool(case["read_first"]) for case in cases)
    return {
        "suite": "offline-fixtures-v2",
        "repository_count": len(cases),
        "entry": {
            **_metrics(entry_tp, entry_predicted, entry_expected),
            "top_1_accuracy": round(top_1 / positive_cases, 4),
            "top_3_recall": round(top_3 / positive_cases, 4),
        },
        "core_recall": round(core_hits / core_expected, 4),
        "reading_top_1_accuracy": round(reading_top_1 / reading_cases, 4),
        "repositories": results,
    }


def run_real_repositories(
    repositories_dir: Path, selected: tuple[str, ...] = ()
) -> dict[str, object]:
    manifest = json.loads(
        (Path(__file__).parent / "repositories" / "repositories.yaml").read_text()
    )
    results = []
    repositories = [
        item
        for item in manifest["repositories"]
        if not selected or item["name"] in selected
    ]
    unknown = set(selected) - {item["name"] for item in repositories}
    if unknown:
        raise RuntimeError(f"Unknown benchmark repositories: {', '.join(sorted(unknown))}")
    for item in repositories:
        root = repositories_dir / item["name"]
        if not root.is_dir():
            raise RuntimeError(f"Missing benchmark checkout: {root}")
        commit = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if commit != item["commit"]:
            raise RuntimeError(
                f"Commit mismatch for {item['name']}: expected {item['commit']}, found {commit}"
            )
        started = perf_counter()
        analysis = analyze_repository(root)
        elapsed = perf_counter() - started
        results.append(
            {
                **item,
                "repository_type_actual": analysis.repository_type,
                "entry_points": list(analysis.entry_points[:12]),
                "architectural_core": list(analysis.architectural_core[:12]),
                "recommended_reading_order": list(analysis.recommended_reading_order[:12]),
                "coverage": {
                    "total_source_files": analysis.coverage.total_source_files,
                    "supported_source_files": analysis.coverage.supported_source_files,
                    "parsed_files": analysis.coverage.parsed_files,
                    "parse_failures": analysis.coverage.parse_failures,
                    "parse_recoveries": analysis.coverage.parse_recoveries,
                    "analyzed_percentage": analysis.coverage.analyzed_percentage,
                    "status": analysis.coverage.status,
                },
                "source_categories": analysis.source_categories,
                "packages": analysis.packages,
                "elapsed_seconds": round(elapsed, 4),
            }
        )
        print(f"{item['name']}: {elapsed:.2f}s", file=sys.stderr)
    return {
        "suite": "real-repositories-v2",
        "repository_count": len(results),
        "metrics": evaluate_real_results(results),
        "repositories": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--real-repositories", action="store_true")
    parser.add_argument("--repositories-dir", type=Path)
    parser.add_argument("--repository", action="append", default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--evaluate-results", type=Path)
    arguments = parser.parse_args()
    if arguments.evaluate_results:
        result = json.loads(arguments.evaluate_results.read_text())
        result["metrics"] = evaluate_real_results(result["repositories"])
    elif arguments.real_repositories:
        if arguments.repositories_dir is None:
            parser.error("--real-repositories requires --repositories-dir")
        result = run_real_repositories(arguments.repositories_dir, tuple(arguments.repository))
    else:
        result = run_fixtures()
    rendered = json.dumps(result, indent=2)
    if arguments.output:
        arguments.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()