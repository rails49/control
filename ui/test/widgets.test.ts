/**
 * Widgets in the editor (ADR-0087, #928): placed off the palette, moved,
 * deleted and undone the way a symbol is, never turned, and renamed in their
 * properties with the topic following the name.
 *
 * No DOM. The editor is driven through the same `Gesture` the canvas drives,
 * grid squares in; the dialog is `widget-properties.test.ts`.
 */

import { describe, expect, it } from "vitest";

import type { Drawing, WidgetKind } from "../src/model/drawing.js";
import { Editor } from "../src/model/editor.js";
import { editingMachine, Gesture } from "../src/model/gesture.js";
import { fitBox } from "../src/model/scene.js";
import { UNREVIEWED } from "../src/model/store.js";
import { pressableAt, under, within } from "../src/model/under.js";
import {
  mintWidget,
  editorText,
  selectionKey,
  toggleTrouble,
  togglePosition,
  widgetBounds,
  widgetOf,
  widgetTopic,
  widgetTrouble,
} from "../src/model/widgets.js";
import { editorMenu } from "../src/ui/tc-editor.js";

/** One turnout at (0, 0), and nothing else. */
function sheet(): Editor {
  const drawing: Drawing = {
    drawing: "widgets",
    symbols: { sw1: { kind: "turnout", at: [0, 0] } },
    wires: [],
  };
  return new Editor(drawing);
}

/** A widget of each kind dropped off the palette, the pointer at the middle
 *  of a square: a text widget and a button land on that square, and a
 *  toggle's two squares centre on the pointer as near as the grid allows. */
function placed(): Editor {
  const editor = sheet();
  (["text", "button", "toggle"] as const).forEach((kind, row) => {
    editor.beginPlace(kind);
    editor.dropPending(6.5, 2 * row + 4.5);
  });
  return editor;
}

const INPUT = { button: 0, shift: false, touch: false, screen: { x: 0, y: 0 } };

/** A press, a move and a release, as the canvas would feed them. */
function dragged(
  editor: Editor,
  from: { x: number; y: number },
  to: { x: number; y: number },
  frozen = false,
): void {
  const machine = editingMachine(
    new Gesture(),
    () => editor,
    () => UNREVIEWED,
    () => frozen,
  );
  machine.down(from, INPUT);
  machine.moved(to, { x: 100, y: 100 });
  machine.up(to, { x: 100, y: 100 });
}

describe("placing a widget", () => {
  it("drops each kind, named for its kind, with no size, under the pointer", () => {
    const editor = placed();
    expect(editor.widgets).toEqual({
      text1: { kind: "text", at: [6, 4] },
      button1: { kind: "button", at: [6, 6], payload: "button1" },
      toggle1: { kind: "toggle", at: [6, 8], on: "on", off: "off" },
    });
    expect(editor.drawing.symbols).toEqual({ sw1: { kind: "turnout", at: [0, 0] } });
  });

  it("selects what it placed", () => {
    const editor = sheet();
    editor.beginPlace("button");
    editor.dropPending(6.5, 4.5);
    expect([...editor.selection]).toEqual([selectionKey("button1")]);
  });

  it("names the next one of a kind with the lowest free number", () => {
    const editor = placed();
    editor.placeWidget("text", [0, 10]);
    expect(Object.keys(editor.widgets)).toContain("text2");
    expect(mintWidget(editor.drawing, "toggle")).toBe("toggle2");
  });

  /** Nothing checks whether a widget overlaps anything (store/DRAWING.md). */
  it("lands over a symbol", () => {
    const editor = sheet();
    editor.beginPlace("text");
    expect(editor.placementAt(0.5, 0.5)!.blocked).toEqual([]);
    expect(editor.dropPending(0.5, 0.5)).toBe("text1");
  });

  it("is one undo step each, and redone", () => {
    const editor = placed();
    editor.undo();
    expect(Object.keys(editor.widgets)).toEqual(["text1", "button1"]);
    editor.undo();
    editor.undo();
    expect(editor.drawing.widgets ?? {}).toEqual({});
    editor.redo();
    expect(Object.keys(editor.widgets)).toEqual(["text1"]);
  });

  /** `r` and `f` turn a symbol on its way; a widget on its way stays as it
   *  is, and so does the turn the next symbol takes. */
  it("does not turn or flip on its way", () => {
    const editor = sheet();
    editor.beginPlace("turnout");
    editor.turnPending();
    editor.cancelPending();
    editor.beginPlace("toggle");
    editor.turnPending();
    editor.flipPending();
    expect(editor.pending).toEqual({ kind: "toggle" });
    editor.dropPending(6.5, 4.5);
    expect(editor.widgets.toggle1).not.toHaveProperty("rot");
    editor.beginPlace("turnout");
    expect(editor.pending).toEqual({ kind: "turnout", rot: 90 });
  });
});

