/**
 * Every command the editor offers: what it is called, the key that does the
 * same thing, the menu it sits in, and when it is dead.
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

export type CommandId =
  | "new"
  | "open"
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
  | "fit";

/** Where the editor stands, as far as a command needs to know. */
export interface Standing {
  /** The drawing that is open, `""` while none is. */
  opened: string;
  /** Whether the store has been given every edit. */
  saved: boolean;
  /** How many drawings there are to open. */
  drawings: number;
  /** How many symbols are selected. */
  selection: number;
  /** Whether the one selected symbol has anything to set. False wherever the
   *  selection is not exactly one: a group selection is a move about to
   *  happen, and a kind with nothing to set opens no dialog at all. */
  editable: boolean;
  /** Whether there is a snapshot behind, and one ahead. */
  undo: boolean;
  redo: boolean;
}

/** Where the editor stands before it has been told anything: nothing open,
 *  nothing chosen, nothing to take back. */
export const NOTHING: Standing = {
  opened: "",
  saved: true,
  drawings: 0,
  selection: 0,
  editable: false,
  undo: false,
  redo: false,
};

export interface Command {
  label: string;
  /** The key that does the same thing, as it reads beside the label.
   *  Undefined where there is none to name: Chrome keeps `⌘N` for a new
   *  window and it never reaches the page, `⌘O` is unreliable for the same
   *  reason, and a blank is better than a binding the browser eats. */
  key?: string;
  enabled(standing: Standing): boolean;
}

export const COMMANDS: Record<CommandId, Command> = {
  new: { label: "New…", enabled: () => true },
  open: { label: "Open", enabled: ({ drawings }) => drawings > 0 },
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
  // The view is the canvas's own, so it is there to be changed whatever the
  // drawing is: an empty sheet still zooms.
  "zoom-in": { label: "Zoom in", key: "+", enabled: () => true },
  "zoom-out": { label: "Zoom out", key: "−", enabled: () => true },
  fit: { label: "Fit", key: "0", enabled: () => true },
};

/** A verb that reads the selection is dead without one. */
function hasSelection({ selection }: Standing): boolean {
  return selection > 0;
}

export interface Menu {
  name: string;
  /** The items in order, `null` where a divider parts two groups. */
  items: (CommandId | null)[];
}

/** The bar, left to right. Zoom and fit are named here and pressed elsewhere:
 *  they are also the three buttons pinned at the bar's right end, being the
 *  commands pressed constantly while drawing. */
export const MENUS: Menu[] = [
  { name: "File", items: ["new", "open", "save", "save-as", null, "export-svg"] },
  {
    name: "Edit",
    items: ["undo", "redo", null, "rotate", "flip", "delete", null, "properties"],
  },
  { name: "View", items: ["zoom-in", "zoom-out", "fit"] },
];

/** The three pinned at the right end of the bar, in the order they sit in. */
export const TOOLS: CommandId[] = ["zoom-out", "zoom-in", "fit"];
