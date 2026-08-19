// Generated from src/tc49/store/drawing.py. Run `tc49 symbols` to update.
//
// The symbol library: what pins each kind has, what transits run between
// them, and which position each leg of a motorised kind wants. Artwork is
// hand-written against these names.

export const PINS = {
  block: ["A", "B"],
  crossing: ["a1", "a2", "b1", "b2"],
  crossing_90: ["a1", "a2", "b1", "b2"],
  crossing_90d: ["a1", "a2", "b1", "b2"],
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
  crossing_90: {
    a: ["a1", "a2"],
    b: ["b1", "b2"],
  },
  crossing_90d: {
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

/** A leg of such a kind: what a transit name is written on. Written to
 *  distribute over the kinds, because `keyof` over a union of the leg objects
 *  would intersect their keys, and no leg is common to all of them. */
export type Leg<K extends LibraryKind = LibraryKind> = {
  [P in K]: keyof (typeof TRANSITS)[P];
}[K];

/** Which position a kind's motor must be in for a way to take each of its
 *  legs. Every motorised kind has one motor and two positions, and a slip's
 *  legs are not named for them, so the library says which is which. */
export const POSITIONS = {
  double_slip: {
    a: "straight",
    b: "straight",
    slip_1: "curved",
    slip_2: "curved",
  },
  single_slip: {
    a: "straight",
    b: "straight",
    slip: "curved",
  },
  turnout: {
    diverging: "curved",
    straight: "straight",
  },
} as const;

/** A kind with a motor: it is commanded by address into one of two positions,
 *  and it is the only sort of kind that carries an address. */
export type MotorisedKind = keyof typeof POSITIONS;

/** What a motor can be set to. */
export type Position = "curved" | "straight";

/** The palette. A free-standing bend is not on it: it is placed by clicking
 *  empty canvas while drawing a wire. */
export const PLACEABLE = [
  "block",
  "crossing",
  "crossing_90",
  "crossing_90d",
  "double_slip",
  "portal",
  "single_slip",
  "terminal",
  "turnout",
] as const;

/** Symbols sit in whole squares with pins at face centres, so they turn in
 *  quarters. */
export const ROTATIONS = [0, 90, 180, 270] as const;

export type Rotation = (typeof ROTATIONS)[number];
