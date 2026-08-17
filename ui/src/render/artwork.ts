/**
 * What each symbol looks like, hand-written against the generated pin names
 * (#52) in the symbol's own coordinates: one square is one unit, the origin is
 * the top left of the unturned footprint, and `transformOf` puts it on the
 * grid.
 *
 * Every leg is drawn from the anchors `geometry.ts` gives, so the artwork and
 * the wires meet by construction, and every dimension that is not an anchor is
 * a named constant in `units.ts`. Each kind has exactly one appearance
 * (EDITOR.md#symbol-geometry): diagonal legs are always 45 degrees, and a wire
 * meeting one at another angle reads as a rounded bend rather than a kink,
 * because every stroke ends in a round cap.
 */

import { svg, type SVGTemplateResult } from "lit";

import { TRANSITS, type Kind, type LibraryKind } from "../symbols.generated.js";
import type { SymbolSpec } from "../model/drawing.js";
import { anchorIn, footprintOf, type Point } from "../model/geometry.js";
import { WHOLE } from "../model/inspect.js";
import { BEND, BLOCK, PORTAL, SLIP, TERMINAL } from "./units.js";

const NONE: ReadonlySet<string> = new Set();

/**
 * Draw a symbol, with the legs a chosen transit takes lit.
 *
 * The way is lit leg by leg rather than symbol by symbol (EDITOR.md), so a
 * stroke knows which legs run over it: a crossing's route is two half-strokes
 * meeting at the frog, and a slip lights its entry half, its tick and its exit
 * half. `WHOLE` lights every stroke, which is what a symbol with no legs the
 * artwork draws — a joiner, a block end, the generic box — is lit by.
 */
export function artwork(
  spec: SymbolSpec,
  lit: ReadonlySet<string> = NONE,
): SVGTemplateResult {
  const on: Lit = (...legs) =>
    lit.has(WHOLE) || legs.some((leg) => lit.has(leg)) ? " lit" : "";
  switch (spec.kind) {
    case "connection":
      return opaque(spec, lit);
    case "block":
      return block(on);
    case "terminal":
      return terminal(on);
    case "portal":
      return portal(on);
    case "pin":
      return bend(on);
    case "turnout":
      return turnout(on);
    case "crossing":
    case "crossing_90":
    case "crossing_90d":
      return crossed(spec.kind, on);
    case "single_slip":
      return crossed(spec.kind, on, ["slip"]);
    case "double_slip":
      return crossed(spec.kind, on, ["slip_1", "slip_2"]);
  }
}

/** Whether any of the legs running over a stroke is lit, as the class suffix
 *  the stroke takes. */
type Lit = (...legs: string[]) => string;

/** The generic connection symbol: a box with the pins it declares and no
 *  turnout detail, which is exactly what it knows about itself. It is legacy
 *  and not on the palette; drawings that still have one have to open
 *  (store/DRAWING.md). */
/** The box lights whenever any of its legs does. It declares real transits,
 *  so a way through it names one — but the box draws no leg to light, having
 *  no fixed pin set and no turnout detail to show. */
function opaque(spec: SymbolSpec, lit: ReadonlySet<string>): SVGTemplateResult {
  const { w, h } = footprintOf(spec);
  return svg`
    <rect class=${`opaque${lit.size > 0 ? " lit" : ""}`} x="0.15" y="0.15"
          width=${w - 0.3} height=${h - 0.3} rx="0.12" />
  `;
}

/**
 * A block: a rectangle with a 1G track stub each side, a signal on each stub,
 * and a plus at the rectangle's lower corner on the A side.
 *
 * The signal is part of what a block is rather than anything placed
 * (store/DRAWING.md), and the pair is point symmetric — above the track at A,
 * below at B — so a rotation or a flip reads naturally. Sensors are not drawn
 * and nothing is written outside the rectangle; the label goes inside it, and
 * the canvas draws that upright, outside the turned group.
 */
function block(on: Lit): SVGTemplateResult {
  const [a, b] = [anchorIn("block", "A"), anchorIn("block", "B")];
  const { x, y, w, h } = BLOCK.body;
  const { at, mast, head } = BLOCK.signal;
  const { arm } = BLOCK.plus;
  return svg`
    <path class=${`track${on()}`} d=${path(a, { x, y: a.y })} />
    <path class=${`track${on()}`} d=${path({ x: x + w, y: b.y }, b)} />
    <rect class=${`block-body${on()}`}
          x=${x} y=${y} width=${w} height=${h} />
    ${signal(a.x + at, a.y, -1, mast, head)}
    ${signal(b.x - at, b.y, 1, mast, head)}
    <path class="mark" d=${`M${n(BLOCK.plus.x - arm)} ${n(BLOCK.plus.y)}
      h${n(2 * arm)} M${n(BLOCK.plus.x)} ${n(BLOCK.plus.y - arm)}
      v${n(2 * arm)}`} />
  `;
}

/** A short mast with a round head, standing away from the track: `away` is -1
 *  above it and +1 below. */
function signal(
  x: number,
  y: number,
  away: number,
  mast: number,
  head: number,
): SVGTemplateResult {
  const top = y + away * mast;
  return svg`
    <path class="mast" d=${`M${n(x)} ${n(y)} V${n(top)}`} />
    <circle class="signal" cx=${n(x)} cy=${n(top + away * head)} r=${head} />
  `;
}

