/**
 * What is drawn for a drawing's wires: each wire's straight part, and a curve
 * wherever a run changes direction (EDITOR.md#drawing-wires, which states the
 * rules).
 *
 * A wire is a pair of pins and carries no geometry, so all of this is worked
 * out from where the pins are, on every render. Nothing here is stored and
 * nothing derives from it.
 */

import {
  pinName,
  symbolOf,
  wireKey,
  wirePins,
  type Drawing,
  type PinRef,
} from "../model/drawing.js";
import { legOf, localOf, unit, type Point } from "../model/geometry.js";
import { CLAIMS } from "../model/panel.js";
import { pointOf, type Shift } from "../model/under.js";
import { n, straightAt, type Cut, type Lighting } from "./artwork.js";
import { CURVE } from "./units.js";

/** One stroke of the wires' drawing. */
export interface Stroke {
  from: Point;
  to: Point;
  /** The control point of a curve. Undefined on a wire's straight part. */
  round: Point | undefined;
  /** How the stroke is lit. Undefined where it is not. */
  lit: Lighting | undefined;
}

export interface Wiring {
  /** The wires' straight parts in the drawing's order, then the curves. */
  strokes: Stroke[];
  /** Symbol → pin → what a corner at that pin takes from the symbol, which
   *  draws its own half of the curve (`artwork`). */
  cuts: Map<string, Map<string, Cut>>;
}

/** A wire as it is laid between its two pins. */
interface Laid {
  pins: [PinRef, PinRef];
  at: [Point, Point];
  length: number;
  /** How far short of each pin its straight part stops. */
  short: [number, number];
  lit: Lighting | undefined;
}

/** One end of a laid wire. */
interface End {
  wire: Laid;
  end: 0 | 1;
}

/** What meets at one place on the sheet. */
interface Meeting {
  at: Point;
  /** The wired pins there: one, or several where a pin sits on a pin. */
  pins: Set<PinRef>;
  /** The ends of the wires that leave the place. */
  ends: End[];
  /** The wires of no length joining its pins. */
  joins: Laid[];
  /** How the most strongly lit wire there is lit. */
  lit: Lighting | undefined;
}

/** One of the tracks meeting at a place. */
interface Side {
  /** The direction it runs in from the place. */
  toward: Point;
  /** How far along it a corner may run. */
  reach: number;
  /** The pin whose symbol's track it is, or undefined for a wire. */
  pin: PinRef | undefined;
  /** The wire end it is, or undefined for a symbol's track. */
  end: End | undefined;
}

/** A turn or a length smaller than this is none: the arithmetic's noise. */
const NOTHING = 1e-6;

/**
 * The strokes of a drawing's wires, and what their corners take from the
 * symbols.
 *
 * Where exactly two tracks meet at a place and are not in line, both stop
 * short of it and a quadratic curve with the place as its control point joins
 * them. A track is a wire, or a symbol's own at one of its wired pins
 * (`legOf`). A wire's part of the curve is a stroke here; a symbol's is its
 * half, which the symbol draws itself from the entry in `cuts`. A curve
 * between two wires is one stroke, lit as the more strongly lit one is.
 *
 * `lit` is how each lit wire is lit, by `wireKey`, and `shift` is how far a
 * drag in flight has moved each symbol.
 */
