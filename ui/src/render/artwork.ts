/**
 * What each symbol looks like, hand-written against the generated pin names
 * (#52) in the symbol's own coordinates: one square is one unit, the origin is
 * the top left of the unturned footprint, and `transformOf` puts it on the
 * grid.
 *
 * Every leg is drawn from the anchors `geometry.ts` gives, so the artwork and
 * the wires meet by construction, and every dimension that is not an anchor is
 * a named constant in `units.ts`. A turnout has two forms, one for each
 * direction its straight road can take, and every other kind exactly one
 * appearance (EDITOR.md#symbol-geometry): diagonal legs are always 45 degrees.
 * Where a wire leaves a pin out of line with the leg, the leg stops short of
 * the pin and carries on round its half of the curve that joins the two
 * (`wires.ts`), unless the leg is itself a curve all the way to the pin.
 */

import { nothing, svg, type SVGTemplateResult } from "lit";

import type { TrainColour } from "../colour.generated.js";
import {
  POSITIONS,
  TRANSITS,
  type Kind,
  type LibraryKind,
  type Position,
} from "../symbols.generated.js";
import {
  motorised,
  type SymbolSpec,
  type WidgetKind,
  type WidgetSpec,
} from "../model/drawing.js";
import {
  FOOTPRINTS,
  anchorIn,
  unit,
  uprightAt,
  type Point,
} from "../model/geometry.js";
import { WHOLE } from "../model/inspect.js";
import { CLAIMS, type Claim } from "../model/panel.js";
import {
  ansi,
  editorRuns,
  newWidget,
  togglePosition,
  type Run,
} from "../model/widgets.js";
import { BEND, BLOCK, CURVE, PORTAL, TERMINAL, W, WIDGET, trainStyle } from "./units.js";

/** How a lit leg or wire is drawn. On a run, the claim on it and the colour
 *  of the train holding it, where the roster has that train; in edit mode
 *  neither. A stroke with a claim is painted by `trainStyle`. */
export interface Lighting {
  claim?: Claim;
  colour?: TrainColour;
}

const NONE: ReadonlySet<string> = new Set();
const UNLIT: ReadonlyMap<string, Lighting> = new Map();
/** What a signal shows, as the dispatcher publishes it (GLOSSARY.md). */
export type Aspect = "stop" | "caution" | "clear";

const RESTING: ReadonlyMap<string, Aspect> = new Map();
const UNCUT: ReadonlyMap<string, Cut> = new Map();

/** What a wire's corner takes from a symbol at one pin (`wiring`). */
export interface Cut {
  /** How far short of the pin the symbol's track stops. */
  by: number;
  /** Where the symbol's half of the corner ends, in the symbol's own
   *  coordinates: the middle of the curve. Undefined at a bend, which has no
   *  track to draw a half with. */
  mid: Point | undefined;
}

/** What a detector reads at the block end it watches (GLOSSARY.md,
 *  **Detector**). */
export type Reading = "occupied" | "clear" | "unknown";

/**
 * Draw a symbol, with the legs a chosen transit takes lit.
 *
 * The way is lit leg by leg rather than symbol by symbol (EDITOR.md), and
 * every leg of a turnout, a crossing or a slip is one stroke from pin to pin.
 * `WHOLE` lights every stroke, which is what a symbol with no legs the
 * artwork draws — a joiner or a block end — is lit by. Each lit leg is drawn
 * as its `Lighting` says, so two routes through one symbol are each drawn in
 * their own train's colour (ui/PANEL.md).
 *
 * `dark` names the block ends that carry no signal, which `dark` in
 * inspect.ts works out. It defaults to none, so a palette tile and a drag
 * ghost — neither of which has a `/review` to ask — draw the whole symbol.
 *
 * `aspects` names what each end's signal shows, keyed by end letter. It
 * defaults to empty, which is edit mode: no aspect class, so every lamp
 * stays lit and the symbol says what a signal is rather than what one is
 * doing.
 *
 * `position` is where a point lies, as `layout`'s `wanted/point` row says
 * (ui/PANEL.md): the roads only the other position offers are drawn set
 * against. The run view hands none for a point on a lit road, the road being
 * the position. It defaults to none, which is edit mode and a symbol nothing has
 * commanded yet — a drawing says what a point is, never where it lies.
 *
 * `cut` names the pins where the track meets another out of line (`wiring`).
 * Every stroke ending at such a pin stops short of it and carries on round
 * its half of the corner, so the half is lit, faint or selected as the track
 * is. It defaults to none, which is a symbol with no wires: a palette tile, a
 * ghost. A bend named in it draws no dot, the corner passing beside its pin.
 */
