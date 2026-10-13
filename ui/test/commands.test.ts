/**
 * What a view offers and what is dead, with no DOM.
 *
 * The enablement rules are neither the document nor the DOM, so they are a
 * module in `model/` with a test (EDITOR.md#tests). Every one of them is a
 * thing that would otherwise be read off a component: Save dead with nothing
 * open, Rotate dead on an empty selection, Undo dead at the end of the stack.
 */

import { describe, expect, it } from "vitest";

import {
  backupWords,
  COMMANDS,
  frozen,
  isLoaded,
  NOTHING,
  RAIL,
  supply,
  type CommandId,
  type Standing,
  unbuilt,
} from "../src/model/commands.js";
import { VIEWS } from "../src/model/views.js";

function standing(parts: Partial<Standing> = {}): Standing {
  return { ...NOTHING, ...parts };
}

/** Whether a command applies where the editor stands. */
function on(id: CommandId, parts: Partial<Standing> = {}): boolean {
  return COMMANDS[id].enabled(standing(parts));
}

/** The four verbs the rail deliberately leaves out. They apply to a selection
 *  and read in the editor's right-click menu with their keys beside them
 *  (ADR-0064); `menu.test.ts` is where that menu is checked. */
const SELECTION: CommandId[] = ["rotate", "flip", "delete", "properties"];

describe("the rail", () => {
  it("carries the editor's groups in the order the rail draws them", () => {
    expect(RAIL.edit.map((group) => [group.name, group.items])).toEqual([
      ["View", ["zoom-out", "zoom-in", "fit", "netlist"]],
      ["File", ["save", "export-svg"]],
      ["Edit", ["undo", "redo"]],
    ]);
  });

  /** The run view's document is a railroad somebody else is running, so it
   *  has no File and no Edit; what it presses instead is HOLD and GO, which
   *  is a gesture on the bus rather than a verb of this app's. */
  it("gives the run view a View group and nothing else", () => {
    expect(RAIL.run.map((group) => [group.name, group.items])).toEqual([
      ["View", ["zoom-out", "zoom-in", "fit"]],
    ]);
  });

  /** Zoom and fit are pressed constantly in both views, and both draw on the
   *  one canvas (#168), so a person who has learnt where Fit is does not learn
   *  it again on the other view. */
  it("opens every view that has a group with the same three", () => {
    for (const groups of Object.values(RAIL)) {
      if (groups.length === 0) continue;
      expect(groups[0]!.items.slice(0, 3)).toEqual(["zoom-out", "zoom-in", "fit"]);
    }
  });

  it("puts every command but the selection verbs on the editor's rail", () => {
    const placed = RAIL.edit.flatMap((group) => group.items);
    const wanted = Object.keys(COMMANDS).filter(
      (id) => !SELECTION.includes(id as CommandId),
    );
    expect([...placed].sort()).toEqual(wanted.sort());
  });

  /** Four buttons that are dead whenever nothing is selected say less than a
   *  menu that opens on the thing they act on (ADR-0064). */
  it("leaves the selection verbs to the right-click menu", () => {
    const placed = Object.values(RAIL).flatMap((groups) =>
      groups.flatMap((group) => group.items),
    );
    for (const id of SELECTION) expect(placed).not.toContain(id);
  });

  /** Every button a view draws has to be a command, or the rail would look one
   *  up and find nothing. */
  it("names only commands in every view's groups", () => {
    for (const groups of Object.values(RAIL)) {
      for (const group of groups) {
        for (const id of group.items) expect(COMMANDS[id]).toBeDefined();
      }
    }
  });
});

describe("the key beside the label", () => {
  it("names the key of every command that has one", () => {
    const keys = Object.fromEntries(
      Object.entries(COMMANDS).map(([id, command]) => [id, command.key]),
    );
    expect(keys).toEqual({
      save: "Mod+S",
      "export-svg": undefined,
      undo: "Mod+Z",
      redo: "Shift+Mod+Z",
      rotate: "R",
      flip: "F",
      delete: "⌫",
      properties: undefined,
      "zoom-in": "+",
      "zoom-out": "−",
      fit: "0",
      netlist: "N",
    });
  });
});

/** The glyph on each button: Bootstrap Icons as Shoelace ships them, and
 *  look's own `throttle` and `rotate` where Bootstrap has none (look#12). */
