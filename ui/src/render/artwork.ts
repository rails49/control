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

export function artwork(spec: SymbolSpec): SVGTemplateResult {
  switch (spec.kind) {
    case "block":
      return block();
    case "terminal":
      return terminal();
    case "portal":
      return portal();
    case "pin":
      return bend();
    case "turnout":
      return turnout();
    case "crossing":
      return diamond(spec);
    case "single_slip":
      return diamond(spec, [SLIP_LOW]);
    case "double_slip":
      return diamond(spec, [SLIP_LOW, SLIP_HIGH]);
  }
}

/** Which appearance a symbol is drawn in, the default where it says nothing. */
export function appearanceOf(spec: SymbolSpec): string {
  const offered = APPEARANCES[spec.kind] ?? [];
  const chosen = spec.angle ?? "";
  return offered.includes(chosen) ? chosen : (offered[0] ?? "x");
}

/** A block carries a signal and a sensor at each end, always, so both are
 *  part of the artwork rather than anything placed (store/DRAWING.md). */
function block(): SVGTemplateResult {
  return svg`
    <path class="track" d="M0 0.5 H2" />
    <rect class="block-body" x="0.2" y="0.32" width="1.6" height="0.36" rx="0.08" />
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
function terminal(): SVGTemplateResult {
  return svg`
    <path class="track" d="M0 0.5 H0.62" />
    <path class="stop" d="M0.62 0.28 V0.72" />
    <path class="stop" d="M0.5 0.36 L0.62 0.5 L0.5 0.64" />
  `;
}

/** Paired by label with another portal somewhere else on the drawing. */
function portal(): SVGTemplateResult {
  return svg`
    <path class="track" d="M0 0.5 H0.4" />
    <path class="portal-mouth" d="M0.4 0.24 L0.9 0.5 L0.4 0.76 Z" />
  `;
}

function bend(): SVGTemplateResult {
  return svg`<circle class="bend" cx="0" cy="0.5" r="0.07" />`;
}

function turnout(): SVGTemplateResult {
  return svg`
    <path class="track" d="M0 0.5 H2" />
    <path class="track" d="M0.6 0.5 Q1.15 0.5 1.5 0" />
  `;
}

function diamond(spec: SymbolSpec, slips: string[] = []): SVGTemplateResult {
  const routes = ROUTES[appearanceOf(spec)] ?? ROUTES.x!;
  return svg`
    <path class="track" d=${routes.a} />
    <path class="track" d=${routes.b} />
    ${slips.map((slip) => svg`<path class="track slip" d=${slip} />`)}
  `;
}

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
