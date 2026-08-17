// Generated from src/tc49/store/drawing.py. Run `tc49 symbols` to update.
//
// The symbol library: what pins each kind has, and what transits run between
// them. Artwork is hand-written against these names.

export const PINS = {
  block: ["A", "B"],
  crossing: ["a1", "a2", "b1", "b2"],
  double_slip: ["a1", "a2", "b1", "b2"],
  pin: ["P"],
  portal: ["P"],
  single_slip: ["a1", "a2", "b1", "b2"],
  terminal: ["P"],
  turnout: ["toe", "straight", "diverging"],
} as const;

/** A symbol kind. */
export type Kind = keyof typeof PINS;

/** A pin of one kind, or of any kind. */
export type Pin<K extends Kind = Kind> = (typeof PINS)[K][number];

/** The transits a kind of fixed geometry declares, each between two pins. */
export const TRANSITS = {
  crossing: {
    a: ["a1", "a2"],
    b: ["b1", "b2"],
  },
  double_slip: {
    a: ["a1", "a2"],
    b: ["b1", "b2"],
    slip_1: ["a1", "b2"],
    slip_2: ["b1", "a2"],
  },
  single_slip: {
    a: ["a1", "a2"],
    b: ["b1", "b2"],
    slip: ["a1", "b2"],
  },
  turnout: {
    diverging: ["toe", "diverging"],
    straight: ["toe", "straight"],
  },
} as const;

/** A kind whose transits the library fixes. */
export type LibraryKind = keyof typeof TRANSITS;

/** A leg of such a kind: what a transit name is written on. */
export type Leg<K extends LibraryKind = LibraryKind> =
  keyof (typeof TRANSITS)[K];

/** The palette. A free-standing bend is not on it: it is placed by clicking
 *  empty canvas while drawing a wire. */
export const PLACEABLE = [
  "block",
  "crossing",
  "double_slip",
  "portal",
  "single_slip",
  "terminal",
  "turnout",
] as const;

/** The kinds drawn in several appearances, chosen in the properties dialog.
 *  All appearances of a kind share one footprint and one pin set. */
export const ANGLED = ["crossing", "double_slip", "single_slip"] as const;

export type AngledKind = (typeof ANGLED)[number];

/** Symbols sit in whole squares with pins at face centres, so they turn in
 *  quarters. */
export const ROTATIONS = [0, 90, 180, 270] as const;

export type Rotation = (typeof ROTATIONS)[number];
