# Architecture benchmark

The architecture benchmark is separate from the unit-test suite. Its default
mode creates three deterministic repositories in temporary directories and
requires no network access:

```console
uv run python benchmarks/runner.py
```

The fixture suite reports entry precision, recall, F1, Top-1 accuracy and Top-3
recall, core recall, and reading-first Top-1 accuracy. Fixtures are regression
signals; they are not presented as representative ecosystem performance.

## Pinned repository corpus

`repositories/repositories.yaml` records 30 repositories at the exact commits
used by the isolated V1 evaluation. `gold/real-repositories.json` contains
separate human-curated expectations for execution entries, architectural core,
reading-first files, and repository type. `gold/v1-baseline.json` is the
immutable aggregate from the `0.4.0` evaluation and is never recomputed by this
runner.

Prepare each checkout at its recorded commit under a common directory, then run:

```console
uv run python benchmarks/runner.py \
	--real-repositories \
	--repositories-dir /path/to/repos \
	--output /tmp/explain-repo-v2.json
```

The runner refuses a checkout whose `HEAD` differs from the manifest. Select
one or more repositories for iteration with a repeatable option:

```console
uv run python benchmarks/runner.py \
	--real-repositories \
	--repositories-dir /path/to/repos \
	--repository requests \
	--repository react
```

Re-evaluate a saved result without rerunning static analysis:

```console
uv run python benchmarks/runner.py \
	--evaluate-results /tmp/explain-repo-v2.json \
	--output /tmp/explain-repo-v2-evaluated.json
```

## Metric definitions

- Entry precision and recall compare all returned entry candidates with gold
	patterns across supported repositories.
- Entry Top-1 and Top-3 measure repositories that have at least one expected
	entry.
- Entry contamination is the proportion of supported repositories whose entry
	list contains tests, examples, docs, fixtures, benchmarks, scripts, tools, or
	vendored paths.
- Core repository recall measures whether any expected core path appears in the
	first five core results.
- Core Top-5 precision measures how many occupied first-five core slots match a
	gold core pattern.
- Reading Top-1 measures whether the first recommendation matches a gold
	reading-first path.
- Type accuracy compares the inferred label with the corpus label for supported
	repositories.
- Unsupported coverage detection checks that unsupported and mixed controls are
	reported with `unsupported` or `partial` coverage.

Gold annotations are necessarily judgment-bearing. A release must report metric
definitions and residual misses rather than tune rules solely to corpus names.