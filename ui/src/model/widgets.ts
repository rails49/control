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

import { WIDGET } from "../render/units.js";
import type { Drawing, WidgetKind, WidgetSpec } from "./drawing.js";
import type { Point } from "./geometry.js";
import { isWidgetName } from "./rules.js";
import type { Box } from "./scene.js";

/** The kinds, in the order the palette offers them. */
export const WIDGET_KINDS: readonly WidgetKind[] = ["text", "button", "toggle"];

/** The sizes a widget's words come in, and how they sit
 *  (`tc49.store.drawing.WIDGET_TEXT`, `WIDGET_ALIGN`). */
export const WIDGET_TEXT = ["small", "normal", "large"] as const;
export const WIDGET_ALIGN = ["left", "center", "right"] as const;

/** The squares a widget is placed by, from `at` (#939): a button's one, a
 *  toggle's two, and a text widget's one cell its words run from. */
export function widgetFootprint(kind: WidgetKind): [number, number] {
  return kind === "toggle" ? [2, 1] : [1, 1];
}

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
 * A new widget: words and alignment left to the schema's defaults, and each
 * kind's payload keys filled so that the store takes it. A toggle's two
 * payloads must differ, so they start as `on` and `off`; a button sends its
 * own name until somebody types something else.
 */
export function newWidget(
  kind: WidgetKind,
  name: string,
  at: [number, number],
): WidgetSpec {
  const spec: WidgetSpec = { kind, at };
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

/** Why a toggle's two payloads will not do: a page reads its position by
 *  comparing the row with them, so they must differ (ADR-0087 decision 4). */
export function toggleTrouble(spec: WidgetSpec): string | null {
  return spec.kind === "toggle" && spec.on === spec.off
    ? "on and off must differ"
    : null;
}

/** What the editor shows of a text widget: its default, or its name and a
 *  question mark where it has none, so that it can be seen and taken. */
export function editorText(name: string, spec: WidgetSpec): string {
  return spec.default || `${name}?`;
}

/**
 * Where a widget is on the canvas, in squares: a button's and a toggle's
 * footprint, and a text widget's words as the editor shows them, run from
 * its cell the way `align` says and one square tall. There is no DOM here to
 * measure the words, so their width is their length at an average advance.
 */
export function widgetBounds(name: string, spec: WidgetSpec): Box {
  const [c, r] = spec.at;
  if (spec.kind !== "text") {
    const [w, h] = widgetFootprint(spec.kind);
    return { x: c, y: r, w, h };
  }
  const w =
    editorText(name, spec).length * WIDGET.text[spec.text ?? "normal"] * WIDGET.advance;
  const align = spec.align ?? "center";
  const x = align === "left" ? c : align === "right" ? c + 1 - w : c + 0.5 - w / 2;
  return { x, y: r, w, h: 1 };
}

/** The middle of a widget, which is what a rubber band takes it by. */
export function widgetCentre(name: string, spec: WidgetSpec): Point {
  const { x, y, w, h } = widgetBounds(name, spec);
  return { x: x + w / 2, y: y + h / 2 };
}

/** Whether a widget, drawn `shift` from where the document puts it, covers a
 *  point. */
export function widgetCovers(
  name: string,
  spec: WidgetSpec,
  point: Point,
  shift: Point = { x: 0, y: 0 },
): boolean {
  const { w, h, ...corner } = widgetBounds(name, spec);
  const [x, y] = [corner.x + shift.x, corner.y + shift.y];
  return point.x >= x && point.x < x + w && point.y >= y && point.y < y + h;
}

// --- what the run view shows and sends ---------------------------------------

/** Where every widget row is, `tc49/ui/…`: the session reads these before it
 *  reads anything as JSON, a widget payload being raw (ADR-0087 decision 4). */
export const WIDGET_PREFIX = "tc49/ui/";

/** The three colours a text widget renders, each drawn in look's own
 *  (`--red`, `--amber`, `--green`). */
export type Colour = "red" | "amber" | "green";

/** A stretch of a text widget's words that look the same. */
export interface Run {
  text: string;
  bold: boolean;
  colour: Colour | null;
}

/** The SGR codes that set a colour, bright or not. */
const COLOURS: Record<number, Colour> = {
  31: "red",
  91: "red",
  33: "amber",
  93: "amber",
  32: "green",
  92: "green",
};

/** Every escape sequence a terminal knows: a CSI sequence (`ESC [`, SGR among
 *  them), an OSC string, or any other escape, such as `ESC ( B`. A lone ESC
 *  is one too. */
const ESCAPE =
  // eslint-disable-next-line no-control-regex
  /\x1b(?:\[([0-?]*)([ -/]*)([@-~])|\][^\x07\x1b]*(?:\x07|\x1b\\)?|[ -/]*[0-~]?)/g;

/**
 * A text row as the run view shows it: bold and three colours read off its
 * ANSI SGR codes, and every other escape sequence removed (ADR-0087
 * decision 4). `1` is bold and `22` ends it; `31`/`91` red, `33`/`93` amber
 * and `32`/`92` green, `39` ending the colour; `0`, or no code at all, resets
 * both. Any other code changes nothing, the arguments of an extended colour
 * (`38;5;n`, `38;2;r;g;b`) among them.
 */
export function ansi(text: string): Run[] {
  const runs: Run[] = [];
  let bold = false;
  let colour: Colour | null = null;
  const add = (words: string) => {
    if (words === "") return;
    const last = runs.at(-1);
    if (last !== undefined && last.bold === bold && last.colour === colour) {
      last.text += words;
    } else {
      runs.push({ text: words, bold, colour });
    }
  };
  let from = 0;
  for (const found of text.matchAll(ESCAPE)) {
    add(text.slice(from, found.index));
    from = found.index + found[0].length;
    const [, params, between, final] = found;
    if (final !== "m" || between !== "" || !/^[0-9;]*$/.test(params ?? "")) continue;
    const codes = params === "" ? [0] : params!.split(";").map((code) => Number(code || 0));
    for (let at = 0; at < codes.length; at++) {
      const code = codes[at]!;
      if (code === 0) [bold, colour] = [false, null];
      else if (code === 1) bold = true;
      else if (code === 22) bold = false;
      else if (code === 39) colour = null;
      else if (code in COLOURS) colour = COLOURS[code]!;
      else if (code === 38 || code === 48 || code === 58) {
        at += codes[at + 1] === 5 ? 2 : codes[at + 1] === 2 ? 4 : 0;
      }
    }
  }
  add(text.slice(from));
  return runs;
}

/** A toggle's position, read by comparing its row with its two payloads
 *  (ADR-0087 decision 4): its default where there is no row (#939), and
 *  `null` where there is neither or the row is neither payload. */
export function togglePosition(
  spec: WidgetSpec,
  row: string | undefined,
): "on" | "off" | null {
  if (row === undefined) {
    return spec.default === "on" || spec.default === "off" ? spec.default : null;
  }
  if (row === spec.on) return "on";
  if (row === spec.off) return "off";
  return null;
}

/** What a press on a widget publishes: the payload raw, as typed, on the
 *  widget's own topic, and whether the broker keeps it. */
export interface WidgetPress {
  topic: string;
  payload: string;
  retain: boolean;
}

/**
 * What a press on a widget sends, `row` being what its topic last carried:
 * a button its payload, once and not kept, being an event; a toggle the
 * other position's payload, kept, being the position — and `on` where it
 * shows neither, there being no other position to go to. A text widget is
 * not pressed (ADR-0087).
 */
export function widgetPress(
  name: string,
  spec: WidgetSpec,
  row: string | undefined,
): WidgetPress | null {
  const topic = widgetTopic(spec.kind, name);
  if (spec.kind === "button") return { topic, payload: spec.payload ?? "", retain: false };
  if (spec.kind !== "toggle") return null;
  const payload = togglePosition(spec, row) === "on" ? spec.off : spec.on;
  return { topic, payload: payload ?? "", retain: true };
}
