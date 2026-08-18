/**
 * The editing session: a drawing, what is selected, the wire being drawn, and
 * the snapshots undo restores.
 *
 * No DOM, so this is where the tests are (EDITOR.md). It is the layer where a
 * bug is invisible on screen and corrupt in the file — a move that detaches a
 * wire, an undo that half-restores — and the layer a Lit component should have
 * nothing to add to.
 *
 * It derives nothing. Counting the wires a pin holds is reading the document;
 * junctions, transits and what excludes what come from the store's `/review`.
 */

import type { Kind } from "../symbols.generated.js";
import {
  clone,
  pinsOf,
  symbolOf,
  wireKey,
  wirePins,
  type Drawing,
  type PinRef,
  type SymbolSpec,
  type Wire,
} from "./drawing.js";
import {
  anchorOf,
  clear,
  faceAt,
  flipped,
  movedBy,
  overlaps,
  placed,
  taken,
  turned,
} from "./geometry.js";
import { settle } from "./naming.js";
import type { Review } from "./store.js";

/** What a new symbol of each kind is called: `sw1`, `sw2`, and so on. Short,
 *  because a key is read in the wire list far more than anywhere else, and the
 *  two that were not are the two whose names are now hidden anyway. */
const PREFIXES: Record<Kind, string> = {
  block: "b",
  terminal: "e",
  portal: "p",
  pin: "n",
  turnout: "sw",
  crossing: "x",
  crossing_90: "x90",
  crossing_90d: "x90d",
  single_slip: "ss",
  double_slip: "ds",
};

const DEPTH = 200; // snapshots kept; the document is small and edits are rare

/** How a symbol is turned, which is all a placement carries besides its kind. */
export type Facing = Pick<SymbolSpec, "rot" | "flip">;

/** A symbol on its way from the palette: an ordinary spec without a placement
 *  yet, of a kind the palette can offer. */
type Placing = SymbolSpec & { kind: Kind };

/** Where a pending placement would land, and what is in the way. */
export interface Landing {
  at: [number, number];
  /** The squares another symbol already has. Empty is a drop that can land. */
  blocked: [number, number][];
}

export class Editor {
  private past: Drawing[] = [];
  private future: Drawing[] = [];
  private chosen = new Set<string>();
  private drawingFrom: PinRef | null = null;
  private placing: Placing | null = null;
  private facing: Facing = {};
  private changes = 0;

  constructor(private current: Drawing) {}

  get drawing(): Drawing {
    return this.current;
  }

  get selection(): ReadonlySet<string> {
    return this.chosen;
  }

  /** The pin a wire is being drawn from, if one is. */
  get pendingFrom(): PinRef | null {
    return this.drawingFrom;
  }

  /** The symbol on its way from the palette, if one is: what it is and how it
   *  is turned, which is everything about it that is not the pointer. */
  get pending(): Placing | null {
    return this.placing;
  }

  get canUndo(): boolean {
    return this.past.length > 0;
  }

  get canRedo(): boolean {
    return this.future.length > 0;
  }

  // --- reading the document ----------------------------------------------

  /** The wires a pin holds. Two is what every pin wants; a bend wants both
   *  of its own, being a bend rather than an end. */
  degree(pin: PinRef): number {
    return this.current.wires.filter((wire) => wirePins(wire).includes(pin))
      .length;
  }

  /** Whether a pin can take another wire. */
  free(pin: PinRef): boolean {
    const spec = this.current.symbols[symbolOf(pin)];
    return spec !== undefined && this.degree(pin) < wiresWanted(spec.kind);
  }

  pinsOf(name: string): PinRef[] {
    const spec = this.current.symbols[name];
    return spec === undefined ? [] : pinsOf(spec).map((pin) => `${name}.${pin}`);
  }

  /** Every pin on the drawing, with where it sits. */
  allPins(): { pin: PinRef; x: number; y: number }[] {
    return Object.entries(this.current.symbols).flatMap(([name, spec]) =>
      pinsOf(spec).map((pin) => ({
        pin: `${name}.${pin}`,
        ...anchorOf(spec, pin),
      })),
    );
  }

