/**
 * Units and colours (EDITOR.md#units-and-colours).
 *
 * One grid square is the unit G. Every dimension here is a fraction of it, so
 * the drawing scales as one piece and how large G is on screen is the
 * `viewBox`'s business alone. Configuring the look is editing this module:
 * nothing else in the editor holds a dimension or a colour, and the colours
 * reach the stylesheets as the custom properties `ui/shared.styles.ts`
 * declares.
 */

/** Track and wire width, W = f·G with f = 0.15. Everything below is written in
 *  terms of it where it is really a track dimension, and in G where it is a
 *  distance along the grid. */
export const W = 0.15;

/** Pins are circles of diameter W. */
export const PIN = W / 2;

/**
 * The dot marking a face centre: where a wire can land a bend, and where every
 * pin sits.
 *
 * Drawn only while a wire is in flight, which is the one moment the answer is
 * being asked for, so the sheet is bare the rest of the time. Well under
 * `PIN`, so a symbol already there covers the dot beneath it rather than
 * ringing it.
 */
export const FACE = 0.04;

/** A free-standing bend when a transit lights it: a dot wider than the
 *  pin over it, so the way shows past it. Unlit it is not drawn at all — the
 *  pin is already there in edit mode, and a black ring around a green pin says
 *  nothing about the drawing. */
export const BEND = 0.75 * W;

/**
 * The weight of a mark drawn as a one-unit line: the strokes at a portal's
 * mouth. Thinner than any track, which is what keeps a mark a mark.
 */
export const HAIRLINE = 0.03;

const BODY = { w: 4, h: 0.8 }; // the block's rectangle
const SPAN = 6; // the block's footprint, and its two pins

/**
 * Block, 6×1: a centred rectangle with a 1G track stub each side, a signal on
 * each stub, and a plus at the rectangle's lower corner on side A.
 *
 * The signal is a plaque: no mast, an octagonal outline with its
 * corners chamfered at 45 degrees, and a green lamp beside a red one. The pair
 * is point symmetric about the block's centre, below the track at the A end and
 * above at the B end — on the left of a train leaving through that end, as the
 * SBB places signals — so a rotation or a flip reads naturally and the lamp
 * order turns with the plaque.
 */
export const BLOCK = {
  body: {
    x: (SPAN - BODY.w) / 2,
    y: (1 - BODY.h) / 2,
    w: BODY.w,
    h: BODY.h,
    border: 0.3 * W,
  },
  signal: {
    at: 0.5, // along the stub, from the pin
    w: 0.53,
    h: 0.22,
    chamfer: 0.09,
    gap: 0.09, // between the plaque and the edge of the track
    lamp: 0.055, // radius
    apart: 0.11, // each lamp's centre, either side of the plaque's
  },
  plus: {
    x: (SPAN - BODY.w) / 2 + 0.2,
    y: (1 + BODY.h) / 2 - 0.18,
    arm: 0.75 * W,
  },
};

/** Terminal, 1×1: a stub from the pin to the buffer stop's bar, which is wider
 *  than the track so that the stub's square end stays inside it. */
export const TERMINAL = { stub: 0.6, bar: { h: 0.6, w: 1.2 * W } };

/**
 * Portal, 1×1: the stub, cut off at the mouth, and the two strokes carrying on
 * past it.
 *
 * The cut and both strokes share one lean, written as dx per dy. `stub` and
 * `first` are where the cut and the nearer stroke cross the track's centreline,
 * and `reach` is how far a stroke runs either side of it.
 */
export const PORTAL = {
  stub: 0.69,
  lean: -0.41,
  mouth: { first: 0.7, apart: 0.09, reach: 0.27 },
  /**
   * Where the label of a portal that pairs with nothing begins, in the symbol's
   * own coordinates: past the mouth, which is the side no wire lands on, so the
   * mark sits in the space the vanishing track leaves.
   *
   * The end nearest the mouth sits on the point (`labelAnchor`), so the label
   * runs outwards however long it is; a centred one would run back over the
   * artwork it marks. Smaller than a block's label, a portal being a sixth of a
   * block's footprint, and there is no rectangle to fit it to.
   */
  mark: { x: 1.2, y: 0.5, size: 0.3 },
};

