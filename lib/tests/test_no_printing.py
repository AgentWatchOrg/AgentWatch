import ast
from pathlib import Path

import pytest

SOURCE_DIRECTORY: Path = Path(__file__).resolve().parent.parent / "src" / "agent_watch"
PRINTING_CALL_NAMES: frozenset[str] = frozenset({"print", "click.echo", "click.secho"})


def find_printing_calls(source_file: Path, source_root: Path) -> list[str]:
    printing_calls: list[str] = []
    for node in ast.walk(ast.parse(source_file.read_text())):
        if isinstance(node, ast.Call) and ast.unparse(node.func) in PRINTING_CALL_NAMES:
            printing_calls.append(f"{source_file.relative_to(source_root)}:{node.lineno} {ast.unparse(node.func)}")
    return printing_calls


@pytest.mark.parametrize("source_file", sorted(SOURCE_DIRECTORY.rglob("*.py")),
                         ids=lambda source_file: str(source_file.relative_to(SOURCE_DIRECTORY)))
def test_source_uses_the_logger_instead_of_printing(source_file: Path) -> None:
    assert find_printing_calls(source_file, SOURCE_DIRECTORY) == []


def test_printing_calls_are_detected(tmp_path: Path) -> None:
    offending_file: Path = tmp_path / "offending.py"
    offending_file.write_text("import click\nprint('a')\nclick.echo('b')\n")

    assert find_printing_calls(offending_file, tmp_path) == ["offending.py:2 print", "offending.py:3 click.echo"]
