/**
 * What is under a point on the canvas: the drawing read from a grid position
 * back to the thing a click there means.
 *
 * Grid coordinates throughout. Converting the pointer's pixels into squares is
 * the canvas component's business, and the only part of the question that needs
 * a DOM; everything after it is the document and the store's answer, so it
 * lives here where it can be tested.
 *
 * Nothing here derives anything. Symbols and wires are the document's own,
 * junctions and joints are read off `/review`.
 */

import { anchorOf, cellsOf, centreOf } from "./geometry.js";
import type { Point } from "./geometry.js";
import {
  pinsOf,
  symbolOf,
  wirePins,
  type AnyKind,
  type Drawing,
  type PinRef,
} from "./drawing.js";
import type { Joint, Junction, Review } from "./store.js";

/** How near a pointer has to come to a pin or a line, in squares. */
const HIT = 0.22;

/**
 * How far a symbol is drawn from where the document puts it.
 *
 * Nothing but a drag in flight moves anything, and a click has to land on what
 * is on screen rather than on what the file says. Taking it as a function of
 * the name keeps the drag itself out of here: this module is told where things
 * are drawn and never learns why.
 */
export type Shift = (name: string) => Point;

const HERE: Shift = () => ({ x: 0, y: 0 });

/** What a point on the canvas landed on. */
export interface Under {
  pin: PinRef | null;
  symbol: string | null;
  /** The symbol's kind, which is what says whether it has properties to open
   *  and whether its name is the user's. The menu asks rather than reaching
   *  into the drawing itself. */
  kind: AnyKind | null;
  junction: Junction | null;
  joint: Joint | null;
  wire: [PinRef, PinRef] | null;
}

export function under(
  drawing: Drawing,
  review: Review,
  at: Point,
  shift: Shift = HERE,
): Under {
  // A pin beats the symbol carrying it: a press on one starts a wire, while a
  // press anywhere else on the symbol takes hold of the symbol. The symbol is
  // named either way, so a right-click on a pin still asks about the turnout.
  const pin = pinNear(drawing, at, shift);
  const symbol = pin === null ? symbolAt(drawing, at, shift) : symbolOf(pin);
  return {
    pin,
    symbol,
    kind: symbol === null ? null : (drawing.symbols[symbol]?.kind ?? null),
    junction: junctionOf(review, symbol),
    joint: jointNear(drawing, review, at, shift),
    // Only where no symbol is. A symbol's own wires pass within a hair of its
    // pins, and an abutted one has no length at all, so a wire is near wherever
    // a symbol is; a click on a turnout is a question about the turnout.
    wire: symbol === null ? wireNear(drawing, at, shift) : null,
  };
}

/**
 * The symbols a rubber band takes: those whose centre it covers.
 *
 * By the centre rather than by any overlap, so a band drawn along a row takes
 * that row and not the block reaching into it from the next one. The two
 * corners arrive in whatever order they were dragged.
 */
export function within(drawing: Drawing, from: Point, to: Point): string[] {
  const [x0, x1] = [Math.min(from.x, to.x), Math.max(from.x, to.x)];
  const [y0, y1] = [Math.min(from.y, to.y), Math.max(from.y, to.y)];
  return Object.entries(drawing.symbols)
    .filter(([, spec]) => {
      const { x, y } = centreOf(spec);
      return x >= x0 && x <= x1 && y >= y0 && y <= y1;
    })
    .map(([name]) => name);
}

/** The joint whose drawn line passes nearest a point, where one does. Offered
 *  wherever it is found: a joint is a name for the connection, and a bare wire
 *  between two blocks is the only thing there is to click for it. */
