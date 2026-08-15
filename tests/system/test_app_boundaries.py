"""Apps import lib and themselves, never each other (ADR-0013).

The rule is what makes each app deployable on its own, and it is the kind
that decays silently: one convenient import and two containers are welded
together with nothing failing. So it is checked rather than reviewed.

`bench` is exempt by design. It assembles the apps on one bus and is the only
code allowed to import more than one of them.
"""

import ast
from pathlib import Path

import pytest

import tc49

SRC = Path(tc49.__file__).parent
APPS = ("store", "scheduler", "dispatcher", "driver", "simulator")


def tc49_imports(tree: ast.Module) -> set[str]:
    """Every `tc49.…` module the source refers to, as dotted names."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return {n for n in names if n == "tc49" or n.startswith("tc49.")}


@pytest.mark.parametrize("package", (*APPS, "lib"))
def test_package_imports_only_itself_and_lib(package: str) -> None:
    allowed = (f"tc49.{package}.", f"tc49.{package}", "tc49.lib.", "tc49.lib")
    offences: list[str] = []
    for module in sorted((SRC / package).rglob("*.py")):
        tree = ast.parse(module.read_text())
        for name in sorted(tc49_imports(tree)):
            if not name.startswith(allowed):
                offences.append(f"{module.relative_to(SRC.parent)} imports {name}")
    assert not offences, "\n".join(
        [*offences, f"'{package}' may import only tc49.{package} and tc49.lib"]
    )


def test_every_app_has_a_package() -> None:
    """The app list here and the tree on disk must not drift apart."""
    for app in APPS:
        assert (SRC / app / "__init__.py").exists(), f"no package for app '{app}'"
