import { beforeEach, describe, expect, it } from "vitest";

import {
  emptyDrawing,
  wirePins,
  type Drawing,
  type PinRef,
} from "../src/model/drawing.js";
import { Editor } from "../src/model/editor.js";
import { anchorOf } from "../src/model/geometry.js";

let editor: Editor;

beforeEach(() => {
  editor = new Editor(emptyDrawing("test"));
});

/** Every wire, as its two pins sorted, which is how one is compared. */
function wires(): string[] {
  return editor.drawing.wires
    .map((wire) => [...wirePins(wire)].sort().join(" "))
    .sort();
}

function place(kind: "block" | "turnout" | "terminal", at: [number, number]) {
  return editor.place(kind, at);
}

describe("placing symbols", () => {
  it("mints the lowest free name per kind", () => {
    expect(place("block", [0, 0])).toBe("b1");
    expect(place("block", [0, 4])).toBe("b2");
    expect(place("turnout", [0, 8])).toBe("sw1");
  });

  it("gives a block a length, so the drawing the store takes is complete", () => {
    place("block", [0, 0]);
    expect(editor.drawing.symbols.b1!.length).toBe(1000);
  });

  it("labels a fresh portal rather than leaving it unnamed", () => {
    const name = editor.place("portal", [0, 0])!;
    expect(editor.drawing.symbols[name]!.label).toBe("p1");
  });

  it("selects what it just placed", () => {
    const name = place("block", [0, 0]);
    expect([...editor.selection]).toEqual([name]);
  });
});

/**
 * A square holds at most one symbol (EDITOR.md#canvas). A block is six of them,
 * so a placement can cover another symbol without its own cell being taken,
 * which is the case worth testing: the canvas only hit-tests the cell clicked.
 */
describe("a placement that would cover another symbol", () => {
  it("is refused, and writes nothing", () => {
    place("terminal", [3, 0]);
    expect(place("block", [0, 0])).toBeNull();
    expect(Object.keys(editor.drawing.symbols)).toEqual(["e1"]);
  });

  it("is refused without spending an undo step", () => {
    place("terminal", [3, 0]);
    place("block", [0, 0]);
    expect(editor.canUndo).toBe(true);
    editor.undo();
    expect(editor.drawing.symbols).toEqual({});
  });

  it("takes the same cell once the other symbol is gone", () => {
    place("terminal", [3, 0]);
    editor.remove();
    expect(place("block", [0, 0])).toBe("b1");
  });

  it("lets a bend sit on an occupied square, covering none itself", () => {
    place("block", [0, 0]);
    editor.startWire("b1.B");
    editor.bend(3, 0.5); // a face of a square the block covers
    expect(editor.overlaps()).toEqual([]);
  });
});

describe("moving a selection onto another symbol", () => {
  beforeEach(() => {
    place("terminal", [0, 0]);
    place("terminal", [4, 0]);
  });

  it("refuses the offset that would land on it", () => {
    editor.select(["e1"]);
    expect(editor.canMove(4, 0)).toBe(false);
    editor.move(4, 0);
    expect(editor.drawing.symbols.e1!.at).toEqual([0, 0]);
  });

  it("allows the offsets either side of it", () => {
    editor.select(["e1"]);
    expect(editor.canMove(3, 0)).toBe(true);
    expect(editor.canMove(5, 0)).toBe(true);
  });

  it("ignores the symbols moving with it", () => {
    editor.select(["e1", "e2"]);
    expect(editor.canMove(4, 0)).toBe(true);
  });
});

describe("an overlap a rotate made", () => {
  it("is reported, naming the symbols and the squares they share", () => {
    place("block", [0, 0]);
    place("terminal", [0, 3]);
    expect(editor.overlaps()).toEqual([]);
    // The block runs east over six squares; turned, it runs south over the
    // terminal's.
    editor.select(["b1"]);
    editor.rotate();
    expect(editor.overlaps()).toEqual([
      { cell: [0, 3], symbols: ["b1", "e1"] },
    ]);
  });

  it("stops being reported once the overlap is undone", () => {
    place("block", [0, 0]);
    place("terminal", [0, 3]);
    editor.select(["b1"]);
    editor.rotate();
    expect(editor.overlaps()).toHaveLength(1);
    editor.undo();
    expect(editor.overlaps()).toEqual([]);
  });
});

