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
 * What a placement does: the footprint it leaves, how it moves a point of the
 * symbol's own coordinates, and the SVG transform that does the same to the
 * artwork. All three come out of one walk over the flip and the quarter turns,
 * so the artwork and the pins cannot disagree about where a leg ends.
 *
 * Flip first, then turn. Either order draws every symbol the editor can make,
 * but only a fixed one makes `rot` and `flip` mean one thing. An SVG transform
 * list is applied right to left, so the turns are written in reverse and the
 * flip last of all.
 */
function placement(
  spec: SymbolSpec,
  base: Footprint,
): { footprint: Footprint; move: (point: Point) => Point; transform: string } {
  let { w, h } = base;
  const moves: ((point: Point) => Point)[] = [];
  const turns: string[] = [];
  if (spec.flip) {
    const across = w;
    moves.push(({ x, y }) => ({ x: across - x, y }));
  }
  for (let turn = (spec.rot ?? 0) / 90; turn > 0; turn--) {
    const down = h;
    moves.push(({ x, y }) => ({ x: down - y, y: x }));
    turns.unshift(`translate(${down} 0) rotate(90)`);
    [w, h] = [h, w];
  }
  return {
    footprint: { w, h },
    move: (point) => moves.reduce((moved, step) => step(moved), point),
    transform:
      turns.join(" ") +
      (spec.flip ? ` translate(${base.w} 0) scale(-1 1)` : ""),
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

/**
 * How far a symbol's label is turned from upright, in degrees.
 *
 * A block standing on end is read bottom to top rather than sideways, so a
 * quarter turn takes the label with it. Neither the flip nor which end carries
 * the plus comes into it: a vertical block reads the same way whichever end is
 * A, which is what keeps the label from turning over as the block is flipped.
 */
export function labelTurn(spec: SymbolSpec): number {
  return (spec.rot ?? 0) % 180 === 0 ? 0 : -90;
}

/** The middle of a placed symbol's footprint, which is where a label goes. */
export function centreOf(spec: SymbolSpec): Point {
  const [c, r] = spec.at ?? [0, 0];
  const { w, h } = placed(spec).footprint;
  return { x: c + w / 2, y: r + h / 2 };
}

/** The SVG transform that takes a symbol's own coordinates onto the grid: the
 *  placement `placed` and `anchorOf` work out, written for the artwork. */
export function transformOf(spec: SymbolSpec): string {
  const [c, r] = spec.at ?? [0, 0];
  const { transform } = placement(spec, footprintOf(spec));
  return `translate(${c} ${r}) ${transform}`.replace(/\s+/g, " ").trim();
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

/**
 * Whether every square `spec` covers is free of the other symbols, ignoring
 * those named in `ignoring` — the ones moving with it.
 *
 * A square holds at most one symbol (EDITOR.md#canvas), and this is the test
 * placing and dragging make before they write. A bend covers no square, so it
 * is always clear.
 */
export function clear(
  spec: SymbolSpec,
  symbols: Record<string, SymbolSpec>,
  ignoring: ReadonlySet<string> = new Set(),
): boolean {
  return taken(spec, symbols, ignoring).length === 0;
}

/** Which of `spec`'s squares another symbol already has — what `clear` answers
 *  in the negative, and what a refused placement marks so that the square in
 *  the way is the one the eye goes to (EDITOR.md#canvas). */
export function taken(
  spec: SymbolSpec,
  symbols: Record<string, SymbolSpec>,
  ignoring: ReadonlySet<string> = new Set(),
): [number, number][] {
  const held = new Set(
    Object.entries(symbols)
      .filter(([name]) => !ignoring.has(name))
      .flatMap(([, other]) => cellsOf(other).map(key)),
  );
  return cellsOf(spec).filter((cell) => held.has(key(cell)));
}

/**
 * The squares more than one symbol covers, with the symbols on each.
 *
 * Rotate and flip change a footprint and are not constrained, so an overlap is
 * read off the drawing rather than raised by the edit that made it
 * (EDITOR.md#canvas): it then reads the same after an undo, or after opening a
 * file that already had one.
 */
export function overlaps(
  symbols: Record<string, SymbolSpec>,
): { cell: [number, number]; symbols: string[] }[] {
  const on = new Map<string, { cell: [number, number]; symbols: string[] }>();
  for (const [name, spec] of Object.entries(symbols)) {
    for (const cell of cellsOf(spec)) {
      const shared = on.get(key(cell)) ?? { cell, symbols: [] };
      shared.symbols.push(name);
      on.set(key(cell), shared);
    }
  }
  return [...on.values()].filter((shared) => shared.symbols.length > 1);
}

function key([c, r]: [number, number]): string {
  return `${c},${r}`;
}

/** A quarter turn clockwise, keeping `at` where it is. */
export function turned<T extends SymbolSpec>(spec: T): T {
  return { ...spec, rot: (((spec.rot ?? 0) + 90) % 360) as Rotation };
}

/** Mirrored across the symbol's own vertical axis. */
export function flipped<T extends SymbolSpec>(spec: T): T {
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
 * Where a bend dropped at a point would sit: the centre of the face `faceAt`
 * chooses for it.
 *
 * This is where a click lands while a wire is being drawn, so it is also where
 * the wireline has to end and what the dots on the sheet mark. One function
 * for all three, so a preview cannot promise a point the drop does not use.
 */
export function facePoint(x: number, y: number): Point {
  const { at, rot } = faceAt(x, y);
  return anchorOf({ kind: "pin", at, rot }, "P");
}

function map(
  anchors: Record<string, Point>,
  move: (point: Point) => Point,
): Record<string, Point> {
  return Object.fromEntries(
    Object.entries(anchors).map(([pin, point]) => [pin, move(point)]),
  );
}
