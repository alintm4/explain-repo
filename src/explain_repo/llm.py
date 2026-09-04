"""Optional Anthropic descriptions based only on extracted structure."""

from __future__ import annotations

import os

from .parser import FileInfo


def describe_file(info: FileInfo) -> str:
    """Generate a one-line description without sending source code."""
    try:
        from anthropic import Anthropic
    except ImportError as error:
        raise RuntimeError(
            "The --llm option requires the LLM extra: uvx --from 'explain-repo[llm]' explain-repo"
        ) from error

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
    client = Anthropic()
    response = client.messages.create(
        model=os.getenv("EXPLAIN_REPO_ANTHROPIC_MODEL", "claude-3-5-haiku-latest"),
        max_tokens=80,
        messages=[
            {
                "role": "user",
                "content": (
                    "Describe this Python file's likely responsibility in one plain-English "
                    "sentence. Use only the extracted structure below and do not speculate "
                    f"beyond it.\n{structure!r}"
                ),
            }
        ],
    )
    text_blocks = [block.text for block in response.content if block.type == "text"]
    return " ".join(text_blocks).strip()