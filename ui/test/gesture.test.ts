/**
 * What a pointer gesture means, driven as the canvas drives it: one call per
 * event, grid squares in, an outcome back. No DOM anywhere; the screen pixels
 * the slop rule needs are just numbers the tests choose.
 */

import { describe, expect, it } from "vitest";

import type { Drawing } from "../src/model/drawing.js";
import { Editor } from "../src/model/editor.js";
import { Gesture } from "../src/model/gesture.js";
import type { Review } from "../src/model/store.js";

/** A review that says nothing, which is what a drawing has before the store
 *  has answered for it. */
const NOTHING: Review = {
  red_pins: [],
  junctions: [],
  joints: [],
  layout: null,
  explain: null,
  refused: null,
};

/** Two turnouts three squares apart, each one square: sw1 on (0, 0) and sw2 on
 *  (3, 0). Their centres are half a square from every pin, outside the hit
 *  radius, so a press there takes the symbol. */
function turnouts(): Editor {
  const drawing: Drawing = {
    drawing: "gesture",
    symbols: {
      sw1: { kind: "turnout", at: [0, 0] },
      sw2: { kind: "turnout", at: [3, 0] },
    },
    wires: [],
  };
  return new Editor(drawing);
}

/** Two blocks far apart. A block is six squares, so b1's pins sit at (0, 0.5)
 *  and (6, 0.5), and b2's at (8, 0.5) and (14, 0.5). */
function blocks(): Editor {
  const drawing: Drawing = {
    drawing: "gesture",
    symbols: {
      b1: { kind: "block", at: [0, 0], length: 1000 },
      b2: { kind: "block", at: [8, 0], length: 1000 },
    },
    wires: [],
  };
  return new Editor(drawing);
}

/** One bend on the west face of the square at (4, 2), which is the point
 *  (4, 2.5). */
function bend(): Editor {
  const drawing: Drawing = {
    drawing: "gesture",
    symbols: { n1: { kind: "pin", at: [4, 2], rot: 0 } },
    wires: [],
  };
  return new Editor(drawing);
}

function down(
  gesture: Gesture,
  editor: Editor,
  x: number,
  y: number,
  input: { shift?: boolean; button?: number; screen?: { x: number; y: number } } = {},
) {
  return gesture.down(
    editor,
    NOTHING,
    { x, y },
    {
      button: input.button ?? 0,
      shift: input.shift ?? false,
      screen: input.screen ?? { x: 0, y: 0 },
    },
  );
}

/**
 * A press on a pin has not said yet which of two things it means: a click
 * starts a wire, a drag past the slop takes hold of the bend
 * (EDITOR.md#editing).
 */
describe("the slop between a wire-click and a bend-drag", () => {
  it("holds the press without saying anything", () => {
    const editor = blocks();
    const gesture = new Gesture();
    expect(down(gesture, editor, 0, 0.5)).toBe("quiet");
    expect(editor.pendingFrom).toBeNull();
    expect([...editor.selection]).toEqual([]);
  });

  it("reads a release within the slop as a click, and starts a wire", () => {
    const editor = blocks();
    const gesture = new Gesture();
    down(gesture, editor, 0, 0.5);
    expect(gesture.moved(editor, { x: 0, y: 0.5 }, { x: 3, y: 0 })).toBe(
      "quiet",
    );
    expect(gesture.up(editor, { x: 0, y: 0.5 })).toBe("render");
    expect(editor.pendingFrom).toBe("b1.A");
  });

  it("reads a move past the slop as a drag, and picks up the symbol", () => {
    const editor = bend();
    const gesture = new Gesture();
    down(gesture, editor, 4, 2.5);
    expect(gesture.moved(editor, { x: 4.2, y: 2.5 }, { x: 20, y: 0 })).toBe(
      "picked",
    );
    expect([...editor.selection]).toEqual(["n1"]);
    expect(editor.pendingFrom).toBeNull();
  });

  it("skips the press for a shift-click, which is the selection gesture", () => {
    const editor = blocks();
    const gesture = new Gesture();
    expect(down(gesture, editor, 0, 0.5, { shift: true })).toBe("picked");
    expect([...editor.selection]).toEqual(["b1"]);
    expect(editor.pendingFrom).toBeNull();
  });
});

/** With a wire in progress, a click on empty canvas bends it through a
 *  free-standing pin and a click on a pin ends it (EDITOR.md#editing). */
describe("a wire in progress", () => {
  it("bends through empty canvas and ends on a pin", () => {
    const editor = blocks();
    const gesture = new Gesture();
    down(gesture, editor, 0, 0.5);
    gesture.up(editor, { x: 0, y: 0.5 });
    expect(down(gesture, editor, 4, 3)).toBe("changed");
    expect(editor.pendingFrom).not.toBe("b1.A");
    expect(down(gesture, editor, 8, 0.5)).toBe("changed");
    expect(editor.pendingFrom).toBeNull();
    expect(editor.drawing.wires).toHaveLength(2);
  });
});

/** The drag holds its last legal offset while the pointer is over an obstacle,
 *  and catches up once the offset is clear again (EDITOR.md#canvas). */