describe("moving a widget", () => {
  it("takes the widget under a press and drags it by whole squares", () => {
    const editor = placed();
    dragged(editor, { x: 6.2, y: 4.5 }, { x: 9.4, y: 5.6 });
    expect(editor.widgets.text1!.at).toEqual([9, 5]);
    expect(editor.widgets.button1!.at).toEqual([6, 6]);
  });

  it("moves with symbols in one selection, and undoes in one step", () => {
    const editor = placed();
    editor.select(["sw1", selectionKey("toggle1")]);
    editor.move(2, 1);
    expect(editor.widgets.toggle1!.at).toEqual([8, 9]);
    expect(editor.drawing.symbols.sw1!.at).toEqual([2, 1]);
    editor.undo();
    expect(editor.widgets.toggle1!.at).toEqual([6, 8]);
    expect(editor.drawing.symbols.sw1!.at).toEqual([0, 0]);
  });

  it("is taken by a rubber band round its middle", () => {
    const editor = placed();
    expect(within(editor.drawing, { x: 4, y: 3 }, { x: 9, y: 7 })).toEqual([
      selectionKey("text1"),
      selectionKey("button1"),
    ]);
  });

  it("is what a press over a symbol lands on, being drawn over it", () => {
    const editor = sheet();
    editor.placeWidget("text", [0, 0]);
    const found = under(editor.drawing, UNREVIEWED, { x: 0.3, y: 0.8 });
    expect(found).toMatchObject({ widget: "text1", symbol: null, wire: null });
  });
});

describe("deleting a widget", () => {
  it("takes the selected widgets and leaves the rest", () => {
    const editor = placed();
    editor.select([selectionKey("button1")]);
    editor.remove();
    expect(Object.keys(editor.widgets)).toEqual(["text1", "toggle1"]);
    expect(editor.selection.size).toBe(0);
    editor.undo();
    expect(Object.keys(editor.widgets)).toEqual(["text1", "button1", "toggle1"]);
  });

  /** A drawing with none writes none, as before the first was placed. */
  it("leaves no widgets key behind the last one", () => {
    const editor = sheet();
    editor.placeWidget("text", [3, 3]);
    editor.remove();
    expect(editor.drawing).not.toHaveProperty("widgets");
  });
});

describe("turning", () => {
  it("leaves a widget as it is under rotate and flip", () => {
    const editor = placed();
    editor.select([selectionKey("text1"), "sw1"]);
    editor.rotate();
    editor.flip();
    expect(editor.widgets.text1).toEqual({ kind: "text", at: [6, 4] });
    expect(editor.drawing.symbols.sw1).toMatchObject({ rot: 90, flip: true });
  });

  it("is not a change at all with only widgets selected", () => {
    const editor = placed();
    editor.select([selectionKey("text1")]);
    const was = editor.revision;
    editor.rotate();
    editor.flip();
    expect(editor.revision).toBe(was);
  });

  it("is not offered in a widget's menu", () => {
    const at = {
      x: 0,
      y: 0,
      pin: null,
      symbol: null,
      kind: null,
      widget: "text1",
      junction: null,
      joint: null,
      wire: null,
    };
    expect(editorMenu(at).map((item) => item.label)).toEqual(["Properties…", "Delete"]);
  });
});

