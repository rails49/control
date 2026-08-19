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

/** The properties dialog applying a name, which is where a rename is refused. */
function rename(shell: TcEditor, was: string, name: string): void {
  shell.renderRoot.querySelector("tc-properties")!.dispatchEvent(
    new CustomEvent("properties", {
      detail: { was, name, spec: { kind: "turnout", at: [0, 0] } },
    }),
  );
}

describe("a name the drawing will not take", () => {
  it("is listed, being the author's own mistake", async () => {
    const { shell } = await mounted();

    rename(shell, "sw1", "b1");
    await settled(shell);

    expect(listed(shell)).toEqual(["'b1' is not a name this drawing can take"]);
  });

  /** It used to share `trouble`, which every review cleared. Split off without
   *  that clearing, a refusal stayed listed against a drawing that no longer
   *  had the problem — and kept the panel from ever reading clean again. */
  it("stops being listed once an edit is accepted", async () => {
    const { shell } = await mounted();
    rename(shell, "sw1", "b1");
    await settled(shell);

    shell.renderRoot.querySelector("tc-canvas")!.dispatchEvent(new CustomEvent("edit"));
    await settled(shell);

    expect(listed(shell)).toEqual(["Every pin holds its wires."]);
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