/**
 * A turnout and a slip are driven by commanding an address (ADR-0022), so one
 * carrying none is a drawing that derives and cannot be run. The editor cannot
 * say whether an address is right — only the person wiring the railroad knows
 * that — so having none is the whole of the check, and it is read off the open
 * drawing the way an overlap is.
 */
describe("a motorised symbol with no address", () => {
  it("names a turnout and both slips", () => {
    place("turnout", [0, 0]);
    editor.place("single_slip", [3, 0]);
    editor.place("double_slip", [6, 0]);
    expect(editor.unaddressed().sort()).toEqual(["ds1", "ss1", "sw1"]);
  });

  it("passes over a fixed crossing, which has no motor to address", () => {
    editor.place("crossing", [0, 0]);
    editor.place("crossing_90", [3, 0]);
    editor.place("crossing_90d", [5, 0]);
    place("block", [0, 3]);
    editor.place("portal", [0, 6]);
    expect(editor.unaddressed()).toEqual([]);
  });

  it("stops naming it as soon as an address is typed", () => {
    place("turnout", [0, 0]);
    const spec = editor.drawing.symbols.sw1!;
    expect(editor.edit("sw1", "sw1", { ...spec, addr: "31" })).toBe(true);
    expect(editor.unaddressed()).toEqual([]);
  });

  it("names it again when the address is cleared", () => {
    place("turnout", [0, 0]);
    const spec = editor.drawing.symbols.sw1!;
    editor.edit("sw1", "sw1", { ...spec, addr: "31" });
    editor.edit("sw1", "sw1", { ...spec, addr: "" });
    expect(editor.unaddressed()).toEqual(["sw1"]);
  });
});

describe("staging a drawing that has never been placed", () => {
  const unplaced = (): Drawing => ({
    drawing: "facing-pair",
    symbols: {
      west: { kind: "block", length: 1000 },
      east: { kind: "block", length: 1000 },
      west_stop: { kind: "terminal" },
    },
    wires: [["west.B", "east.A"]],
  });

  it("gives every symbol somewhere of its own to be dragged from", () => {
    editor.reset(unplaced());
    expect(editor.stage()).toBe(true);
    const seen = Object.values(editor.drawing.symbols).map((spec) =>
      String(spec.at),
    );
    expect(new Set(seen).size).toBe(3);
  });

  it("leaves a placed drawing exactly as it found it", () => {
    const drawing = unplaced();
    for (const [index, spec] of Object.values(drawing.symbols).entries()) {
      spec.at = [index * 4, 0];
    }
    editor.reset(drawing);
    expect(editor.stage()).toBe(false);
    expect(editor.canUndo).toBe(false);
  });

  it("is an ordinary edit, so undo takes it back", () => {
    editor.reset(unplaced());
    editor.stage();
    editor.undo();
    expect(editor.drawing.symbols.west!.at).toBeUndefined();
  });

  it("touches no wire, so it cannot change what derives", () => {
    editor.reset(unplaced());
    editor.stage();
    expect(wires()).toEqual(["east.A west.B"]);
  });
});