describe("renaming a widget", () => {
  it("rewrites the key in place, keeps it selected, and undoes", () => {
    const editor = placed();
    editor.select([selectionKey("button1")]);
    const spec = { ...editor.widgets.button1!, payload: "horn" };
    expect(editor.editWidget("button1", "horn", spec)).toBe(true);
    expect(Object.keys(editor.widgets)).toEqual(["text1", "horn", "toggle1"]);
    expect(editor.widgets.horn!.payload).toBe("horn");
    expect([...editor.selection]).toEqual([selectionKey("horn")]);
    editor.undo();
    expect(Object.keys(editor.widgets)).toEqual(["text1", "button1", "toggle1"]);
  });

  it("refuses a name another widget has, and keeps the old one", () => {
    const editor = placed();
    expect(editor.editWidget("button1", "text1", editor.widgets.button1!)).toBe(false);
    expect(Object.keys(editor.widgets)).toEqual(["text1", "button1", "toggle1"]);
    expect(editor.canUndo).toBe(true);
    expect(editor.widgets.text1!.kind).toBe("text");
  });

  it("refuses a name that is not one topic level", () => {
    const editor = placed();
    for (const name of ["a/b", "a.b", "a b", "+", ""]) {
      expect(editor.editWidget("text1", name, editor.widgets.text1!), name).toBe(false);
    }
  });

  /** A widget's namespace is its own: a symbol's name is no clash. */
  it("may take a name a symbol wears", () => {
    const editor = placed();
    expect(editor.editWidget("text1", "sw1", editor.widgets.text1!)).toBe(true);
  });

  it("says why a name will not do", () => {
    const taken = ["text1", "button1"];
    expect(widgetTrouble("button1", "text1", taken)).toBe("'button1' is already taken");
    expect(widgetTrouble("text1", "text1", taken)).toBeNull();
    expect(widgetTrouble("lights", "text1", taken)).toBeNull();
    expect(widgetTrouble("", "text1", taken)).toBe("a widget needs a name");
    expect(widgetTrouble("a.b", "text1", taken)).toContain("cannot name a widget");
  });
});

describe("a widget's topic", () => {
  it("is the kind's row with the name as its last level", () => {
    const topics: [WidgetKind, string][] = [
      ["text", "tc49/ui/state/text/current"],
      ["toggle", "tc49/ui/state/toggle/current"],
      ["button", "tc49/ui/button/current"],
    ];
    for (const [kind, topic] of topics) expect(widgetTopic(kind, "current")).toBe(topic);
  });
});

describe("what the store would refuse", () => {
  it("refuses a toggle whose on and off are the same", () => {
    expect(toggleTrouble({ kind: "toggle", at: [0, 0], on: "x", off: "x" }))
      .not.toBeNull();
    expect(toggleTrouble({ kind: "toggle", at: [0, 0], on: "on", off: "off" }))
      .toBeNull();
  });
});

describe("a frozen drawing", () => {
  it("does not move a widget", () => {
    const editor = placed();
    editor.clearSelection();
    dragged(editor, { x: 6.2, y: 4.5 }, { x: 9.4, y: 5.6 }, true);
    expect(editor.widgets.text1!.at).toEqual([6, 4]);
    expect(editor.selection.size).toBe(0);
  });
});

