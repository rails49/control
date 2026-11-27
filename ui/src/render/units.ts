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

import type { TrainColour } from "../colour.generated.js";

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
 * each stub, and an A at the rectangle's lower corner on side A. A run adds a
 * small square at each end inside the rectangle, what its detector reads.
 *
 * The signal is a plaque: no mast, an octagonal outline with its corners
 * chamfered at 45 degrees, and three lamps in a row — green, red, amber,
 * ordered by distance from the block's rectangle with green furthest. The pair
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
    // Three lamps at the two-lamp plaque's own pitch and end margins, so only
    // the middle section is longer: 2 x pitch + a lamp + 2 x 0.1 of margin.
    // The width across, the chamfer and the gap are untouched.
    w: 0.75,
    h: 0.22,
    chamfer: 0.09,
    gap: 0.09, // between the plaque and the edge of the track
    lamp: 0.055, // radius
    pitch: 0.22, // centre to centre; the outer two sit this far off the middle
  },
  /**
   * The square showing a detector's reading on a run (#898), inside the
   * rectangle at the corner of its own end that the A does not take: top
   * at A, bottom at B, point symmetric as the signals are. `inset` is how far
   * it sits in from the rectangle's edges, so a long label passes between
   * the two.
   */
  detector: { size: 0.14, inset: 0.08 },
  /** The letter A marking side A, centred on this point and smaller than the
   *  label (#922). */
  endA: {
    x: (SPAN - BODY.w) / 2 + 0.2,
    y: (1 + BODY.h) / 2 - 0.21,
    size: 0.3,
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
 * How far from the frog a diverging road's curve begins and ends, along the
 * leg it is in line with: the length of a 45 degree leg, so the curve of a
 * turnout whose straight road is horizontal ends on its diverging pin.
 */
export const CURVE = Math.SQRT1_2;

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
 * A widget's face (#939). A text widget is its words at one of three sizes,
 * `advance` of their size wide per character on average. A button is a ring
 * `ring` in radius and `ringWidth` thick round a disc `disc` in radius,
 * centred on its square. A toggle is a rounded `track` across its two squares
 * with a knob `knob` in radius.
 */
export const WIDGET = {
  text: { small: 0.3, normal: 0.4, large: 0.55 },
  advance: 0.55,
  ring: 0.36,
  ringWidth: 0.08,
  disc: 0.2,
  track: { x: 0.1, y: 0.2, w: 1.8, h: 0.6 },
  knob: 0.25,
};

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

/** A note beside a marker on a run. It is not text on a symbol and has no
 *  rectangle to fit, so it keeps a size of its own rather than following the
 *  label's. */
export const NOTE = 0.22;

/**
 * One value for each train colour (LAYOUT.md#roster-schema), as the palette
 * entry `--train-<name>`, keyed by the generated union `TrainColour`.
 *
 * Each shows against the paper and against the track at 3:1 or more, and is
 * at least 0.1 apart in OKLab from the other nine and from `--wrong`,
 * `--green`, `--chosen`, `--unfinished`, `--hint`, `--track` and `--amber` in
 * its theme (`test/styles.test.ts`).
 */
type TrainEntries = Record<`--train-${TrainColour}`, string>;

const TRAIN: TrainEntries = {
  "--train-orange": "#e1630f",
  "--train-purple": "#7b48b7",
  "--train-brown": "#994e18",
  "--train-pink": "#de3c8d",
  "--train-olive": "#606f15",
  "--train-teal": "#038478",
  "--train-navy": "#2a63a8",
  "--train-magenta": "#ab219f",
  "--train-gold": "#ae7e00",
  "--train-maroon": "#9c4566",
};

const TRAIN_DARK: TrainEntries = {
  "--train-orange": "#d26000",
  "--train-purple": "#a560e4",
  "--train-brown": "#906f63",
  "--train-pink": "#b169a2",
  "--train-olive": "#549015",
  "--train-teal": "#279087",
  "--train-navy": "#6369b7",
  "--train-magenta": "#d83fc3",
  "--train-gold": "#9c7e00",
  "--train-maroon": "#c34560",
};

/**
 * The palette, as the custom properties the stylesheets read. Track is black
 * and a block's rectangle white in edit mode; run mode recolours by toggling
 * classes rather than by editing these.
 */
export const COLOURS: Record<string, string> = {
  "--ink": "#1c1f24",
  "--paper": "#fbfbfa",
  "--rule": "#d9d6d0",
  // The run view's background, which shows in the gaps between its panels
  // (#1390), and the shade every other row of a list takes on the paper.
  "--gap": "#c3c0b9",
  "--stripe": "#f2f2f1",
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
  // The signal lamps, named for their colours: an aspect is a set of lit
  // lamps, not a lamp, so no lamp can be named for an aspect (ADR-0025).
  "--green": "#17a24a",
  "--red": "#e0332a",
  "--amber": "#e8a021",
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
  ...TRAIN,
};

/**
 * The same palette on a dark page, entry for entry.
 *
 * `prefers-color-scheme` decides, with no toggle in the page (look#12). The
 * work pane follows it; the chrome is look's and does not.
 * `test/styles.test.ts` asserts every colour has a value here.
 *
 * The values are not inversions. Track and ink swap ends, because the paper
 * does; a signal lamp, a train colour, and the two weights a fault is marked
 * in keep their hue and are lifted until they carry on the dark ground,
 * since what each colour *means* is the same page of look's `docs/LOOK.md` in
 * either theme. A pale ground — a lit block body, a red one — becomes a dark
 * ground of the same hue rather than a pale one on a dark page.
 *
 * An exported file takes the light palette whichever theme drew it
 * (`tc-canvas.styles.ts`): it is a file that leaves here, and it should not
 * depend on the settings of the machine it was saved from.
 */
export const DARK: Record<string, string> = {
  "--ink": "#e6e8ea",
  "--paper": "#14171b",
  "--rule": "#2f343b",
  "--gap": "#0a0c0f",
  "--stripe": "#1e2125",
  "--face": "#6b7078",
  "--track": "#dfe3e8",
  "--body": "#1b1f26",
  "--chosen": "#4d90ef",
  "--good": "#3ed17f",
  "--wrong": "#f2555f",
  "--unfinished": "#8b95a3",
  "--hint": "#8d939c",
  "--green": "#2fbf5e",
  "--red": "#f04a40",
  "--amber": "#f0ad35",
  "--lit": "#e09a4a",
  "--lit-body": "#3a2e1d",
  "--wrong-body": "#3d2125",
  "--tint-1": "#2fb99a",
  "--tint-2": "#e09a4a",
  ...TRAIN_DARK,
};