export function wiring(
  drawing: Drawing,
  lit: ReadonlyMap<string, Lighting>,
  shift?: Shift,
): Wiring {
  const laid: Laid[] = [];
  const meetings = new Map<string, Meeting>();
  for (const wire of drawing.wires) {
    const pins = wirePins(wire);
    const from = pointOf(drawing, pins[0], shift);
    const to = pointOf(drawing, pins[1], shift);
    if (from === null || to === null) continue;
    const one: Laid = {
      pins,
      at: [from, to],
      length: Math.hypot(to.x - from.x, to.y - from.y),
      short: [0, 0],
      lit: lit.get(wireKey(wire)),
    };
    laid.push(one);
    pins.forEach((pin, index) => {
      const end = index as 0 | 1;
      const place = `${n(one.at[end].x)},${n(one.at[end].y)}`;
      const met: Meeting = meetings.get(place) ?? {
        at: one.at[end],
        pins: new Set(),
        ends: [],
        joins: [],
        lit: undefined,
      };
      met.pins.add(pin);
      met.lit = stronger(met.lit, one.lit);
      if (one.length >= NOTHING) met.ends.push({ wire: one, end });
      else if (end === 0) met.joins.push(one);
      meetings.set(place, met);
    });
  }

  const curves: Stroke[] = [];
  const passed = new Set<Laid>();
  const cuts: Wiring["cuts"] = new Map();
  const cut = (pin: PinRef, taken: Cut) => {
    const symbol = symbolOf(pin);
    const pins = cuts.get(symbol) ?? new Map<string, Cut>();
    cuts.set(symbol, pins.set(pinName(pin), taken));
  };
  /** A point of the sheet in the coordinates of the symbol a pin is on. */
  const own = (pin: PinRef, at: Point): Point => {
    const symbol = symbolOf(pin);
    const moved = shift?.(symbol) ?? { x: 0, y: 0 };
    return localOf(drawing.symbols[symbol]!, {
      x: at.x - moved.x,
      y: at.y - moved.y,
    });
  };
  for (const met of meetings.values()) {
    const sides = sidesOf(drawing, met);
    if (sides.length !== 2) continue;
    const [one, two] = sides as [Side, Side];
    if (!turns(one.toward, two.toward)) continue;
    const [a, b] = [far(one, two), far(two, one)];
    if (Math.min(a, b) < NOTHING) continue;
    const from = along(met.at, one.toward, a);
    const to = along(met.at, two.toward, b);
    const mid = {
      x: (from.x + 2 * met.at.x + to.x) / 4,
      y: (from.y + 2 * met.at.y + to.y) / 4,
    };
    // Two wires share one curve. With a symbol's track on either side the
    // curve is split at its middle, and each side has its own half.
    const split = one.pin !== undefined || two.pin !== undefined;
    if (!split) curves.push({ from, round: met.at, to, lit: met.lit });
    const halves: [Side, number, Point][] = [
      [one, a, from],
      [two, b, to],
    ];
    for (const [side, by, stop] of halves) {
      if (side.end !== undefined) side.end.wire.short[side.end.end] = by;
      if (side.pin !== undefined) {
        cut(side.pin, { by, mid: own(side.pin, mid) });
      } else if (split) {
        const round = { x: (met.at.x + stop.x) / 2, y: (met.at.y + stop.y) / 2 };
        curves.push({ from: mid, round, to: stop, lit: met.lit });
      }
    }
    for (const pin of met.pins) {
      if (drawing.symbols[symbolOf(pin)]!.kind === "pin") {
        cut(pin, { by: Math.min(a, b), mid: undefined });
      }
    }
    for (const wire of met.joins) passed.add(wire);
  }

  const lines = laid
    .filter((wire) => !passed.has(wire) && !usedUp(wire))
    .map(({ at: [from, to], length, short, lit }): Stroke => {
      const run = length < NOTHING ? { x: 0, y: 0 } : unit(from, to);
      return {
        from: along(from, run, short[0]),
        to: along(to, run, -short[1]),
        round: undefined,
        lit,
      };
    });
  return { strokes: [...lines, ...curves], cuts };
}

/** The tracks meeting at a place: the symbols' own first, then the wires in
 *  the drawing's order. A bend has no track. */
function sidesOf(drawing: Drawing, met: Meeting): Side[] {
  const sides: Side[] = [];
  for (const pin of met.pins) {
    const spec = drawing.symbols[symbolOf(pin)]!;
    const leg = legOf(spec, pinName(pin));
    if (leg === null) continue;
    sides.push({
      toward: { x: -leg.x, y: -leg.y },
      reach: straightAt(spec, pinName(pin)),
      pin,
      end: undefined,
    });
  }
  for (const end of met.ends) {
    const { wire } = end;
    sides.push({
      toward: unit(wire.at[end.end], wire.at[1 - end.end]!),
      reach: wire.length / 2,
      pin: undefined,
      end,
    });
  }
  return sides;
}

/** How far along one side of a place its corner runs: `CURVE`, or as far as
 *  the side reaches where that is less, and along a symbol's track no further
 *  than along the track it meets. */
function far(side: Side, other: Side): number {
  return Math.min(
    CURVE,
    side.reach,
    side.pin === undefined ? Infinity : other.reach,
  );
}

/** Whether a run turns between two directions out of one place. Two that are
 *  opposite are in line, and two that are the same double back. */
function turns(one: Point, two: Point): boolean {
  return Math.abs(one.x * two.y - one.y * two.x) > NOTHING;
}

/** Whether the corners at a wire's two ends leave it no straight part. */
function usedUp({ length, short }: Laid): boolean {
  return length >= NOTHING && length - short[0] - short[1] < NOTHING;
}

function along(from: Point, toward: Point, by: number): Point {
  return { x: from.x + toward.x * by, y: from.y + toward.y * by };
}

/** How the more strongly lit of two wires is lit: the lit one of a lit and an
 *  unlit, and of two a run lights, the one whose claim `CLAIMS` puts first. */
function stronger(
  one: Lighting | undefined,
  two: Lighting | undefined,
): Lighting | undefined {
  if (one === undefined || two === undefined) return one ?? two;
  const rank = ({ claim }: Lighting) =>
    claim === undefined ? CLAIMS.length : CLAIMS.indexOf(claim);
  return rank(two) < rank(one) ? two : one;
}
