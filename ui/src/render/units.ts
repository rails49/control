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

const BODY = { w: 4, h: 0.8 }; // the block's rectangle
const SPAN = 6; // the block's footprint, and its two pins

/**
 * Block, 6×1: a centred rectangle with a 1G track stub each side, a signal on
 * each stub, and a plus at the rectangle's lower corner on side A.
 *
 * The signals are point symmetric about the centre — above the track at the A
 * end, below at the B end — so a rotation or a flip reads naturally.
 */
export const BLOCK = {
  body: {
    x: (SPAN - BODY.w) / 2,
    y: (1 - BODY.h) / 2,
    w: BODY.w,
    h: BODY.h,
    border: 0.3 * W,
  },
  signal: { at: 0.5, mast: 1.6 * W, head: 0.6 * W },
  plus: {
    x: (SPAN - BODY.w) / 2 + 0.2,
    y: (1 + BODY.h) / 2 - 0.18,
    arm: 0.75 * W,
  },
};

/** Terminal, 1×1: a stub from the pin to the buffer stop's bar. */
export const TERMINAL = { stub: 0.6, bar: { h: 0.6, w: 0.7 * W } };

/** Portal, 1×1: a stub and the mouth the label is drawn beside. */
export const PORTAL = {
  stub: 0.4,
  mouth: { tip: 0.9, half: 0.26 },
  label: 0.16,
};

/**
 * Where a slip's tick leaves each of its two legs, as a distance from the
 * frog. Provisional geometry, finalised by eye (EDITOR.md): the tick is the
 * road a slip has and a plain crossing has not, so it is drawn as track, bent
 * round the frog, and far enough out to leave daylight between it and the
 * crossing — nearer in, the corner fills and a slip reads as a fat crossing.
 */
export const SLIP = 0.5;

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
  "--lit": "#a55b12",
  "--lit-body": "#f4e3cd",
  "--tint-0": "#1f6feb",
  "--tint-1": "#14866d",
  "--tint-2": "#a55b12",
  "--tint-3": "#8250df",
  "--tint-4": "#b3417a",
  "--tint-5": "#56761c",
};
