/**
 * Where a symbol's pins are, given where the symbol sits.
 *
 * The canvas is a grid of squares. A symbol occupies whole squares and its
 * pins sit at the centres of square sides, which is why it turns in quarters
 * and flips rather than taking a free angle (EDITOR.md). Everything here is in
 * square units, with the origin at the top left of the grid; pixels are the
 * canvas component's business.
 *
 * Footprints and anchors are hand-written artwork against the generated pin
 * names (#52), so a renamed pin fails to compile here.
 *
 * A free-standing bend has one pin and occupies no square, being on a
 * boundary. It is still placed like any other symbol: `at` is a cell and `rot`
 * turns its single pin onto that cell's west, north, east or south face. Two
 * cells share a face, so `faceAt` picks one of the two spellings and the
 * editor only ever writes that one.
 */

import { PINS, type Kind, type Rotation } from "../symbols.generated.js";
import { pinsOf, type SymbolSpec } from "./drawing.js";

export interface Point {
  x: number;
  y: number;
}

export interface Footprint {
  w: number;
  h: number;
}

/** The squares each kind covers, unturned. A bend covers none. */
export const FOOTPRINTS: Record<Kind, Footprint> = {
  block: { w: 6, h: 1 },
  terminal: { w: 1, h: 1 },
  portal: { w: 1, h: 1 },
  pin: { w: 1, h: 1 },
  turnout: { w: 1, h: 1 },
  crossing: { w: 2, h: 1 },
  crossing_90: { w: 1, h: 1 },
  crossing_90d: { w: 2, h: 1 },
  single_slip: { w: 2, h: 1 },
  double_slip: { w: 2, h: 1 },
};

/**
 * Each pin at a face centre of its unturned footprint, per EDITOR.md's
 * symbol geometry.
 *
 * A crossing and the slips take two squares: route `a` is the horizontal and
 * route `b` the 45 degree diagonal, and the two meet at the face centre the
 * two squares share, which makes the crossing exactly two turnouts toe to toe.
 * That is what puts `a1` and `b1` on one side and `a2` and `b2` on the other
 * (store/DRAWING.md), and a slip is then a road from one side to the other.
 */
const DIAMOND = {
  a1: { x: 0, y: 0.5 },
  a2: { x: 2, y: 0.5 },
  b1: { x: 0.5, y: 1 },
  b2: { x: 1.5, y: 0 },
};

export const ANCHORS: { [K in Kind]: Record<(typeof PINS)[K][number], Point> } =
  {
    block: { A: { x: 0, y: 0.5 }, B: { x: 6, y: 0.5 } },
    terminal: { P: { x: 0, y: 0.5 } },
    portal: { P: { x: 0, y: 0.5 } },
    pin: { P: { x: 0, y: 0.5 } },
    turnout: {
      toe: { x: 0, y: 0.5 },
      straight: { x: 1, y: 0.5 },
      diverging: { x: 0.5, y: 0 },
    },
    crossing: DIAMOND,
    single_slip: DIAMOND,
    double_slip: DIAMOND,
    // The upright one is the same crossing through the four faces of one
    // square; the diagonal one is a symmetric X, which needs two squares
    // because a symmetric X through one square would want corner pins.
    crossing_90: {
      a1: { x: 0, y: 0.5 },
      a2: { x: 1, y: 0.5 },
      b1: { x: 0.5, y: 1 },
      b2: { x: 0.5, y: 0 },
    },
    crossing_90d: {
      a1: { x: 0.5, y: 1 },
      a2: { x: 1.5, y: 0 },
      b1: { x: 0.5, y: 0 },
      b2: { x: 1.5, y: 1 },
    },
  };

/** Where a kind's pin sits in the symbol's own coordinates, which is where the
 *  artwork's legs have to end for the strokes and the wires to meet. */
export function anchorIn(kind: Kind, pin: string): Point {
  const point = (ANCHORS[kind] as Record<string, Point>)[pin];
  if (point === undefined) throw new Error(`'${kind}' has no pin '${pin}'`);
  return point;
}

/**
 * A generic connection symbol declares its own pins, so it has no footprint in
 * the library: it takes a box tall enough to hold them, half down each side.
 * That draws no turnout detail, which is all the symbol claims to know.
 */
function opaque(spec: SymbolSpec): {
  footprint: Footprint;
  anchors: Record<string, Point>;
} {
  const pins = pinsOf(spec);
  const down = Math.max(1, Math.ceil(pins.length / 2));
  const anchors: Record<string, Point> = {};
  pins.forEach((pin, index) => {
    const side = index < down ? 0 : 2;
    anchors[pin] = { x: side, y: (side === 0 ? index : index - down) + 0.5 };
  });
  return { footprint: { w: 2, h: down }, anchors };
}

/** The footprint and pin anchors a placement gives a symbol, local to `at`. */
export function placed(spec: SymbolSpec): {
  footprint: Footprint;
  anchors: Record<string, Point>;
} {
  const base =
    spec.kind === "connection"
      ? opaque(spec)
      : {
          footprint: FOOTPRINTS[spec.kind],
          anchors: ANCHORS[spec.kind] as Record<string, Point>,
        };
  const { footprint, move } = placement(spec, base.footprint);
  return { footprint, anchors: map(base.anchors, move) };
}

/**
 * What a placement does: the footprint it leaves, and how it moves a point of
 * the symbol's own coordinates into the cell at `at`.
 *
 * Flip first, then turn. Either order draws every symbol the editor can make,
 * but only a fixed one makes `rot` and `flip` mean one thing.
 */
