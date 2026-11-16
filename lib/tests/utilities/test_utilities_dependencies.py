import ast
from pathlib import Path

import pytest

UTILITIES_DIRECTORY: Path = Path(__file__).resolve().parents[2] / "src" / "agent_watch" / "utilities"
LAYER_PACKAGES: tuple[str, ...] = ("agent_watch.api", "agent_watch.cli", "agent_watch.rest_api")


def imported_module_names(source_file: Path) -> list[str]:
    module_names: list[str] = []
    for node in ast.walk(ast.parse(source_file.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            module_names.append(node.module)
        elif isinstance(node, ast.Import):
            module_names += [alias.name for alias in node.names]
    return module_names


@pytest.mark.parametrize("source_file", sorted(UTILITIES_DIRECTORY.glob("*.py")), ids=lambda source_file: source_file.name)
def test_utilities_never_import_from_the_layers_that_use_them(source_file: Path) -> None:
    assert [name for name in imported_module_names(source_file) if name.startswith(LAYER_PACKAGES)] == []


def test_imported_module_names_finds_both_import_forms(tmp_path: Path) -> None:
    sample_file: Path = tmp_path / "sample.py"
    sample_file.write_text("import logging\nfrom agent_watch.api.github_client import GitHubClient\n")

    assert imported_module_names(sample_file) == ["logging", "agent_watch.api.github_client"]
