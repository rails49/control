/**
 * Units and colours (EDITOR.md#units-and-colours).
 *
 * One grid square is the unit G. Every dimension here is a fraction of it, so
 * the drawing scales as one piece and how large G is on screen is the
 * `viewBox`'s business alone. Configuring the look is editing this module:
 * nothing else in the editor holds a dimension or a colour, and the colours
 * reach the stylesheets as the custom properties `styles.ts` declares.
 */

/** Track and wire width, W = f·G with f = 0.15. Everything below is written in
 *  terms of it where it is really a track dimension, and in G where it is a
 *  distance along the grid. */
export const W = 0.15;

/** Pins are circles of diameter W. */
export const PIN = W / 2;

/** A free-standing bend: a joint dot, drawn a little wider than the pin over
 *  it so that a way lit through it shows. */
export const BEND = 0.75 * W;

/**
 * The weight of a mark the sample tiles draw as a one-unit line: a slip's tick
 * and the strokes at a portal's mouth. Thinner than any track, which is what
 * keeps a mark a mark.
 */
export const HAIRLINE = 0.03;

const BODY = { w: 4, h: 0.8 }; // the block's rectangle
const SPAN = 6; // the block's footprint, and its two pins

/**
 * Block, 6×1: a centred rectangle with a 1G track stub each side, a signal on
 * each stub, and a plus at the rectangle's lower corner on side A.
 *
 * The signal is the sample's plaque: no mast, an octagonal outline with its
 * corners chamfered at 45 degrees, and a green lamp beside a red one. The pair
 * is point symmetric about the block's centre, above the track at the A end and
 * below at the B end, so a rotation or a flip reads naturally and the lamp
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
  label: 0.16,
};

/**
 * A slip's tick: the road it has and a plain crossing has not, drawn as two
 * strokes, one parallel to each of the two legs the road joins. `off` is how
 * far a stroke sits from its leg's centreline, and `arm` how far it runs from
 * the corner where the two offset lines cross.
 */
export const SLIP = { off: 0.22, arm: 0.14 };

/** The label under a symbol, and the one inside a block. */
export const LABEL = { size: 0.22, below: 0.32 };

/**
 * The palette, as the custom properties the stylesheets read. Track is black
 * and a block's rectangle white in edit mode; run mode, out of scope for now,
 * recolours by toggling classes rather than by editing these.
 */
export const COLOURS: Record<string, string> = {
  "--ink": "#1c1f24",
  "--paper": "#fbfbfa",
  "--rule": "#d9d6d0",
  "--track": "#12151a",
  "--body": "#ffffff",
  "--chosen": "#1f6feb",
  "--good": "#1a7f37",
  "--wrong": "#cc2936",
  "--hint": "#7c8087",
  "--clear": "#17a24a",
  "--danger": "#e0332a",
  "--lit": "#a55b12",
  "--lit-body": "#f4e3cd",
  "--tint-0": "#1f6feb",
  "--tint-1": "#14866d",
  "--tint-2": "#a55b12",
  "--tint-3": "#8250df",
  "--tint-4": "#b3417a",
  "--tint-5": "#56761c",
};
