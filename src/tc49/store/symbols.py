"""The symbol library, rendered as TypeScript for the editor (ADR-0014).

`PINS`, `LIBRARY` and `POSITIONS` in [drawing.py](drawing.py) are the
authority for each kind's pins, its transits and the position each leg of a
motorised one wants, and the editor needs the same names to draw a symbol and
attach a wire to the right pin. Written twice the two would drift, so the
TypeScript is generated: `tc49 generate` writes it and a test asserts the
committed file is current. The names become union types, so a renamed pin is a
compile error rather than a wrong drawing.

Artwork is not generated. Footprints, anchor offsets and the strokes between
them are hand-written TypeScript against these names (ui/EDITOR.md).
"""

from tc49.store.drawing import BEND, LIBRARY, PINS, POSITIONS, ROTATIONS

GENERATED_PATH = "ui/src/symbols.generated.ts"

_HEADER = """\
// Generated from src/tc49/store/drawing.py. Run `tc49 generate` to update.
//
// The symbol library: what pins each kind has, what transits run between
// them, and which position each leg of a motorised kind wants. Artwork is
// hand-written against these names.
"""


def render() -> str:
    """The whole of `ui/src/symbols.generated.ts`."""
    sections = (
        _HEADER,
        _pins(),
        _transits(),
        _positions(),
        _placeable(),
        _rotations(),
    )
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

/** A leg of such a kind: what a transit name is written on. Written to
 *  distribute over the kinds, because `keyof` over a union of the leg objects
 *  would intersect their keys, and no leg is common to all of them. */
export type Leg<K extends LibraryKind = LibraryKind> = {{
  [P in K]: keyof (typeof TRANSITS)[P];
}}[K];
"""


def _positions() -> str:
    rows = ""
    for kind, legs in sorted(POSITIONS.items()):
        written = "".join(
            f'    {leg}: "{position}",\n' for leg, position in sorted(legs.items())
        )
        rows += f"  {kind}: {{\n{written}  }},\n"
    positions = " | ".join(
        f'"{position}"'
        for position in sorted(
            {p for legs in POSITIONS.values() for p in legs.values()}
        )
    )
    return f"""\
/** Which position a kind's motor must be in for a way to take each of its
 *  legs. Every motorised kind has one motor and two positions, and no kind's
 *  legs are named for them, so the library says which is which. */
export const POSITIONS = {{
{rows}}} as const;

/** A kind with a motor: it is commanded by address into one of two positions,
 *  and it is the only sort of kind that carries an address. */
export type MotorisedKind = keyof typeof POSITIONS;

/** What a motor can be set to. */
export type Position = {positions};
"""


def _placeable() -> str:
    rows = "".join(f'  "{kind}",\n' for kind in sorted(PINS) if kind != BEND)
    return f"""\
/** The palette. A free-standing bend is not on it: it is placed by clicking
 *  empty canvas while drawing a wire. */
export const PLACEABLE = [
{rows}] as const;
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
