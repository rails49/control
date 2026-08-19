// @vitest-environment happy-dom

/**
 * What the band says about the drawing itself: it derives, or it does not
 * (#91, ADR-0024).
 *
 * The canvas is where you find out where, so the shell's whole job here is to
 * hand the band one fact off the review and to stop handing it the moment the
 * drawing derives again. A DOM test of the shell, mounted the way
 * `refusals.test.ts` mounts it, because the fact crosses two components.
 */

import { beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-editor.js";
import type { Drawing } from "../src/model/drawing.js";
import type { Editor } from "../src/model/editor.js";
import type { Review } from "../src/model/store.js";
import type { TcEditor } from "../src/ui/tc-editor.js";
import type { TcHeader } from "../src/ui/tc-header.js";

/** A drawing the store is happy with: nothing to report. */
const CLEAN: Review = {
  red_pins: [],
  unpaired_portals: [],
  junctions: [],
  joints: [],
  motor_faults: [],
  layout: null,
  explain: null,
  refused: null,
  offending: [],
};

/** What derivation came back with over a way it refused (#93). */
const REFUSED: Review = {
  ...CLEAN,
  refused: "the way out of 'b1' leads back into 'b1'",
  offending: [{ ends: ["b1.a", "b1.b"], way: [["sw1", "toe"]] }],
};

/** What `/review` answers with, swapped per test. */
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

/** A mounted editor holding `symbols`, wired to nothing. */
async function mounted(symbols: Drawing["symbols"]) {
  const shell = document.createElement("tc-editor");
  document.body.append(shell);
  await shell.updateComplete;
  const session = (shell as unknown as { editor: Editor }).editor;
  session.reset({ drawing: "gotthard", symbols, wires: [] });
  return shell;
}

/** One turnout and one block, neither overlapping the other. */
const APART: Drawing["symbols"] = {
  sw1: { kind: "turnout", at: [0, 0] },
  b1: { kind: "block", at: [4, 0] },
};

/** Let the review in flight settle, then let Lit paint what it said. */
async function settled(shell: TcEditor): Promise<void> {
  for (let turn = 0; turn < 5; turn++) await Promise.resolve();
  await shell.updateComplete;
  await band(shell).updateComplete;
}

function band(shell: TcEditor): TcHeader {
  return shell.renderRoot.querySelector("tc-header")!;
}

/** What the band's indicator reads, or `null` while it is clean. */
function indicator(shell: TcEditor): string | null {
  const mark = band(shell).renderRoot.querySelector(".refused");
  return mark === null ? null : mark.textContent!.trim();
}

/** An edit of the drawing, as the canvas reports one. */
function edit(shell: TcEditor): void {
  shell.renderRoot.querySelector("tc-canvas")!.dispatchEvent(new CustomEvent("edit"));
}

describe("what the band says about the drawing", () => {
  it("marks a drawing derivation refused", async () => {
    const shell = await mounted(APART);

    answer = () => Promise.resolve(REFUSED);
    edit(shell);
    await settled(shell);

    expect(indicator(shell)).toBe("does not derive");
  });

  it("clears as soon as an edit derives again", async () => {
    const shell = await mounted(APART);
    answer = () => Promise.resolve(REFUSED);
    edit(shell);
    await settled(shell);

    answer = () => Promise.resolve(CLEAN);
    edit(shell);
    await settled(shell);

    expect(indicator(shell)).toBeNull();
  });

  /** An overlap is cosmetic and derives fine, so it wears the quieter mark on
   *  the canvas (#92) and leaves the band clean. */
  it("stays clean where two symbols share a square", async () => {
    const shell = await mounted({
      sw1: { kind: "turnout", at: [0, 0] },
      sw2: { kind: "turnout", at: [0, 0] },
    });

    edit(shell);
    await settled(shell);

    expect(indicator(shell)).toBeNull();
  });

  /** A turnout with no address derives as well: a valid layout nobody can
   *  drive yet, marked on the canvas in that same quiet weight (#96). */
  it("stays clean where a turnout carries no address", async () => {
    const shell = await mounted({ sw1: { kind: "turnout", at: [0, 0] } });

    edit(shell);
    await settled(shell);

    expect(indicator(shell)).toBeNull();
  });

  /** One is the author's to fix and the other is not, so the store going quiet
   *  neither raises the indicator nor takes it down. */
  it("shows beside a store that stops answering", async () => {
    const shell = await mounted(APART);
    answer = () => Promise.resolve(REFUSED);
    edit(shell);
    await settled(shell);

    answer = () => Promise.reject(new Error("no store"));
    edit(shell);
    await settled(shell);

    expect(indicator(shell)).toBe("does not derive");
    expect(band(shell).trouble).toContain("no store");
  });
});
