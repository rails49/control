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

import { afterEach, beforeEach, expect, test } from "vitest";
import "@shoelace-style/shoelace/dist/components/input/input.js";

import "../src/ui/tc-app.js";
import type { Drawing } from "../src/model/drawing.js";
import type { Editor } from "../src/model/editor.js";
import type { TcCanvas } from "../src/ui/tc-canvas.js";
import type { TcApp } from "../src/ui/tc-app.js";
import { inside, mounted, serving, session } from "./support/shell.js";

/** One turnout, selected, the way the right-click that opens the properties
 *  dialog leaves it. */
const DRAWING: Drawing = {
  drawing: "one-turnout",
  symbols: { sw1: { kind: "turnout", at: [0, 0] } },
  wires: [],
};

beforeEach(() => {
  // The shell asks the store what it has the moment it is connected, and no
  // store is running here.
  serving({ broken: new Error("no store") });
});

// A shell listens on the window for as long as it is in the page, so one left
// behind would answer the next test's keystrokes too.
afterEach(() => {
  document.body.replaceChildren();
});

/** A mounted editor holding one selected turnout, and a Shoelace input to
 *  type into, standing in for the properties dialog's name field. */
async function holding(): Promise<{
  shell: TcApp;
  editing: Editor;
  field: HTMLInputElement;
}> {
  const shell = await mounted();
  const editing = session(shell);
  editing.reset(structuredClone(DRAWING));
  editing.select(["sw1"]);

  const control = document.createElement("sl-input");
  document.body.append(control);
  await control.updateComplete;
  return { shell, editing, field: control.shadowRoot!.querySelector("input")! };
}

/** How often the canvas was asked to change the view. The zoom keys say
 *  nothing about the document, so this is what says they arrived. */
function views(shell: TcApp): () => number {
  const canvas = inside(shell, "tc-canvas") as TcCanvas;
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
  const { editing, field } = await holding();
  const was = structuredClone(editing.drawing.symbols["sw1"]);

  for (const letter of "far_frog") key(field, letter);

  expect(editing.drawing.symbols["sw1"]).toEqual(was);
});

test("backspace in a control neither deletes the symbol nor is swallowed", async () => {
  const { editing, field } = await holding();

  const event = key(field, "Backspace");

  expect(editing.drawing.symbols["sw1"]).toBeDefined();
  expect(event.defaultPrevented).toBe(false);
});

test("the same keys still reach the canvas from outside a control", async () => {
  const { editing } = await holding();

  key(window, "r");

  expect(editing.drawing.symbols["sw1"]!.rot).toBe(90);
});

/**
 * Nothing on the rail comes down over the work, so there is no state in which
 * the keyboard belongs to the chrome (ADR-0064). What the bar's open menu used
 * to take — `r`, Escape, the zoom keys — the canvas keeps whatever the rail is
 * showing, and #85's rule that a shortcut is not a bare key survives as the
 * keys the browser is not allowed to have.
 */
test("the canvas keys reach it whatever the rail is showing", async () => {
  const { shell, editing } = await holding();
  const asked = views(shell);

  key(window, "r");
  for (const name of ["0", "+", "-"]) key(window, name);

  expect(editing.drawing.symbols["sw1"]!.rot).toBe(90);
  expect(asked()).toBe(3);
});

test("escape clears the selection, there being no menu to close first", async () => {
  const { shell, editing } = await holding();
  await shell.updateComplete;

  key(window, "Escape");

  expect([...editing.selection]).toEqual([]);
});

/** ⌘S is the editor's save, so Chrome's "Save page as…" never opens over the
 *  app. */
test("save's key is taken from the browser", async () => {
  await holding();

  const event = key(window, "s", { meta: true });

  expect(event.defaultPrevented).toBe(true);
});

/** ⌘Z is the editor's undo for the same reason. */
test("undo's key is taken from the browser and undoes the edit", async () => {
  const { editing } = await holding();
  key(window, "r");
  const turned = structuredClone(editing.drawing.symbols["sw1"]);

  const event = key(window, "z", { meta: true });

  expect(event.defaultPrevented).toBe(true);
  expect(editing.drawing.symbols["sw1"]).not.toEqual(turned);
});
