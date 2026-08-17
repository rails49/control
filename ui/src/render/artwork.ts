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
import { BEND, BLOCK, PORTAL, SLIP, TERMINAL, W } from "./units.js";

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
  const { at } = BLOCK.signal;
  const { arm } = BLOCK.plus;
  return svg`
    <path class=${`track${on()}`} d=${path(a, { x, y: a.y })} />
    <path class=${`track${on()}`} d=${path({ x: x + w, y: b.y }, b)} />
    <rect class=${`block-body${on()}`}
          x=${x} y=${y} width=${w} height=${h} />
    ${signal(a.x + at, a.y, -1)}
    ${signal(b.x - at, b.y, 1)}
    <path class="mark" d=${`M${n(BLOCK.plus.x - arm)} ${n(BLOCK.plus.y)}
      h${n(2 * arm)} M${n(BLOCK.plus.x)} ${n(BLOCK.plus.y - arm)}
      v${n(2 * arm)}`} />
  `;
}

/**
 * A signal standing clear of the track: the sample's plaque, a green lamp and a
 * red one, no mast.
 *
 * `away` is -1 above the track and +1 below, and it turns the whole signal, so
 * the lamp order reverses with it. The two signals of a block are one point
 * symmetric pair (EDITOR.md#symbol-geometry), which is what a rotation or a
 * flip of the block maps onto itself.
 */
function signal(x: number, y: number, away: -1 | 1): SVGTemplateResult {
  const { w, h, chamfer: c, gap, lamp, apart } = BLOCK.signal;
  const middle = y + away * (W / 2 + gap + h / 2);
  const [x0, x1] = [x - w / 2, x + w / 2];
  const [y0, y1] = [middle - h / 2, middle + h / 2];
  return svg`
    <path class="plaque" d=${`M${n(x0)} ${n(y0 + c)} L${n(x0 + c)} ${n(y0)}
      H${n(x1 - c)} L${n(x1)} ${n(y0 + c)} V${n(y1 - c)} L${n(x1 - c)} ${n(y1)}
      H${n(x0 + c)} L${n(x0)} ${n(y1 - c)} Z`} />
    <circle class="lamp clear"
            cx=${n(x + away * apart)} cy=${n(middle)} r=${lamp} />
    <circle class="lamp danger"
            cx=${n(x - away * apart)} cy=${n(middle)} r=${lamp} />
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
function terminal(on: Lit): SVGTemplateResult {
  const p = anchorIn("terminal", "P");
  const bar = { x: TERMINAL.stub, y: p.y };
  return svg`
    <path class=${`track cut${on()}`} d=${path(p, bar)} />
    <path class="stop" d=${`M${n(bar.x)} ${n(bar.y - TERMINAL.bar.h / 2)}
      V${n(bar.y + TERMINAL.bar.h / 2)}`} />
  `;
}

/**
 * Paired by label with another portal somewhere else on the drawing.
 *
 * The mouth is the sample's: the stub cut off at an angle, and two strokes
 * carrying on past it at that same lean. The cut is a clip rather than a filled
 * shape, so the stub is ordinary track that lights and widens like the rest of
 * it, and nothing is painted over the junction tint behind the symbol. The
 * stroke runs a track width past the cut, which is what the clip needs to have
 * something to cut at every height across the track.
 */
function portal(on: Lit): SVGTemplateResult {
  const p = anchorIn("portal", "P");
  const { first, apart } = PORTAL.mouth;
  return svg`
    <path class=${`track${on()}`} clip-path=${`url(#${MOUTH})`}
          d=${path(p, { x: PORTAL.stub + W, y: p.y })} />
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
  if (on() === "") return svg``;
  const p = anchorIn("pin", "P");
  return svg`<circle class="bend lit" cx=${p.x} cy=${p.y} r=${BEND} />`;
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
      return { legs: [leg], as: "tick", d: tick(frog, p(from), p(to)) };
    }),
  ])}`;
}

/**
 * A slip's tick: two strokes, one parallel to each of the two legs the road
 * joins, meeting where their offset lines cross.
 *
 * It falls in the obtuse sector between the two legs, which is the only pair a
 * slip road can join, so where the tick is says which road the symbol has. One
 * path rather than two, so the corner mitres itself and a lit slip is three
 * strokes: its entry half, its tick, its exit half.
 */
function tick(frog: Point, from: Point, to: Point): string {
  const u = unit(frog, from);
  const v = unit(frog, to);
  const into = unit(frog, { x: frog.x + u.x + v.x, y: frog.y + u.y + v.y });
  const corner = crossing(off(frog, u, into), u, off(frog, v, into), v);
  return `M${n(corner.x + u.x * SLIP.arm)} ${n(corner.y + u.y * SLIP.arm)}
    L${n(corner.x)} ${n(corner.y)}
    L${n(corner.x + v.x * SLIP.arm)} ${n(corner.y + v.y * SLIP.arm)}`;
}

/** A unit vector from one point toward another. */
function unit(from: Point, to: Point): Point {
  const span = Math.hypot(to.x - from.x, to.y - from.y);
  return { x: (to.x - from.x) / span, y: (to.y - from.y) / span };
}

/** The frog shifted `SLIP.off` off a leg, on the side `into` points: a point of
 *  the line the tick's stroke along that leg runs down. */
function off(frog: Point, along: Point, into: Point): Point {
  const dot = into.x * along.x + into.y * along.y;
  const away = unit(
    { x: 0, y: 0 },
    { x: into.x - dot * along.x, y: into.y - dot * along.y },
  );
  return { x: frog.x + away.x * SLIP.off, y: frog.y + away.y * SLIP.off };
}

/** Where two lines cross, each given as a point and a direction. */
function crossing(p: Point, u: Point, q: Point, v: Point): Point {
  const span =
    ((q.x - p.x) * v.y - (q.y - p.y) * v.x) / (u.x * v.y - u.y * v.x);
  return { x: p.x + u.x * span, y: p.y + u.y * span };
}

/** The roads of a symbol, lit ones last: legs share track where they meet,
 *  and a lit stroke drawn under an unlit one would be half hidden. Sorting is
 *  stable, so unlit roads keep the order they are written in. */
function roads(
  on: Lit,
  drawn: { legs: string[]; d: string; as?: string }[],
): SVGTemplateResult[] {
  return [...drawn]
    .sort(
      (a, b) => (on(...a.legs) === "" ? 0 : 1) - (on(...b.legs) === "" ? 0 : 1),
    )
    .map(
      ({ legs, d, as }) =>
        svg`<path class=${`${as ?? "track"}${on(...legs)}`} d=${d} />`,
    );
}

/** A stroke from one point to another, in the symbol's own coordinates. */
function path(from: Point, to: Point): string {
  return `M${n(from.x)} ${n(from.y)} L${n(to.x)} ${n(to.y)}`;
}

function middle(a: Point, b: Point): Point {
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
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
