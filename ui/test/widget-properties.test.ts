// @vitest-environment happy-dom

/**
 * What a widget's properties dialog holds (EDITOR.md#properties, ADR-0087):
 * the name, the topic it ends, a text widget's words, and the kind's own
 * text and a toggle's default position (#939). A DOM test at the dialog's own seam, as `properties.test.ts` is for a
 * symbol's.
 */

import { describe, expect, it } from "vitest";

import "../src/ui/tc-widget-properties.js";
import type {
  TcWidgetProperties,
  WidgetProperties,
} from "../src/ui/tc-widget-properties.js";
import type { WidgetSpec } from "../src/model/drawing.js";
import type SlInput from "@shoelace-style/shoelace/dist/components/input/input.js";

async function opened(
  name: string,
  spec: WidgetSpec,
  taken: readonly string[] = [name],
): Promise<TcWidgetProperties> {
  const dialog = document.createElement("tc-widget-properties");
  dialog.editing = { name, spec };
  dialog.taken = taken;
  document.body.append(dialog);
  await dialog.updateComplete;
  return dialog;
}

function fields(dialog: TcWidgetProperties): string[] {
  return [...dialog.renderRoot.querySelectorAll<SlInput>("sl-input, sl-select")].map(
    (input) => input.label,
  );
}

function field(dialog: TcWidgetProperties, label: string): SlInput {
  return [...dialog.renderRoot.querySelectorAll<SlInput>("sl-input")].find(
    (input) => input.label === label,
  )!;
}

/** A choice made in one of the dialog's selects. */
async function chosen(
  dialog: TcWidgetProperties,
  label: string,
  value: string,
): Promise<void> {
  const select = [...dialog.renderRoot.querySelectorAll<SlInput>("sl-select")].find(
    (one) => one.label === label,
  )!;
  select.value = value;
  select.dispatchEvent(new CustomEvent("sl-change"));
  await dialog.updateComplete;
}

async function typed(
  dialog: TcWidgetProperties,
  label: string,
  value: string,
): Promise<void> {
  const input = field(dialog, label);
  input.value = value;
  input.dispatchEvent(new CustomEvent("sl-input"));
  await dialog.updateComplete;
}

/** Press Apply, and answer with every `widget-properties` event it emitted —
 *  none where the dialog refused what it is holding. */
function applying(dialog: TcWidgetProperties): WidgetProperties[] {
  const handed: WidgetProperties[] = [];
  dialog.addEventListener("widget-properties", (event) =>
    handed.push((event as CustomEvent<WidgetProperties>).detail),
  );
  const buttons = [...dialog.renderRoot.querySelectorAll("sl-button")];
  (buttons.find((one) => one.textContent!.trim() === "Apply") as HTMLElement).click();
  return handed;
}

const TEXT: WidgetSpec = { kind: "text", at: [2, 1] };
const BUTTON: WidgetSpec = { kind: "button", at: [2, 3], payload: "button1" };
const TOGGLE: WidgetSpec = { kind: "toggle", at: [2, 5], on: "on", off: "off" };

describe("the fields", () => {
  it("offers each kind its own fields beside the name and topic, and no size", () => {
    return Promise.all([
      opened("text1", TEXT).then((dialog) =>
        expect(fields(dialog)).toEqual([
          "Name",
          "Topic",
          "Text size",
          "Alignment",
          "Default",
        ]),
      ),
      opened("button1", BUTTON).then((dialog) =>
        expect(fields(dialog)).toEqual(["Name", "Topic", "Payload"]),
      ),
      opened("toggle1", TOGGLE).then((dialog) =>
        expect(fields(dialog)).toEqual(["Name", "Topic", "On", "Off", "Default"]),
      ),
    ]);
  });

  it("shows the whole topic, read-only", async () => {
    const dialog = await opened("toggle1", TOGGLE);
    const topic = field(dialog, "Topic");
    expect(topic.value).toBe("tc49/ui/state/toggle/toggle1");
    expect(topic.readonly).toBe(true);
  });
});

describe("a rename", () => {
  it("shows the new topic as it is typed", async () => {
    const dialog = await opened("button1", BUTTON);
    await typed(dialog, "Name", "horn");
    expect(field(dialog, "Topic").value).toBe("tc49/ui/button/horn");
  });

  it("is handed back with what else was typed", async () => {
    const dialog = await opened("button1", BUTTON);
    await typed(dialog, "Name", "horn");
    await typed(dialog, "Payload", "toot");
    expect(applying(dialog)).toEqual([
      { was: "button1", name: "horn", spec: { ...BUTTON, payload: "toot" } },
    ]);
  });

  it("is refused onto a name another widget has, and says so beside it", async () => {
    const dialog = await opened("button1", BUTTON, ["text1", "button1"]);
    await typed(dialog, "Name", "text1");
    expect(field(dialog, "Name").helpText).toBe("'text1' is already taken");
    expect(field(dialog, "Name").classList.contains("refused")).toBe(true);
    expect(applying(dialog)).toEqual([]);
  });

  it("is refused onto a name that is not one topic level", async () => {
    const dialog = await opened("text1", TEXT);
    await typed(dialog, "Name", "track/current");
    expect(applying(dialog)).toEqual([]);
  });
});

describe("what the store would refuse", () => {
  it("refuses a toggle whose on and off are the same", async () => {
    const dialog = await opened("toggle1", TOGGLE);
    await typed(dialog, "Off", "on");
    expect(field(dialog, "Off").helpText).toBe("on and off must differ");
    expect(applying(dialog)).toEqual([]);
  });

  it("writes no empty default", async () => {
    const dialog = await opened("text1", { ...TEXT, default: "—" });
    await typed(dialog, "Default", "");
    expect(applying(dialog)).toEqual([
      { was: "text1", name: "text1", spec: { ...TEXT } },
    ]);
  });

  it("writes the toggle's default chosen, and none for none", async () => {
    const dialog = await opened("toggle1", TOGGLE);
    await chosen(dialog, "Default", "on");
    expect(applying(dialog)).toEqual([
      { was: "toggle1", name: "toggle1", spec: { ...TOGGLE, default: "on" } },
    ]);
    const again = await opened("toggle1", { ...TOGGLE, default: "off" });
    await chosen(again, "Default", "none");
    expect(applying(again)).toEqual([
      { was: "toggle1", name: "toggle1", spec: { ...TOGGLE } },
    ]);
  });
});