/**
 * A slip's tick: the road it has and a plain crossing has not, drawn as two
 * strokes, one parallel to each of the two legs the road joins. `off` is how
 * far a stroke sits from its leg's centreline, and `arm` how far it runs from
 * the corner where the two offset lines cross.
 *
 * The tick carries its own weight rather than the portal mouth's hairline. It
 * is the one mark that has to read against 45 degree track beside it, and at a
 * hairline it did not (#59), so it is half again as heavy and a third longer.
 * `lit` is what it grows to when a transit takes the slip road, kept in
 * proportion to the weight rather than pinned to a number of its own.
 */
const TICK = 0.045;

export const SLIP = { off: 0.22, arm: 0.182, weight: TICK, lit: 1.5 * TICK };

/**
 * The label inside a block, which is the only text a symbol carries.
 *
 * `size` is what it is drawn at when it fits, and `advance` is what a glyph is
 * assumed to be wide, as a fraction of the size. The estimate is deliberately
 * generous: the alternative is measuring the drawn text, which means a second
 * render pass to read a number the label is already laid out from, and a
 * label a few percent smaller than it had to be is invisible where a render
 * loop is not.
 */
export const LABEL = { size: 0.5, advance: 0.55 };

/**
 * The size a label is drawn at: `LABEL.size`, or as much smaller as it takes
 * to sit inside `width`.
 *
 * There is no floor. A name long enough to shrink past legibility is drawn
 * small rather than clipped, because the zoom can rescue small text and
 * nothing rescues text that is not there.
 */
export function fitted(text: string, width: number): number {
  return Math.min(LABEL.size, width / (text.length * LABEL.advance));
}

/**
 * The ring a turnout or a slip with no address wears: drawn round the squares
 * the symbol covers, inset so the stroke sits inside its own footprint and two
 * symbols side by side wear two rings rather than share one line.
 *
 * Dashed and lighter than any track, so it reads as a mark on the drawing
 * rather than as something built on the railroad, and it leaves the artwork it
 * is about legible underneath.
 */
export const RING = {
  inset: 0.07,
  radius: 0.12,
  weight: 2 * HAIRLINE,
  dash: 0.16,
  gap: 0.12,
};

/** A note beside a marker on the panel. It is not text on a symbol and has no
 *  rectangle to fit, so it keeps a size of its own rather than following the
 *  label's. */
export const NOTE = 0.22;

/**
 * The palette, as the custom properties the stylesheets read. Track is black
 * and a block's rectangle white in edit mode; run mode, out of scope for now,
 * recolours by toggling classes rather than by editing these.
 */
export const COLOURS: Record<string, string> = {
  "--ink": "#1c1f24",
  "--paper": "#fbfbfa",
  "--rule": "#d9d6d0",
  "--face": "#a8a49b",
  "--track": "#12151a",
  "--body": "#ffffff",
  "--chosen": "#1f6feb",
  "--good": "#22c55e",
  "--wrong": "#cc2936",
  // The quieter of the two weights a fault is marked in: what derives but is
  // unfinished, against the red of what stops derivation (ADR-0024). A slate
  // rather than a second shade of alarm, so the two are told apart at a glance,
  // and it carries no other meaning on the canvas the way an amber next to the
  // lit way would.
  "--unfinished": "#5b6472",
  "--hint": "#7c8087",
  "--clear": "#17a24a",
  "--danger": "#e0332a",
  "--lit": "#a55b12",
  "--lit-body": "#f4e3cd",
  // A way lit because derivation refused over it wears the red every other
  // stopping fault wears, and a block on it takes the pale ground of that red
  // as a chosen transit takes the pale ground of `--lit`.
  "--wrong-body": "#f7dcdf",
  // The netlist pane's accents. They were a palette of six, one per junction
  // region on the canvas; the canvas tints no junction at all now, so what is
  // left is what the panes still read.
  "--tint-1": "#14866d",
  "--tint-2": "#a55b12",
};