  // --- placing and editing symbols ---------------------------------------

  /**
   * Place a symbol from the palette, joining any pin it lands on. Answers with
   * its name, or `null` where it would cover a square another symbol already
   * has: a square holds at most one symbol (EDITOR.md#canvas), and a block is
   * six of them, so a placement can overlap without its own cell being taken.
   */
  place(kind: Kind, at: [number, number], facing: Facing = {}): string | null {
    const name = mint(this.current, kind);
    const spec: SymbolSpec = { kind, at, ...facing, ...defaults(kind, name) };
    if (!clear(spec, this.current.symbols)) return null;
    this.push();
    this.current.symbols[name] = spec;
    this.abut([name]);
    this.chosen = new Set([name]);
    return name;
  }

  // --- dragging a symbol out of the palette -------------------------------

  /** Take a symbol off the palette. It starts turned the way the last one was
   *  left: a rotated run of turnouts costs one keypress for the run rather
   *  than one for each of them (EDITOR.md#palette). */
  beginPlace(kind: Kind): void {
    this.placing = { kind, ...this.facing };
  }

  /** A quarter turn of the symbol being dragged, by the same rule that turns a
   *  selected one, and remembered for the next drag. */
  turnPending(): void {
    this.reorient(turned);
  }

  flipPending(): void {
    this.reorient(flipped);
  }

  cancelPending(): void {
    this.placing = null;
  }

  /**
   * Where the dragged symbol would land with the pointer here, and which of
   * the squares it wants another symbol already has.
   *
   * The footprint centres on the pointer, against the orientation it is being
   * dragged in rather than the kind's own, so a turn that transposes 6×1 into
   * 1×6 re-centres with it. `at` is a whole cell, so an even-width footprint
   * lands half a square off; that is as close as the grid allows.
   */
  placementAt(x: number, y: number): Landing | null {
    if (this.placing === null) return null;
    const { w, h } = placed(this.placing).footprint;
    const at: [number, number] = [
      Math.round(x - w / 2),
      Math.round(y - h / 2),
    ];
    return { at, blocked: taken({ ...this.placing, at }, this.current.symbols) };
  }

  /** Drop it. Refused where the squares are taken, so a drop the ghost showed
   *  as blocked is a drop that does nothing. */
  dropPending(x: number, y: number): string | null {
    const landing = this.placementAt(x, y);
    if (this.placing === null || landing === null) return null;
    if (landing.blocked.length > 0) return null;
    const { kind } = this.placing;
    const facing = facingOf(this.placing);
    this.placing = null;
    return this.place(kind, landing.at, facing);
  }

  private reorient(change: (spec: Placing) => Placing): void {
    if (this.placing === null) return;
    this.placing = change(this.placing);
    this.facing = facingOf(this.placing);
  }

  /**
   * Give every unplaced symbol somewhere to be dragged from, and say whether
   * there was anything to do.
   *
   * No committed drawing has any placement and there is no auto-layout, so
   * each railroad is drawn once by hand (EDITOR.md). Opening one would
   * otherwise pile every symbol on the origin, where the first drag cannot
   * pick one out. Dealing them into rows says nothing about the topology, and
   * it is an ordinary edit: undo takes it back and it reaches the file only if
   * the drawing is saved.
   */
  stage(): boolean {
    const loose = Object.entries(this.current.symbols).filter(
      ([, spec]) => spec.at === undefined,
    );
    if (loose.length === 0) return false;
    this.push();
    const across = Math.ceil(Math.sqrt(loose.length));
    loose.forEach(([name, spec], index) => {
      const at: [number, number] = [
        (index % across) * 3,
        Math.floor(index / across) * 3,
      ];
      this.current.symbols[name] = { ...spec, at };
    });
    return true;
  }

  select(names: Iterable<string>, add = false): void {
    const chosen = add ? new Set(this.chosen) : new Set<string>();
    for (const name of names) chosen.add(name);
    this.chosen = chosen;
  }