describe("abutting", () => {
  it("writes a real wire when a pin lands on another's", () => {
    place("block", [0, 0]); // b1.B is at (6, 0.5)
    place("terminal", [6, 0]); // e1.P is at (6, 0.5)
    expect(wires()).toEqual(["b1.B e1.P"]);
  });

  it("leaves the wire behind when the symbol is dragged away", () => {
    // Position never determines topology: the join is in the file, so
    // dragging stretches the wire instead of breaking it.
    place("block", [0, 0]);
    place("terminal", [6, 0]);
    editor.select(["e1"]);
    editor.move(4, 3);
    expect(wires()).toEqual(["b1.B e1.P"]);
  });

  it("joins a pin once, however many pins share the point", () => {
    // A square holds one symbol, so the pins that can meet at a point are the
    // two either side of the face plus any number of bends, which cover no
    // square. Both of the first two fill up, leaving the bend nothing to join.
    place("block", [0, 0]);
    place("terminal", [6, 0]);
    editor.startWire("b1.A");
    editor.bend(8, 0.5);
    editor.cancelWire();
    editor.select(["n1"]);
    editor.move(-2, 0);
    expect(wires()).toEqual(["b1.A n1.P", "b1.B e1.P"]);
  });

  it("does not join a pin that already holds its wire", () => {
    place("block", [0, 0]);
    place("terminal", [6, 0]);
    editor.select(["b1"]);
    editor.move(0, 0); // no move at all, and nothing to re-join
    expect(wires()).toEqual(["b1.B e1.P"]);
  });

  it("does not join two bends twice over", () => {
    // Both pins want two wires, so a second wire between the same pair fills
    // both and reads as a finished join while being an edge nobody drew.
    place("block", [0, 0]);
    editor.startWire("b1.B");
    editor.bend(8, 0.5);
    editor.cancelWire();
    place("block", [0, 4]);
    editor.startWire("b2.B");
    editor.bend(8, 0.5);
    editor.cancelWire();
    editor.select(["n1", "n2"]);
    editor.move(1, 0);
    expect(wires().filter((wire) => wire === "n1.P n2.P")).toHaveLength(1);
  });

  it("joins on a rotation that brings two pins together", () => {
    // The pin the rotation arrives at is a bend, which covers no square: two
    // symbols that both cover one could not be here to meet.
    place("terminal", [0, 0]);
    editor.startWire("e1.P");
    editor.bend(2.5, 0); // n1.P on the north face of (2, 0)
    editor.cancelWire();
    place("terminal", [2, 0]); // e2.P at (2, 0.5): nothing to join
    expect(wires()).toEqual(["e1.P n1.P"]);
    editor.select(["e2"]);
    editor.rotate(); // e2.P swings to (2.5, 0), onto the bend
    expect(wires()).toEqual(["e1.P n1.P", "e2.P n1.P"]);
  });
});

