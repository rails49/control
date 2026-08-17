"""The generated TypeScript view of the symbol library.

One test matters: the committed file is what the library renders today. It is
the whole point of generating it, since the editor draws against these names
and a stale file would draw the wrong symbol without failing anywhere.
"""

from tc49.store.drawing import LIBRARY, PINS
from tc49.store.symbols import GENERATED, render
from tests.harness import ROOT


def test_the_committed_file_is_current() -> None:
    assert (ROOT / GENERATED).read_text() == render(), "run `tc49 symbols`"


def test_every_kind_and_pin_is_named() -> None:
    generated = render()
    for kind, pins in PINS.items():
        assert f"  {kind}: [" in generated
        for pin in pins:
            assert f'"{pin}"' in generated


def test_every_library_transit_is_named() -> None:
    generated = render()
    for transits in LIBRARY.values():
        for leg, (a, b) in transits.items():
            assert f'    {leg}: ["{a}", "{b}"],' in generated
