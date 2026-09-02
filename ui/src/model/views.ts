/**
 * The views the app has of the railroad it has loaded, as data
 * ([ADR-0038](../../../docs/adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md)).
 *
 * One app, one railroad, N views. The band renders the list as a **selector**,
 * one icon-button per view with the current one marked: two of them were a
 * single toggle, and the third made it this, which is the redesign ADR-0038
 * said the list would keep small. A stock screen and a schedule table add an
 * entry here rather than force another, which is the whole reason this is a
 * list and not a boolean.
 *
 * The labels are here and the icons are not: an icon is a `lit` template and
 * `model/` imports no `ui/`. `ICONS` in `ui/icons.ts` is keyed by `ViewId`, so
 * a view without one is a compile error, exactly as `GLYPHS` is keyed by
 * `CommandId`.
 */

export type ViewId = "run" | "edit";

export interface View {
  id: ViewId;
  /** What the view is called, on the control that switches to it. */
  label: string;
}

/** Every view, in the order the control offers them. The app opens in the
 *  first of them: it is a control surface, and the editor is the setup tool
 *  you go to deliberately. */
export const VIEWS: View[] = [
  { id: "run", label: "Run" },
  { id: "edit", label: "Edit" },
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
