/**
 * Every command a view offers: what it is called, the key that does the same
 * thing, the menu it sits in, and when it is dead.
 *
 * The rail and the keyboard both come through here, so a button and the key
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

import type { Power } from "./trace.js";
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
  /** The run's track power, as `state/power` says, `null` with no session.
   *  Power on or stopped freezes the drawing (`frozen` below); it is read
   *  afresh and nothing is latched, so switching it off thaws the drawing on
   *  its own. Trains standing on the layout do not freeze it: a save names
   *  the railroad again and the rebuild keeps them where they fit (ADR-0071). */
  power: Power | null;
  /** The railroad the run has loaded, as `tc49/layout/state/railroad` names
   *  it, `null` with no session. Where it is the open drawing, a save is what
   *  the apps build next, so Save waits for power off and ON waits for the
   *  save (`isLoaded` below). */
  loaded: string | null;
  /** Whether backup has anything to say without being asked (#321). */
  backup: BackupStanding;
}

/**
 * What backup says from outside its own dialog: the run view's note in the
 * band and the mark on `File ▸ Backup…` both read it, so the two never
 * disagree (#688).
 *
 * Six values, and the first that holds is the one:
 *
 * - `inside` — the store is inside another repository: a developer's session
 *   on the bench store of a checkout, which is not meant to be backed up. No
 *   note and no mark.
 * - `unset` — the store is no repository: a box deployed and never set up, or
 *   a store copied to a new box with backup switched on and no repository with
 *   it. A switch that says on hides nothing here.
 * - `behind` — the copy off this machine is more than a day behind. Each
 *   failure on its own is a network coming and going; a day of them is a
 *   repository that moved or a key that stopped working.
 * - `blocked` — a repository with something in `needs`: no remote, or a key
 *   this store cannot read.
 * - `off` — a repository whose backup a person switched off.
 * - `quiet` — everything else, including a copy that failed an hour ago, and
 *   anything before the store has been asked. Saying so every time would
 *   teach a person to ignore it.
 */
export type BackupStanding = "quiet" | "inside" | "unset" | "behind" | "blocked" | "off";

/** What each standing says, in the words the note and the mark both wear;
 *  `null` where it says nothing. */
export function backupWords(standing: BackupStanding): string | null {
  switch (standing) {
    case "unset":
      return "no backup set up";
    case "behind":
      return "backup behind";
    case "blocked":
      return "backup cannot run";
    case "off":
      return "backup is off";
    default:
      return null;
  }
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
  power: null,
  loaded: null,
  backup: "quiet",
};

/**
 * Whether the drawing is frozen: track power on or stopped, and it is
 * ([ADR-0071](../../../docs/adr/0071-a-rebuild-under-the-same-name-keeps-the-placements.md),
 * decision 5). With power on the run moves trains over what the dispatcher
 * built, so the drawing must not drift from it; with power off nothing moves,
 * and a save of the loaded railroad builds it again with the trains kept where
 * they fit. Stopped is frozen too: it is an emergency stop somebody clears
 * back to on, not a rest. With no session (`null`) there is no run to drift
 * from.
 *
 * The one reading of the rule. `editing` below kills the commands that would
 * change the document, the editing view's gestures ask it before they mean
 * anything, and the band prints its word off it rather than reading power of
 * its own.
 */
export function frozen({ power }: Standing): boolean {
  return power === "on" || power === "stopped";
}

/** Whether the open drawing is the railroad the run has loaded: the one whose
 *  save the apps build next (ADR-0071). A drawing forked by Save As, or one
 *  started with New, is not, and its saves name nothing. */
export function isLoaded({ opened, loaded }: Standing): boolean {
  return opened !== "" && opened === loaded;
}

/** Whether ON waits for a save: the loaded railroad's drawing holds edits the
 *  store has not been given, and the run view draws the open drawing, so power
 *  on would run trains under track the dispatcher is not running (ADR-0071,
 *  decision 6). STOP and OFF never wait. */
export function unbuilt(standing: Standing): boolean {
  return isLoaded(standing) && !standing.saved;
}

export interface Command {
  label: string;
  /** What the item has to say before anybody opens it, or `null` for the
   *  ordinary case of nothing. The rail draws a mark and says these words; the
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
    // Saving the loaded railroad names it again, and the layout builds only
    // with power off, so while it is frozen the save would write a drawing no
    // app runs (ADR-0071). Any other drawing is only a file.
    enabled: (standing) =>
      standing.opened !== "" &&
      !standing.saved &&
      !(frozen(standing) && isLoaded(standing)),
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
 * What the `Backup…` item says without being opened: the run view's note, in
 * the same words.
 *
 * The words are the whole of the warning: a mark somebody has to open a dialog
 * to understand is a mark they learn to ignore.
 */
function backupSays({ backup }: Standing): string | null {
  return backupWords(backup);
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
 * not one of them — it writes the document out rather than changing it — and
 * its own rule is above.
 */
function editing(rule: (standing: Standing) => boolean): Command["enabled"] {
  return (standing) => !frozen(standing) && rule(standing);
}

export interface Group {
  /** What the group is, which is the accessible name of the run of buttons.
   *  The words are the old menu titles: the grouping did not change, only the
   *  row it was drawn in (ADR-0064). */
  name: string;
  /** The commands in it, in the order they sit. */
  items: CommandId[];
}

/**
 * The rail down the left, top to bottom, for each view.
 *
 * The rail is the shell's and its groups are the current view's: they act on
 * the document that view has open (ADR-0038, ADR-0064). The editor's document
 * is a drawing, so it has a `File` and an `Edit`; the run view's is a railroad
 * somebody else is running, so it has neither, and what it presses instead —
 * HOLD and GO — is not a command and has no key, being a gesture on the bus
 * rather than a verb of this app's.
 *
 * **`View` comes first wherever there is one.** Zoom and fit are pressed
 * constantly — while drawing, and while following a train across a railroad
 * too large to see at once — and both views draw on the one canvas (#168), so
 * the three sit in the same place whichever view is up. A person who has
 * learnt where Fit is does not learn it again on the other view.
 *
 * Which railroad is loaded is not here. That is the whole system's and the
 * band's picker sets it, so `File ▸ Open` is gone from both views
 * ([#167](https://github.com/rails49/control/issues/167)).
 *
 * Rotate, Flip, Delete and Properties are not here either. They apply to a
 * selection and already read in the right-click menu with their keys beside
 * them; four buttons that are dead whenever nothing is selected say less than
 * a menu that opens on the thing they act on (ADR-0064).
 */
export const RAIL: Record<ViewId, Group[]> = {
  edit: [
    { name: "View", items: ["zoom-out", "zoom-in", "fit", "netlist"] },
    { name: "File", items: ["new", "save", "save-as", "export-svg", "backup"] },
    { name: "Edit", items: ["undo", "redo"] },
  ],
  run: [{ name: "View", items: ["zoom-out", "zoom-in", "fit"] }],
  // The throttle draws no document: there is nothing to zoom, nothing to
  // save, and the two gestures it writes are controls in the view itself
  // rather than buttons on the rail (ui/THROTTLE.md).
  throttle: [],
  // Stock draws two documents and neither is a drawing: there is no viewport
  // to move, and what it writes — a model, a roster — are controls in the
  // view itself for the same reason the throttle's gestures are
  // (ui/STOCK.md). A `Save` here would be a second Save meaning something
  // else than the one beside it.
  stock: [],
};
