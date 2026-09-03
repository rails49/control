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
  | "netlist"
  | "backup";

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
  /** How many trains stand on the layout, as the run says. Any of them
   *  freezes the drawing (`frozen` below). A count and not a flag, because
   *  what the run knows is which trains are placed and the rule is read off
   *  it afresh — nothing here is latched, so the last train leaving thaws
   *  the drawing on its own. */
  placed: number;
  /** Whether backup has anything to say without being asked (#321). */
  backup: BackupStanding;
}

/**
 * What backup says from outside its own dialog.
 *
 * Two things are worth a mark on a menu somebody is not looking at, and both
 * are the same failure: believing the railroad is safe when it is not.
 *
 * - `never` — nothing has ever been backed up and nothing is going to be.
 *   Automated backup is off until a person turns it on (#321), which leaves it
 *   off for exactly the person it was written for: the one who drew a railroad
 *   over months and never thought about backups.
 * - `behind` — backup is on and the copy off this machine has been failing for
 *   more than a day. Each failure on its own is a network coming and going;
 *   a day of them is a remote that moved or a credential that expired.
 *
 * `quiet` is everything else, including a copy that failed an hour ago. Saying
 * so every time would teach a person to ignore it.
 */
export type BackupStanding = "quiet" | "never" | "behind";

/** Where the editor stands before it has been told anything: nothing open,
 *  nothing chosen, nothing to take back. */
export const NOTHING: Standing = {
  opened: "",
  saved: true,
  selection: 0,
  editable: false,
  undo: false,
  redo: false,
  placed: 0,
  backup: "quiet",
};

/**
 * Whether the drawing is frozen: any train placed, and it is
 * ([ADR-0038](../../../docs/adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md),
 * #169). You do not rewire track with locomotives standing on it.
 *
 * The one reading of the rule. `editing` below kills the commands that would
 * change the document, the editing view's gestures ask it before they mean
 * anything, and the band prints its word off it rather than counting trains
 * of its own.
 */
export function frozen({ placed }: Standing): boolean {
  return placed > 0;
}

export interface Command {
  label: string;
  /** What the item has to say before anybody opens it, or `null` for the
   *  ordinary case of nothing. The bar draws a mark and says these words; the
   *  command still runs, so this warns and never disables. */
  mark?(standing: Standing): string | null;
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
  undo: { label: "Undo", key: "⌘Z", enabled: editing(({ undo }) => undo) },
  redo: { label: "Redo", key: "⇧⌘Z", enabled: editing(({ redo }) => redo) },
  rotate: { label: "Rotate", key: "R", enabled: editing(hasSelection) },
  flip: { label: "Flip", key: "F", enabled: editing(hasSelection) },
  delete: { label: "Delete", key: "⌫", enabled: editing(hasSelection) },
  properties: {
    label: "Properties…",
    enabled: editing(({ selection, editable }) => selection === 1 && editable),
  },
  // The view is the surface's own, so it is there to be changed whatever the
  // drawing is and whichever view is current: an empty sheet still zooms, and
  // both views draw on the one canvas, which has the one viewport
  // ([#168](https://github.com/rails49/control/issues/168)).
  "zoom-in": { label: "Zoom in", key: "+", enabled: () => true },
  "zoom-out": { label: "Zoom out", key: "−", enabled: () => true },
  fit: { label: "Fit", key: "0", enabled: () => true },
  // Not the canvas's view but what the drawing derives to, so this one does
  // need a drawing: with none open there is nothing derived to consult, and
  // the pane would open on a hint and take a fifth of the width to say it
  // (ADR-0024).
  netlist: {
    label: "Netlist",
    key: "N",
    enabled: ({ opened }) => opened !== "",
  },
  // The store's and not the drawing's, so nothing about what is open makes it
  // dead: a store with no railroad in it yet is one somebody is about to draw
  // in, and what backup says about it — that it is no git repository, and the
  // command that would make it one — is worth reading before the first save
  // rather than after it (ADR-0053).
  backup: { label: "Backup…", enabled: () => true, mark: backupSays },
};

/**
 * What the `Backup…` item says without being opened.
 *
 * The words are the whole of the warning: a mark somebody has to open a dialog
 * to understand is a mark they learn to ignore.
 */
function backupSays({ backup }: Standing): string | null {
  if (backup === "never") {
    return "this railroad has never been backed up";
  }
  if (backup === "behind") {
    return "the copy on the other machine is more than a day behind";
  }
  return null;
}

/** A verb that reads the selection is dead without one. */
function hasSelection({ selection }: Standing): boolean {
  return selection > 0;
}

/**
 * A verb that changes the document, which is dead while the drawing is frozen
 * whatever else is true of it (#169).
 *
 * Written as a wrapper so that the category is named once and a command joins
 * it by wearing it: a new verb that draws is frozen by being declared with
 * this, rather than by someone remembering to repeat the condition. Saving is
 * not one of them — it writes the document out rather than changing it, and
 * the edits it carries were made before the train arrived.
 */
function editing(rule: (standing: Standing) => boolean): Command["enabled"] {
  return (standing) => !frozen(standing) && rule(standing);
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
    {
      name: "File",
      items: ["new", "save", "save-as", null, "export-svg", null, "backup"],
    },
    {
      name: "Edit",
      items: ["undo", "redo", null, "rotate", "flip", "delete", null, "properties"],
    },
    { name: "View", items: ["zoom-in", "zoom-out", "fit", null, "netlist"] },
  ],
  run: [{ name: "View", items: ["zoom-in", "zoom-out", "fit"] }],
  // The throttle draws no document: there is nothing to zoom, nothing to
  // save, and the two gestures it writes are controls in the view itself
  // rather than verbs in a menu (ui/THROTTLE.md).
  throttle: [],
  // Stock draws two documents and neither is a drawing: there is no viewport
  // to move, and what it writes — a model, a roster — are controls in the
  // view itself for the same reason the throttle's gestures are
  // (ui/STOCK.md). `File ▸ Save` here would be a second Save meaning
  // something else than the one beside it.
  stock: [],
};

/** What each view pins at the right end of the bar, in the order they sit in.
 *  Zoom and fit are pressed constantly — while drawing, and while following a
 *  train across a railroad too large to see at once — and `View ▸ Zoom in` is
 *  three clicks for what is then one. Both views draw on one canvas, so both
 *  get the same three (#168). */
export const TOOLS: Record<ViewId, CommandId[]> = {
  edit: ["zoom-out", "zoom-in", "fit"],
  run: ["zoom-out", "zoom-in", "fit"],
  throttle: [],
  stock: [],
};
