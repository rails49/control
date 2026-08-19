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
  isName,
  motorised,
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
import { remint, settle } from "./naming.js";
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
    return this.put(kind, at, facing, undefined, true);
  }

  /**
   * The one that writes. `label` is a portal mate's, carried from the first
   * half of the pair rather than minted afresh; `snapshot` is false for that
   * second drop, so a pair placed by one gesture is one undo step
   * ([ADR-0020](../../../docs/adr/0020-a-portal-is-placed-as-a-pair.md)).
   */
  private put(
    kind: Kind,
    at: [number, number],
    facing: Facing,
    label: string | undefined,
    snapshot: boolean,
  ): string | null {
    const name = mint(this.current, kind);
    const spec: SymbolSpec = {
      kind,
      at,
      ...facing,
      ...defaults(kind, this.current, label),
    };
    if (!clear(spec, this.current.symbols)) return null;
    if (snapshot) this.push();
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

  /**
   * Drop it. Refused where the squares are taken, so a drop the ghost showed
   * as blocked is a drop that does nothing.
   *
   * A portal is placed as a pair (ADR-0020): dropping the first half puts its
   * mate straight back in flight wearing the same label, so the next click
   * lands the far end. The mate starts turned 180 degrees, because track that
   * vanishes and continues the same way somewhere else has its two mouths
   * facing opposite; `r` turns it for the drawings that do not.
   */
  dropPending(x: number, y: number): string | null {
    const landing = this.placementAt(x, y);
    if (this.placing === null || landing === null) return null;
    if (landing.blocked.length > 0) return null;
    const { kind, label } = this.placing;
    const facing = facingOf(this.placing);
    this.placing = null;
    if (kind !== "portal" || label !== undefined) {
      return this.put(kind, landing.at, facing, label, label === undefined);
    }
    const wearing = mintLabel(this.current);
    const name = this.put(kind, landing.at, facing, wearing, true);
    if (name !== null) {
      this.placing = { ...turned(turned({ kind, ...facing })), label: wearing };
    }
    return name;
  }

  /** Whether what is in flight is the second half of a portal pair, which is
   *  the one pending placement a release does not abandon: it was put there by
   *  a drop rather than by a press on the palette. */
  get mating(): boolean {
    return this.placing !== null && this.placing.label !== undefined;
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

  /**
   * The motorised symbols carrying no address: a drawing that derives and
   * cannot yet be driven (ADR-0022, ADR-0024).
   *
   * Whether an address is the right one is knowledge the drawing does not
   * hold, so having none at all is the whole of the check. It is read off the
   * open document, as an overlap is, so the mark clears on the keystroke that
   * types one rather than on the next answer from the store.
   *
   * Which kinds have a motor is the library's, through `motorised`; a fixed
   * crossing has none and is never named.
   */
  unaddressed(): string[] {
    return Object.entries(this.current.symbols)
      .filter(([, spec]) => motorised(spec.kind) && !spec.addr)
      .map(([name]) => name);
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
   *  as red — unless it is a bend left holding nothing, which `sweep` takes. */
  remove(): void {
    if (this.chosen.size === 0) return;
    this.push();
    const gone = new Set(this.chosen);
    for (const name of gone) delete this.current.symbols[name];
    this.current.wires = this.current.wires.filter(
      (wire) => !wirePins(wire).some((pin) => gone.has(symbolOf(pin))),
    );
    this.chosen = new Set();
    this.sweep();
  }

  /**
   * Bends no wire touches at all, gone.
   *
   * A bend is wiring rather than track: it has no name anyone sees, covers no
   * square, and says nothing but where a wire turns a corner. One left holding
   * nothing is therefore debris — invisible on the canvas, hard to find in the
   * file, and enough on its own to make derivation refuse the drawing. A
   * symbol pin left short is the opposite: it is the mark that says where the
   * track now stops, so a bend still holding one wire stays and stays red.
   *
   * Every such bend goes, not only the ones this edit stranded. Since no edit
   * can leave one any more, the rest are what a drawing was opened with, and
   * taking those is a repair: they cannot be selected — a bend holding nothing
   * draws nothing to click — so the alternative is a file nobody can fix here.
   * It is the edit's own undo step either way.
   *
   * Sweeping cannot cascade: a bend with no wires holds none to take away.
   */
  private sweep(): void {
    for (const [name, spec] of Object.entries(this.current.symbols)) {
      if (spec.kind === "pin" && this.degree(`${name}.P`) === 0) {
        delete this.current.symbols[name];
      }
    }
    this.chosen = new Set(
      [...this.chosen].filter((name) => name in this.current.symbols),
    );
    if (
      this.drawingFrom !== null &&
      !(symbolOf(this.drawingFrom) in this.current.symbols)
    ) {
      this.drawingFrom = null;
    }
  }

  /**
   * Cut a wire, and say whether there was one to cut. Both pins it held are
   * left short of one, which `/review` reports as red — the normal state of a
   * drawing mid-edit, and what says where the track now stops. A bend left
   * holding nothing is not that state and goes, `sweep` saying why.
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
    this.sweep();
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
      // A wire in flight points at a pin by name too, and the dialog opens
      // without ending one. Left behind it would write a wire naming a symbol
      // that no longer exists, which the store refuses to load.
      if (this.drawingFrom !== null && symbolOf(this.drawingFrom) === was) {
        this.drawingFrom = `${name}${this.drawingFrom.slice(was.length)}`;
      }
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

  /**
   * The same pass, run once on the drawing as it was opened, with no typed
   * connection name honoured (naming.ts). A name a person typed is one the
   * editor cannot settle when an edit merges two connections wearing them, so
   * no open drawing holds one.
   *
   * Not an undo step: `reset` has just emptied the stack, and the drawing as
   * opened is the drawing as loaded.
   */
  remint(review: Review, at: number): boolean {
    return at === this.revision && remint(this.current, review);
  }

  /** How many times the document has changed. Only useful for telling whether
   *  it changed while something else was being worked out. */
  get revision(): number {
    return this.changes;
  }

  // --- drawing wires ------------------------------------------------------

  /**
   * Start a wire at a pin, or end the one in progress there. Refused at a pin
   * whose symbol is not there, which a press held across a delete can offer.
   *
   * This is the invariant the rest of the wire-drawing relies on: a wire in
   * flight always names a pin that exists, kept true here, by `sweep` when the
   * symbol goes, and by `edit` when it is renamed. Without it the next click
   * writes a wire naming nothing, and the drawing will not load again.
   */
  startWire(pin: PinRef): void {
    if (!(symbolOf(pin) in this.current.symbols)) return;
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
   *  finished join while being a parallel edge nobody drew. */
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
   * stretches it rather than breaking the join.
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
    // Nothing in flight outlives the undo of what it was anchored to. A wire
    // would otherwise name a pin that is gone (#74); a portal's mate would
    // land wearing a label nothing else wears, which is the lone portal the
    // pair exists to prevent (ADR-0020).
    this.placing = null;
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
 *  document the store will take. A portal's label is what pairs it: `label` is
 *  the one its mate already wears, and a first half mints a fresh one. */
function defaults(
  kind: Kind,
  drawing: Drawing,
  label?: string,
): Partial<SymbolSpec> {
  if (kind === "block") return { length: 1000 };
  if (kind === "portal") return { label: label ?? mintLabel(drawing) };
  return {};
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

/**
 * The lowest `p<n>` no portal wears.
 *
 * Labels are minted from the labels in the drawing rather than from `mint()`'s
 * free names, because deletion frees a name while a label outlives it: delete
 * one portal of the pair labelled `p1` and the survivor still wears `p1`, so a
 * label minted as a name would hand `p1` to the next portal placed and pair it
 * with the orphan (ADR-0020).
 */
export function mintLabel(drawing: Drawing): string {
  const worn = new Set(
    Object.values(drawing.symbols)
      .filter((spec) => spec.kind === "portal")
      .map((spec) => spec.label),
  );
  for (let n = 1; ; n++) {
    const label = `${PREFIXES.portal}${n}`;
    if (!worn.has(label)) return label;
  }
}

/** The lowest free `<prefix><n>` for a kind. */
export function mint(drawing: Drawing, kind: Kind): string {
  const prefix = PREFIXES[kind];
  for (let n = 1; ; n++) {
    const name = `${prefix}${n}`;
    if (!(name in drawing.symbols)) return name;
  }
}