  clearSelection(): void {
    this.chosen = new Set();
  }

  /**
   * Move the selection. Wires carry no geometry, so every wire the move
   * touches rubber-bands by itself and a move cannot change what derives.
   */
  move(dx: number, dy: number): void {
    if (this.chosen.size === 0 || (dx === 0 && dy === 0)) return;
    if (!this.canMove(dx, dy)) return;
    this.push();
    for (const name of this.chosen) {
      this.current.symbols[name] = movedBy(this.at(name), dx, dy);
    }
    this.abut([...this.chosen]);
  }

  /**
   * Put a bend on the face nearest a point, `rot` and all, and say whether that
   * moved it.
   *
   * A bend's `rot` is which face of its cell it sits on rather than a turn of
   * artwork, so translating it by whole cells the way `move` shifts everything
   * else leaves it forever on faces of the orientation it was drawn with — west
   * faces only, or north faces only (EDITOR.md#canvas). Dragged on its own it
   * snaps to whichever face is nearest instead. In a selection of several it
   * still translates rigidly, that being the rule the others obey.
   */
  reface(name: string, x: number, y: number): boolean {
    const spec = this.current.symbols[name];
    if (spec === undefined || spec.kind !== "pin") return false;
    const { at, rot } = faceAt(x, y);
    const [c, r] = spec.at ?? [0, 0];
    if (at[0] === c && at[1] === r && rot === (spec.rot ?? 0)) return false;
    this.push();
    this.current.symbols[name] = { ...spec, at, rot };
    this.abut([name]);
    return true;
  }

  /**
   * Whether the selection can shift by this much without landing on anything
   * outside it. The selection translates rigidly, so symbols inside it keep
   * whatever spacing they had and only the rest of the drawing is in the way.
   */
  canMove(dx: number, dy: number): boolean {
    return [...this.chosen].every((name) =>
      clear(movedBy(this.at(name), dx, dy), this.current.symbols, this.chosen),
    );
  }

  /** The squares more than one symbol covers. Rotate and flip may make one,
   *  and the editor reports it rather than refusing (EDITOR.md#canvas). */
  overlaps(): { cell: [number, number]; symbols: string[] }[] {
    return overlaps(this.current.symbols);
  }

  /** A quarter turn clockwise, each selected symbol about its own cell. */
  rotate(): void {
    this.transform(turned);
  }

  flip(): void {
    this.transform(flipped);
  }

  /** Delete the selection, and with it every wire it holds. Whatever was on
   *  the far end of those wires is left a pin short, which `/review` reports
   *  as red. */
  remove(): void {
    if (this.chosen.size === 0) return;
    this.push();
    const gone = new Set(this.chosen);
    for (const name of gone) delete this.current.symbols[name];
    this.current.wires = this.current.wires.filter(
      (wire) => !wirePins(wire).some((pin) => gone.has(symbolOf(pin))),
    );
    this.chosen = new Set();
  }

  /**
   * Cut a wire, and say whether there was one to cut. Both pins it held are
   * left short of one, which `/review` reports as red — the normal state of a
   * drawing mid-edit, and what says where the track now stops.
   *
   * A wire has no symbol to select, so this is the one verb that takes what it
   * acts on rather than reading the selection (EDITOR.md#editing).
   */
  unwire(pins: [PinRef, PinRef]): boolean {
    const cut = [...pins].sort().join(" ");
    const kept = this.current.wires.filter((wire) => wireKey(wire) !== cut);
    if (kept.length === this.current.wires.length) return false;
    this.push();
    this.current.wires = kept;
    return true;
  }

