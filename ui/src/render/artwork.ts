/**
 * What each symbol looks like, hand-written against the generated pin names
 * (#52) in the symbol's own coordinates: one square is one unit, the origin is
 * the top left of the unturned footprint, and `transformOf` puts it on the
 * grid. Legs end exactly on the anchors `geometry.ts` gives, so the artwork
 * and the wires meet.
 *
 * A crossing or a slip is drawn as a diamond and comes in several appearances,
 * because wires meet a symbol at whatever angle their pins give them and a
 * crossing drawn for legs at 0 and 15 degrees is not a rotation of one drawn
 * for 15 and 30. An appearance changes the strokes between the pins and never
 * the pins, so choosing one cannot resize a symbol or change what derives.
 */

import { svg, type SVGTemplateResult } from "lit";

import type { Kind } from "../symbols.generated.js";
import type { SymbolSpec } from "../model/drawing.js";
import { footprintOf } from "../model/geometry.js";
import { WHOLE } from "../model/inspect.js";

/** The appearances each angled kind offers, the first being its default. */
export const APPEARANCES: Record<string, string[]> = {
  crossing: ["x", "shallow"],
  single_slip: ["x", "shallow"],
  double_slip: ["x", "shallow"],
};

/** The two through routes of a diamond, per appearance. `shallow` runs each
 *  route level into the middle and out again, which reads as legs meeting at a
 *  shallower angle than the plain crossing. */
const ROUTES: Record<string, { a: string; b: string }> = {
  x: { a: "M0 1.5 L2 0.5", b: "M0 0.5 L2 1.5" },
  shallow: {
    a: "M0 1.5 Q0.7 1.5 1 1 Q1.3 0.5 2 0.5",
    b: "M0 0.5 Q0.7 0.5 1 1 Q1.3 1.5 2 1.5",
  },
};

const SLIP_LOW = "M0 1.5 Q1 1.1 2 1.5"; // a1 to b2, around the foot of the diamond
const SLIP_HIGH = "M0 0.5 Q1 0.9 2 0.5"; // b1 to a2, around the head of it

const NONE: ReadonlySet<string> = new Set();

/**
 * Draw a symbol, with the legs a chosen transit takes lit.
 *
 * The way is lit leg by leg rather than symbol by symbol (EDITOR.md), so each
 * leg is one stroke of its own from pin to pin: the turnout's diverging road
 * runs from the toe, not from where it leaves the straight, and a diamond's
 * two routes and its slips are four separate paths. `WHOLE` lights every
 * stroke, which is what a symbol with no legs the artwork draws — a joiner, a
 * block end, the generic box — has to be lit by.
 */
export function artwork(
  spec: SymbolSpec,
  lit: ReadonlySet<string> = NONE,
): SVGTemplateResult {
  const on = (leg: string) => (lit.has(WHOLE) || lit.has(leg) ? " lit" : "");
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
      return diamond(spec, on);
    case "single_slip":
      return diamond(spec, on, { slip: SLIP_LOW });
    case "double_slip":
      return diamond(spec, on, { slip_1: SLIP_LOW, slip_2: SLIP_HIGH });
  }
}

/** Whether a leg is lit, as the class suffix a stroke takes. */
type Lit = (leg: string) => string;

/** Which appearance a symbol is drawn in, the default where it says nothing. */
export function appearanceOf(spec: SymbolSpec): string {
  const offered = APPEARANCES[spec.kind] ?? [];
  const chosen = spec.angle ?? "";
  return offered.includes(chosen) ? chosen : (offered[0] ?? "x");
}

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

/** A block carries a signal and a sensor at each end, always, so both are
 *  part of the artwork rather than anything placed (store/DRAWING.md). */
function block(on: Lit): SVGTemplateResult {
  return svg`
    <path class=${`track${on(WHOLE)}`} d="M0 0.5 H2" />
    <rect class=${`block-body${on(WHOLE)}`} x="0.2" y="0.32"
          width="1.6" height="0.36" rx="0.08" />
    <path class="mast" d="M0.42 0.32 V0.14" />
    <circle class="signal" cx="0.42" cy="0.1" r="0.08" />
    <path class="mast" d="M1.58 0.68 V0.86" />
    <circle class="signal" cx="1.58" cy="0.9" r="0.08" />
    <rect class="sensor" x="0.28" y="0.4" width="0.1" height="0.2" />
    <rect class="sensor" x="1.62" y="0.4" width="0.1" height="0.2" />
  `;
}

/** A deliberate track end: the buffer stop that makes a missing wire a
 *  visible error rather than a silently terminal block. */
function terminal(on: Lit): SVGTemplateResult {
  return svg`
    <path class=${`track${on(WHOLE)}`} d="M0 0.5 H0.62" />
    <path class="stop" d="M0.62 0.28 V0.72" />
    <path class="stop" d="M0.5 0.36 L0.62 0.5 L0.5 0.64" />
  `;
}

/** Paired by label with another portal somewhere else on the drawing. */
function portal(on: Lit): SVGTemplateResult {
  return svg`
    <path class=${`track${on(WHOLE)}`} d="M0 0.5 H0.4" />
    <path class="portal-mouth" d="M0.4 0.24 L0.9 0.5 L0.4 0.76 Z" />
  `;
}

function bend(on: Lit): SVGTemplateResult {
  return svg`<circle class=${`bend${on(WHOLE)}`} cx="0" cy="0.5" r="0.07" />`;
}

/** Each road drawn from the toe, so lighting the diverging leg lights the way
 *  a train actually takes rather than the curve beyond the frog. */
function turnout(on: Lit): SVGTemplateResult {
  return svg`${roads(on, [
    { leg: "straight", d: "M0 0.5 H2" },
    { leg: "diverging", d: "M0 0.5 H0.6 Q1.15 0.5 1.5 0" },
  ])}`;
}

function diamond(
  spec: SymbolSpec,
  on: Lit,
  slips: Record<string, string> = {},
): SVGTemplateResult {
  const routes = ROUTES[appearanceOf(spec)] ?? ROUTES.x!;
  return svg`${roads(on, [
    { leg: "a", d: routes.a },
    { leg: "b", d: routes.b },
    ...Object.entries(slips).map(([leg, d]) => ({ leg, d, slip: true })),
  ])}`;
}

/** The roads of a symbol, lit ones last: legs share track where they meet,
 *  and a lit stroke drawn under an unlit one would be half hidden. Sorting is
 *  stable, so unlit roads keep the order they are written in. */
function roads(
  on: Lit,
  drawn: { leg: string; d: string; slip?: boolean }[],
): SVGTemplateResult[] {
  return [...drawn]
    .sort((a, b) => (on(a.leg) === "" ? 0 : 1) - (on(b.leg) === "" ? 0 : 1))
    .map(
      ({ leg, d, slip }) =>
        svg`<path class=${`track${slip ? " slip" : ""}${on(leg)}`} d=${d} />`,
    );
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
  single_slip: { kind: "single_slip" },
  double_slip: { kind: "double_slip" },
};
