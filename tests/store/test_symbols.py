"""The generated TypeScript view of the symbol library.

One test matters: the committed file is what the library renders today. It is
the whole point of generating it, since the editor draws against these names
and a stale file would draw the wrong symbol without failing anywhere.
"""

from tc49.store.drawing import LIBRARY, PINS, POSITIONS
from tc49.store.symbols import GENERATED, render
from tests.harness import ROOT


def test_the_committed_file_is_current() -> None:
    assert (ROOT / GENERATED).read_text() == render(), "run `tc49 generate`"


def test_every_kind_is_rendered_with_its_own_pins() -> None:
    """Asserted as the whole row. Looking for a pin name anywhere in the file
    would pass on a `turnout` that had lost `diverging`, since the transits
    below mention it too."""
    generated = render()
    for kind, pins in PINS.items():
        written = ", ".join(f'"{pin}"' for pin in pins)
        assert f"  {kind}: [{written}],\n" in generated


def test_every_library_transit_is_named() -> None:
    generated = render()
    for transits in LIBRARY.values():
        for leg, (a, b) in transits.items():
            assert f'    {leg}: ["{a}", "{b}"],' in generated


def test_every_motorised_leg_is_rendered_with_the_position_it_wants() -> None:
    """The table reaches the editor with the rest of the generated symbol data
    (ADR-0022), so the editor never spells out which leg wants which position."""
    generated = render()
    for legs in POSITIONS.values():
        for leg, position in legs.items():
            assert f'    {leg}: "{position}",\n' in generated
