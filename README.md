# explain-repo

`explain-repo` statically analyzes a local or remote Python repository and
produces a guided onboarding report. It parses Python with the standard-library
`ast` module, resolves internal imports, builds a NetworkX dependency graph, and
separates likely entry points from heavily imported core dependencies without
reading meaning into source text.

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
uvx explain-repo . --llm
```

Sample terminal output:

```text
Entry Points
┏━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ # ┃ File           ┃ Imported by ┃ Imports ┃ Dependencies           ┃
┡━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━┩
│ 1 │ src/app/main.py│           0 │       3 │ src/app/service.py, ...│
└───┴────────────────┴─────────────┴─────────┴────────────────────────┘

Core Dependencies
┏━━━┳━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ # ┃ File               ┃ Imported by ┃ Imports ┃ Dependencies ┃
┡━━━╇━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ 1 │ src/app/core.py    │          12 │       1 │ src/app/types.py │
└───┴────────────────────┴─────────────┴─────────┴──────────────────┘

Core Abstractions
┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ File               ┃ Classes              ┃ Functions        ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ src/app/core.py    │ Repository (load)    │ create_app       │
│ src/app/service.py │ AnalysisService (run)│ analyze          │
└────────────────────┴──────────────────────┴──────────────────┘
```

A file is classified only when its dominant degree is at least two and at
least twice the opposite degree after adding one to both sides. The smoothing
avoids division by zero, while the minimum degree prevents a one-import package
shim from looking like an application entry point. Files that match neither
signal are leaves. Files without functions or classes remain available in JSON
and the ranked sections but are omitted from `Core Abstractions`.

Syntax-invalid files are skipped with a warning. Common generated directories,
including `.git`, `.venv`, `venv`, `node_modules`, `__pycache__`, `build`, and
`dist`, are excluded from scanning. Circular imports are represented as ordinary
cycles in the graph and require no recursive traversal.

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
	uvx --refresh --from explain-repo==0.3.0 explain-repo /path/to/repository --top 3 --llm
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