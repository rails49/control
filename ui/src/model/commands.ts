/**
 * Every command a view offers: what it is called, the key that does the same
 * thing, the menu it sits in, and when it is dead.
 *
 * The menu bar and the keyboard both come through here, so an item and the key
 * printed beside it cannot come to mean different things. That is what makes a
 * menu bar the second thing EDITOR.md#editing endorses rather than the first
 * it refuses: the header carries no bare verb button, and a menu names the key
 * it duplicates.
 *
 * It is a module in `model/` with a test because the enablement rules are
 * neither the document nor the DOM (EDITOR.md#tests). `Standing` is what a
 * component reads off itself and hands over; nothing here touches an `Editor`,
 * so the rules are driven from plain values.
 *
 * The glyphs are not declared here. They are `lit` templates and `model/`
 * imports no `ui/`; `GLYPHS` in `ui/icons.ts` is keyed by `CommandId`, so a
 * command without a glyph is a compile error rather than a drift.
 */

import type { ViewId } from "./views.js";

export type CommandId =
  | "new"
  | "save"
  | "save-as"
  | "export-svg"
  | "undo"
  | "redo"
  | "rotate"
  | "flip"
  | "delete"
  | "properties"
  | "zoom-in"
  | "zoom-out"
  | "fit"
  | "netlist";

/** Where the editor stands, as far as a command needs to know. */
export interface Standing {
  /** The drawing that is open, `""` while none is. */
  opened: string;
  /** Whether the store has been given every edit. */
  saved: boolean;
  /** How many symbols are selected. */
  selection: number;
  /** Whether the one selected symbol has anything to set. False wherever the
   *  selection is not exactly one: a group selection is a move about to
   *  happen, and a kind with nothing to set opens no dialog at all. */
  editable: boolean;
  /** Whether there is a snapshot behind, and one ahead. */
  undo: boolean;
  redo: boolean;
  /** Whether the current view's drawing surface has a viewport to change. The
   *  editor's canvas has one; the run view's picture is fitted to the sheet
   *  and gains one when the two become one canvas
   *  ([#168](https://github.com/rails49/control/issues/168)). */
  zoomable: boolean;
}

/** Where the editor stands before it has been told anything: nothing open,
 *  nothing chosen, nothing to take back. */
export const NOTHING: Standing = {
  opened: "",
  saved: true,
  selection: 0,
  editable: false,
  undo: false,
  redo: false,
  zoomable: false,
};

export interface Command {
  label: string;
  /** The key that does the same thing, as it reads beside the label.
   *  Undefined where there is none to name: Chrome keeps `⌘N` for a new
   *  window and it never reaches the page, so a blank is better than a
   *  binding the browser eats. */
  key?: string;
  enabled(standing: Standing): boolean;
}

export const COMMANDS: Record<CommandId, Command> = {
  new: { label: "New…", enabled: () => true },
  save: {
    label: "Save",
    key: "⌘S",
    enabled: ({ opened, saved }) => opened !== "" && !saved,
  },
  "save-as": {
    label: "Save As…",
    key: "⇧⌘S",
    enabled: ({ opened }) => opened !== "",
  },
  // The picture is of what is on the sheet, so unsaved edits are in it and
  // only having nothing open makes it dead.
  "export-svg": {
    label: "Export SVG…",
    enabled: ({ opened }) => opened !== "",
  },
  undo: { label: "Undo", key: "⌘Z", enabled: ({ undo }) => undo },
  redo: { label: "Redo", key: "⇧⌘Z", enabled: ({ redo }) => redo },
  rotate: { label: "Rotate", key: "R", enabled: hasSelection },
  flip: { label: "Flip", key: "F", enabled: hasSelection },
  delete: { label: "Delete", key: "⌫", enabled: hasSelection },
  properties: {
    label: "Properties…",
    enabled: ({ selection, editable }) => selection === 1 && editable,
  },
  // The view is the surface's own, so it is there to be changed whatever the
  // drawing is: an empty sheet still zooms. What it needs is a surface that
  // has a viewport at all.
  "zoom-in": { label: "Zoom in", key: "+", enabled: zooms },
  "zoom-out": { label: "Zoom out", key: "−", enabled: zooms },
  fit: { label: "Fit", key: "0", enabled: zooms },
  // Not the canvas's view but what the drawing derives to, so this one does
  // need a drawing: with none open there is nothing derived to consult, and
  // the pane would open on a hint and take a fifth of the width to say it
  // (ADR-0024).
  netlist: {
    label: "Netlist",
    key: "N",
    enabled: ({ opened }) => opened !== "",
  },
};

/** A verb that reads the selection is dead without one. */
function hasSelection({ selection }: Standing): boolean {
  return selection > 0;
}

/** A verb that moves a viewport is dead on a surface that has none. */
function zooms({ zoomable }: Standing): boolean {
  return zoomable;
}

export interface Menu {
  name: string;
  /** The items in order, `null` where a divider parts two groups. */
  items: (CommandId | null)[];
}

/**
 * The bar, left to right, for each view.
 *
 * The bar is the shell's and its menus are the current view's: it acts on the
 * document that view has open (ADR-0038). The editor's document is a drawing,
 * so it has a `File` and an `Edit`; the run view's is a railroad somebody else
 * is running, so it has neither, and what it presses instead — HOLD and GO —
 * is not a command and has no key, being a gesture on the bus rather than a
 * verb of this app's.
 *
 * Which railroad is loaded is not here either. That is the whole system's and
 * the band's picker sets it, so `File ▸ Open` is gone from both views
 * ([#167](https://github.com/rails49/control/issues/167)).
 */
export const MENUS: Record<ViewId, Menu[]> = {
  edit: [
    { name: "File", items: ["new", "save", "save-as", null, "export-svg"] },
    {
      name: "Edit",
      items: ["undo", "redo", null, "rotate", "flip", "delete", null, "properties"],
    },
    { name: "View", items: ["zoom-in", "zoom-out", "fit", null, "netlist"] },
  ],
  run: [{ name: "View", items: ["zoom-in", "zoom-out", "fit"] }],
};

/** What each view pins at the right end of the bar, in the order they sit in.
 *  Zoom and fit are pressed constantly while drawing, and `View ▸ Zoom in` is
 *  three clicks for what is then one. */
export const TOOLS: Record<ViewId, CommandId[]> = {
  edit: ["zoom-out", "zoom-in", "fit"],
  run: [],
};
