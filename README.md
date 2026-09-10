# explain-repo

`explain-repo` is a deterministic repository architecture discovery tool for
local and remote Python, JavaScript, and TypeScript repositories. It uses source
structure, import relationships, executable metadata, package boundaries, and
source roles to answer three separate questions:

- Where can execution start?
- Which files form the architectural core?
- In what order should a person read the repository?

Every entry candidate includes its evidence. Dependency centrality contributes
to core ranking, but a graph root is not treated as executable merely because
nothing imports it. The deterministic report never requires an LLM.

## Installation

Run the published package without installing it globally:

```console
uvx explain-repo ./path/to/repository
uvx explain-repo https://github.com/OWNER/REPOSITORY.git
```

For local development:

```console
git clone <repository-url>
cd explain-repo
uv sync
uv run pytest
uvx --from . explain-repo ./path/to/repository
```

Python 3.11 or newer is required.

## Usage

The CLI accepts either a local directory or a Git repository URL. Remote
repositories are cloned into a temporary directory, analyzed, and automatically
deleted afterward. The original repository is not modified.

Analyze a public GitHub repository without cloning it manually:

```console
uvx explain-repo https://github.com/OWNER/REPOSITORY.git
```

Use `--ref` to analyze a branch, tag, or commit:

```console
uvx explain-repo https://github.com/OWNER/REPOSITORY.git --ref develop
uvx explain-repo https://github.com/OWNER/REPOSITORY.git --ref v1.2.0
uvx explain-repo https://github.com/OWNER/REPOSITORY.git --ref a1b2c3d
```

HTTPS and SSH Git URLs are supported. Private repositories work when your local
Git installation already has access through SSH keys or a credential helper.
The `--ref` option applies only to URL sources; local directories are analyzed
as they currently exist on disk.

```console
explain-repo [OPTIONS] SOURCE
```

| Option | Description |
| --- | --- |
| `--top N` | Number of files to show (default: `10`). |
| `--json` | Output structured JSON. |
| `--ref REF` | Branch, tag, or commit to analyze for a Git URL. |
| `--rank-method METHOD` | Use `indegree` or `pagerank` (default: `pagerank`). |
| `--include-category CATEGORY` | Include a normally excluded source category; repeatable. |
| `--llm` | Add structure-only LLM descriptions. |
| `--llm-provider PROVIDER` | Use `ollama` or `anthropic` (default: `ollama`). |
| `--version` | Show the version and exit. |
| `--help` | Show help and exit. |

Examples:

```console
uvx explain-repo . --top 5
uvx explain-repo https://github.com/OWNER/REPOSITORY.git --top 5
uvx explain-repo . --rank-method indegree
uvx explain-repo . --json > report.json
uvx explain-repo . --include-category test --include-category example
uvx explain-repo . --llm
```

Available categories are `test`, `example`, `documentation`, `fixture`,
`generated`, `vendor`, and `development`.

The terminal report contains coverage and repository type followed by separate
execution entry, architectural core, recommended reading order, and core
abstraction sections. JSON includes the evidence and full machine-readable
details behind those views.

```text
Repository .
Languages Python  Type cli  Coverage 100.0%

Execution Entry Points
┏━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ File                    ┃ Confidence ┃ Evidence                 ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ src/explain_repo/cli.py │       1.00 │ console script metadata  │
└─────────────────────────┴────────────┴──────────────────────────┘
```

## Analysis model

**Execution entry points** require executable evidence: Python console scripts,
JavaScript package `bin` declarations, Python `__main__.py` modules, exact Python
main guards, or conventional CLI/application paths. Thin launchers remain valid
when they delegate immediately.

**Architectural core** ranks production modules that other production modules
depend on. The selected graph rank is combined with local structural evidence
and penalties for generic compatibility, type, utility, generated, and
non-production modules. PageRank is evidence of dependency importance, not
evidence of executability.

**Recommended reading order** is purpose-aware. It begins with a public package
surface or executable root, then moves toward high-value implementation files.

Production source is the default analysis surface. Tests, examples,
documentation, fixtures, generated files, vendored code, and development
scripts remain counted in `source_categories` but cannot contaminate default
rankings. Use `--include-category` to opt into any of them.

Coverage reports total source-like files, supported and unsupported files,
parse failures and recoveries, analyzed percentage, and one of `complete`,
`partial`, `parse_failures`, or `unsupported`. Low-coverage repositories are
reported honestly rather than receiving confident rankings from a small
language slice. Recognized Python and Node workspace metadata also produces
per-package results and cross-package dependencies for monorepos.

Python is parsed with the standard-library `ast` module. JavaScript and
TypeScript are parsed with tree-sitter. Supported extensions are `.py`, `.js`,
`.jsx`, `.cjs`, `.mjs`, `.ts`, `.tsx`, `.cts`, and `.mts`.

Invalid Python files are excluded from the graph. Tree-sitter may recover useful
structure from JavaScript and TypeScript syntax errors; recoveries are included
and counted separately. Relative JavaScript/TypeScript imports use extension
guessing and directory `index` resolution. Bare third-party imports are recorded
but are not resolved into `node_modules`.

Common generated and environment directories including `.git`, `.venv`,
`venv`, `node_modules`, `__pycache__`, `build`, and `dist` are excluded from
scanning. Circular imports are represented as ordinary graph cycles.

## JSON output

The principal top-level fields are `repository_type`, `languages`, `coverage`,
`source_categories`, `packages`, `package_results`, `entry_points`,
`architectural_core`, `recommended_reading_order`, and `analysis_warnings`.
The `core_dependencies` alias and historical `python_file_count` field remain
for `0.4.x` consumers. Despite its name, `python_file_count` counts all supported
source files; new consumers should use `coverage.supported_source_files`.