/** A deliberate track end: the buffer stop that makes a missing wire a
 *  visible error rather than a silently terminal block. */
function terminal(on: Lit): SVGTemplateResult {
  const p = anchorIn("terminal", "P");
  const bar = { x: TERMINAL.stub, y: p.y };
  return svg`
    <path class=${`track${on()}`} d=${path(p, bar)} />
    <path class="stop" d=${`M${n(bar.x)} ${n(bar.y - TERMINAL.bar.h / 2)}
      V${n(bar.y + TERMINAL.bar.h / 2)}`} />
  `;
}

/** Paired by label with another portal somewhere else on the drawing. The
 *  label is the symbol's meaning, so the canvas draws it beside the mouth in
 *  both modes: matching a pair by eye is how a typo in one is found. */
function portal(on: Lit): SVGTemplateResult {
  const p = anchorIn("portal", "P");
  const { tip, half } = PORTAL.mouth;
  return svg`
    <path class=${`track${on()}`} d=${path(p, { x: PORTAL.stub, y: p.y })} />
    <path class="portal-mouth" d=${`M${n(PORTAL.stub)} ${n(p.y - half)}
      L${n(tip)} ${n(p.y)} L${n(PORTAL.stub)} ${n(p.y + half)} Z`} />
  `;
}

function bend(on: Lit): SVGTemplateResult {
  const p = anchorIn("pin", "P");
  return svg`<circle class=${`bend${on()}`} cx=${p.x} cy=${p.y} r=${BEND} />`;
}

/** Each road drawn from the toe, so lighting the diverging leg lights the way
 *  a train actually takes rather than the curve beyond the frog. The diverging
 *  road is the one 45 degree leg ending on a face centre, which is how
 *  turnouts stack between parallel station tracks. */
function turnout(on: Lit): SVGTemplateResult {
  const p = (pin: string) => anchorIn("turnout", pin);
  return svg`${roads(on, [
    { legs: ["straight"], d: path(p("toe"), p("straight")) },
    { legs: ["diverging"], d: path(p("toe"), p("diverging")) },
  ])}`;
}

/**
 * A crossing, a slip, or one of the two 90 degree crossings: the same drawing
 * from the same four pins, differing only in where those pins are.
 *
 * Each route is two half-strokes meeting at the frog, and a slip's tick
 * bridges its two legs there. Which legs run over a half-stroke is read off
 * the library: every transit through the pin it ends at lights it, which is
 * what makes a lit slip its entry half, its tick and its exit half.
 */
function crossed(
  kind: LibraryKind,
  on: Lit,
  slips: string[] = [],
): SVGTemplateResult {
  const p = (pin: string) => anchorIn(kind, pin);
  const frog = middle(p("a1"), p("a2"));
  const legs = TRANSITS[kind] as Record<string, readonly [string, string]>;
  const over = (pin: string) =>
    Object.keys(legs).filter((leg) => legs[leg]!.includes(pin));
  return svg`${roads(on, [
    ...["a1", "a2", "b1", "b2"].map((pin) => ({
      legs: over(pin),
      d: path(p(pin), frog),
    })),
    ...slips.map((leg) => {
      const [from, to] = legs[leg]!;
      return {
        legs: [leg],
        d: path(toward(frog, p(from), SLIP), toward(frog, p(to), SLIP)),
      };
    }),
  ])}`;
}

/** The roads of a symbol, lit ones last: legs share track where they meet,
 *  and a lit stroke drawn under an unlit one would be half hidden. Sorting is
 *  stable, so unlit roads keep the order they are written in. */
function roads(
  on: Lit,
  drawn: { legs: string[]; d: string }[],
): SVGTemplateResult[] {
  return [...drawn]
    .sort(
      (a, b) => (on(...a.legs) === "" ? 0 : 1) - (on(...b.legs) === "" ? 0 : 1),
    )
    .map(({ legs, d }) => svg`<path class=${`track${on(...legs)}`} d=${d} />`);
}

/** A stroke from one point to another, in the symbol's own coordinates. */
function path(from: Point, to: Point): string {
  return `M${n(from.x)} ${n(from.y)} L${n(to.x)} ${n(to.y)}`;
}

function middle(a: Point, b: Point): Point {
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}

/** The point `away` from `from` along the line to `to`. */
function toward(from: Point, to: Point, away: number): Point {
  const span = Math.hypot(to.x - from.x, to.y - from.y);
  return {
    x: from.x + ((to.x - from.x) / span) * away,
    y: from.y + ((to.y - from.y) / span) * away,
  };
}

/** Path data reads better without a float's tail, and nothing here is drawn
 *  to more than a thousandth of a square. */
function n(value: number): number {
  return Math.round(value * 1000) / 1000;
}

/**
 * The palette's order, the one EDITOR.md's table documents: grouped by what
 * the symbols are rather than by their names, which is how `PLACEABLE` comes
 * out of the generator. A test asserts the two hold the same kinds, so a new
 * placeable kind has to be given a place here rather than appearing wherever
 * the alphabet puts it.
 */
export const PALETTE: readonly Kind[] = [
  "block",
  "terminal",
  "turnout",
  "crossing",
  "single_slip",
  "double_slip",
  "crossing_90",
  "crossing_90d",
  "portal",
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