describe("drawing wires", () => {
  it("joins two pins", () => {
    place("block", [0, 0]);
    place("block", [7, 0]);
    editor.startWire("b1.B");
    expect(editor.endWire("b2.A")).toBe(true);
    expect(wires()).toEqual(["b1.B b2.A"]);
    expect(editor.pendingFrom).toBeNull();
  });

  it("bends through a free-standing pin on a click on empty canvas", () => {
    place("block", [0, 0]);
    place("block", [4, 4]);
    editor.startWire("b1.B");
    const bend = editor.bend(3.5, 1);
    expect(bend).toBe("n1.P");
    expect(editor.drawing.symbols.n1!.kind).toBe("pin");
    expect(editor.endWire("b2.A")).toBe(true);
    expect(wires()).toEqual(["b1.B n1.P", "b2.A n1.P"]);
  });

  it("puts the bend where it was clicked", () => {
    place("block", [0, 0]);
    editor.startWire("b1.B");
    editor.bend(3.4, 1.6);
    const { x, y } = anchorOf(editor.drawing.symbols.n1!, "P");
    expect(Math.hypot(x - 3.4, y - 1.6)).toBeLessThan(0.75);
  });

  it("refuses a pin that already holds its wire", () => {
    place("block", [0, 0]);
    place("terminal", [6, 0]); // abuts, filling e1.P
    place("block", [8, 0]);
    editor.startWire("b2.A");
    expect(editor.endWire("e1.P")).toBe(false);
    expect(wires()).toEqual(["b1.B e1.P"]);
  });

  it("refuses to end a wire where it started", () => {
    place("block", [0, 0]);
    editor.startWire("b1.B");
    expect(editor.endWire("b1.B")).toBe(false);
  });

  it("lets a bend take its second wire but not a third", () => {
    place("block", [0, 0]);
    place("block", [8, 0]);
    place("block", [8, 4]);
    editor.startWire("b1.B");
    editor.bend(8, 0.5);
    editor.endWire("b2.A");
    expect(editor.free("n1.P")).toBe(false);
  });

  it("refuses a second wire between the same two pins", () => {
    place("block", [0, 0]);
    editor.startWire("b1.B");
    editor.bend(8, 0.5);
    editor.cancelWire();
    place("block", [0, 4]);
    editor.startWire("b2.B");
    editor.bend(8, 0.5);
    editor.endWire("n1.P");
    editor.startWire("n1.P");
    expect(editor.endWire("n2.P")).toBe(false);
  });

  it("abandons the wire when the pin it starts from is deleted", () => {
    // Otherwise the next click writes a wire naming a symbol that is gone,
    // which the store refuses to load: an unwired bend is debris, but this is
    // a file that will not open.
    place("block", [0, 0]);
    place("block", [10, 0]);
    editor.select(["b1"]);
    editor.startWire("b1.B");
    editor.remove();

    expect(editor.pendingFrom).toBeNull();
    expect(editor.endWire("b2.A")).toBe(false);
    expect(wires()).toEqual([]);
  });

  it("abandons the wire when the bend it starts from is swept", () => {
    place("block", [0, 0]);
    place("block", [10, 0]);
    editor.startWire("b1.B");
    editor.bend(8, 0.5); // n1, holding the one wire, and the wire goes on

    editor.unwire(["b1.B", "n1.P"]);

    expect(editor.drawing.symbols.n1).toBeUndefined();
    expect(editor.pendingFrom).toBeNull();
    expect(editor.endWire("b2.A")).toBe(false);
    expect(wires()).toEqual([]);
  });

  it("follows the pin it starts from through a rename", () => {
    place("block", [0, 0]);
    place("block", [10, 0]);
    editor.startWire("b1.B");
    editor.edit("b1", "west", { ...editor.drawing.symbols.b1!, kind: "block" });

    expect(editor.pendingFrom).toBe("west.B");
    expect(editor.endWire("b2.A")).toBe(true);
    expect(wires()).toEqual(["b2.A west.B"]);
  });

  it("refuses to start at a pin whose symbol is gone", () => {
    // The invariant the rest of this relies on: a wire in flight always names
    // a pin that is there, so nothing downstream has to check.
    place("block", [0, 0]);
    place("block", [10, 0]);
    editor.select(["b1"]);
    editor.remove();

    editor.startWire("b1.B");

    expect(editor.pendingFrom).toBeNull();
    expect(editor.endWire("b2.A")).toBe(false);
    expect(wires()).toEqual([]);
  });

  it("leaves what is drawn behind when the wire is abandoned", () => {
    // A red pin is the normal state of a drawing mid-edit, so abandoning is
    // not an undo.
    place("block", [0, 0]);
    editor.startWire("b1.B");
    editor.bend(8, 0.5);
    editor.cancelWire();
    expect(wires()).toEqual(["b1.B n1.P"]);
    expect(editor.pendingFrom).toBeNull();
  });
});

describe("deleting", () => {
  it("takes the symbol's wires with it", () => {
    place("block", [0, 0]);
    place("terminal", [6, 0]);
    editor.select(["e1"]);
    editor.remove();
    expect(editor.drawing.symbols.e1).toBeUndefined();
    expect(wires()).toEqual([]);
  });

  it("leaves the far pin a wire short, which is what makes it red", () => {
    place("block", [0, 0]);
    place("terminal", [6, 0]);
    editor.select(["e1"]);
    editor.remove();
    expect(editor.degree("b1.B")).toBe(0);
    expect(editor.free("b1.B")).toBe(true);
  });

  it("sweeps up a bend both its neighbours left behind", () => {
    place("block", [0, 0]);
    editor.startWire("b1.B");
    editor.bend(8, 0.5);
    place("block", [10, 0]);
    editor.startWire("n1.P");
    editor.endWire("b2.A");

    editor.select(["b1", "b2"]);
    editor.remove();

    expect(editor.drawing.symbols.n1).toBeUndefined();
  });

  it("clears the selection it just deleted", () => {
    place("block", [0, 0]);
    editor.select(["b1"]);
    editor.remove();
    expect([...editor.selection]).toEqual([]);
  });
});

/** A wire has no symbol to select, so cutting it is the one verb that takes
 *  what it acts on rather than reading the selection. */
