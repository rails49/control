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
 * Each command names its glyph: a Bootstrap icon as Shoelace ships it, or one
 * of look's own (look#12). `COMMANDS` is keyed by `CommandId`, so a command
 * without one is a compile error.
 */

import type { PowerShown, PowerState } from "@rails49/look";

import { trackLive, type DrivingMode, type Power } from "./trace.js";
import type { ViewId } from "./views.js";

export type CommandId =
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
  /** Whether the last save of the open drawing did not land: the store
   *  refused it or did not answer. The edits stay on the page, marked
   *  unsaved, until a save lands (`stranded` below). */
  failed: boolean;
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
   *  Power on or draining freezes the drawing (`frozen` below); it is read
   *  afresh and nothing is latched, so switching it off thaws the drawing on
   *  its own. Trains standing on the layout do not freeze it: a save names
   *  the railroad again and the rebuild keeps them where they fit (ADR-0071).
   *  Null power alone freezes nothing: a joined page whose drawing does not
   *  derive reads none, and that drawing must stay editable to be fixed. */
  power: Power | null;
  /** The railroad the run has loaded, as `tc49/layout/state/railroad` names
   *  it, `null` with no session. Where it is the open drawing, a save is what
   *  the apps build next, so the editor saves only with power off and ON
   *  saves first (`owed` below). Null with a drawing open is a page that has
   *  lost the broker, and that freezes the drawing (`unheard` below). */
  loaded: string | null;
}

/**
 * What backup says from outside its own dialog: the note in the band and the
 * words beside `Settings ▸ Backup…` both read it, so the two never disagree
 * (#688, #733).
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

/** What each standing says, in the words the note and the settings dialog
 *  both wear; `null` where it says nothing. */
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
  failed: false,
  selection: 0,
  editable: false,
  undo: false,
  redo: false,
  power: null,
  loaded: null,
};

/**
 * Whether the drawing is frozen: track power on or draining, and it is
 * ([ADR-0071](../../../docs/adr/0071-a-rebuild-under-the-same-name-keeps-the-placements.md),
 * decision 5). With power on the run moves trains over what the dispatcher
 * built, so the drawing must not drift from it; with power off nothing moves,
 * and a save of the loaded railroad builds it again with the trains kept where
 * they fit. Stopped is frozen too: it is an emergency stop somebody clears
 * back to on, not a rest.
 *
 * It is frozen as well while a drawing is open and the page has not heard
 * which railroad is loaded (`unheard` below). A page with nothing open holds
 * no railroad, so there is nothing to drift.
 *
 * The one reading of the rule. `editing` below kills the commands that would
 * change the document, and the editing view's gestures ask it before they
 * mean anything. With power on the Edit view does not open at all
 * (`shut`, `model/views.ts`; ADR-0085, decision 3); the freeze is what holds
 * from the moment power lands until the page has moved to the run view, and
 * the whole of it on a page that has lost the broker.
 */
export function frozen(standing: Standing): boolean {
  return trackLive(standing.power) || unheard(standing);
}

/** Whether a drawing is open and the row naming the loaded railroad is not
 *  heard: the page has lost the broker (#792). The editor holds no railroad
 *  but the one the row last named (ADR-0072, decision 3), so the open drawing
 *  is the loaded railroad's, and the page cannot know whether its track has
 *  power. It keys on the row, not on power, which also reads null on a joined
 *  page whose drawing does not derive. Nothing is latched: the row heard again
 *  with power off lifts it. */
export function unheard({ opened, loaded }: Standing): boolean {
  return opened !== "" && loaded === null;
}

/** Whether the open drawing is the railroad the run has loaded: the one whose
 *  save the apps build next (ADR-0071). The editor holds no other (ADR-0072,
 *  decision 3), but before the row arrives the open drawing is `""`. */
export function isLoaded({ opened, loaded }: Standing): boolean {
  return opened !== "" && opened === loaded;
}