export function artwork(
  spec: SymbolSpec,
  lit: ReadonlyMap<string, Lighting> = UNLIT,
  dark: ReadonlySet<string> = NONE,
  aspects: ReadonlyMap<string, Aspect> = RESTING,
  position?: Position,
  cut: ReadonlyMap<string, Cut> = UNCUT,
): SVGTemplateResult {
  const on: Lit = (...legs) =>
    lit.get(WHOLE) ?? legs.map((leg) => lit.get(leg)).find((one) => one !== undefined);
  const set = against(spec, position);
  const end: End = (pin) => {
    const at = anchorIn(spec.kind, pin, spec.rot);
    const taken = cut.get(pin);
    if (taken?.mid === undefined) return { at, corner: undefined };
    const back = unit(at, middleOf(spec.kind));
    const short = { x: at.x + back.x * taken.by, y: at.y + back.y * taken.by };
    return { at: short, corner: [middle(at, short), taken.mid] };
  };
  switch (spec.kind) {
    case "block":
      return block(spec, on, dark, aspects, end);
    case "terminal":
      return terminal(on, end);
    case "portal":
      return portal(on, end);
    case "pin":
      return cut.has("P") ? svg`` : bend(on);
    case "turnout":
      return turnout(spec, on, set, end);
    case "crossing":
    case "crossing_90":
    case "crossing_90d":
    case "single_slip":
    case "double_slip":
      return crossed(spec.kind, on, set, end);
  }
}

/** Where a symbol's track ends toward a pin: at the pin, or short of it with
 *  the symbol's half of a corner carrying on from there. */
interface Ending {
  at: Point;
  /** The half corner beyond `at`: a quadratic's control point and its end. */
  corner: [Point, Point] | undefined;
}

type End = (pin: string) => Ending;

/** The middle of a kind's unturned footprint, which every kind's track leaves
 *  its pins in line with. It is the frog of a kind that has one. */
function middleOf(kind: Kind): Point {
  const { w, h } = FOOTPRINTS[kind];
  return { x: w / 2, y: h / 2 };
}

/** The legs drawn straight through the frog. Every other leg the library
 *  declares is a curve round it. */
const THROUGH: ReadonlySet<string> = new Set(["straight", "a", "b"]);

/**
 * How far back from a pin a symbol's track runs straight, which is as far as
 * a wire's corner may cut into it (`wiring`).
 *
 * A stub is straight to the block's rectangle or the buffer, and a through
 * road to the frog. A portal's stub keeps a track width before its mouth, so
 * the round cap a corner begins with stays inside the cut. A road that curves
 * round the frog is straight to `CURVE` short of it, which at a pin on a 45
 * degree leg is no distance at all: the curve ends on the pin.
 */
export function straightAt(spec: SymbolSpec, pin: string): number {
  switch (spec.kind) {
    case "block":
      return BLOCK.body.x;
    case "terminal":
      return TERMINAL.stub;
    case "portal":
      return PORTAL.stub - W;
    case "pin":
      return 0;
    default: {
      const at = anchorIn(spec.kind, pin, spec.rot);
      const frog = middleOf(spec.kind);
      const legs: Record<string, readonly string[]> = TRANSITS[spec.kind];
      const curved = Object.entries(legs).some(
        ([leg, ends]) => !THROUGH.has(leg) && ends.includes(pin),
      );
      const toFrog = Math.hypot(at.x - frog.x, at.y - frog.y);
      return Math.max(0, toFrog - (curved ? CURVE : 0));
    }
  }
}

