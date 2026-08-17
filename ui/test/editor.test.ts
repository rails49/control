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
    const name = editor.place("portal", [0, 0]);
    expect(editor.drawing.symbols[name]!.label).toBe(name);
  });

  it("selects what it just placed", () => {
    const name = place("block", [0, 0]);
    expect([...editor.selection]).toEqual([name]);
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
    place("block", [0, 0]); // b1.B is at (2, 0.5)
    place("terminal", [2, 0]); // end1.P is at (2, 0.5)
    expect(wires()).toEqual(["b1.B end1.P"]);
  });

  it("leaves the wire behind when the symbol is dragged away", () => {
    // Position never determines topology: the joint is in the file, so
    // dragging stretches the wire instead of breaking it.
    place("block", [0, 0]);
    place("terminal", [2, 0]);
    editor.select(["end1"]);
    editor.move(4, 3);
    expect(wires()).toEqual(["b1.B end1.P"]);
  });

  it("joins a pin once, however many pins share the point", () => {
    place("block", [0, 0]);
    place("terminal", [2, 0]);
    place("terminal", [2, 0]);
    expect(wires()).toEqual(["b1.B end1.P"]);
  });

  it("does not join a pin that already holds its wire", () => {
    place("block", [0, 0]);
    place("terminal", [2, 0]);
    editor.select(["b1"]);
    editor.move(0, 0); // no move at all, and nothing to re-join
    expect(wires()).toEqual(["b1.B end1.P"]);
  });

  it("does not join two bends twice over", () => {
    // Both pins want two wires, so a second wire between the same pair fills
    // both and reads as a finished joint while being an edge nobody drew.
    place("block", [0, 0]);
    editor.startWire("b1.B");
    editor.bend(4, 0.5);
    editor.cancelWire();
    place("block", [0, 4]);
    editor.startWire("b2.B");
    editor.bend(4, 0.5);
    editor.cancelWire();
    editor.select(["n1", "n2"]);
    editor.move(1, 0);
    expect(wires().filter((wire) => wire === "n1.P n2.P")).toHaveLength(1);
  });

  it("joins on a rotation that brings two pins together", () => {
    place("block", [0, 0]); // A at (0, 0.5), B at (2, 0.5)
    place("terminal", [3, 0]); // P at (3, 0.5): nothing to join
    expect(wires()).toEqual([]);
    editor.select(["end1"]);
    editor.rotate(); // P swings to (3.5, 0)
    editor.rotate(); // and on to (4, 0.5)
    expect(wires()).toEqual([]);
    editor.select(["b1"]);
    editor.move(2, 0); // b1.B now at (4, 0.5)
    expect(wires()).toEqual(["b1.B end1.P"]);
  });
});

describe("drawing wires", () => {
  it("joins two pins", () => {
    place("block", [0, 0]);
    place("block", [4, 0]);
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
    place("terminal", [2, 0]); // abuts, filling end1.P
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
    editor.bend(4, 0.5);
    editor.endWire("b2.A");
    expect(editor.free("n1.P")).toBe(false);
  });

  it("refuses a second wire between the same two pins", () => {
    place("block", [0, 0]);
    editor.startWire("b1.B");
    editor.bend(4, 0.5);
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
    editor.bend(4, 0.5);
    editor.cancelWire();
    expect(wires()).toEqual(["b1.B n1.P"]);
    expect(editor.pendingFrom).toBeNull();
  });
});

describe("deleting", () => {
  it("takes the symbol's wires with it", () => {
    place("block", [0, 0]);
    place("terminal", [2, 0]);
    editor.select(["end1"]);
    editor.remove();
    expect(editor.drawing.symbols.end1).toBeUndefined();
    expect(wires()).toEqual([]);
  });

  it("leaves the far pin a wire short, which is what makes it red", () => {
    place("block", [0, 0]);
    place("terminal", [2, 0]);
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
    place("terminal", [2, 0]);
    const before = wires();
    editor.select(["b1"]);
    editor.move(-3, 5);
    expect(wires()).toEqual(before);
  });
});

describe("undo and redo", () => {
  it("restores the document one edit at a time", () => {
    place("block", [0, 0]);
    place("block", [4, 0]);
    editor.undo();
    expect(Object.keys(editor.drawing.symbols)).toEqual(["b1"]);
    editor.undo();
    expect(Object.keys(editor.drawing.symbols)).toEqual([]);
    expect(editor.canUndo).toBe(false);
  });

  it("restores wires as well as symbols", () => {
    place("block", [0, 0]);
    place("terminal", [2, 0]);
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
    place("block", [4, 0]);
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
    place("block", [4, 0]);
    editor.select(["b1", "b2"]);
    editor.undo();
    expect([...editor.selection]).toEqual(["b1"]);
  });

  it("abandons a half-drawn wire", () => {
    place("block", [0, 0]);
    editor.startWire("b1.B");
    editor.bend(4, 0.5);
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
    place("terminal", [2, 0]);
    editor.edit("b1", "up_w", { kind: "block", at: [0, 0], length: 1000 });
    expect(wires()).toEqual(["end1.P up_w.B"]);
    expect(editor.drawing.symbols.b1).toBeUndefined();
  });

  it("keeps a renamed symbol where the file wrote it", () => {
    // `put` merges by key and adds a new symbol at the end, so a rename that
    // deleted and re-added would move the symbol to the bottom of the file.
    place("block", [0, 0]);
    place("block", [4, 0]);
    place("block", [8, 0]);
    editor.edit("b2", "middle", { kind: "block", at: [4, 0], length: 1000 });
    expect(Object.keys(editor.drawing.symbols)).toEqual(["b1", "middle", "b3"]);
  });

  it("refuses a name the drawing cannot take", () => {
    place("block", [0, 0]);
    place("block", [4, 0]);
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
    expect(found.get("b1.B")).toBe("3,1.5");
  });
});
