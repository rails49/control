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

  it("labels a fresh portal after itself rather than leaving it unnamed", () => {
    const name = editor.place("portal", [0, 0])!;
    expect(editor.drawing.symbols[name]!.label).toBe(name);
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
    expect(Object.keys(editor.drawing.symbols)).toEqual(["end1"]);
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
    editor.select(["end1"]);
    expect(editor.canMove(4, 0)).toBe(false);
    editor.move(4, 0);
    expect(editor.drawing.symbols.end1!.at).toEqual([0, 0]);
  });

  it("allows the offsets either side of it", () => {
    editor.select(["end1"]);
    expect(editor.canMove(3, 0)).toBe(true);
    expect(editor.canMove(5, 0)).toBe(true);
  });

  it("ignores the symbols moving with it", () => {
    editor.select(["end1", "end2"]);
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
      { cell: [0, 3], symbols: ["b1", "end1"] },
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
    place("terminal", [6, 0]); // end1.P is at (6, 0.5)
    expect(wires()).toEqual(["b1.B end1.P"]);
  });

  it("leaves the wire behind when the symbol is dragged away", () => {
    // Position never determines topology: the joint is in the file, so
    // dragging stretches the wire instead of breaking it.
    place("block", [0, 0]);
    place("terminal", [6, 0]);
    editor.select(["end1"]);
    editor.move(4, 3);
    expect(wires()).toEqual(["b1.B end1.P"]);
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
    expect(wires()).toEqual(["b1.A n1.P", "b1.B end1.P"]);
  });

  it("does not join a pin that already holds its wire", () => {
    place("block", [0, 0]);
    place("terminal", [6, 0]);
    editor.select(["b1"]);
    editor.move(0, 0); // no move at all, and nothing to re-join
    expect(wires()).toEqual(["b1.B end1.P"]);
  });

  it("does not join two bends twice over", () => {
    // Both pins want two wires, so a second wire between the same pair fills
    // both and reads as a finished joint while being an edge nobody drew.
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
    editor.startWire("end1.P");
    editor.bend(2.5, 0); // n1.P on the north face of (2, 0)
    editor.cancelWire();
    place("terminal", [2, 0]); // end2.P at (2, 0.5): nothing to join
    expect(wires()).toEqual(["end1.P n1.P"]);
    editor.select(["end2"]);
    editor.rotate(); // end2.P swings to (2.5, 0), onto the bend
    expect(wires()).toEqual(["end1.P n1.P", "end2.P n1.P"]);
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
    place("terminal", [6, 0]); // abuts, filling end1.P
    place("block", [8, 0]);
    editor.startWire("b2.A");
    expect(editor.endWire("end1.P")).toBe(false);
    expect(wires()).toEqual(["b1.B end1.P"]);
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
    editor.select(["end1"]);
    editor.remove();
    expect(editor.drawing.symbols.end1).toBeUndefined();
    expect(wires()).toEqual([]);
  });

  it("leaves the far pin a wire short, which is what makes it red", () => {
    place("block", [0, 0]);
    place("terminal", [6, 0]);
    editor.select(["end1"]);
    editor.remove();
    expect(editor.degree("b1.B")).toBe(0);
    expect(editor.free("b1.B")).toBe(true);
  });

  it("clears the selection it just deleted", () => {
    place("block", [0, 0]);
    editor.select(["b1"]);
    editor.remove();
    expect([...editor.selection]).toEqual([]);
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
    editor.select(["end1"]);
    editor.remove();
    editor.undo();
    expect(wires()).toEqual(["b1.B end1.P"]);
    expect(editor.drawing.symbols.end1).toBeDefined();
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

describe("the properties dialog", () => {
  it("takes a symbol's own properties", () => {
    place("block", [0, 0]);
    editor.edit("b1", "b1", {
      kind: "block",
      at: [0, 0],
      length: 2400,
      label: "Zürich HB Gleis 1",
    });
    expect(editor.drawing.symbols.b1!.length).toBe(2400);
    expect(editor.drawing.symbols.b1!.label).toBe("Zürich HB Gleis 1");
  });

  it("rewrites every wire when a symbol is renamed", () => {
    // A wire is written `<symbol>.<pin>` and is the only thing pointing at a
    // symbol, so a rename that missed one would break the drawing silently.
    place("block", [0, 0]);
    place("terminal", [6, 0]);
    editor.edit("b1", "up_w", { kind: "block", at: [0, 0], length: 1000 });
    expect(wires()).toEqual(["end1.P up_w.B"]);
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

describe("naming a junction by hand", () => {
  it("writes the name onto every symbol of the region, undoably", () => {
    place("turnout", [0, 0]);
    place("turnout", [4, 0]);
    expect(editor.nameJunction(["sw1", "sw2"], "airolo")).toBe(true);
    expect(editor.drawing.symbols.sw2!.connection).toBe("airolo");
    editor.undo();
    expect(editor.drawing.symbols.sw2!.connection).toBeUndefined();
  });

  it("refuses what the drawing schema would refuse", () => {
    place("turnout", [0, 0]);
    expect(editor.nameJunction(["sw1"], "")).toBe(false);
    expect(editor.nameJunction(["sw1"], "a.b")).toBe(false);
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