function placement(
  spec: SymbolSpec,
  base: Footprint,
): { footprint: Footprint; move: (point: Point) => Point } {
  let { w, h } = base;
  const moves: ((point: Point) => Point)[] = [];
  if (spec.flip) {
    const across = w;
    moves.push(({ x, y }) => ({ x: across - x, y }));
  }
  for (let turn = (spec.rot ?? 0) / 90; turn > 0; turn--) {
    const down = h;
    moves.push(({ x, y }) => ({ x: down - y, y: x }));
    [w, h] = [h, w];
  }
  return {
    footprint: { w, h },
    move: (point) => moves.reduce((moved, step) => step(moved), point),
  };
}

/** Where a point of a symbol's own coordinates lands on the grid: the same
 *  flip, quarter turns and offset the pins take, which is what lets a label be
 *  drawn upright beside a part of the artwork that turned. */
export function gridPointOf(spec: SymbolSpec, local: Point): Point {
  const [c, r] = spec.at ?? [0, 0];
  const { x, y } = placement(spec, footprintOf(spec)).move(local);
  return { x: c + x, y: r + y };
}

/** Where a pin of a placed symbol sits on the grid. */
export function anchorOf(spec: SymbolSpec, pin: string): Point {
  const [c, r] = spec.at ?? [0, 0];
  const local = placed(spec).anchors[pin];
  if (local === undefined) {
    throw new Error(`'${spec.kind}' has no pin '${pin}'`);
  }
  return { x: c + local.x, y: r + local.y };
}

/** The middle of a placed symbol's footprint, which is where a label goes. */
export function centreOf(spec: SymbolSpec): Point {
  const [c, r] = spec.at ?? [0, 0];
  const { w, h } = placed(spec).footprint;
  return { x: c + w / 2, y: r + h / 2 };
}

/**
 * The SVG transform that takes a symbol's own coordinates onto the grid: the
 * same flip, quarter turns and offset `placed` and `anchorOf` work out, so the
 * artwork and the pins can never disagree about where a leg ends.
 */
export function transformOf(spec: SymbolSpec): string {
  const start = footprintOf(spec);
  let { w, h } = start;
  const [c, r] = spec.at ?? [0, 0];
  const turns: string[] = [];
  for (let turn = (spec.rot ?? 0) / 90; turn > 0; turn--) {
    turns.unshift(`translate(${h} 0) rotate(90)`);
    [w, h] = [h, w];
  }
  const flip = spec.flip ? ` translate(${start.w} 0) scale(-1 1)` : "";
  return `translate(${c} ${r}) ${turns.join(" ")}${flip}`.replace(/\s+/g, " ");
}

/** A kind's footprint before it is turned. */
export function footprintOf(spec: SymbolSpec): Footprint {
  return spec.kind === "connection"
    ? opaque(spec).footprint
    : FOOTPRINTS[spec.kind];
}

/** The squares a placed symbol occupies. A bend occupies none. */
export function cellsOf(spec: SymbolSpec): [number, number][] {
  if (spec.kind === "pin") return [];
  const [c, r] = spec.at ?? [0, 0];
  const { w, h } = placed(spec).footprint;
  const cells: [number, number][] = [];
  for (let dy = 0; dy < h; dy++) {
    for (let dx = 0; dx < w; dx++) cells.push([c + dx, r + dy]);
  }
  return cells;
}

/** A quarter turn clockwise, keeping `at` where it is. */
export function turned(spec: SymbolSpec): SymbolSpec {
  return { ...spec, rot: (((spec.rot ?? 0) + 90) % 360) as Rotation };
}

/** Mirrored across the symbol's own vertical axis. */
export function flipped(spec: SymbolSpec): SymbolSpec {
  return { ...spec, flip: !spec.flip };
}

export function movedBy(spec: SymbolSpec, dx: number, dy: number): SymbolSpec {
  const [c, r] = spec.at ?? [0, 0];
  return { ...spec, at: [c + dx, r + dy] };
}

/**
 * The placement of a bend at the face centre nearest a point.
 *
 * Faces are the half-grid points with one whole coordinate and one half one.
 * The west and north faces of a cell are enough to name every face, so those
 * are the two spellings the editor writes.
 */
export function faceAt(x: number, y: number): { at: [number, number]; rot: 0 | 90 } {
  const west = { at: [Math.round(x), Math.floor(y)] as [number, number], rot: 0 as const };
  const north = { at: [Math.floor(x), Math.round(y)] as [number, number], rot: 90 as const };
  const to = (face: typeof west | typeof north) => {
    const point = anchorOf({ kind: "pin", at: face.at, rot: face.rot }, "P");
    return (point.x - x) ** 2 + (point.y - y) ** 2;
  };
  return to(west) <= to(north) ? west : north;
}

/**
 * A point pulled onto the nearest multiple of 15 degrees from another, keeping
 * its distance. The wireline follows the pointer this way while a wire is
 * being drawn: it is an aid for laying parallel track, not a rule, and a click
 * on a pin overrides it, because a wire takes whatever angle its two pins give
 * it (EDITOR.md).
 */
export function snapped(from: Point, to: Point, step = 15): Point {
  const away = Math.hypot(to.x - from.x, to.y - from.y);
  const quantum = (step * Math.PI) / 180;
  const angle =
    Math.round(Math.atan2(to.y - from.y, to.x - from.x) / quantum) * quantum;
  return {
    x: from.x + away * Math.cos(angle),
    y: from.y + away * Math.sin(angle),
  };
}

function map(
  anchors: Record<string, Point>,
  move: (point: Point) => Point,
): Record<string, Point> {
  return Object.fromEntries(
    Object.entries(anchors).map(([pin, point]) => [pin, move(point)]),
  );
}