describe("cutting a wire", () => {
  it("drops it, leaving both symbols and both pins short", () => {
    place("block", [0, 0]);
    place("terminal", [6, 0]);
    expect(wires()).toEqual(["b1.B e1.P"]);

    expect(editor.unwire(["b1.B", "e1.P"])).toBe(true);

    expect(wires()).toEqual([]);
    expect(editor.drawing.symbols.b1).toBeDefined();
    expect(editor.drawing.symbols.e1).toBeDefined();
    expect(editor.degree("b1.B")).toBe(0);
    expect(editor.degree("e1.P")).toBe(0);
  });

  it("takes the pins in either order, a wire being undirected", () => {
    place("block", [0, 0]);
    place("terminal", [6, 0]);
    expect(editor.unwire(["e1.P", "b1.B"])).toBe(true);
    expect(wires()).toEqual([]);
  });

  it("cuts the one wire and no other", () => {
    place("block", [0, 0]);
    place("terminal", [6, 0]);
    editor.place("terminal", [-1, 0], { rot: 180 });
    expect(wires()).toEqual(["b1.A e2.P", "b1.B e1.P"]);
    editor.unwire(["b1.B", "e1.P"]);
    expect(wires()).toEqual(["b1.A e2.P"]);
  });

  it("says so where there is no such wire, and changes nothing", () => {
    place("block", [0, 0]);
    place("terminal", [6, 0]);
    const was = editor.revision;
    expect(editor.unwire(["b1.A", "e1.P"])).toBe(false);
    expect(wires()).toEqual(["b1.B e1.P"]);
    // No snapshot taken, so it is not an undo step of its own.
    expect(editor.revision).toBe(was);
  });

  it("sweeps up the bend whose last wire it was", () => {
    place("block", [0, 0]);
    editor.startWire("b1.B");
    editor.bend(8, 0.5);
    place("block", [10, 0]);
    editor.startWire("n1.P");
    editor.endWire("b2.A");

    editor.unwire(["b1.B", "n1.P"]);
    expect(editor.drawing.symbols.n1).toBeDefined(); // still holds one
    editor.unwire(["n1.P", "b2.A"]);

    expect(editor.drawing.symbols.n1).toBeUndefined();
  });

  it("puts a swept bend back on undo, the cut being one step", () => {
    place("block", [0, 0]);
    editor.startWire("b1.B");
    editor.bend(8, 0.5);
    editor.unwire(["b1.B", "n1.P"]);
    expect(editor.drawing.symbols.n1).toBeUndefined();

    editor.undo();

    expect(editor.drawing.symbols.n1).toBeDefined();
    expect(wires()).toEqual(["b1.B n1.P"]);
  });

  it("is one undo step", () => {
    place("block", [0, 0]);
    place("terminal", [6, 0]);
    editor.unwire(["b1.B", "e1.P"]);
    editor.undo();
    expect(wires()).toEqual(["b1.B e1.P"]);
  });
});

describe("moving", () => {
  it("moves every selected symbol together", () => {
    place("block", [0, 0]);
    place("block", [0, 4]);
    editor.select(["b1", "b2"]);
    editor.move(2, 1);
    expect(editor.drawing.symbols.b1!.at).toEqual([2, 1]);
    expect(editor.drawing.symbols.b2!.at).toEqual([2, 5]);
  });

  it("cannot change what the drawing means", () => {
    // Wires carry no geometry, so a move rubber-bands them by construction:
    // the wire list is the same list afterwards.
    place("block", [0, 0]);
    place("terminal", [6, 0]);
    const before = wires();
    editor.select(["b1"]);
    editor.move(-3, 5);
    expect(wires()).toEqual(before);
  });
});

