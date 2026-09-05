from pathlib import Path

import pytest

from explain_repo.parser import parse_file, parse_repository


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


def test_parse_typescript_extracts_local_imports_and_exported_definitions(
    tmp_path: Path,
) -> None:
    (tmp_path / "helper.ts").write_text(
        "export function helper(): void {}\n", encoding="utf-8"
    )
    source = tmp_path / "main.ts"
    source.write_text(
        """import { helper } from './helper';
import React from 'react';
export function run(): void {}
export const load = (): void => {};
export class App {
    start(): void {}
}
""",
        encoding="utf-8",
    )

    info = parse_repository(tmp_path)[Path("main.ts")]

    assert info.syntax_error is None
    assert [imported.module for imported in info.imports] == ["helper", "react"]
    assert info.functions == ["run", "load"]
    assert info.classes == ["App"]
    assert info.class_methods == {"App": ["start"]}


@pytest.mark.parametrize("extension", [".js", ".jsx", ".ts", ".tsx"])
def test_parse_file_dispatches_javascript_typescript_extensions(
    tmp_path: Path, extension: str
) -> None:
    source = tmp_path / f"component{extension}"
    source.write_text(
        "export function render() {}\nexport class Component {}\n",
        encoding="utf-8",
    )

    info = parse_file(source)

    assert info.syntax_error is None
    assert info.functions == ["render"]
    assert info.classes == ["Component"]