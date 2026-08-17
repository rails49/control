"""The symbol library, rendered as TypeScript for the editor (ADR-0014).

`PINS` and `LIBRARY` in [drawing.py](drawing.py) are the authority for each
kind's pins and transits, and the editor needs the same names to draw a symbol
and attach a wire to the right pin. Written twice the two would drift, so the
TypeScript is generated: `tc49 symbols` writes it and a test asserts the
committed file is current. The names become union types, so a renamed pin is a
compile error rather than a wrong drawing.

Artwork is not generated. Footprints, anchor offsets, and the appearances of
crossings and slips are hand-written TypeScript against these names.
"""

from tc49.store.drawing import ANGLED, LIBRARY, PINS, ROTATIONS

GENERATED = "ui/src/symbols.generated.ts"

_HEADER = """\
// Generated from src/tc49/store/drawing.py. Run `tc49 symbols` to update.
//
// The symbol library: what pins each kind has, and what transits run between
// them. Artwork is hand-written against these names.
"""


def render() -> str:
    """The whole of `ui/src/symbols.generated.ts`."""
    sections = (_HEADER, _pins(), _transits(), _placeable(), _angled(), _rotations())
    return "\n".join(sections)


def _pins() -> str:
    rows = "".join(f"  {kind}: {_list(pins)},\n" for kind, pins in sorted(PINS.items()))
    return f"""\
export const PINS = {{
{rows}}} as const;

/** A symbol kind. */
export type Kind = keyof typeof PINS;

/** A pin of one kind, or of any kind. */
export type Pin<K extends Kind = Kind> = (typeof PINS)[K][number];
"""


def _transits() -> str:
    rows = ""
    for kind, transits in sorted(LIBRARY.items()):
        legs = "".join(
            f"    {leg}: {_list(pins)},\n" for leg, pins in sorted(transits.items())
        )
        rows += f"  {kind}: {{\n{legs}  }},\n"
    return f"""\
/** The transits a kind of fixed geometry declares, each between two pins. */
export const TRANSITS = {{
{rows}}} as const;

/** A kind whose transits the library fixes. */
export type LibraryKind = keyof typeof TRANSITS;

/** A leg of such a kind: what a transit name is written on. */
export type Leg<K extends LibraryKind = LibraryKind> =
  keyof (typeof TRANSITS)[K];
"""


def _placeable() -> str:
    rows = "".join(f'  "{kind}",\n' for kind in sorted(PINS) if kind != "pin")
    return f"""\
/** The palette. A free-standing bend is not on it: it is placed by clicking
 *  empty canvas while drawing a wire. */
export const PLACEABLE = [
{rows}] as const;
"""


def _angled() -> str:
    return f"""\
/** The kinds drawn in several appearances, chosen in the properties dialog.
 *  All appearances of a kind share one footprint and one pin set. */
export const ANGLED = {_list(sorted(ANGLED))} as const;

export type AngledKind = (typeof ANGLED)[number];
"""


def _rotations() -> str:
    numbers = ", ".join(str(rotation) for rotation in ROTATIONS)
    return f"""\
/** Symbols sit in whole squares with pins at face centres, so they turn in
 *  quarters. */
export const ROTATIONS = [{numbers}] as const;

export type Rotation = (typeof ROTATIONS)[number];
"""


def _list(names: tuple[str, ...] | list[str]) -> str:
    return "[" + ", ".join(f'"{name}"' for name in names) + "]"
