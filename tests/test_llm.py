import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from explain_repo.llm import describe_file
from explain_repo.parser import FileInfo, ImportInfo


class _Response(io.BytesIO):
    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def test_ollama_receives_only_extracted_structure() -> None:
    info = FileInfo(
        path=Path("pkg/service.py"),
        imports=[ImportInfo(module="pkg.core", names=("Engine",))],
        functions=["build_service"],
        classes=["Service"],
        class_methods={"Service": ["run"]},
    )
    response = _Response(json.dumps({"response": "Coordinates the service."}).encode())

    with patch("explain_repo.llm.urlopen", return_value=response) as mocked_urlopen:
        description = describe_file(info, "ollama")

    request = mocked_urlopen.call_args.args[0]
    payload = json.loads(request.data)
    assert description == "Coordinates the service."
    assert payload["model"] == "qwen2.5-coder:3b"
    assert payload["stream"] is False
    assert "pkg.core" in payload["prompt"]
    assert "build_service" in payload["prompt"]
    assert "Service" in payload["prompt"]


def test_unknown_llm_provider_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        describe_file(FileInfo(path=Path("app.py")), "unknown")