/** How a stroke the legs run over is lit, `undefined` where none of them
 *  is. */
type Lit = (...legs: string[]) => Lighting | undefined;

/**
 * A stroke of track, plain or lit as `lighting` says: `lit`, and on a run the
 * claim, with the train's colour as `--train`. A committed stroke is a thin
 * line along the middle of the track, so the plain track is drawn under it.
 */
function track(
  classes: string,
  d: string,
  lighting: Lighting | undefined,
  clip?: string,
): SVGTemplateResult {
  const plain = svg`<path class=${classes} clip-path=${clip ?? nothing} d=${d} />`;
  if (lighting === undefined) return plain;
  const { claim, colour } = lighting;
  const lit = svg`<path class=${`${classes} lit${claim === undefined ? "" : ` ${claim}`}`}
    style=${claim === undefined ? nothing : trainStyle(colour)}
    clip-path=${clip ?? nothing} d=${d} />`;
  return claim === "committed" ? svg`${plain}${lit}` : lit;
}

/** Whether a stroke is set against: every leg over it wants the position the
 *  point is not in, so the road it draws is not one the point offers. */
type Against = (legs: readonly string[]) => boolean;

const NEITHER: Against = () => false;

/** The library declares which position each leg wants, so where a point lies
 *  is enough to say which roads it does not offer. A kind with no motor —
 *  a fixed crossing, a block — has none whatever it is handed. */
function against(spec: SymbolSpec, position: Position | undefined): Against {
  const { kind } = spec;
  if (position === undefined || !motorised(kind)) return NEITHER;
  const wants: Record<string, Position> = POSITIONS[kind];
  return (legs) =>
    legs.length > 0 && legs.every((leg) => wants[leg] !== position);
}

/**
 * A block: a rectangle with a 1G track stub each side, a signal on each stub,
 * and an A at the rectangle's lower corner on the A side, drawn upright as the
 * label is (`uprightAt`).
 *
 * The signal is part of what a block is rather than anything placed
 * (store/DRAWING.md), and the pair is point symmetric — below the track at A,
 * above at B, on the left of a train leaving through that end, as the SBB
 * places signals — so a rotation or a flip reads naturally. Detectors are not
 * part of it: a run draws their readings over it (`detectors`). Nothing is
 * written outside the rectangle; the label goes inside it, and the canvas
 * draws that outside the turned group.
 *
 * An end named in `dark` draws no signal at all rather than a dim one. A dim
 * signal is an aspect, and there is no signal there to be showing one: nothing
 * leaves that end for a signal to clear for.
 */
function block(
  spec: SymbolSpec,
  on: Lit,
  dark: ReadonlySet<string>,
  aspects: ReadonlyMap<string, Aspect>,
  end: End,
): SVGTemplateResult {
  const [a, b] = [anchorIn("block", "A"), anchorIn("block", "B")];
  const { x, y, w, h } = BLOCK.body;
  const { at } = BLOCK.signal;
  return svg`
    ${track("track", path(end("A"), { x, y: a.y }), on())}
    ${track("track", path({ x: x + w, y: b.y }, end("B")), on())}
    <rect class=${`block-body${on() === undefined ? "" : " lit"}`}
          x=${x} y=${y} width=${w} height=${h} />
    ${dark.has("A")
      ? svg``
      : svg`<g class=${`signal end-A ${aspects.get("A") ?? ""}`.trim()}>
          ${signal(a.x + at, a.y, 1)}</g>`}
    ${dark.has("B")
      ? svg``
      : svg`<g class=${`signal end-B ${aspects.get("B") ?? ""}`.trim()}>
          ${signal(b.x - at, b.y, -1)}</g>`}
    <text class="end-a" font-size=${BLOCK.endA.size}
          transform=${uprightAt(spec, BLOCK.endA)}>A</text>
  `;
}

/**
 * What each end's detector reads, as a square inside the block's rectangle at
 * that end (#898): the class says the reading, `occupied` filled, `clear`
 * hollow, `unknown` grey. An end with no reading is drawn `unknown`, since
 * every block end has a detector and silence says nothing about the track.
 *
 * A square and in no lamp colour, because the signals at the same ends are
 * round red and green lamps. Drawn in the block's own frame, so a turned or
 * flipped block keeps each square at the end it reads. Run mode only: a
 * drawing has no readings.
 */
