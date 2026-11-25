"""The lock table and the questions asked of it (#1315)."""

import ast
from pathlib import Path

import tc49.dispatcher.table
from tests.system.test_app_boundaries import tc49_imports


def test_the_table_imports_only_lib() -> None:
    """It holds the rules, and nothing of the dispatcher that does bus work,
    chooses routes, locks or checks safety."""
    source = Path(tc49.dispatcher.table.__file__).read_text()
    assert {
        name
        for name in tc49_imports(ast.parse(source))
        if not name.startswith("tc49.lib")
    } == set()
