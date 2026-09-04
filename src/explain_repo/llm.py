"""Optional LLM descriptions based only on extracted structure."""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .parser import FileInfo


def _prompt(info: FileInfo) -> str:
    imports = [
        "." * imported.level
        + (imported.module or "")
        + (f": {', '.join(imported.names)}" if imported.names else "")
        for imported in info.imports
    ]
    structure = {
        "path": info.path.as_posix(),
        "imports": imports,
        "functions": info.functions,
        "classes": info.classes,
        "class_methods": info.class_methods,
    }
    return (
        "Describe this Python file's likely responsibility in one plain-English "
        "sentence. Use only the extracted structure below and do not speculate "
        f"beyond it.\n{structure!r}"
    )


def _describe_with_ollama(info: FileInfo) -> str:
    base_url = os.getenv("EXPLAIN_REPO_OLLAMA_URL", "http://localhost:11434").rstrip("/")
    payload = json.dumps(
        {
            "model": os.getenv("EXPLAIN_REPO_OLLAMA_MODEL", "qwen2.5-coder:3b"),
            "prompt": _prompt(info),
            "stream": False,
        }
    ).encode("utf-8")
    request = Request(
        f"{base_url}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=120) as response:
            result = json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"Ollama returned HTTP {error.code}") from error
    except URLError as error:
        raise RuntimeError(
            "Cannot connect to Ollama. Install Ollama, run 'ollama serve', and pull "
            "the configured model."
        ) from error
    description = result.get("response", "").strip()
    if not description:
        raise RuntimeError("Ollama returned an empty description")
    return description


def _describe_with_anthropic(info: FileInfo) -> str:
    try:
        from anthropic import Anthropic
    except ImportError as error:
        raise RuntimeError(
            "Anthropic requires the LLM extra: "
            "uvx --from 'explain-repo[llm]' explain-repo"
        ) from error

    client = Anthropic()
    response = client.messages.create(
        model=os.getenv("EXPLAIN_REPO_ANTHROPIC_MODEL", "claude-3-5-haiku-latest"),
        max_tokens=80,
        messages=[{"role": "user", "content": _prompt(info)}],
    )
    text_blocks = [block.text for block in response.content if block.type == "text"]
    return " ".join(text_blocks).strip()


def describe_file(info: FileInfo, provider: str = "ollama") -> str:
    """Generate a one-line description without sending source code."""
    if provider == "ollama":
        return _describe_with_ollama(info)
    if provider == "anthropic":
        return _describe_with_anthropic(info)
    raise ValueError(f"Unsupported LLM provider: {provider}")