describe("undo and redo", () => {
  it("restores the document one edit at a time", () => {
    place("block", [0, 0]);
    place("block", [7, 0]);
    editor.undo();
    expect(Object.keys(editor.drawing.symbols)).toEqual(["b1"]);
    editor.undo();
    expect(Object.keys(editor.drawing.symbols)).toEqual([]);
    expect(editor.canUndo).toBe(false);
  });

  it("restores wires as well as symbols", () => {
    place("block", [0, 0]);
    place("terminal", [6, 0]);
    editor.select(["e1"]);
    editor.remove();
    editor.undo();
    expect(wires()).toEqual(["b1.B e1.P"]);
    expect(editor.drawing.symbols.e1).toBeDefined();
  });

  it("redoes what it undid, and no more", () => {
    place("block", [0, 0]);
    editor.undo();
    editor.redo();
    expect(Object.keys(editor.drawing.symbols)).toEqual(["b1"]);
    expect(editor.canRedo).toBe(false);
  });

  it("drops the redo stack once a new edit lands on it", () => {
    place("block", [0, 0]);
    place("block", [7, 0]);
    editor.undo();
    place("turnout", [8, 0]);
    expect(editor.canRedo).toBe(false);
    expect(Object.keys(editor.drawing.symbols).sort()).toEqual(["b1", "sw1"]);
  });

  it("snapshots rather than sharing, so an edit cannot reach into the past", () => {
    place("block", [0, 0]);
    editor.select(["b1"]);
    editor.move(3, 3);
    editor.undo();
    expect(editor.drawing.symbols.b1!.at).toEqual([0, 0]);
  });

  it("forgets a selection the undo removed", () => {
    place("block", [0, 0]);
    place("block", [7, 0]);
    editor.select(["b1", "b2"]);
    editor.undo();
    expect([...editor.selection]).toEqual(["b1"]);
  });

  it("abandons a half-drawn wire", () => {
    place("block", [0, 0]);
    editor.startWire("b1.B");
    editor.bend(8, 0.5);
    editor.undo();
    expect(editor.pendingFrom).toBeNull();
    expect(wires()).toEqual([]);
  });
});

describe("renaming the drawing", () => {
  it("restamps the document", () => {
    editor.rename("fork");
    expect(editor.drawing.drawing).toBe("fork");
  });

  it("keeps the new name through undo, so Save keeps writing the new file", () => {
    place("block", [0, 0]);
    editor.rename("fork");
    editor.undo();
    expect(editor.drawing.drawing).toBe("fork");
    editor.redo();
    expect(editor.drawing.drawing).toBe("fork");
  });
});

describe("the properties dialog", () => {
  it("takes a symbol's own properties", () => {
    place("block", [0, 0]);
    editor.edit("b1", "b1", { kind: "block", at: [0, 0], length: 2400 });
    expect(editor.drawing.symbols.b1!.length).toBe(2400);
  });

  it("rewrites every wire when a symbol is renamed", () => {
    // A wire is written `<symbol>.<pin>` and is the only thing pointing at a
    // symbol, so a rename that missed one would break the drawing silently.
    place("block", [0, 0]);
    place("terminal", [6, 0]);
    editor.edit("b1", "up_w", { kind: "block", at: [0, 0], length: 1000 });
    expect(wires()).toEqual(["e1.P up_w.B"]);
    expect(editor.drawing.symbols.b1).toBeUndefined();
  });

  it("keeps a renamed symbol where the file wrote it", () => {
    // `put` merges by key and adds a new symbol at the end, so a rename that
    // deleted and re-added would move the symbol to the bottom of the file.
    place("block", [0, 0]);
    place("block", [7, 0]);
    place("block", [14, 0]);
    editor.edit("b2", "middle", { kind: "block", at: [7, 0], length: 1000 });
    expect(Object.keys(editor.drawing.symbols)).toEqual(["b1", "middle", "b3"]);
  });

  it("refuses a name the drawing cannot take", () => {
    place("block", [0, 0]);
    place("block", [7, 0]);
    const spec = { kind: "block" as const, at: [0, 0] as [number, number] };
    expect(editor.edit("b1", "b2", spec)).toBe(false); // taken
    expect(editor.edit("b1", "a.b", spec)).toBe(false); // a pin, not a symbol
    expect(editor.edit("b1", "", spec)).toBe(false);
    expect(Object.keys(editor.drawing.symbols)).toEqual(["b1", "b2"]);
  });

  it("brings the selection with the new name", () => {
    place("block", [0, 0]);
    editor.select(["b1"]);
    editor.edit("b1", "up_w", { kind: "block", at: [0, 0], length: 1000 });
    expect([...editor.selection]).toEqual(["up_w"]);
  });

  it("is one undo step, rename and properties together", () => {
    place("block", [0, 0]);
    editor.edit("b1", "up_w", { kind: "block", at: [0, 0], length: 2400 });
    editor.undo();
    expect(editor.drawing.symbols.b1!.length).toBe(1000);
  });
});

