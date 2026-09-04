# explain-repo

`explain-repo` statically analyzes a local Python repository and produces a
guided onboarding report. It parses Python with the standard-library `ast`
module, resolves internal imports, builds a NetworkX dependency graph, and ranks
files without reading meaning into source text.

## Installation

Run the published package without installing it globally:

```console
uvx explain-repo ./path/to/repository
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

The CLI accepts a path to a local directory. It does not download or analyze a
GitHub URL directly. To analyze a repository that is not already on your
computer, clone it first:

```console
git clone https://github.com/OWNER/REPOSITORY.git
uvx explain-repo REPOSITORY
```

The cloned directory can be deleted after the report is generated. Direct
GitHub URL support is planned for a future release.

```console
explain-repo [OPTIONS] PATH

Options:
  --top INTEGER RANGE             Number of files to show. [default: 10]
  --json                          Output structured JSON.
  --rank-method [indegree|pagerank]
								  Ranking algorithm. [default: pagerank]
	--llm                           Add structure-only LLM descriptions.
	--llm-provider [ollama|anthropic]
																	Provider used with --llm. [default: ollama]
  --version                       Show the version and exit.
  --help                          Show help and exit.
```

Examples:

```console
uvx explain-repo . --top 5
uvx explain-repo . --rank-method indegree
uvx explain-repo . --json > report.json
uvx explain-repo . --llm
```

Sample terminal output:

```text
Suggested Reading Order
┏━━━┳━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ # ┃ File               ┃ Why central               ┃ Dependencies     ┃
┡━━━╇━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ 1 │ src/app/core.py    │ imported by 12 other files │ src/app/types.py │
│ 2 │ src/app/service.py │ imported by 4 other files  │ src/app/core.py  │
└───┴────────────────────┴───────────────────────────┴──────────────────┘

Core Abstractions
┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ File               ┃ Classes              ┃ Functions        ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ src/app/core.py    │ Repository (load)    │ create_app       │
│ src/app/service.py │ AnalysisService (run)│ analyze          │
└────────────────────┴──────────────────────┴──────────────────┘
```

Syntax-invalid files are skipped with a warning. Common generated directories,
including `.git`, `.venv`, `venv`, `node_modules`, `__pycache__`, `build`, and
`dist`, are excluded from scanning. Circular imports are represented as ordinary
cycles in the graph and require no recursive traversal.

## Optional LLM descriptions

LLM descriptions use only the file path and extracted imports, function names,
class names, and method names. Full source content is never sent.

### Ollama (free and local)

Ollama is the default provider. Install it from
[ollama.com](https://ollama.com), then download the default model:

```console
ollama pull qwen2.5-coder:3b
```

Ensure Ollama is running, then analyze a repository:

```console
uvx explain-repo . --llm
```

No API key or paid account is required, and extracted structure stays on your
computer. Select another installed model with `EXPLAIN_REPO_OLLAMA_MODEL`, or a
different server with `EXPLAIN_REPO_OLLAMA_URL`.

### Anthropic

Anthropic remains available as an optional hosted provider. Install the `llm`
extra and provide credentials in the environment:

```console
export ANTHROPIC_API_KEY="..."
uv sync --extra llm
uv run explain-repo . --llm --llm-provider anthropic
```

Override the default Anthropic model with `EXPLAIN_REPO_ANTHROPIC_MODEL`.

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