  /**
   * Apply the properties dialog: the symbol's own properties, and a rename
   * where the name changed. Answers whether it took.
   *
   * A wire is written `<symbol>.<pin>` and is the only thing that points at a
   * symbol, so a rename rewrites the wires and nothing else. A one-symbol
   * junction takes its symbol's name, so renaming a lone turnout renames its
   * connection too — which is the drawing's rule, not this one's
   * (store/DRAWING.md).
   */
  edit(was: string, name: string, spec: SymbolSpec): boolean {
    if (!(was in this.current.symbols)) return false;
    if (name !== was && (!isName(name) || name in this.current.symbols)) {
      return false;
    }
    this.push();
    // Rebuilt in order rather than deleted and re-added: the file keeps the
    // order it was written in, and a renamed symbol should keep its place.
    this.current.symbols = Object.fromEntries(
      Object.entries(this.current.symbols).map(([key, value]) =>
        key === was ? [name, spec] : [key, value],
      ),
    );
    if (name !== was) {
      this.current.wires = this.current.wires.map((wire) => renamed(wire, was, name));
      this.chosen = new Set(
        [...this.chosen].map((chosen) => (chosen === was ? name : chosen)),
      );
    }
    return true;
  }

  /**
   * Mint the names the drawing has not settled, folding into the snapshot the
   * edit that caused them. Naming is a consequence of the edit rather than an
   * edit of its own, so one action stays one undo step, and nothing interrupts
   * a sketch to ask what a junction is called.
   *
   * `at` is the revision the review was of. A review is a round trip, and an
   * edit can land while it is in flight; writing its answer onto a drawing
   * that has moved on would name junctions that are no longer there.
   */
  settle(review: Review, at: number): boolean {
    return at === this.revision && settle(this.current, review);
  }

  /** How many times the document has changed. Only useful for telling whether
   *  it changed while something else was being worked out. */
  get revision(): number {
    return this.changes;
  }

  // --- drawing wires ------------------------------------------------------

  /** Start a wire at a pin, or end the one in progress there. */
  startWire(pin: PinRef): void {
    this.drawingFrom = pin;
  }

  /** A click on empty canvas: a bend at the nearest face centre, and the wire
   *  carries on from it. */
  bend(x: number, y: number): PinRef {
    if (this.drawingFrom === null) throw new Error("no wire is being drawn");
    this.push();
    const name = mint(this.current, "pin");
    const { at, rot } = faceAt(x, y);
    this.current.symbols[name] = { kind: "pin", at, rot };
    this.current.wires.push([this.drawingFrom, `${name}.P`]);
    this.drawingFrom = `${name}.P`;
    return this.drawingFrom;
  }

  /** End the wire at a pin. Refused where the pin has no room, so a click
   *  that cannot land is a click that does nothing. */
  endWire(pin: PinRef): boolean {
    if (this.drawingFrom === null || pin === this.drawingFrom) return false;
    if (!this.free(pin) || this.joined(this.drawingFrom, pin)) return false;
    this.push();
    this.current.wires.push([this.drawingFrom, pin]);
    this.drawingFrom = null;
    return true;
  }

  /** Whether a wire already joins two pins. Two bends each want two wires, so
   *  a second wire between the same pair would fill both and read as a
   *  finished joint while being a parallel edge nobody drew. */
  private joined(a: PinRef, b: PinRef): boolean {
    return this.current.wires.some((wire) => {
      const pins = wirePins(wire);
      return pins.includes(a) && pins.includes(b);
    });
  }

  /** Abandon the wire. What is already drawn stays, ending in a red pin,
   *  which is the normal state of a drawing mid-edit. */
  cancelWire(): void {
    this.drawingFrom = null;
  }

  /**
   * Join every free pin of these symbols to a free pin sitting on the same
   * point. Dropping a symbol onto another is the fast way to wire them, and
   * what it writes is a real wire of zero length: dragging apart later
   * stretches it rather than breaking the joint.
   */
  abut(names: string[]): void {
    const moved = new Set(names);
    const pins = this.allPins();
    for (const { pin, x, y } of pins) {
      if (!moved.has(symbolOf(pin))) continue;
      for (const other of pins) {
        if (
          symbolOf(other.pin) !== symbolOf(pin) &&
          other.x === x &&
          other.y === y &&
          this.free(pin) &&
          this.free(other.pin) &&
          !this.joined(pin, other.pin)
        ) {
          this.current.wires.push([pin, other.pin]);
        }
      }
    }
  }