describe("reading the document", () => {
  it("reports every pin and where it sits", () => {
    place("block", [1, 1]);
    const found = new Map<PinRef, string>(
      editor.allPins().map(({ pin, x, y }) => [pin, `${x},${y}`]),
    );
    expect(found.get("b1.A")).toBe("1,1.5");
    expect(found.get("b1.B")).toBe("7,1.5");
  });
});

describe("dragging a symbol out of the palette", () => {
  it("centres the footprint on the pointer", () => {
    editor.beginPlace("turnout");
    // 1×1, so the pointer sits in the cell it lands on.
    expect(editor.placementAt(4.4, 2.6)!.at).toEqual([4, 2]);
  });

  it("centres a long footprint too, half a square off where it must be", () => {
    editor.beginPlace("block");
    // 6×1: the centre of cells 8..13 is 11, half a square from the pointer,
    // which is as close as a whole `at` allows.
    expect(editor.placementAt(10.5, 2.5)!.at).toEqual([8, 2]);
  });

  it("re-centres on the footprint a turn transposes", () => {
    editor.beginPlace("block");
    editor.turnPending();
    // 6×1 turned is 1×6: the pointer keeps the middle, so the span moves from
    // across to down.
    expect(editor.placementAt(10.5, 10.5)!.at).toEqual([10, 8]);
  });

  it("names the squares in the way before the drop, not just that there are some", () => {
    place("terminal", [4, 2]);
    editor.beginPlace("turnout");
    expect(editor.placementAt(4.5, 2.5)!.blocked).toEqual([[4, 2]]);
    expect(editor.placementAt(6.5, 2.5)!.blocked).toEqual([]);
  });

  it("drops nothing where the ghost said it was blocked", () => {
    place("terminal", [4, 2]);
    editor.beginPlace("turnout");
    expect(editor.dropPending(4.5, 2.5)).toBeNull();
    expect(Object.keys(editor.drawing.symbols)).toEqual(["e1"]);
  });

  it("writes the orientation it was dragged in", () => {
    editor.beginPlace("turnout");
    editor.turnPending();
    editor.flipPending();
    const name = editor.dropPending(4.5, 2.5)!;
    expect(editor.drawing.symbols[name]).toMatchObject({ rot: 90, flip: true });
  });

  it("keeps that orientation for the next drag, whatever the kind", () => {
    editor.beginPlace("turnout");
    editor.turnPending();
    editor.dropPending(4.5, 2.5);
    editor.beginPlace("terminal");
    expect(editor.pending).toMatchObject({ kind: "terminal", rot: 90 });
  });

  it("leaves a plain drop plain, writing no rot or flip at all", () => {
    editor.beginPlace("turnout");
    const name = editor.dropPending(4.5, 2.5)!;
    expect(editor.drawing.symbols[name]).toEqual({ kind: "turnout", at: [4, 2] });
  });

  it("wires what it lands against, like any other placement", () => {
    place("terminal", [0, 0]);
    editor.beginPlace("terminal");
    editor.flipPending(); // its pin swings from the west face to the east one
    editor.dropPending(-0.5, 0.5);
    expect(wires()).toEqual(["e1.P e2.P"]);
  });

  it("forgets the drag when it is abandoned", () => {
    editor.beginPlace("turnout");
    editor.cancelPending();
    expect(editor.pending).toBeNull();
    expect(editor.placementAt(4.5, 2.5)).toBeNull();
  });
});

/**
 * A portal is placed as a pair (ADR-0020): the drop lands one half and puts the
 * other straight back in flight, so a portal never sits alone by accident.
 */