export function detectors(
  readings: ReadonlyMap<string, Reading>,
): SVGTemplateResult {
  const { x, y, w, h } = BLOCK.body;
  const { size, inset } = BLOCK.detector;
  const at = {
    A: { x: x + inset, y: y + inset },
    B: { x: x + w - inset - size, y: y + h - inset - size },
  };
  return svg`${(["A", "B"] as const).map(
    (end) => svg`<rect class=${`detector end-${end} ${readings.get(end) ?? "unknown"}`}
      x=${n(at[end].x)} y=${n(at[end].y)} width=${size} height=${size} />`,
  )}`;
}

/**
 * A signal standing clear of the track: a plaque and three lamps, no mast.
 * The caller wraps it in a group naming the block end it governs (`end-A`,
 * `end-B`), which is what lets run mode show one aspect per end while edit
 * mode keeps every lamp lit.
 *
 * The lamps are ordered by distance from the block's rectangle — green
 * furthest, red between, amber nearest — the Swiss head laid on its side with
 * its top pointing away from the block. Distance from the rectangle is the
 * only orientation-stable way to say it: `away` is -1 above the track and +1
 * below and turns the whole signal, so the order turns with it and the two
 * signals of a block stay one point symmetric pair
 * (EDITOR.md#symbol-geometry), which a rotation or a flip maps onto itself.
 */
function signal(x: number, y: number, away: -1 | 1): SVGTemplateResult {
  const { w, h, chamfer: c, gap, lamp, pitch } = BLOCK.signal;
  const middle = y + away * (W / 2 + gap + h / 2);
  const [x0, x1] = [x - w / 2, x + w / 2];
  const [y0, y1] = [middle - h / 2, middle + h / 2];
  return svg`
    <path class="plaque" d=${`M${n(x0)} ${n(y0 + c)} L${n(x0 + c)} ${n(y0)}
      H${n(x1 - c)} L${n(x1)} ${n(y0 + c)} V${n(y1 - c)} L${n(x1 - c)} ${n(y1)}
      H${n(x0 + c)} L${n(x0)} ${n(y1 - c)} Z`} />
    <circle class="lamp green"
            cx=${n(x - away * pitch)} cy=${n(middle)} r=${lamp} />
    <circle class="lamp red"
            cx=${n(x)} cy=${n(middle)} r=${lamp} />
    <circle class="lamp amber"
            cx=${n(x + away * pitch)} cy=${n(middle)} r=${lamp} />
  `;
}

/**
 * A deliberate track end: the buffer stop that makes a missing wire a visible
 * error rather than a silently terminal block.
 *
 * The stub is cut square rather than round-capped, so it stays inside the bar
 * instead of bulging past it. The cut at the pin end shows nothing: the pin
 * covers it in edit mode, and in run mode the incoming wire's round cap does.
 */
function terminal(on: Lit, end: End): SVGTemplateResult {
  const p = anchorIn("terminal", "P");
  const bar = { x: TERMINAL.stub, y: p.y };
  return svg`
    ${track("track cut", path(end("P"), bar), on())}
    <path class="buffer" d=${`M${n(bar.x)} ${n(bar.y - TERMINAL.bar.h / 2)}
      V${n(bar.y + TERMINAL.bar.h / 2)}`} />
  `;
}

/**
 * Paired by label with another portal somewhere else on the drawing.
 *
 * The mouth is the stub cut off at an angle, and two strokes
 * carrying on past it at that same lean. The cut is a clip rather than a filled
 * shape, so the stub is ordinary track that lights and widens like the rest of
 * it rather than a solid the sheet shows through nothing of. The stroke runs a
 * track width past the cut, which is what the clip needs to have something to
 * cut at every height across the track.
 */
