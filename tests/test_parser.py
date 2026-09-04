from pathlib import Path

from explain_repo.parser import parse_file


def test_parse_file_extracts_module_structure(tmp_path: Path) -> None:
    source = tmp_path / "sample.py"
    source.write_text(
        """import numpy as np
from . import helpers
from utils.tools import build as make

def public_function():
    pass

async def async_function():
    pass

class Service:
    def run(self):
        pass
""",
        encoding="utf-8",
    )

    info = parse_file(source)

    assert info.syntax_error is None
    assert info.functions == ["public_function", "async_function"]
    assert info.classes == ["Service"]
    assert info.class_methods == {"Service": ["run"]}
    assert info.imports[0].aliases == (("numpy", "np"),)
    assert info.imports[1].module is None
    assert info.imports[1].level == 1
    assert info.imports[1].names == ("helpers",)
    assert info.imports[2].module == "utils.tools"


def test_parse_file_returns_syntax_error(tmp_path: Path) -> None:
    source = tmp_path / "broken.py"
    source.write_text("def broken(:\n", encoding="utf-8")

    info = parse_file(source)

    assert info.syntax_error is not None
    assert info.functions == []