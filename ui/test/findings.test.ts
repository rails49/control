// @vitest-environment happy-dom

/**
 * What the findings panel lists, and for how long.
 *
 * The panel is where you look for what to fix in the drawing (#84), so what
 * lands there and what does not is behaviour, not layout — and a finding that
 * outlives what caused it is as wrong as one that never appears. A DOM test
 * because the split is between two pieces of the shell's own state; the shell
 * mounts under happy-dom the way `keys.test.ts` mounts it.
 */

import { beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-editor.js";
import type { Drawing } from "../src/model/drawing.js";
import type { Editor } from "../src/model/editor.js";
import type { Review } from "../src/model/store.js";
import type { TcEditor } from "../src/ui/tc-editor.js";
import type { TcProperties } from "../src/ui/tc-properties.js";
import type SlInput from "@shoelace-style/shoelace/dist/components/input/input.js";

/** Two symbols, so a rename onto a taken name has something to collide with. */
const DRAWING: Drawing = {
  drawing: "two-symbols",
  symbols: { sw1: { kind: "turnout", at: [0, 0] }, b1: { kind: "block", at: [4, 0] } },
  wires: [],
};

/** A drawing the store is happy with: nothing to report. */
const CLEAN: Review = {
  red_pins: [],
  unpaired_portals: [],
  junctions: [],
  joints: [],
  layout: null,
  explain: null,
  refused: null,
  offending: [],
};

/** What `/review` answers with, swapped per test. Rejecting stands for a store
 *  that is not running. */
let answer: () => Promise<unknown>;

beforeEach(() => {
  answer = () => Promise.resolve(CLEAN);
  globalThis.fetch = ((path: string) => {
    const payload = path === "/review" ? answer() : Promise.resolve({ drawings: [] });
    return payload.then(
      (body) => ({ ok: true, json: () => Promise.resolve(body) }) as unknown as Response,
    );
  }) as unknown as typeof fetch;
});

/** A mounted editor holding the drawing above. */
async function mounted() {
  const shell = document.createElement("tc-editor");
  document.body.append(shell);
  await shell.updateComplete;
  const session = (shell as unknown as { editor: Editor }).editor;
  session.reset(structuredClone(DRAWING));
  return { shell, session };
}

/** The lines the findings panel is showing. */
function listed(shell: TcEditor): string[] {
  return [...shell.renderRoot.querySelectorAll(".findings p")].map((line) =>
    line.textContent!.trim(),
  );
}

/** Let the review in flight settle, then let Lit paint what it said. */
async function settled(shell: { updateComplete: Promise<boolean> }): Promise<void> {
  for (let turn = 0; turn < 5; turn++) await Promise.resolve();
  await shell.updateComplete;
}

/** The properties dialog, opened on the one selected symbol the way the
 *  `Properties…` command opens it. */
async function opened(shell: TcEditor, session: Editor, name: string) {
  session.select([name]);
  shell.renderRoot
    .querySelector("tc-menubar")!
    .dispatchEvent(new CustomEvent("command", { detail: "properties" }));
  await settled(shell);
  const dialog = shell.renderRoot.querySelector("tc-properties")!;
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
 * made. Now the dialog refuses and stays open, and the findings say nothing.
 */
describe("a name the drawing will not take", () => {
  it("is refused with the dialog still open", async () => {
    const { shell, session } = await mounted();
    const dialog = await opened(shell, session, "b1");

    await typed(dialog, field(dialog), "sw1");
    await apply(dialog);
    await settled(shell);

    expect(dialog.renderRoot.querySelector("sl-dialog")).not.toBeNull();
    expect(session.drawing.symbols).toHaveProperty("b1");
  });

  it("stays in the field, to be edited rather than retyped", async () => {
    const { shell, session } = await mounted();
    const dialog = await opened(shell, session, "b1");

    await typed(dialog, field(dialog), "sw1");
    await apply(dialog);

    expect(field(dialog).value).toBe("sw1");
  });

  it("says which name is taken, beside the field it was typed in", async () => {
    const { shell, session } = await mounted();
    const dialog = await opened(shell, session, "b1");

    await typed(dialog, field(dialog), "sw1");

    expect(field(dialog).getAttribute("help-text")).toContain(
      "'sw1' is already taken",
    );
  });

  it("refuses a name that is not a legal key the same way", async () => {
    const { shell, session } = await mounted();
    const dialog = await opened(shell, session, "b1");

    await typed(dialog, field(dialog), "b1.A");
    await apply(dialog);

    expect(dialog.renderRoot.querySelector("sl-dialog")).not.toBeNull();
    expect(field(dialog).getAttribute("help-text")).toContain("cannot name");
  });

  it("puts nothing in the findings, which are about the drawing", async () => {
    const { shell, session } = await mounted();
    const dialog = await opened(shell, session, "b1");

    await typed(dialog, field(dialog), "sw1");
    await apply(dialog);
    await settled(shell);

    expect(listed(shell)).toEqual(["Every pin holds its wires."]);
  });

  it("closes on a name the drawing can take, having renamed the symbol", async () => {
    const { shell, session } = await mounted();
    const dialog = await opened(shell, session, "b1");

    await typed(dialog, field(dialog), "claro_1");
    await apply(dialog);
    await settled(shell);

    expect(Object.keys(session.drawing.symbols).sort()).toEqual([
      "claro_1",
      "sw1",
    ]);
    expect(listed(shell)).toEqual(["Every pin holds its wires."]);
  });
});

/** A drawing's own name is still asked for with a prompt and still refused in
 *  the panel: it is not typed in a dialog that could hold it open. */
describe("a name no drawing can wear", () => {
  it("is listed, being the author's own mistake", async () => {
    const { shell } = await mounted();
    window.prompt = () => "a/b";

    shell.renderRoot
      .querySelector("tc-menubar")!
      .dispatchEvent(new CustomEvent("command", { detail: "new" }));
    await settled(shell);

    expect(listed(shell)).toEqual(["'a/b' cannot name a file"]);
  });
});

describe("a store that is not answering", () => {
  /** Not one of the author's mistakes, so it reads in the band instead — and
   *  it used to be drawn *instead of* the findings, hiding every one of them
   *  until the next successful review. */
  it("is not listed among the findings", async () => {
    const { shell } = await mounted();

    answer = () => Promise.reject(new Error("no store"));
    shell.renderRoot.querySelector("tc-canvas")!.dispatchEvent(new CustomEvent("edit"));
    await settled(shell);

    expect(listed(shell)).toEqual(["Every pin holds its wires."]);
    expect(shell.renderRoot.querySelector("tc-header")!.trouble).toContain("no store");
  });
});