describe("a drag over an obstacle", () => {
  it("holds the last legal offset and catches up past it", () => {
    const editor = turnouts();
    const gesture = new Gesture();
    expect(down(gesture, editor, 0.5, 0.5)).toBe("picked");
    expect([...editor.selection]).toEqual(["sw1"]);

    expect(gesture.moved(editor, { x: 2.5, y: 0.5 }, { x: 0, y: 0 })).toBe(
      "render",
    );
    expect(gesture.shift(editor, "sw1")).toEqual({ x: 2, y: 0 });

    // Offset 3 would put sw1 on sw2's square: the drag keeps offset 2.
    expect(gesture.moved(editor, { x: 3.5, y: 0.5 }, { x: 0, y: 0 })).toBe(
      "quiet",
    );
    expect(gesture.shift(editor, "sw1")).toEqual({ x: 2, y: 0 });

    expect(gesture.moved(editor, { x: 4.5, y: 0.5 }, { x: 0, y: 0 })).toBe(
      "render",
    );
    expect(gesture.shift(editor, "sw1")).toEqual({ x: 4, y: 0 });

    expect(gesture.up(editor, { x: 4.5, y: 0.5 })).toBe("changed");
    expect(editor.drawing.symbols.sw1!.at).toEqual([4, 0]);
  });

  it("says nothing when a drag ends where it began", () => {
    const editor = turnouts();
    const gesture = new Gesture();
    down(gesture, editor, 0.5, 0.5);
    expect(gesture.up(editor, { x: 0.5, y: 0.5 })).toBe("quiet");
    expect(editor.drawing.symbols.sw1!.at).toEqual([0, 0]);
  });
});

/** A lone bend follows the faces, which are half a square apart, rather than
 *  translating by whole cells (EDITOR.md#canvas). */
describe("dragging a lone bend", () => {
  it("draws it on the nearest face and writes that face on release", () => {
    const editor = bend();
    const gesture = new Gesture();
    down(gesture, editor, 4, 2.5);
    gesture.moved(editor, { x: 4.2, y: 2.5 }, { x: 20, y: 0 });

    // The north face of the same square is half a square over and half up.
    expect(gesture.moved(editor, { x: 4.5, y: 2 }, { x: 30, y: 0 })).toBe(
      "render",
    );
    expect(gesture.shift(editor, "n1")).toEqual({ x: 0.5, y: -0.5 });

    expect(gesture.up(editor, { x: 4.5, y: 2 })).toBe("changed");
    expect(editor.drawing.symbols.n1).toMatchObject({ at: [4, 2], rot: 90 });
  });
});

/** Shift-click is the selection gesture throughout: it adds an unselected
 *  symbol and subtracts a selected one (EDITOR.md#editing). */
describe("shift-click on the selection", () => {
  it("adds, then subtracts", () => {
    const editor = turnouts();
    const gesture = new Gesture();
    down(gesture, editor, 0.5, 0.5);
    gesture.up(editor, { x: 0.5, y: 0.5 });

    down(gesture, editor, 3.5, 0.5, { shift: true });
    gesture.up(editor, { x: 3.5, y: 0.5 });
    expect([...editor.selection].sort()).toEqual(["sw1", "sw2"]);

    expect(down(gesture, editor, 0.5, 0.5, { shift: true })).toBe("picked");
    gesture.up(editor, { x: 0.5, y: 0.5 });
    expect([...editor.selection]).toEqual(["sw2"]);
  });
});

/** A drag over empty canvas is the rubber band, taking the symbols whose
 *  centres it covers on release. */
describe("the rubber band", () => {
  it("clears the selection, follows the pointer, and selects on release", () => {
    const editor = turnouts();
    const gesture = new Gesture();
    editor.select(["sw1"]);

    expect(down(gesture, editor, 6, 3)).toBe("picked");
    expect([...editor.selection]).toEqual([]);

    expect(gesture.moved(editor, { x: -1, y: -1 }, { x: 0, y: 0 })).toBe(
      "render",
    );
    expect(gesture.band).toEqual({ from: { x: 6, y: 3 }, to: { x: -1, y: -1 } });

    expect(gesture.up(editor, { x: -1, y: -1 })).toBe("picked");
    expect(gesture.band).toBeNull();
    expect([...editor.selection].sort()).toEqual(["sw1", "sw2"]);
  });
});

/** The middle button pans. The machine cannot reach the viewBox, so the pan
 *  comes back as the grid delta the view should move by, and the anchor stays:
 *  the view moves under the pointer. */
describe("panning", () => {
  it("answers a middle-button drag with the view's delta", () => {
    const editor = turnouts();
    const gesture = new Gesture();
    expect(down(gesture, editor, 2, 1, { button: 1 })).toBe("quiet");
    expect(gesture.moved(editor, { x: 3, y: 1.5 }, { x: 0, y: 0 })).toEqual({
      pan: { x: -1, y: -0.5 },
    });
    expect(gesture.up(editor, { x: 3, y: 1.5 })).toBe("quiet");
  });
});

/** The right button is one of the ways out of a palette drag, and otherwise
 *  asks about what was clicked (EDITOR.md#palette). */
describe("the right-click", () => {
  it("cancels a palette drag instead of opening a menu", () => {
    const editor = turnouts();
    const gesture = new Gesture();
    editor.beginPlace("turnout");
    const { outcome, found } = gesture.menu(editor, NOTHING, { x: 1, y: 1 });
    expect(outcome).toBe("render");
    expect(found).toBeNull();
    expect(editor.pending).toBeNull();
  });

  it("selects the unselected symbol it lands on, so the menu applies to it", () => {
    const editor = turnouts();
    const gesture = new Gesture();
    const { outcome, found } = gesture.menu(editor, NOTHING, {
      x: 0.5,
      y: 0.5,
    });
    expect(outcome).toBe("picked");
    expect(found?.symbol).toBe("sw1");
    expect([...editor.selection]).toEqual(["sw1"]);
  });

  it("leaves a selected symbol's selection alone", () => {
    const editor = turnouts();
    const gesture = new Gesture();
    editor.select(["sw1", "sw2"]);
    const { outcome, found } = gesture.menu(editor, NOTHING, {
      x: 0.5,
      y: 0.5,
    });
    expect(outcome).toBe("quiet");
    expect(found?.symbol).toBe("sw1");
    expect([...editor.selection].sort()).toEqual(["sw1", "sw2"]);
  });
});
