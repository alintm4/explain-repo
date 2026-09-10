# Architecture benchmark

The benchmark is separate from the unit-test suite:

```console
uv run python benchmarks/runner.py
```

The default run uses small, deterministic fixtures under `fixtures/` and does
not require network access. Use `--real-repositories` only after pinned commits
and per-repository gold annotations from the isolated V1 evaluation have been
imported into `repositories/repositories.yaml` and `gold/`.

`gold/v1-baseline.json` records the immutable aggregate supplied by the V1
evaluation. It is not recomputed or adjusted by this runner. The original
per-repository V1 artifacts were not available in this checkout, so the real
repository manifest deliberately does not fabricate commit hashes or gold
paths.

The fixture benchmark reports entry-point precision, recall, F1, Top-1
accuracy, Top-3 recall, core recall, and reading-first Top-1 accuracy. Results
are emitted as JSON for regression comparisons.