function portal(on: Lit, end: End): SVGTemplateResult {
  const p = anchorIn("portal", "P");
  const { first, apart } = PORTAL.mouth;
  return svg`
    ${track("track", path(end("P"), { x: PORTAL.stub + W, y: p.y }), on(), `url(#${MOUTH})`)}
    ${[first, first + apart].map(
      (across) => svg`<path class="portal-mouth" d=${leaning(across, p.y)} />`,
    )}
  `;
}

/** A stroke at the mouth's lean, crossing the track's centreline at `across`
 *  and running `reach` either side of it. */
function leaning(across: number, y: number): string {
  const { reach } = PORTAL.mouth;
  const dx = PORTAL.lean * reach;
  return `M${n(across - dx)} ${n(y - reach)} L${n(across + dx)} ${n(y + reach)}`;
}

/** The id of the clip that cuts a portal's stub off at the mouth. */
const MOUTH = "portal-cut";

/**
 * What the artwork needs defined once per SVG root, which is the portal's cut.
 * A drawing may hold several portals and the palette draws another, so the
 * definition cannot live inside the symbol: the canvas puts this in its `defs`
 * and the palette in one hidden `svg` of its own.
 */
export const DEFS: SVGTemplateResult = svg`
  <clipPath id=${MOUTH} clipPathUnits="userSpaceOnUse">
    <path d=${`M-1 -1 L${n(cutAt(-1))} -1 L${n(cutAt(2))} 2 L-1 2 Z`} />
  </clipPath>
`;

/** Where the mouth's cut crosses a height, on the lean it shares with the two
 *  strokes beyond it. A portal's pin is always at `(0, 0.5)`. */
function cutAt(y: number): number {
  return PORTAL.stub + PORTAL.lean * (y - 0.5);
}

/** Drawn only when a transit lights it. In edit mode the canvas already puts a
 *  pin on the bend, and a dot under it would show as nothing but a ring around
 *  it (#59); run mode, where pins are hidden, lights the whole drawing and gets
 *  its dot back. */
function bend(on: Lit): SVGTemplateResult {
  const lighting = on();
  if (lighting === undefined) return svg``;
  const { claim, colour } = lighting;
  const p = anchorIn("pin", "P");
  return svg`<circle class=${`bend lit${claim === undefined ? "" : ` ${claim}`}`}
    style=${claim === undefined ? nothing : trainStyle(colour)}
    cx=${p.x} cy=${p.y} r=${BEND} />`;
}

/**
 * Each road drawn from the toe, so lighting the diverging leg lights the way
 * a train actually takes rather than the curve beyond the frog. The straight
 * road is the one straight stroke and the diverging road a curve, so the
 * drawing shows which is which. The frog is the middle of the straight road.
 */
function turnout(
  spec: SymbolSpec,
  on: Lit,
  set: Against,
  end: End,
): SVGTemplateResult {
  const p = (pin: string) => anchorIn("turnout", pin, spec.rot);
  const frog = middle(p("toe"), p("straight"));
  return svg`${roads(
    on,
    [
      { legs: ["straight"], d: path(end("toe"), end("straight")) },
      { legs: ["diverging"], d: curve(frog, end("toe"), end("diverging")) },
    ],
    set,
  )}`;
}

/**
 * A crossing, a slip, or one of the two 90 degree crossings: the same drawing
 * from the same four pins, differing only in where those pins are.
 *
 * Each leg the library declares is one stroke between its two pins: a through
 * route, `a` or `b`, straight across the frog, and a slip road the curve a
 * turnout's diverging road is.
 */
function crossed(
  kind: LibraryKind,
  on: Lit,
  set: Against,
  end: End,
): SVGTemplateResult {
  const p = (pin: string) => anchorIn(kind, pin);
  const frog = middle(p("a1"), p("a2"));
  const legs = TRANSITS[kind] as Record<string, readonly [string, string]>;
  return svg`${roads(
    on,
    Object.entries(legs).map(([leg, [from, to]]) => ({
      legs: [leg],
      d:
        THROUGH.has(leg)
          ? path(end(from), end(to))
          : curve(frog, end(from), end(to)),
    })),
    set,
  )}`;
}

/**
 * A road that turns 45 degrees at the frog: in line with one leg to `CURVE`
 * short of the frog, one quadratic curve with the frog as its control point
 * to `CURVE` past it, then in line with the other leg. It leaves and meets
 * both pins in line, so a wire carrying on from either does not kink.
 */
function curve(frog: Point, from: Ending, to: Ending): string {
  const near = (pin: Point): Point => {
    const along = unit(frog, pin);
    return { x: frog.x + along.x * CURVE, y: frog.y + along.y * CURVE };
  };
  const [a, b] = [near(from.at), near(to.at)];
  return `${leave(from)} L${n(a.x)} ${n(a.y)}
    Q${n(frog.x)} ${n(frog.y)} ${n(b.x)} ${n(b.y)} ${arrive(to)}`;
}

/**
 * The roads of a symbol, drawn in layers: those set against first, then the
 * unlit, then the lit, and on a run the lit from the weakest claim to the
 * strongest, so a wider line is always over a thinner one. Legs share track
 * where they meet, and a faint stroke over a solid one, or an unlit over a
 * lit, would hide half of it. Sorting is stable, so roads of one layer keep
 * the order they are written in.
 */
function roads(
  on: Lit,
  drawn: { legs: string[]; d: string }[],
  set: Against = NEITHER,
): SVGTemplateResult[] {
  const layer = (legs: string[]) => {
    if (set(legs)) return 0;
    const lighting = on(...legs);
    if (lighting === undefined) return 1;
    return lighting.claim === undefined ? 2 : 2 + CLAIMS.length - CLAIMS.indexOf(lighting.claim);
  };
  return [...drawn]
    .sort((a, b) => layer(a.legs) - layer(b.legs))
    .map(({ legs, d }) =>
      track(`track${set(legs) ? " against" : ""}`, d, on(...legs)),
    );
}

/** A stroke from one point to another, in the symbol's own coordinates.
 *  Either may be an ending, whose half corner the stroke carries on round. */
function path(from: Point | Ending, to: Point | Ending): string {
  return `${leave(from)} ${arrive(to)}`;
}

/** Where a stroke begins: at a point, or at the far end of an ending's half
 *  corner, coming round it. */
function leave(from: Point | Ending): string {
  if (!("at" in from)) return `M${n(from.x)} ${n(from.y)}`;
  const { at, corner } = from;
  if (corner === undefined) return `M${n(at.x)} ${n(at.y)}`;
  const [control, mid] = corner;
  return `M${n(mid.x)} ${n(mid.y)} Q${n(control.x)} ${n(control.y)} ${n(at.x)} ${n(at.y)}`;
}

/** Where a stroke ends: at a point, or round an ending's half corner. */
function arrive(to: Point | Ending): string {
  if (!("at" in to)) return `L${n(to.x)} ${n(to.y)}`;
  const { at, corner } = to;
  if (corner === undefined) return `L${n(at.x)} ${n(at.y)}`;
  const [control, mid] = corner;
  return `L${n(at.x)} ${n(at.y)} Q${n(control.x)} ${n(control.y)} ${n(mid.x)} ${n(mid.y)}`;
}

function middle(a: Point, b: Point): Point {
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}

/** Path data reads better without a float's tail, and nothing here is drawn
 *  to more than a thousandth of a square. */
export function n(value: number): number {
  return Math.round(value * 1000) / 1000;
}

/**
 * A widget's face (#939), the same in the editor and on a run, with no box,
 * name or kind round it.
 *
 * - A text widget is its words alone, run from its cell the way `align` says.
 *   On a run they are the row, else the default, else nothing, the row's ANSI
 *   bold and colours as runs of their own (`ansi`). In the editor they are
 *   the default, its codes read as on a run, or the name and a question mark
 *   in the hint's colour where there is none (`editorRuns`). Nothing cuts
 *   them but the canvas's edge.
 * - A button is a ring round a disc.
 * - A toggle is a rounded track with a knob: at the right on a green track
 *   for `on`, at the left for `off`, and in the middle where the position is
 *   not known (`togglePosition`). The editor has no rows, so it shows the
 *   default, or `off` where there is none.
 */
export function widgetFace(
  name: string,
  spec: WidgetSpec,
  running: boolean,
  row?: string,
): SVGTemplateResult {
  const [c, r] = spec.at;
  if (spec.kind === "button") {
    return svg`
      <circle class="widget-ring" cx=${c + 0.5} cy=${r + 0.5} r=${WIDGET.ring}
              stroke-width=${WIDGET.ringWidth} />
      <circle class="widget-disc" cx=${c + 0.5} cy=${r + 0.5} r=${WIDGET.disc} />
    `;
  }
  if (spec.kind === "toggle") {
    const position = running
      ? togglePosition(spec, row)
      : (togglePosition(spec, undefined) ?? "off");
    const { x, y, w, h } = WIDGET.track;
    const knob =
      position === "on" ? x + w - h / 2 : position === "off" ? x + h / 2 : x + w / 2;
    return svg`
      <rect class=${`widget-track ${position ?? "unknown"}`}
            x=${c + x} y=${r + y} width=${w} height=${h} rx=${h / 2} />
      <circle class="widget-knob" cx=${c + knob} cy=${r + 0.5} r=${WIDGET.knob} />
    `;
  }
  const runs: Run[] = running ? ansi(row ?? spec.default ?? "") : editorRuns(name, spec);
  const align = spec.align ?? "center";
  const x = align === "left" ? c : align === "right" ? c + 1 : c + 0.5;
  const anchor = align === "left" ? "start" : align === "right" ? "end" : "middle";
  return svg`
    <text class=${!running && ansi(spec.default ?? "").length === 0 ? "widget-text placeholder" : "widget-text"}
          x=${x} y=${r + 0.5} text-anchor=${anchor} dominant-baseline="central"
          font-size=${WIDGET.text[spec.text ?? "normal"]}>${runs.map(
            ({ text, bold, colour }) =>
              svg`<tspan class=${[bold ? "bold" : "", colour ?? ""].join(" ").trim()}>${text}</tspan>`,
          )}</text>
  `;
}

/** A widget of a kind as its palette tile and the ghost on its way from the
 *  palette show it: a new one's face, a text widget's words the word `text`,
 *  drawn at `size` — `normal`, what a new one starts at, unless the caller
 *  asks for another (the palette's tile asks for `large`, #1279). */
export function widgetSample(
  kind: WidgetKind,
  at: [number, number],
  size: NonNullable<WidgetSpec["text"]> = "normal",
): SVGTemplateResult {
  const spec = newWidget(kind, kind, at);
  if (kind === "text") {
    spec.default = "text";
    spec.text = size;
  }
  return widgetFace(kind, spec, false);
}

/**
 * The palette's groups, the ones EDITOR.md's table documents: grouped by what
 * the symbols are rather than by their names, which is how `PLACEABLE` comes
 * out of the generator. A test asserts the groups hold the same kinds, so a
 * new placeable kind has to be given a home here rather than appearing
 * wherever the alphabet puts it.
 *
 * A group is a list of rows, two tiles to a row at most. The block stands
 * alone, being the only symbol that is a place rather than a way through one.
 * Then the points, the turnout on a row of its own so the two slips sit side
 * by side; the crossings, the two 90 degree ones side by side; and the two
 * ends of a drawing: where track stops and where it leaves the sheet.
 */
export const PALETTE: readonly (readonly (readonly Kind[])[])[] = [
  [["block"]],
  [["turnout"], ["single_slip", "double_slip"]],
  [["crossing_90", "crossing_90d"], ["crossing"]],
  [["terminal", "portal"]],
];

/** What a palette tile shows: the symbol at its default placement. */
export const TILE: Record<Kind, SymbolSpec> = {
  block: { kind: "block" },
  terminal: { kind: "terminal" },
  portal: { kind: "portal" },
  pin: { kind: "pin" },
  turnout: { kind: "turnout" },
  crossing: { kind: "crossing" },
  crossing_90: { kind: "crossing_90" },
  crossing_90d: { kind: "crossing_90d" },
  single_slip: { kind: "single_slip" },
  double_slip: { kind: "double_slip" },
};