## Optional LLM descriptions

LLM descriptions use only the file path and extracted imports, function names,
class names, and method names. Full source content is never sent.

### Ollama (free and local)

Ollama is the default provider in `explain-repo` `0.2.0` and newer. It runs on
your computer, requires no API key, and has no per-request charge.

1. Install Ollama. On Linux:

	```console
	curl -fsSL https://ollama.com/install.sh | sh
	```

	For macOS or Windows, use the installer from
	[ollama.com/download](https://ollama.com/download).

2. Confirm the installation:

	```console
	ollama --version
	```

3. Download the default model (approximately 2 GB):

	```console
	ollama pull qwen2.5-coder:3b
	ollama list
	```

4. Start the local server if the installer did not start it automatically:

	```console
	ollama serve
	```

	Keep that terminal open. A message that port `11434` is already in use
	usually means Ollama is already running.

5. From another terminal, test the current source checkout:

	```console
	cd /home/alintm4/Desktop/read-repo
	uvx --from . explain-repo /path/to/repository --top 3 --llm
	```

6. Run the published release from anywhere:

	```console
	uvx --refresh --from explain-repo==0.5.0 explain-repo /path/to/repository --top 3 --llm
	```

Each top-ranked file causes one local model request. Use a small `--top` value
for faster reports on machines with limited memory.

To select another installed model, set `EXPLAIN_REPO_OLLAMA_MODEL`:

```console
EXPLAIN_REPO_OLLAMA_MODEL=qwen2.5-coder:7b uvx explain-repo . --llm
```

To connect to Ollama on another machine, set the server URL:

```console
EXPLAIN_REPO_OLLAMA_URL=http://hostname:11434 uvx explain-repo . --llm
```

If the command reports that it cannot connect:

```console
ollama serve
curl http://localhost:11434/api/tags
```

If it reports that the model is missing, run:

```console
ollama pull qwen2.5-coder:3b
```

No API key or paid account is required, and extracted structure stays on your
computer.

### Anthropic

Anthropic remains available as an optional hosted provider. Install the `llm`
extra and provide credentials in the environment:

```console
export ANTHROPIC_API_KEY="..."
uv sync --extra llm
uv run explain-repo . --llm --llm-provider anthropic
```

Override the default Anthropic model with `EXPLAIN_REPO_ANTHROPIC_MODEL`.

## Benchmark

Version `0.5.0` was evaluated against 30 repositories at pinned commits: 23
Python/JavaScript/TypeScript repositories and 7 unsupported or mixed-language
controls. Gold entry, core, reading, and type annotations and all exact commit
SHAs are versioned under `benchmarks/`.

| Metric | `0.4.0` | `0.5.0` |
| --- | ---: | ---: |
| Entry precision | 0.15 | 0.415 |
| Entry recall | 0.35 | 0.680 |
| Entry F1 | 0.21 | 0.515 |
| Entry Top-1 accuracy | 0.52 | 0.769 |
| Repositories with contaminated entries | 0.87 | 0.000 |
| Core surfaced/repository recall | 0.96 | 0.870 |
| Core Top-5 precision | not measured | 0.365 |
| Reading Top-1 accuracy | not measured | 0.391 |
| Repository type accuracy | not measured | 0.739 |
| Unsupported coverage detection | not measured | 1.000 |

The V1 core metric asked whether expected core appeared anywhere in a broader
output; V2 checks only the first five architectural-core results. Those values
are release gates, not a strictly equivalent before/after measure. The V2 run
took 725 seconds total with a 1.8-second median. Next.js was the 275-second
maximum. Profiling showed parsing dominates large-repository runtime; graph
construction and PageRank are comparatively small.

See [benchmarks/README.md](benchmarks/README.md) for exact commands and metric
definitions.

## Limitations

- Static imports cannot prove runtime behavior, framework registration, dynamic
	imports, plugin loading, or reflection.
- Re-export-heavy JavaScript/TypeScript packages can hide public API paths from
	the resolved graph.
- Repository type is metadata- and structure-derived; hybrid projects may have
	more than one defensible label.
- Package discovery may miss custom workspace systems.
- Runtime scales with the number and size of parsed files.
- Go, Rust, Java, C, C++, and other languages contribute to coverage honesty but
	are not yet parsed for architecture.

## Publishing to PyPI

The distribution name, Python requirement, runtime dependencies, build backend,
and `[project.scripts]` entry point are defined in `pyproject.toml`. The script
entry is what lets `uvx` install the distribution and invoke `explain-repo`.

1. Choose the next semantic version and update both `project.version` in
	`pyproject.toml` and `__version__` in `src/explain_repo/__init__.py`.
2. Run `uv lock`, `uv sync`, `uv run pytest`, and
	`uvx --from . explain-repo .`.
3. Build clean wheel and source distributions with `uv build`.
4. Check the release files with `uvx twine check dist/*`.
5. Create a PyPI trusted publisher for the repository's release workflow, or
	create a scoped PyPI API token.
6. Publish interactively with `uv publish`; when prompted for token credentials,
	use `__token__` as the username and the PyPI token as the password. In CI,
	prefer PyPI trusted publishing instead of storing a long-lived token.
7. Verify the published release with
	`uvx --refresh --from explain-repo==<version> explain-repo --help`.

PyPI makes the distribution globally discoverable. Before publication,
`uvx --from . explain-repo PATH` is the correct local equivalent.