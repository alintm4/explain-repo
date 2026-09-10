# Changelog

All notable changes to this project are documented in this file.

## 0.5.0 - 2026-09-10

### Added

- Evidence-backed execution entry discovery from project metadata, Python main
  guards, `__main__` modules, and conventional executable paths.
- Independent architectural-core and purpose-aware reading-order results.
- Coverage summaries with unsupported-language, parse-failure, and recovery
  reporting.
- Production, test, example, documentation, fixture, generated, vendor, and
  development source categories with repeatable CLI opt-ins.
- Python and Node monorepo package boundaries, per-package results, and
  cross-package dependencies.
- Support for `.cjs`, `.mjs`, `.cts`, and `.mts` source modules.
- A reproducible benchmark with 30 pinned repositories, separate gold labels,
  an offline fixture suite, and explicit evaluation metrics.

### Changed

- Production source is now the default architecture surface, preventing tests,
  examples, fixtures, generated files, and developer tooling from dominating
  rankings.
- PageRank and in-degree are used only for architectural-core ranking, not as
  evidence that a graph root is executable.
- JSON reports now include repository type, languages, coverage, source
  categories, packages, evidence, architectural core, reading order, and
  warnings. The `0.4.x` `core_dependencies` and `python_file_count` fields remain
  available.
- Optional LLM prompts are language-aware; deterministic classification remains
  independent of the provider.

### Fixed

- Thin and metadata-declared launchers are no longer discarded for having low
  graph degree.
- Invalid Python files no longer remain as graph nodes; recoverable tree-sitter
  parses are counted separately from hard failures.
- Unsupported and low-coverage repositories no longer receive silently
  confident architecture results.

### Known limitations

- Static analysis cannot resolve every dynamic import, plugin registry, or
  re-export-heavy JavaScript/TypeScript API surface.
- The pinned V2 benchmark records 0.515 entry F1, 0.870 core repository recall,
  0.365 core Top-5 precision, 0.391 reading Top-1 accuracy, and 0.739 repository
  type accuracy. These are release baselines, not claims of complete discovery.