describe("placing a portal", () => {
  /** The labels every portal in the drawing wears, in placement order. */
  function labels(): (string | undefined)[] {
    return Object.values(editor.drawing.symbols)
      .filter((spec) => spec.kind === "portal")
      .map((spec) => spec.label);
  }

  function dropFirst(x = 4.5, y = 2.5): string {
    editor.beginPlace("portal");
    return editor.dropPending(x, y)!;
  }

  it("puts the mate back in flight wearing the same label", () => {
    const name = dropFirst();
    expect(editor.pending).toMatchObject({
      kind: "portal",
      label: editor.drawing.symbols[name]!.label,
    });
  });

  it("turns the mate to face the other way", () => {
    dropFirst();
    expect(editor.pending!.rot).toBe(180);
  });

  it("turns the mate from the facing the first half was dropped in", () => {
    editor.beginPlace("portal");
    editor.turnPending(); // dropped at 90
    editor.dropPending(4.5, 2.5);
    expect(editor.pending!.rot).toBe(270);
  });

  it("leaves the pair wearing one label, with nothing left in flight", () => {
    dropFirst();
    editor.dropPending(20.5, 20.5);
    expect(labels()).toEqual(["p1", "p1"]);
    expect(editor.pending).toBeNull();
  });

  it("takes the pair back in one undo step", () => {
    dropFirst();
    editor.dropPending(20.5, 20.5);
    editor.undo();
    expect(labels()).toEqual([]);
  });

  it("cancels the flight when the half it was anchored to is undone", () => {
    dropFirst();
    editor.undo();
    expect(editor.pending).toBeNull();
    expect(labels()).toEqual([]);
  });

  /**
   * `mint()` frees a name on deletion but the label outlives it, so a label
   * minted as a name would be handed out while an orphan still wore it — and
   * the next portal placed would pair with that orphan silently.
   */
  it("skips a label an orphaned portal still wears", () => {
    dropFirst();
    editor.dropPending(20.5, 20.5); // p1 and p2, both labelled p1
    editor.select(["p1"]);
    editor.remove(); // p2 survives, still wearing label p1
    dropFirst(40.5, 40.5);
    expect(labels()).toEqual(["p1", "p2"]);
  });

  it("knows the mate from a symbol dragged off the palette", () => {
    editor.beginPlace("portal");
    expect(editor.mating).toBe(false);
    editor.dropPending(4.5, 2.5);
    expect(editor.mating).toBe(true);
  });

  /** A pair wears one label between the two of them, so labels advance once
   *  per pair while names advance once per portal: `p3` is called `p3` and
   *  labelled `p2`, which is the divergence ADR-0020 records. */
  it("mints a fresh label for a pair placed after another", () => {
    dropFirst();
    editor.dropPending(20.5, 20.5);
    dropFirst(40.5, 40.5);
    editor.dropPending(60.5, 60.5);
    expect(labels()).toEqual(["p1", "p1", "p2", "p2"]);
    expect(Object.keys(editor.drawing.symbols)).toEqual([
      "p1",
      "p2",
      "p3",
      "p4",
    ]);
  });
});

/**
 * A bend's `rot` is which face of its cell it sits on, so translating it by
 * whole cells keeps it on faces of that one orientation for ever
 * (EDITOR.md#canvas).
 */
describe("dragging a bend", () => {
  beforeEach(() => {
    place("block", [0, 0]);
    editor.startWire("b1.B");
    editor.bend(8, 0.5); // the west face of (8, 0)
  });

  it("starts on the face it was drawn on", () => {
    expect(editor.drawing.symbols.n1).toMatchObject({ at: [8, 0], rot: 0 });
  });

  it("reaches a face of the other orientation, which a move cannot", () => {
    editor.select(["n1"]);
    editor.move(0, 2);
    expect(editor.drawing.symbols.n1!.rot).toBe(0); // still a west face

    expect(editor.reface("n1", 8.5, 2)).toBe(true);
    expect(editor.drawing.symbols.n1).toMatchObject({ at: [8, 2], rot: 90 });
  });

  it("and back again", () => {
    editor.reface("n1", 8.5, 2);
    expect(editor.reface("n1", 6, 3.5)).toBe(true);
    expect(editor.drawing.symbols.n1).toMatchObject({ at: [6, 3], rot: 0 });
  });

  it("spends no undo step on a drag that did not move it", () => {
    const before = editor.revision;
    expect(editor.reface("n1", 8, 0.5)).toBe(false);
    expect(editor.revision).toBe(before);
  });

  it("keeps the wires it holds, which rubber-band with it", () => {
    editor.reface("n1", 8.5, 2);
    expect(wires()).toEqual(["b1.B n1.P"]);
  });

  it("refuses anything that is not a bend", () => {
    expect(editor.reface("b1", 3, 3)).toBe(false);
  });
});