  // --- undo ---------------------------------------------------------------

  undo(): void {
    this.step(this.past, this.future);
  }

  redo(): void {
    this.step(this.future, this.past);
  }

  /** Take a snapshot. Every mutation calls it first: the document is small,
   *  so a copy per edit is cheaper than working out what changed. */
  push(): void {
    this.changes++;
    this.past.push(clone(this.current));
    if (this.past.length > DEPTH) this.past.shift();
    this.future = [];
  }

  /** Wear a new name, history included: the name says which file Save
   *  writes, not what the drawing looks like, so undo never takes it back. */
  rename(name: string): void {
    this.changes++;
    this.current = { ...this.current, drawing: name };
    this.past = this.past.map((one) => ({ ...one, drawing: name }));
    this.future = this.future.map((one) => ({ ...one, drawing: name }));
  }

  /** Adopt a drawing, forgetting the edits that led to the last one — what
   *  loading a railroad does. */
  reset(drawing: Drawing): void {
    this.changes++;
    this.current = drawing;
    this.past = [];
    this.future = [];
    this.chosen = new Set();
    this.drawingFrom = null;
    this.placing = null;
  }

  private step(from: Drawing[], to: Drawing[]): void {
    const restored = from.pop();
    if (restored === undefined) return;
    this.changes++;
    to.push(clone(this.current));
    this.current = restored;
    this.drawingFrom = null;
    this.chosen = new Set(
      [...this.chosen].filter((name) => name in this.current.symbols),
    );
  }

  private transform(change: (spec: SymbolSpec) => SymbolSpec): void {
    if (this.chosen.size === 0) return;
    this.push();
    for (const name of this.chosen) {
      this.current.symbols[name] = change(this.at(name));
    }
    this.abut([...this.chosen]);
  }

  private at(name: string): SymbolSpec {
    const spec = this.current.symbols[name];
    if (spec === undefined) throw new Error(`no symbol '${name}'`);
    return spec;
  }
}

/** How a spec is turned and nothing else, leaving out whichever of the two it
 *  does not write: a placement should stay as plain as the tile it came from. */
function facingOf(spec: SymbolSpec): Facing {
  return {
    ...(spec.rot === undefined ? {} : { rot: spec.rot }),
    ...(spec.flip === undefined ? {} : { flip: spec.flip }),
  };
}

/** A free-standing bend joins two wires; every other pin joins one, the
 *  symbol itself being its second connection. */
export function wiresWanted(kind: string): number {
  return kind === "pin" ? 2 : 1;
}

/** The properties a kind cannot do without, so that a placed symbol is a
 *  document the store will take. A portal's label is what pairs it, and an
 *  empty one is not a name, so a fresh portal is labelled after itself and
 *  stays unpaired until someone says what it pairs with. */
function defaults(kind: Kind, name: string): Partial<SymbolSpec> {
  if (kind === "block") return { length: 1000 };
  if (kind === "portal") return { label: name };
  return {};
}

/** What the drawing schema takes as a name: not empty, and without the `.`
 *  that separates a symbol from its pin or the `/` that separates a path. */
export function isName(name: string): boolean {
  return name !== "" && !name.includes(".") && !name.includes("/");
}

/** A wire with a renamed symbol's pins rewritten, keeping the form it was
 *  written in — a wire that names a connection still names it. */
function renamed(wire: Wire, was: string, name: string): Wire {
  const swap = (pin: PinRef) =>
    symbolOf(pin) === was ? `${name}${pin.slice(was.length)}` : pin;
  const [a, b] = wirePins(wire);
  const pins: [string, string] = [swap(a), swap(b)];
  return Array.isArray(wire) ? pins : { ...wire, pins };
}

/** The lowest free `<prefix><n>` for a kind. */
export function mint(drawing: Drawing, kind: Kind): string {
  const prefix = PREFIXES[kind];
  for (let n = 1; ; n++) {
    const name = `${prefix}${n}`;
    if (!(name in drawing.symbols)) return name;
  }
}
