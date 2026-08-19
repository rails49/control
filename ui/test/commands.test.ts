/**
 * What the editor offers and what is dead, with no DOM.
 *
 * The enablement rules are neither the document nor the DOM, so they are a
 * module in `model/` with a test (EDITOR.md#tests). Every one of them is a
 * thing that would otherwise be read off a component: Save dead with nothing
 * open, Rotate dead on an empty selection, Undo dead at the end of the stack.
 */

import { describe, expect, it } from "vitest";

import {
  COMMANDS,
  MENUS,
  NOTHING,
  type CommandId,
  type Standing,
} from "../src/model/commands.js";

function standing(parts: Partial<Standing> = {}): Standing {
  return { ...NOTHING, ...parts };
}

/** Whether a command applies where the editor stands. */
function on(id: CommandId, parts: Partial<Standing> = {}): boolean {
  return COMMANDS[id].enabled(standing(parts));
}

describe("the menus", () => {
  it("carries the items in the order the bar draws them", () => {
    expect(MENUS.map((menu) => [menu.name, menu.items])).toEqual([
      ["File", ["new", "open", "save", "save-as", null, "export-svg"]],
      [
        "Edit",
        ["undo", "redo", null, "rotate", "flip", "delete", null, "properties"],
      ],
      ["View", ["zoom-in", "zoom-out", "fit"]],
    ]);
  });

  it("puts every command in exactly one menu", () => {
    const placed = MENUS.flatMap((menu) => menu.items).filter(
      (item) => item !== null,
    );
    expect([...placed].sort()).toEqual(Object.keys(COMMANDS).sort());
  });
});

describe("the key beside the label", () => {
  it("names the key of every command that has one", () => {
    const keys = Object.fromEntries(
      Object.entries(COMMANDS).map(([id, command]) => [id, command.key]),
    );
    expect(keys).toEqual({
      new: undefined,
      open: undefined,
      save: "⌘S",
      "save-as": "⇧⌘S",
      "export-svg": undefined,
      undo: "⌘Z",
      redo: "⇧⌘Z",
      rotate: "R",
      flip: "F",
      delete: "⌫",
      properties: undefined,
      "zoom-in": "+",
      "zoom-out": "−",
      fit: "0",
    });
  });
});

describe("what a drawing has to be open for", () => {
  it("saves only a drawing that is open and has edits in it", () => {
    expect(on("save")).toBe(false);
    expect(on("save", { opened: "gotthard", saved: true })).toBe(false);
    expect(on("save", { opened: "gotthard", saved: false })).toBe(true);
  });

  it("forks only what is open, saved or not", () => {
    expect(on("save-as")).toBe(false);
    expect(on("save-as", { opened: "gotthard" })).toBe(true);
    expect(on("save-as", { opened: "gotthard", saved: false })).toBe(true);
  });

  /** The export writes the drawing that is open, saved or not: it is a
   *  picture of what is on the sheet, so unsaved edits belong in it. */
  it("exports only a drawing that is open", () => {
    expect(on("export-svg")).toBe(false);
    expect(on("export-svg", { opened: "gotthard" })).toBe(true);
    expect(on("export-svg", { opened: "gotthard", saved: false })).toBe(true);
  });

  it("always offers a new drawing", () => {
    expect(on("new")).toBe(true);
  });

  /** A submenu of no drawings is an empty box that looks broken — the lesson
   *  the right-click menu already learnt (tc-menu). */
  it("opens a drawing only where there is one to open", () => {
    expect(on("open")).toBe(false);
    expect(on("open", { drawings: 5 })).toBe(true);
  });
});

describe("what the selection has to hold", () => {
  it("transforms only a selection with something in it", () => {
    for (const id of ["rotate", "flip", "delete"] as const) {
      expect(on(id)).toBe(false);
      expect(on(id, { selection: 1 })).toBe(true);
      expect(on(id, { selection: 4 })).toBe(true);
    }
  });

  /** A group selection is a move about to happen, not a question about one
   *  symbol, and a kind with nothing to set opens no dialog at all. */
  it("offers properties to one symbol that has any", () => {
    expect(on("properties", { selection: 1, editable: true })).toBe(true);
    expect(on("properties", { selection: 1, editable: false })).toBe(false);
    expect(on("properties", { selection: 4, editable: true })).toBe(false);
    expect(on("properties")).toBe(false);
  });
});

describe("the ends of the snapshot stack", () => {
  it("undoes and redoes only where there is a snapshot to take", () => {
    expect(on("undo")).toBe(false);
    expect(on("redo")).toBe(false);
    expect(on("undo", { undo: true })).toBe(true);
    expect(on("redo", { redo: true })).toBe(true);
  });
});

/** The view is the canvas's own, so it is there to be changed whatever the
 *  drawing is: an empty sheet still zooms. */
describe("the view", () => {
  it("is always there to change", () => {
    for (const id of ["zoom-in", "zoom-out", "fit"] as const) {
      expect(on(id)).toBe(true);
    }
  });
});