/**
 * Whether the editor saves now: the loaded railroad's drawing holds edits the
 * store has not been given, and track power reads `off`
 * ([ADR-0085](../../../docs/adr/0085-the-editor-saves-when-it-is-left-and-a-railroad-can-be-named-without-being-built.md),
 * decision 1). It is asked on leaving the Edit view, when the page is hidden,
 * before ON and before a railroad is picked; there is no Save of a person's
 * own. The layout builds only with power off, so with power on or draining
 * the save would write a drawing no app runs, and the edits wait on the page
 * (`stranded` below).
 */
export function owed(standing: Standing): boolean {
  return isLoaded(standing) && !standing.saved && standing.power === "off";
}

/**
 * Whether the band says *unsaved*: the drawing holds edits that could not be
 * saved. Power came on from elsewhere while this page had edits — or the page
 * cannot tell, having lost the broker — or the last save did not land. Edits
 * a save is still owed for with power off say nothing: leaving the editor
 * saves them (ADR-0085, decision 1).
 */
export function stranded(standing: Standing): boolean {
  return !standing.saved && (standing.power !== "off" || standing.failed);
}

/**
 * What the band's track-power control shows: where power stands, and why
 * the control is dead, `""` where it is live (look#12). Power is `layout`'s
 * and the control draws it as `layout` says it, `draining` included: the page
 * keeps no wait of its own, `layout` switching the supply off once nothing is
 * moving (ADR-0078).
 *
 * Dead before the station has said where the supply stands and while the
 * broker is not answering, which would swallow the press. Unsaved edits do
 * not make it dead: ON saves them first, and the power comes on once the
 * apps have built what was saved (ADR-0085, decision 2).
 */
export function supply(
  standing: Standing,
  { linked }: { linked: boolean },
): { state: PowerShown; reason: string } {
  const { power } = standing;
  if (power === null || !linked) {
    return { state: power ?? "off", reason: "Waiting for the station" };
  }
  return { state: power, reason: "" };
}

/**
 * What a press on the band's power control asks `layout` for, on
 * `power_wanted` (ADR-0078). The control says what was pressed in look's
 * words: the toggle asks `off` from `on` and `on` from anything else, and the
 * stop sign asks `stopped`. The toggle's `off` is the drain, so it asks for
 * `draining`; its `on` is `on`, from `off` and from `draining` alike, ending
 * a drain; and the stop sign is the emergency stop, `off` at once.
 */
export function asked(press: PowerState): Power {
  switch (press) {
    case "on":
      return "on";
    case "off":
      return "draining";
    case "stopped":
      return "off";
  }
}

/**
 * The driving control on the band: the railroad's driving mode as `layout`
 * says it on `state/driving`, shown by its glyph and tooltip — a person for
 * manual, a robot for automatic — and the mode a press asks for, the other
 * one (ADR-0079). Dead until `layout` has said, a press against a mode not
 * heard being one that could ask for the mode already standing.
 */
export function driving(mode: DrivingMode | null): {
  icon: "person-fill" | "robot";
  label: string;
  next: DrivingMode;
  dead: boolean;
} {
  const automatic = mode === "automatic";
  return {
    icon: automatic ? "robot" : "person-fill",
    label: automatic
      ? "Driving mode automatic: press for manual"
      : "Driving mode manual: press for automatic",
    next: automatic ? "manual" : "automatic",
    dead: mode === null,
  };
}

export interface Command {
  label: string;
  /** The glyph on its button on the rail. */
  icon: string;
  /** The key that does the same thing, in look's form (`Mod+S`), which the
   *  rail shows per platform. Undefined where there is none to name. */
  key?: string;
  enabled(standing: Standing): boolean;
}

