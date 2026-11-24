/**
 * Where a symbol's pins are, given where the symbol sits.
 *
 * The canvas is a grid of squares. A symbol occupies whole squares and its
 * pins sit at the centres of square sides, which is why it turns in quarters
 * and flips rather than taking a free angle (EDITOR.md). A turnout also turns
 * by 45 degrees, which swaps it for a second form with its straight road on
 * the diagonal (`TURNOUT_45`). Everything here is in
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
import type { SymbolSpec } from "./drawing.js";

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
  turnout: { w: 2, h: 1 },
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

/**
 * A turnout takes a slip's two squares and three of its four pin sites. Its
 * frog is the face centre the two squares share, in both forms.
 *
 * Turned a multiple of 90 degrees the straight road is the horizontal, `a1`
 * to `a2`, and the diverging road leaves for `b2`. Turned 45 degrees more the
 * straight road is the diagonal of the mirrored slip, and the diverging road
 * leaves along the horizontal.
 */
const TURNOUT = {
  toe: DIAMOND.a1,
  straight: DIAMOND.a2,
  diverging: DIAMOND.b2,
};

const TURNOUT_45 = {
  toe: { x: 0.5, y: 0 },
  straight: { x: 1.5, y: 1 },
  diverging: { x: 2, y: 0.5 },
};

export const ANCHORS: { [K in Kind]: Record<(typeof PINS)[K][number], Point> } =
  {
    block: { A: { x: 0, y: 0.5 }, B: { x: 6, y: 0.5 } },
    terminal: { P: { x: 0, y: 0.5 } },
    portal: { P: { x: 0, y: 0.5 } },
    pin: { P: { x: 0, y: 0.5 } },
    turnout: TURNOUT,
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
 *  artwork's legs have to end for the strokes and the wires to meet. `rot`
 *  picks a turnout's form and moves nothing else. */
export function anchorIn(kind: Kind, pin: string, rot: Rotation = 0): Point {
  const point = own({ kind, rot })[pin];
  if (point === undefined) throw new Error(`'${kind}' has no pin '${pin}'`);
  return point;
}

/** A symbol's anchors before it is flipped and turned. */
function own(spec: SymbolSpec): Record<string, Point> {
  return spec.kind === "turnout" && (spec.rot ?? 0) % 90 !== 0
    ? TURNOUT_45
    : ANCHORS[spec.kind];
}

/** The quarter turns a placement makes. The 45 degrees a turnout may have
 *  beyond them are its form, not a turn. */
function quarters(spec: SymbolSpec): number {
  return Math.floor((spec.rot ?? 0) / 90);
}

/** The footprint and pin anchors a placement gives a symbol, local to `at`. */
export function placed(spec: SymbolSpec): {
  footprint: Footprint;
  anchors: Record<string, Point>;
} {
  const { footprint, move } = placement(spec, FOOTPRINTS[spec.kind]);
  return { footprint, anchors: map(own(spec), move) };
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
): {
  footprint: Footprint;
  move: (point: Point) => Point;
  back: (point: Point) => Point;
  transform: string;
} {
  let { w, h } = base;
  const moves: ((point: Point) => Point)[] = [];
  const backs: ((point: Point) => Point)[] = [];
  const turns: string[] = [];
  if (spec.flip) {
    const across = w;
    moves.push(({ x, y }) => ({ x: across - x, y }));
    backs.unshift(({ x, y }) => ({ x: across - x, y }));
  }
  for (let turn = quarters(spec); turn > 0; turn--) {
    const down = h;
    moves.push(({ x, y }) => ({ x: down - y, y: x }));
    backs.unshift(({ x, y }) => ({ x: y, y: down - x }));
    turns.unshift(`translate(${down} 0) rotate(90)`);
    [w, h] = [h, w];
  }
  return {
    footprint: { w, h },
    move: (point) => moves.reduce((moved, step) => step(moved), point),
    back: (point) => backs.reduce((moved, step) => step(moved), point),
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

/** Where a point of the grid is in a symbol's own coordinates: `gridPointOf`
 *  undone. */
export function localOf(spec: SymbolSpec, grid: Point): Point {
  const [c, r] = spec.at ?? [0, 0];
  return placement(spec, footprintOf(spec)).back({ x: grid.x - c, y: grid.y - r });
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
 * The direction a placed symbol's track leaves a pin in, as a unit vector on
 * the grid: away from the middle of the footprint, which every kind's legs
 * are in line with where they end, a turnout's in both forms. A wire leaving
 * the same way joins the track in line. A bend has no track and so no leg.
 */
export function legOf(spec: SymbolSpec, pin: string): Point | null {
  if (spec.kind === "pin") return null;
  return unit(centreOf(spec), anchorOf(spec, pin));
}

/** A unit vector from one point toward another. */
export function unit(from: Point, to: Point): Point {
  const span = Math.hypot(to.x - from.x, to.y - from.y);
  return { x: (to.x - from.x) / span, y: (to.y - from.y) / span };
}

/**
 * How far a symbol's label is turned from upright, in degrees.
 *
 * A block standing on end is read bottom to top rather than sideways, so a
 * quarter turn takes the label with it. Neither the flip nor which end carries
 * the A comes into it: a vertical block reads the same way whichever end is
 * A, which is what keeps the label from turning over as the block is flipped.
 */
export function labelTurn(spec: SymbolSpec): number {
  return quarters(spec) % 2 === 0 ? 0 : -90;
}

/** The transform that puts text at `local` inside a symbol's own group and
 *  turns it as the label is turned outside it: the symbol's flip and quarter
 *  turns undone, then `labelTurn`, so it is never upside down or mirrored. */
export function uprightAt(spec: SymbolSpec, local: Point): string {
  const turn = labelTurn(spec) - 90 * quarters(spec);
  return `translate(${local.x} ${local.y})${spec.flip ? " scale(-1 1)" : ""} rotate(${turn})`;
}

/**
 * Which end of an upright label sits on `local`: the end nearest the symbol, so
 * the text runs away from the artwork however long it is.
 *
 * A label beside a symbol is placed at one point of the symbol's own
 * coordinates and drawn upright, so which way it then runs on screen is the
 * placement's business: a portal turned 180 degrees has its mouth to the west
 * and its label has to run west too. Centring the text instead would put a long
 * label back over the artwork it marks.
 *
 * A point straight above or below the symbol leaves no side to prefer, so the
 * label is centred there.
 */
export function labelAnchor(
  spec: SymbolSpec,
  local: Point,
): "start" | "middle" | "end" {
  const along = gridPointOf(spec, local).x - gridPointOf(spec, { x: 0, y: local.y }).x;
  if (Math.abs(along) < 1e-6) return "middle";
  return along > 0 ? "start" : "end";
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
  return FOOTPRINTS[spec.kind];
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

/** One step clockwise, keeping `at` where it is: 45 degrees for a turnout,
 *  a quarter turn for every other kind. */
export function turned<T extends SymbolSpec>(spec: T): T {
  const step = spec.kind === "turnout" ? 45 : 90;
  return { ...spec, rot: (((spec.rot ?? 0) + step) % 360) as Rotation };
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
