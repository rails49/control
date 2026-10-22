/**
 * Widgets on the drawing: a text, a button or a toggle placed beside the track
 * ([ADR-0087](../../../docs/adr/0087-a-widget-is-on-the-drawing-and-control-carries-its-payload-without-reading-it.md)).
 *
 * What the editor needs to know about one and the document does not say: the
 * name a new one gets, what it starts with, the topic its name ends, why a
 * name or a value will not do, and where it sits on the grid. No DOM, so it is
 * tested here (EDITOR.md#tests).
 *
 * A widget lives in the drawing's own `widgets` mapping, not among the
 * symbols, so its name is in a namespace of its own and may be one a symbol
 * also wears. The selection holds both, so a widget is selected under
 * `selectionKey`, which carries the `/` no symbol name can (`isName`).
 */

import type { Drawing, WidgetKind, WidgetSpec } from "./drawing.js";
import type { Point } from "./geometry.js";
import { isWidgetName } from "./rules.js";

/** The kinds, in the order the palette offers them. */
export const WIDGET_KINDS: readonly WidgetKind[] = ["text", "button", "toggle"];

/** The sizes a widget's words come in, and how they sit
 *  (`tc49.store.drawing.WIDGET_TEXT`, `WIDGET_ALIGN`). */
export const WIDGET_TEXT = ["small", "normal", "large"] as const;
export const WIDGET_ALIGN = ["left", "center", "right"] as const;

/** A new widget's size, in squares. */
export const WIDGET_SIZE: [number, number] = [3, 1];

/**
 * The topic each kind's row is on, without the widget's name, which is the
 * one level past it (`tc49.lib.inventory.WIDGET_TOPICS`, ADR-0087 decision 2).
 */
const TOPICS: Record<WidgetKind, string> = {
  text: "tc49/ui/state/text",
  toggle: "tc49/ui/state/toggle",
  button: "tc49/ui/button",
};

/** The whole topic a widget's row is on, which properties shows so that
 *  whoever writes the listener or the script can read it off the screen. */
export function widgetTopic(kind: WidgetKind, name: string): string {
  return `${TOPICS[kind]}/${name}`;
}

const PREFIX = "widget/";

/** What the selection holds for a widget. */
export function selectionKey(name: string): string {
  return `${PREFIX}${name}`;
}

/** The widget a selection entry is, or `null` for a symbol's. */
export function widgetOf(key: string): string | null {
  return key.startsWith(PREFIX) ? key.slice(PREFIX.length) : null;
}

export function isWidgetKind(kind: string): kind is WidgetKind {
  return (WIDGET_KINDS as readonly string[]).includes(kind);
}

/** The lowest free `<kind><n>` among the drawing's widgets: `text1`,
 *  `button1`, and so on. */
export function mintWidget(drawing: Drawing, kind: WidgetKind): string {
  const widgets = drawing.widgets ?? {};
  for (let n = 1; ; n++) {
    const name = `${kind}${n}`;
    if (!(name in widgets)) return name;
  }
}

/**
 * A new widget: 3 × 1, words and alignment left to the schema's defaults, and
 * each kind's payload keys filled so that the store takes it. A toggle's two
 * payloads must differ, so they start as `on` and `off`; a button sends its
 * own name until somebody types something else.
 */
export function newWidget(
  kind: WidgetKind,
  name: string,
  at: [number, number],
): WidgetSpec {
  const spec: WidgetSpec = { kind, at, size: [...WIDGET_SIZE] };
  if (kind === "button") spec.payload = name;
  if (kind === "toggle") Object.assign(spec, { on: "on", off: "off" });
  return spec;
}

/**
 * Why a widget name will not do, or `null` for one that will. The properties
 * dialog is the only place one is typed, so it is asked there before the
 * dialog closes, as `symbolTrouble` is for a symbol. `was` is the name being
 * replaced; `taken` is every widget's name, `was` among them.
 */
export function widgetTrouble(
  name: string,
  was: string,
  taken: readonly string[],
): string | null {
  if (name === "") return "a widget needs a name";
  if (!isWidgetName(name)) {
    return `'${name}' cannot name a widget: letters, digits, '_' and '-' only`;
  }
  if (name !== was && taken.includes(name)) return `'${name}' is already taken`;
  return null;
}

/** Why a size will not do: the store takes two positive whole numbers. */
export function sizeTrouble(size: readonly [number, number]): string | null {
  return size.every((n) => Number.isInteger(n) && n > 0)
    ? null
    : "a size is a positive whole number of squares";
}

/** Why a toggle's two payloads will not do: a page reads its position by
 *  comparing the row with them, so they must differ (ADR-0087 decision 4). */
export function toggleTrouble(spec: WidgetSpec): string | null {
  return spec.kind === "toggle" && spec.on === spec.off
    ? "on and off must differ"
    : null;
}

/** The middle of a widget, which is what a rubber band takes it by. */
export function widgetCentre({ at, size }: WidgetSpec): Point {
  return { x: at[0] + size[0] / 2, y: at[1] + size[1] / 2 };
}

/** Whether a widget, drawn `shift` from where the document puts it, covers a
 *  point. */
export function widgetCovers(
  { at, size }: WidgetSpec,
  point: Point,
  shift: Point = { x: 0, y: 0 },
): boolean {
  const [x, y] = [at[0] + shift.x, at[1] + shift.y];
  return (
    point.x >= x && point.x < x + size[0] && point.y >= y && point.y < y + size[1]
  );
}