describe("the frame a fit looks at", () => {
  it("takes in a widget", () => {
    const editor = sheet();
    editor.placeWidget("toggle", [20, 10]);
    const box = fitBox(editor.drawing);
    expect(box.x + box.w).toBeGreaterThanOrEqual(22);
    expect(box.y + box.h).toBeGreaterThanOrEqual(11);
  });

  it("takes in a text widget's words where they run past its square", () => {
    const editor = sheet();
    editor.placeWidget("text", [20, 10]);
    editor.editWidget("text1", "text1", {
      kind: "text",
      at: [20, 10],
      align: "left",
      default: "a reading far longer than one square",
    });
    expect(fitBox(editor.drawing).x + fitBox(editor.drawing).w).toBeGreaterThan(25);
  });
});

it("tells a widget's selection entry from a symbol's", () => {
  expect(widgetOf(selectionKey("lights"))).toBe("lights");
  expect(widgetOf("sw1")).toBeNull();
});

describe("where a widget is (#939)", () => {
  it("is one square for a button and two for a toggle", () => {
    expect(widgetBounds("b", { kind: "button", at: [3, 2], payload: "b" })).toEqual({
      x: 3,
      y: 2,
      w: 1,
      h: 1,
    });
    expect(
      widgetBounds("t", { kind: "toggle", at: [3, 2], on: "on", off: "off" }),
    ).toEqual({ x: 3, y: 2, w: 2, h: 1 });
  });

  it("runs a text widget's words from its square the way align says", () => {
    const spec = { kind: "text" as const, at: [3, 2] as [number, number], default: "0.4 A" };
    const left = widgetBounds("t", { ...spec, align: "left" });
    const right = widgetBounds("t", { ...spec, align: "right" });
    const centre = widgetBounds("t", spec);
    expect(left.x).toBe(3);
    expect(right.x + right.w).toBeCloseTo(4);
    expect(centre.x + centre.w / 2).toBeCloseTo(3.5);
    expect([left.y, left.h]).toEqual([2, 1]);
  });

  it("measures a text widget by what the editor shows of it", () => {
    const short = widgetBounds("t", { kind: "text", at: [0, 0], default: "A" });
    const long = widgetBounds("t", { kind: "text", at: [0, 0], default: "AAAAAAAA" });
    expect(long.w).toBeCloseTo(8 * short.w);
    const large = widgetBounds("t", { kind: "text", at: [0, 0], default: "A", text: "large" });
    expect(large.w).toBeGreaterThan(short.w);
  });
});

describe("what the editor shows of a text widget", () => {
  it("is its default, or its name and a question mark", () => {
    expect(editorText("current", { kind: "text", at: [0, 0], default: "0.4 A" })).toBe("0.4 A");
    expect(editorText("current", { kind: "text", at: [0, 0] })).toBe("current?");
  });
});

describe("a toggle's position", () => {
  const lights = { kind: "toggle" as const, at: [0, 0] as [number, number], on: "1", off: "0" };

  it("is its default until a row arrives, and then the row's", () => {
    expect(togglePosition(lights, undefined)).toBeNull();
    expect(togglePosition({ ...lights, default: "on" }, undefined)).toBe("on");
    expect(togglePosition({ ...lights, default: "on" }, "0")).toBe("off");
    expect(togglePosition({ ...lights, default: "on" }, "dim")).toBeNull();
  });
});

describe("a press on a run", () => {
  /** A text widget's words may run over the track, and a press on one does
   *  nothing, so it lets the press through to what is under it. */
  it("passes a text widget by and lands on a button", () => {
    const drawing: Drawing = {
      drawing: "run",
      symbols: {},
      wires: [],
      widgets: {
        horn: { kind: "button", at: [2, 0], payload: "horn" },
        current: { kind: "text", at: [2, 0], align: "left", default: "a long reading" },
      },
    };
    expect(pressableAt(drawing, { x: 2.5, y: 0.5 })).toBe("horn");
    expect(pressableAt(drawing, { x: 4.5, y: 0.5 })).toBeNull();
    expect(under(drawing, UNREVIEWED, { x: 4.5, y: 0.5 }).widget).toBe("current");
  });
});
