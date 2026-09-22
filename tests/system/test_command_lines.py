"""The six apps that come up on a broker take their shared flags from one
place, and `lib` says how many they are (#430, #456, #528).

`lib/startup.py::command_line` writes `--broker`, `--railroad` and `--store`
once and says which of the three an app takes. An app declaring one of them
itself gets away with it for exactly as long as the two spellings agree, and
nothing goes red when they stop agreeing: #430 unified four of the six and
left `driver` and `dccex` each holding a `--broker` of its own, word for word
the same as this one. So the rule is checked rather than reviewed.

An app's own flags are untouched by it — the station and the startup file are
the translator's, and are added to the parser `lib` hands back.

One package is not here: the store's face is a subcommand of the `tc49`
script rather than a `__main__` (ADR-0014).

**The number in `lib/startup.py`'s prose is checked here as well.** It says in
present tense how many apps start there, and that sentence went stale twice
while this list grew (#430, #456, #528). A `grep` for the number would not do
it: the same file says six about how things stood before `startup.py`
existed, and those sentences are right as they are. So the two present-tense ones are
pinned by their words, with the number cut out of them and the wrapping taken
out of both sides.
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

STARTUP = SRC / "lib" / "startup.py"
"""Where the shared line is written, read as text rather than imported: one of
the two sentences that count the apps is the module's own docstring and the
other is `command_line`'s, and the file is one thing to read."""

COUNTED = (
    "`lib` is the only place a shape {} of them share can live",
    "**All {} start here**",
)
"""The sentences there that say how many apps come up this way, with the
number cut out. Written out rather than searched for so that rewording one
comes here too — a sentence that no longer reads this way is a sentence
nothing is counting any more."""

NUMBERS = (
    "no",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
)
"""How that prose spells a count. It is prose and spells them out, so a number
is matched as the word it is written as."""


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


def flat(prose: str) -> str:
    """Prose with its wrapping taken out, since where a line ends is the
    formatter's business and a sentence counting the apps straddles a break."""
    return " ".join(prose.split())


def built_on_lib() -> tuple[str, ...]:
    """The packages whose `__main__` takes its command line from `lib`, found
    on disk rather than listed, so an app added or dropped is counted the day
    it lands rather than the day someone remembers this file."""
    return tuple(
        sorted(
            path.parent.name
            for path in SRC.glob("*/__main__.py")
            if "command_line" in calls(ast.parse(path.read_text()))
        )
    )


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


def test_every_main_that_starts_in_lib_is_listed_here() -> None:
    """The list above is what the two tests above run over, so an app missing
    from it is an app nothing checks. It is a hand-written list of apps that
    come up on a broker, and the `__main__` modules on disk are the same
    apps."""
    assert built_on_lib() == tuple(sorted(ON_THE_BROKER))


def test_the_prose_says_how_many_apps_start_there() -> None:
    """`lib/startup.py` counts the apps out loud, and the count is what drifted
    three times (#430, #456, #528). Red if the prose is left behind when an app
    lands, and red if the prose is changed while the apps are not."""
    apps = built_on_lib()
    assert len(apps) < len(NUMBERS), "more apps than this has words for"
    source = flat(STARTUP.read_text())
    for sentence in COUNTED:
        said = flat(sentence.format(NUMBERS[len(apps)]))
        assert said in source, (
            f"{len(apps)} apps start there ({', '.join(apps)}), and"
            f" lib/startup.py does not say so: {said!r}"
        )
