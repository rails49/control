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

import { afterEach, beforeAll, expect, test } from "vitest";
import "@shoelace-style/shoelace/dist/components/input/input.js";

import "../src/ui/tc-editor.js";
import type { Drawing } from "../src/model/drawing.js";
import type { Editor } from "../src/model/editor.js";
import type { TcCanvas } from "../src/ui/tc-canvas.js";
import type { TcMenubar } from "../src/ui/tc-menubar.js";

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

// A shell listens on the window for as long as it is in the page, so one left
// behind would answer the next test's keystrokes too — and answer them with no
// menu down, which is the very thing under test here.
afterEach(() => {
  document.body.replaceChildren();
});

/** A mounted editor holding one selected turnout, and a Shoelace input to
 *  type into, standing in for the properties dialog's name field. */
async function mounted(): Promise<{
  shell: HTMLElement & { updateComplete: Promise<boolean>; renderRoot: ParentNode };
  session: Editor;
  field: HTMLInputElement;
}> {
  const shell = document.createElement("tc-editor");
  document.body.append(shell);
  await shell.updateComplete;
  const session = (shell as unknown as { editor: Editor }).editor;
  session.reset(structuredClone(DRAWING));
  session.select(["sw1"]);

  const control = document.createElement("sl-input");
  document.body.append(control);
  await control.updateComplete;
  return { shell, session, field: control.shadowRoot!.querySelector("input")! };
}

/** The bar's `File` menu, put down the way a pointer puts it down. */
async function opened(shell: {
  renderRoot: ParentNode;
}): Promise<TcMenubar> {
  const bar = shell.renderRoot.querySelector("tc-menubar")!;
  await bar.updateComplete;
  const titles = [...bar.renderRoot.querySelectorAll("button.title")];
  (titles.find((one) => one.textContent!.trim() === "File") as HTMLElement).click();
  await bar.updateComplete;
  return bar;
}

/** How often the canvas was asked to change the view. The zoom keys say
 *  nothing about the document, so this is what says they arrived. */
function views(shell: { renderRoot: ParentNode }): () => number {
  const canvas = shell.renderRoot.querySelector<TcCanvas>("tc-canvas")!;
  let asked = 0;
  canvas.zoom = () => {
    asked += 1;
  };
  canvas.fit = () => {
    asked += 1;
  };
  return () => asked;
}

function key(
  target: EventTarget,
  name: string,
  held: { meta?: boolean; shift?: boolean } = {},
): KeyboardEvent {
  const event = new KeyboardEvent("keydown", {
    key: name,
    metaKey: held.meta ?? false,
    shiftKey: held.shift ?? false,
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

/**
 * The same bug as a key typed into a dialog field reaching the canvas, wearing
 * a menu: with `File` down, `r` would rotate the selection behind it and
 * Escape would clear it rather than closing the menu (#85).
 */
test("the canvas keys do not reach it while a menu is down", async () => {
  const { shell, session } = await mounted();
  const asked = views(shell);
  await opened(shell);
  const was = structuredClone(session.drawing.symbols["sw1"]);

  for (const name of ["r", "f", "Delete", "Backspace", "0", "+", "-"]) {
    key(window, name);
  }

  expect(session.drawing.symbols["sw1"]).toEqual(was);
  expect(asked()).toBe(0);
});

test("escape closes the menu rather than clearing the selection", async () => {
  const { shell, session } = await mounted();
  const bar = await opened(shell);

  key(window, "Escape");
  await bar.updateComplete;

  expect(bar.renderRoot.querySelector("menu")).toBeNull();
  expect([...session.selection]).toEqual(["sw1"]);
});

/**
 * The other half of the rule: a shortcut is not a bare key. `File` prints
 * `Save ⌘S` beside the item, so the press is that item — it takes the menu up
 * and runs, rather than being swallowed under the menu that just taught it
 * (#85).
 */
test("a shortcut printed in the menu runs the command and takes the menu up", async () => {
  const { shell, session } = await mounted();
  key(window, "r");
  const turned = structuredClone(session.drawing.symbols["sw1"]);
  const bar = await opened(shell);

  const event = key(window, "z", { meta: true });
  await bar.updateComplete;

  expect(event.defaultPrevented).toBe(true);
  expect(session.drawing.symbols["sw1"]).not.toEqual(turned);
  expect(bar.renderRoot.querySelector("menu")).toBeNull();
});

/** ⌘S under an open `File` is the editor's save, so Chrome's "Save page as…"
 *  never opens over the app. */
test("save's key is taken from the browser while a menu is down", async () => {
  const { shell } = await mounted();
  await opened(shell);

  const event = key(window, "s", { meta: true });

  expect(event.defaultPrevented).toBe(true);
});

test("the same keys reach the canvas again once the menu is up", async () => {
  const { shell, session } = await mounted();
  const bar = await opened(shell);
  key(window, "Escape");
  await bar.updateComplete;

  key(window, "r");

  expect(session.drawing.symbols["sw1"]!.rot).toBe(90);
});