export const COMMANDS: Record<CommandId, Command> = {
  // The picture is of what is on the sheet, so unsaved edits are in it and
  // only having nothing open makes it dead.
  "export-svg": {
    label: "Export SVG…",
    icon: "box-arrow-up",
    enabled: ({ opened }) => opened !== "",
  },
  undo: {
    label: "Undo",
    icon: "arrow-counterclockwise",
    key: "Mod+Z",
    enabled: editing(({ undo }) => undo),
  },
  redo: {
    label: "Redo",
    icon: "arrow-clockwise",
    key: "Shift+Mod+Z",
    enabled: editing(({ redo }) => redo),
  },
  rotate: { label: "Rotate", icon: "rotate", key: "R", enabled: editing(hasSelection) },
  flip: {
    label: "Flip",
    icon: "symmetry-vertical",
    key: "F",
    enabled: editing(hasSelection),
  },
  delete: { label: "Delete", icon: "trash", key: "⌫", enabled: editing(hasSelection) },
  properties: {
    label: "Properties…",
    icon: "sliders",
    enabled: editing(({ selection, editable }) => selection === 1 && editable),
  },
  // The view is the surface's own, so it is there to be changed whatever the
  // drawing is and whichever view is current: an empty sheet still zooms, and
  // both views draw on the one canvas, which has the one viewport
  // ([#168](https://github.com/rails49/control/issues/168)).
  "zoom-in": { label: "Zoom in", icon: "zoom-in", key: "+", enabled: () => true },
  "zoom-out": { label: "Zoom out", icon: "zoom-out", key: "−", enabled: () => true },
  fit: { label: "Fit", icon: "fullscreen", key: "0", enabled: () => true },
  // Not the canvas's view but what the drawing derives to, so this one does
  // need a drawing: with none open there is nothing derived to consult, and
  // the pane would open on a hint and take a fifth of the width to say it
  // (ADR-0024).
  netlist: {
    label: "Netlist",
    icon: "layout-sidebar-reverse",
    key: "N",
    enabled: ({ opened }) => opened !== "",
  },
};

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
 * this, rather than by someone remembering to repeat the condition.
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
 * somebody else is running, so it has neither. The driving control is not
 * here: the mode is the whole railroad's, so it is on the band (#871).
 *
 * **`View` comes first wherever there is one.** Zoom and fit are pressed
 * constantly — while drawing, and while following a train across a railroad
 * too large to see at once — and both views draw on the one canvas (#168), so
 * the three sit in the same place whichever view is up. A person who has
 * learnt where Fit is does not learn it again on the other view.
 *
 * Which railroad is loaded is not here. That is the whole system's and the
 * settings dialog behind the band's gear sets it, so `File ▸ Open` is gone
 * from both views ([#167](https://github.com/rails49/control/issues/167),
 * ADR-0072). Making one is the dialog's too, so `New` and `Save As` are gone
 * with it: the editor holds the loaded railroad and no other (#734). Backup
 * is the store's and not the drawing's, so it is there too and not in `File`
 * (#733).
 *
 * Rotate, Flip, Delete and Properties are not here either. They apply to a
 * selection and already read in the right-click menu with their keys beside
 * them; four buttons that are dead whenever nothing is selected say less than
 * a menu that opens on the thing they act on (ADR-0064).
 */
export const RAIL: Record<ViewId, Group[]> = {
  edit: [
    { name: "View", items: ["zoom-out", "zoom-in", "fit", "netlist"] },
    { name: "File", items: ["export-svg"] },
    { name: "Edit", items: ["undo", "redo"] },
  ],
  run: [{ name: "View", items: ["zoom-out", "zoom-in", "fit"] }],
  // The throttle draws no document: there is nothing to zoom, and the two gestures it writes are controls in the view itself
  // rather than buttons on the rail (ui/THROTTLE.md).
  throttle: [],
  // Stock draws two documents and neither is a drawing: there is no viewport
  // to move, and what it writes — a model, a roster — are controls in the
  // view itself for the same reason the throttle's gestures are
  // (ui/STOCK.md).
  stock: [],
};
