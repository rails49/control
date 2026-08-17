// @vitest-environment happy-dom

/**
 * The editor's shortcuts against the controls it puts on screen.
 *
 * The one test that needs a DOM. `tc-editor` listens on the window, so every
 * keystroke anywhere on the page reaches it, and a Shoelace control keeps its
 * native input in its own shadow root: the guard that tells a name being typed
 * from `r` meaning rotate is about shadow boundaries, and nothing short of a
 * real one exercises it.
 */

import { beforeAll, expect, test } from "vitest";
import "@shoelace-style/shoelace/dist/components/input/input.js";

import "../src/ui/tc-editor.js";
import type { Drawing } from "../src/model/drawing.js";
import type { Editor } from "../src/model/editor.js";

/** One turnout, selected, the way the right-click that opens the properties
 *  dialog leaves it. */
const DRAWING: Drawing = {
  drawing: "one-turnout",
  symbols: { sw1: { kind: "turnout", at: [0, 0] } },
  wires: [],
};

beforeAll(() => {
  // The shell asks the store what it has the moment it is connected, and no
  // store is running here.
  globalThis.fetch = (() =>
    Promise.reject(new Error("no store"))) as typeof fetch;
});

/** A mounted editor holding one selected turnout, and a Shoelace input to
 *  type into, standing in for the properties dialog's name field. */
async function mounted(): Promise<{ session: Editor; field: HTMLInputElement }> {
  const shell = document.createElement("tc-editor");
  document.body.append(shell);
  await shell.updateComplete;
  const session = (shell as unknown as { editor: Editor }).editor;
  session.reset(structuredClone(DRAWING));
  session.select(["sw1"]);

  const control = document.createElement("sl-input");
  document.body.append(control);
  await control.updateComplete;
  return { session, field: control.shadowRoot!.querySelector("input")! };
}

function key(target: EventTarget, name: string): KeyboardEvent {
  const event = new KeyboardEvent("keydown", {
    key: name,
    bubbles: true,
    composed: true,
    cancelable: true,
  });
  target.dispatchEvent(event);
  return event;
}

test("a name typed into a control does not turn the selection", async () => {
  const { session, field } = await mounted();
  const was = structuredClone(session.drawing.symbols["sw1"]);

  for (const letter of "far_frog") key(field, letter);

  expect(session.drawing.symbols["sw1"]).toEqual(was);
});

test("backspace in a control neither deletes the symbol nor is swallowed", async () => {
  const { session, field } = await mounted();

  const event = key(field, "Backspace");

  expect(session.drawing.symbols["sw1"]).toBeDefined();
  expect(event.defaultPrevented).toBe(false);
});

test("the same keys still reach the canvas from outside a control", async () => {
  const { session } = await mounted();

  key(window, "r");

  expect(session.drawing.symbols["sw1"]!.rot).toBe(90);
});
