/**
 * The views the app has of the railroad it has loaded, as data
 * ([ADR-0038](../../../docs/adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md)).
 *
 * The control surfaces come first and the setup tools last: the app opens on
 * the first of them, and stock and the editor are what you go to
 * deliberately.
 *
 * One app, one railroad, N views. The band renders the list as a **selector**,
 * one icon-button per view with the current one marked: two of them were a
 * single toggle, and the third made it this, which is the redesign ADR-0038
 * said the list would keep small. The stock screen was the first entry to
 * arrive that way rather than force another redesign (#393), and a schedule
 * table adds one the same way — which is the whole reason this is a list and
 * not a boolean.
 *
 * Each view names its glyph, as each command does (`model/commands.ts`).
 */

import { trackLive, type Power } from "./trace.js";

export type ViewId = "run" | "throttle" | "stock" | "edit";

export interface View {
  id: ViewId;
  /** What the view is called, on the control that switches to it. */
  label: string;
  /** The glyph on that control. */
  icon: string;
}

/** Every view, in the order the control offers them. The app opens in the
 *  first of them: it is a control surface, and stock and the editor are the
 *  setup tools you go to deliberately. */
export const VIEWS: View[] = [
  { id: "run", label: "Run", icon: "stoplights" },
  { id: "throttle", label: "Throttle", icon: "throttle" },
  { id: "stock", label: "Stock", icon: "train-freight-front" },
  { id: "edit", label: "Edit", icon: "pencil" },
];

/** The hash that names a view, so a reload and a bookmark keep it. */
export function hashOf(view: ViewId): string {
  return `#${view}`;
}

/** Which view a location hash names. An unknown hash and an absent one are
 *  both the run view: a link that has gone stale opens on the control surface
 *  rather than on nothing. */
export function viewOf(hash: string): ViewId {
  const named = hash.replace(/^#/, "");
  const found = VIEWS.find((view) => view.id === named);
  return found?.id ?? VIEWS[0]!.id;
}

/**
 * Why a view does not open, `""` where it does. The Edit view does not open
 * while track power reads `on` or `draining`
 * ([ADR-0085](../../../docs/adr/0085-the-editor-saves-when-it-is-left-and-a-railroad-can-be-named-without-being-built.md),
 * decision 3): the run is moving trains over what the dispatcher built, and
 * the layout builds only with power off, so an edit made then could not be
 * saved until power is off again. Power coming on while it is open moves the
 * page to the first view. A supply not yet heard (`null`) closes nothing:
 * what a page that has lost the broker may do in the editor is `frozen`'s
 * (`model/commands.ts`).
 */
export function shut(view: ViewId, power: Power | null): string {
  return view === "edit" && trackLive(power) ? "track power is on" : "";
}
