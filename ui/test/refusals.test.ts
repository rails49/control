// @vitest-environment happy-dom

/**
 * A name the editor will not take, and where the refusal is shown.
 *
 * Every other fault is marked on the drawing (ADR-0024), so a name is the one
 * thing left that has to be said in words — and which of the two places says
 * it is behaviour, not layout: a symbol's name is refused in the dialog it was
 * typed in, and a drawing's own name in the band. This is the first of the
 * two; a drawing's name is `Filing`'s and is refused in `filing.test.ts`. A
 * DOM test because it crosses two components; the shell mounts under happy-dom
 * the way `keys.test.ts` mounts it.
 */

import { beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-app.js";
import type { Drawing } from "../src/model/drawing.js";
import type { Editor } from "../src/model/editor.js";
import type { TcApp } from "../src/ui/tc-app.js";
import type { TcHeader } from "../src/ui/tc-header.js";
import type { TcProperties } from "../src/ui/tc-properties.js";
import type SlInput from "@shoelace-style/shoelace/dist/components/input/input.js";
import { inside, mounted, serving, session, settled } from "./support/shell.js";

/** Two symbols, so a rename onto a taken name has something to collide with. */
const DRAWING: Drawing = {
  drawing: "two-symbols",
  symbols: { sw1: { kind: "turnout", at: [0, 0] }, b1: { kind: "block", at: [4, 0] } },
  wires: [],
};

beforeEach(() => {
  serving();
});

/** A mounted editor holding the drawing above, with the review it asks for on
 *  load already answered: that answer clears the band, so a test that raced it
 *  would be testing the timing and not the refusal. */
async function holding(): Promise<{ shell: TcApp; editing: Editor }> {
  const shell = await mounted();
  const editing = session(shell);
  editing.reset(structuredClone(DRAWING));
  return { shell, editing };
}

/** The band across the top, which is where the editor says what it could not
 *  do. */
function band(shell: TcApp): TcHeader {
  return shell.renderRoot.querySelector("tc-header")!;
}

/** The properties dialog, opened on the one selected symbol the way the
 *  `Properties…` command opens it. */
async function opened(shell: TcApp, editing: Editor, name: string) {
  editing.select([name]);
  shell.renderRoot
    .querySelector("tc-menubar")!
    .dispatchEvent(new CustomEvent("command", { detail: "properties" }));
  await settled(shell);
  const dialog = inside(shell, "tc-properties") as TcProperties;
  await dialog.updateComplete;
  return dialog;
}

/** The dialog's name field, as it reads now. */
function field(dialog: TcProperties): SlInput {
  return dialog.renderRoot.querySelector<SlInput>("sl-input")!;
}

/** Type a name into it, which is the one gesture that makes a collision. */
async function typed(
  dialog: TcProperties,
  into: SlInput,
  name: string,
): Promise<void> {
  into.value = name;
  into.dispatchEvent(new CustomEvent("sl-input"));
  await dialog.updateComplete;
}

/** Press Apply. */
async function apply(dialog: TcProperties): Promise<void> {
  const buttons = [...dialog.renderRoot.querySelectorAll("sl-button")];
  (buttons.find((one) => one.textContent!.trim() === "Apply") as HTMLElement).click();
  await dialog.updateComplete;
}

/**
 * A name the drawing already has, typed where names are typed (ADR-0023).
 *
 * It used to close the dialog, discard the edit, and report it in a panel
 * across the screen, which told the author about a keystroke they had just
 * made. Now the dialog refuses and stays open, and nothing else says anything.
 */
describe("a name the drawing will not take", () => {
  it("is refused with the dialog still open", async () => {
    const { shell, editing } = await holding();
    const dialog = await opened(shell, editing, "b1");

    await typed(dialog, field(dialog), "sw1");
    await apply(dialog);
    await settled(shell);

    expect(dialog.renderRoot.querySelector("sl-dialog")).not.toBeNull();
    expect(editing.drawing.symbols).toHaveProperty("b1");
  });

  it("stays in the field, to be edited rather than retyped", async () => {
    const { shell, editing } = await holding();
    const dialog = await opened(shell, editing, "b1");

    await typed(dialog, field(dialog), "sw1");
    await apply(dialog);

    expect(field(dialog).value).toBe("sw1");
  });

  it("says which name is taken, beside the field it was typed in", async () => {
    const { shell, editing } = await holding();
    const dialog = await opened(shell, editing, "b1");

    await typed(dialog, field(dialog), "sw1");

    expect(field(dialog).getAttribute("help-text")).toContain(
      "'sw1' is already taken",
    );
  });

  it("refuses a name that is not a legal key the same way", async () => {
    const { shell, editing } = await holding();
    const dialog = await opened(shell, editing, "b1");

    await typed(dialog, field(dialog), "b1.A");
    await apply(dialog);

    expect(dialog.renderRoot.querySelector("sl-dialog")).not.toBeNull();
    expect(field(dialog).getAttribute("help-text")).toContain("cannot name");
  });

  /** The dialog holds the refusal, so nothing else reports it: a symbol name
   *  read across the screen is what ADR-0023 took away, and the band would be
   *  the same mistake in a new place. */
  it("says nothing in the band, which is not where a symbol is named", async () => {
    const { shell, editing } = await holding();
    const dialog = await opened(shell, editing, "b1");

    await typed(dialog, field(dialog), "sw1");
    await apply(dialog);
    await settled(shell);

    expect(band(shell).trouble).toBeNull();
  });

  /** A refusal never reaches the document, so there is no snapshot of it to
   *  undo back past. */
  it("leaves nothing behind for undo to take back", async () => {
    const { shell, editing } = await holding();
    const dialog = await opened(shell, editing, "b1");

    await typed(dialog, field(dialog), "sw1");
    await apply(dialog);

    expect(editing.canUndo).toBe(false);
  });

  it("closes on a name the drawing can take, having renamed the symbol", async () => {
    const { shell, editing } = await holding();
    const dialog = await opened(shell, editing, "b1");

    await typed(dialog, field(dialog), "station_c_1");
    await apply(dialog);
    await settled(shell);

    expect(Object.keys(editing.drawing.symbols).sort()).toEqual([
      "station_c_1",
      "sw1",
    ]);
  });
});
