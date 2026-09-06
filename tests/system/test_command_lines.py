"""The six apps that come up on a broker take their shared flags from one
place (#430, #456).

`lib/startup.py::command_line` writes `--broker`, `--railroad` and `--store`
once and says which of the three an app takes. An app declaring one of them
itself gets away with it for exactly as long as the two spellings agree, and
nothing goes red when they stop agreeing: #430 unified four of the six and
left `driver` and `dccex` each holding a `--broker` of its own, word for word
the same as this one. So the rule is checked rather than reviewed.

An app's own flags are untouched by it — the station and the startup file are
the translator's, and are added to the parser `lib` hands back.

Two of the packages are not here. `dccex_usb` is on no bus and takes no
broker at all, its flags being a device and a port (ADR-0043), and the
store's face is a subcommand of the `tc49` script rather than a `__main__`
(ADR-0014).
"""

import ast
from pathlib import Path

import pytest

import tc49

SRC = Path(tc49.__file__).parent

ON_THE_BROKER = (
    "scheduler",
    "dispatcher",
    "driver",
    "simulator",
    "layout",
    "dccex",
)
"""The apps a compose service starts with a broker to run on, each a
`python -m tc49.<app>` whose `__main__` parses that line."""

SHARED = ("--broker", "--railroad", "--store")
"""The flags `command_line` writes. An app takes some of them or none, and
declares none of them."""


def calls(tree: ast.Module) -> set[str]:
    """Every function the source calls, by the last name in the call, so that
    `argparse.ArgumentParser(…)` and a bare `ArgumentParser(…)` read alike."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            names.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            names.add(node.func.attr)
    return names


def declared(tree: ast.Module) -> set[str]:
    """The flags this source names in an `add_argument`, which is where a
    second spelling of a shared one would be."""
    return {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_argument"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }


@pytest.fixture(params=ON_THE_BROKER)
def app(request: pytest.FixtureRequest) -> ast.Module:
    """One app's `__main__`, read rather than imported: what is under test is
    what the source says, and importing it would run nothing that says it."""
    return ast.parse((SRC / str(request.param) / "__main__.py").read_text())


def test_the_command_line_is_built_in_lib(app: ast.Module) -> None:
    made = calls(app)
    assert "command_line" in made, "its command line is built somewhere else"
    assert "ArgumentParser" not in made, (
        "it builds a parser of its own, and the flags on it will drift from"
        " lib/startup.py's without a word"
    )


def test_no_app_declares_a_shared_flag(app: ast.Module) -> None:
    both = declared(app) & set(SHARED)
    assert not both, f"declared here as well as in lib: {sorted(both)}"