describe("the glyph on the button", () => {
  it("names one for every command", () => {
    const icons = Object.fromEntries(
      Object.entries(COMMANDS).map(([id, command]) => [id, command.icon]),
    );
    expect(icons).toEqual({
      save: "floppy",
      "export-svg": "box-arrow-up",
      undo: "arrow-counterclockwise",
      redo: "arrow-clockwise",
      rotate: "rotate",
      flip: "symmetry-vertical",
      delete: "trash",
      properties: "sliders",
      "zoom-in": "zoom-in",
      "zoom-out": "zoom-out",
      fit: "fullscreen",
      netlist: "layout-sidebar-reverse",
    });
  });

  it("names one for every view", () => {
    expect(VIEWS.map((view) => [view.id, view.icon])).toEqual([
      ["run", "stoplights"],
      ["throttle", "throttle"],
      ["stock", "train-freight-front"],
      ["edit", "pencil"],
    ]);
  });
});

describe("what a drawing has to be open for", () => {
  it("saves only a drawing that is open and has edits in it", () => {
    expect(on("save")).toBe(false);
    expect(on("save", { opened: "reversing-loops", saved: true })).toBe(false);
    expect(on("save", { opened: "reversing-loops", saved: false })).toBe(true);
  });

  /** The export writes the drawing that is open, saved or not: it is a
   *  picture of what is on the sheet, so unsaved edits belong in it. */
  it("exports only a drawing that is open", () => {
    expect(on("export-svg")).toBe(false);
    expect(on("export-svg", { opened: "reversing-loops" })).toBe(true);
    expect(on("export-svg", { opened: "reversing-loops", saved: false })).toBe(true);
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

/**
 * Track power on or stopped freezes the drawing
 * ([ADR-0071](../../docs/adr/0071-a-rebuild-under-the-same-name-keeps-the-placements.md),
 * decision 5). With power on the run moves trains over what the dispatcher
 * built, so every command that changes the document is dead and the rest are
 * not. With power off a train standing on the layout freezes nothing: a save
 * of the loaded railroad names it again and the rebuild keeps the train.
 *
 * The rule is here rather than on a component for the reason the others are:
 * it is neither the document nor the DOM, and the bar and the keyboard both
 * ask it, so a menu item and the key printed beside it cannot come to mean
 * different things (EDITOR.md#tests).
 */
describe("what track power freezes", () => {
  /** Everything that would change the drawing, alive where it would be alive
   *  with power off. */
  const CHANGES: Partial<Record<CommandId, Partial<Standing>>> = {
    undo: { undo: true },
    redo: { redo: true },
    rotate: { selection: 1 },
    flip: { selection: 1 },
    delete: { selection: 1 },
    properties: { selection: 1, editable: true },
  };

  it("kills every command that changes the drawing while power is on or stopped", () => {
    for (const [id, alive] of Object.entries(CHANGES)) {
      for (const power of ["on", "stopped"] as const) {
        expect(on(id as CommandId, { ...alive, power }), `${id} ${power}`).toBe(false);
      }
    }
  });

  /** No session is no run to drift from, and power off is a rebuild away. */
  it("leaves them alive with power off, or with no session", () => {
    for (const [id, alive] of Object.entries(CHANGES)) {
      expect(on(id as CommandId, { ...alive, power: "off" }), `${id} off`).toBe(true);
      expect(on(id as CommandId, { ...alive, power: null }), `${id} none`).toBe(true);
    }
  });

  /** Look, zoom, inspect the netlist: a frozen drawing is read-only and not
   *  gone. */
  it("leaves looking at the drawing alone", () => {
    const open = { opened: "reversing-loops", power: "on" as const };
    for (const id of ["zoom-in", "zoom-out", "fit"] as const) {
      expect(on(id, open), id).toBe(true);
    }
    expect(on("netlist", open)).toBe(true);
    expect(on("export-svg", open)).toBe(true);
  });

  /** One reading of the freeze, for whoever says why: the band prints its
   *  word off this rather than reading power itself. */
  it("is one question, asked of where the app stands", () => {
    expect(frozen(standing())).toBe(false);
    expect(frozen(standing({ power: "off" }))).toBe(false);
    expect(frozen(standing({ power: "on" }))).toBe(true);
    expect(frozen(standing({ power: "stopped" }))).toBe(true);
  });

  /** The rule is read off power afresh rather than latched, so switching it
   *  off thaws the drawing on its own. */
  it("thaws when power goes off", () => {
    expect(on("rotate", { selection: 1, power: "on" })).toBe(false);
    expect(on("rotate", { selection: 1, power: "off" })).toBe(true);
  });
});

/**
 * Saving the loaded railroad names it again, so every app builds what was
 * written, and the layout builds only with power off (ADR-0071). Save waits
 * for power off on the loaded railroad and on nothing else; ON waits for the
 * save.
 */
describe("saving the loaded railroad", () => {
  const edited = { opened: "toy", loaded: "toy", saved: false };

  it("is dead while power is on or stopped", () => {
    expect(on("save", { ...edited, power: "on" })).toBe(false);
    expect(on("save", { ...edited, power: "stopped" })).toBe(false);
    expect(on("save", { ...edited, power: "off" })).toBe(true);
  });

  /** The rule reads the two names and not the editor: a drawing that is not
   *  the loaded railroad is only a file, and its save builds nothing, so
   *  power does not hold it. The editor opens no such drawing now (ADR-0072,
   *  decision 3), so the case is the rule's and not a path to it. */
  it("leaves another drawing's Save alone", () => {
    expect(on("save", { ...edited, opened: "fork", power: "on" })).toBe(true);
  });

  it("is what ON waits for", () => {
    expect(isLoaded(standing(edited))).toBe(true);
    expect(unbuilt(standing(edited))).toBe(true);
    expect(unbuilt(standing({ ...edited, saved: true }))).toBe(false);
    expect(unbuilt(standing({ ...edited, opened: "fork" }))).toBe(false);
    expect(unbuilt(standing({ ...edited, loaded: null }))).toBe(false);
  });
});

/** The view is the surface's own, so it is there to be changed whatever the
 *  drawing is and whichever view is current: an empty sheet still zooms, and
 *  both views draw on the one canvas (#168). */
describe("the view", () => {
  it("is never dead, there being one viewport under both views", () => {
    for (const id of ["zoom-in", "zoom-out", "fit"] as const) {
      expect(on(id)).toBe(true);
    }
  });

  /** The netlist is not the canvas's view but what the drawing derives to
   *  (ADR-0024), and with nothing open there is no derivation to consult: the
   *  pane would open on a hint and take a fifth of the width to say it. The
   *  keyboard asks this same rule, so `N` on an empty page does nothing
   *  either. */
  it("consults the netlist only of a drawing that is open", () => {
    expect(on("netlist")).toBe(false);
    expect(on("netlist", { opened: "reversing-loops" })).toBe(true);
    expect(on("netlist", { opened: "reversing-loops", saved: false })).toBe(true);
  });
});

/**
 * What backup says without being opened (#321): the band's note and the words
 * beside `Settings ▸ Backup…` both wear these, so the two never disagree
 * (#688, #733).
 */
describe("what backup says without being opened", () => {
  it("says nothing where there is nothing to say", () => {
    expect(backupWords("quiet")).toBeNull();
  });

  it("names what is wrong", () => {
    expect(backupWords("unset")).toBe("no backup set up");
    expect(backupWords("behind")).toBe("backup behind");
    expect(backupWords("blocked")).toBe("backup cannot run");
    expect(backupWords("off")).toBe("backup is off");
  });

  it("says nothing of a store inside another repository", () => {
    expect(backupWords("inside")).toBeNull();
  });
});

/**
 * What the band's track-power control shows: the state, and why it is dead
 * (look#12). The toggle asking for `off` is the drain request (ADR-0062), so
 * while the drain is outstanding it reads `draining`.
 */
describe("what the power control shows", () => {
  const LINKED = { linked: true, draining: false };

  it("shows where the supply stands", () => {
    for (const power of ["on", "off", "stopped"] as const) {
      expect(supply(standing({ power }), LINKED)).toEqual({ state: power, reason: "" });
    }
  });

  it("is dead, and off, before the station has said", () => {
    expect(supply(standing({ power: null }), LINKED)).toEqual({
      state: "off",
      reason: "Waiting for the station",
    });
  });

  /** A broker that is not answering would swallow the press. */
  it("is dead while the broker is not answering", () => {
    expect(supply(standing({ power: "on" }), { ...LINKED, linked: false })).toEqual({
      state: "on",
      reason: "Waiting for the station",
    });
  });

  /** Pressing it then asks for `on`, which is the way out of the wait. */
  it("reads draining while the drain is outstanding", () => {
    expect(supply(standing({ power: "on" }), { ...LINKED, draining: true })).toEqual({
      state: "draining",
      reason: "",
    });
  });

  /** Power on would run trains under track no app built (ADR-0071). */
  it("waits for a save while the loaded railroad is unbuilt and off", () => {
    const edited = { opened: "toy", loaded: "toy", saved: false };
    expect(supply(standing({ ...edited, power: "off" }), LINKED)).toEqual({
      state: "off",
      reason: "Save the railroad first",
    });
    expect(supply(standing({ ...edited, power: "on" }), LINKED)).toEqual({
      state: "on",
      reason: "",
    });
  });
});