function jointNear(
  drawing: Drawing,
  review: Review,
  at: Point,
  shift: Shift,
): Joint | null {
  let best: { joint: Joint; away: number } | null = null;
  for (const joint of review.joints) {
    for (const [a, b] of joint.wires) {
      const from = pointOf(drawing, a, shift);
      const to = pointOf(drawing, b, shift);
      if (from === null || to === null) continue;
      const away = awayFrom(at, from, to);
      if (away <= HIT && (best === null || away < best.away)) {
        best = { joint, away };
      }
    }
  }
  return best?.joint ?? null;
}

/** The wire whose drawn line passes nearest a point, where one does. Read off
 *  the drawing rather than `/review`: a wire is the document's own and needs
 *  no derivation to find. */
function wireNear(
  drawing: Drawing,
  at: Point,
  shift: Shift,
): [PinRef, PinRef] | null {
  let best: { pins: [PinRef, PinRef]; away: number } | null = null;
  for (const wire of drawing.wires) {
    const pins = wirePins(wire);
    const from = pointOf(drawing, pins[0], shift);
    const to = pointOf(drawing, pins[1], shift);
    if (from === null || to === null) continue;
    const away = awayFrom(at, from, to);
    if (away <= HIT && (best === null || away < best.away)) best = { pins, away };
  }
  return best?.pins ?? null;
}

/** Where a pin is drawn on the grid, or nothing where its symbol is gone.
 *  Exported because a wire is drawn between two of these, so the canvas asks
 *  the same question to render as this module asks to hit-test. */
export function pointOf(
  drawing: Drawing,
  pin: PinRef,
  shift: Shift = HERE,
): Point | null {
  const spec = drawing.symbols[symbolOf(pin)];
  if (spec === undefined) return null;
  const { x, y } = anchorOf(spec, pin.slice(pin.indexOf(".") + 1));
  const away = shift(symbolOf(pin));
  return { x: x + away.x, y: y + away.y };
}

/** How far a point lies from a line segment. */
function awayFrom(point: Point, from: Point, to: Point): number {
  const [dx, dy] = [to.x - from.x, to.y - from.y];
  const span = dx * dx + dy * dy;
  const along =
    span === 0
      ? 0
      : Math.max(
          0,
          Math.min(
            1,
            ((point.x - from.x) * dx + (point.y - from.y) * dy) / span,
          ),
        );
  return Math.hypot(from.x + along * dx - point.x, from.y + along * dy - point.y);
}

/** The junction a symbol belongs to, as `/review` grouped them. */
function junctionOf(review: Review, symbol: string | null): Junction | null {
  if (symbol === null) return null;
  return review.junctions.find((one) => one.symbols.includes(symbol)) ?? null;
}

/** The pin nearest a point, where one is within reach. */
function pinNear(drawing: Drawing, at: Point, shift: Shift): PinRef | null {
  let best: { pin: PinRef; away: number } | null = null;
  for (const { pin, x, y } of allPins(drawing)) {
    const moved = shift(symbolOf(pin));
    const away = Math.hypot(x + moved.x - at.x, y + moved.y - at.y);
    if (away <= HIT && (best === null || away < best.away)) best = { pin, away };
  }
  return best?.pin ?? null;
}

/** Every pin on the drawing, with where it sits. */
function allPins(drawing: Drawing): { pin: PinRef; x: number; y: number }[] {
  return Object.entries(drawing.symbols).flatMap(([name, spec]) =>
    pinsOf(spec).map((pin) => ({
      pin: `${name}.${pin}`,
      ...anchorOf(spec, pin),
    })),
  );
}

/** The symbol whose square holds a point. A square holds at most one symbol
 *  (EDITOR.md#canvas), so the first one covering the cell is the answer. */
function symbolAt(drawing: Drawing, at: Point, shift: Shift): string | null {
  const [c, r] = [Math.floor(at.x), Math.floor(at.y)];
  for (const [name, spec] of Object.entries(drawing.symbols)) {
    const moved = shift(name);
    const covers = cellsOf(spec).some(
      ([cx, cy]) => cx + moved.x === c && cy + moved.y === r,
    );
    if (covers) return name;
  }
  return null;
}
