// @vitest-environment happy-dom

/**
 * What the band says about the drawing itself: it is valid, or it is not
 * (#91, ADR-0024, #892).
 *
 * The rule is `Filing`'s and `filing.test.ts` drives it — off the store's
 * refusal and nothing else, an overlap and a missing address being valid, a
 * store that goes quiet leaving the last answer standing. What is left here is
 * the one thing a DOM test can say that the module's cannot: the mark the
 * operator sees is the fact the module holds, carried across two components.
 */

import { beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-app.js";
import type { Drawing } from "../src/model/drawing.js";
import type { Review } from "../src/model/store.js";
import type { TcApp } from "../src/ui/tc-app.js";
import {
  band,
  chips,
  CLEAN,
  edited,
  mounted,
  serving,
  session,
  settled,
  type Answers,
} from "./support/shell.js";

/** What derivation came back with over a way it refused (#93). */
const REFUSED: Review = {
  ...CLEAN,
  refused: "the way out of 'b1' leads back into 'b1'",
  offending: [{ ends: ["b1.a", "b1.b"], way: [["sw1", "toe"]] }],
};

/** The store the shell is wired to, its `/review` answer swapped per test. */
let store: Answers;

beforeEach(() => {
  store = serving();
});

/** A mounted editor holding `symbols`, wired to nothing. */
async function holding(symbols: Drawing["symbols"]): Promise<TcApp> {
  const shell = await mounted();
  session(shell).reset({ drawing: "reversing-loops", symbols, wires: [] });
  return shell;
}

/** One turnout and one block, neither overlapping the other. */
const APART: Drawing["symbols"] = {
  sw1: { kind: "turnout", at: [0, 0] },
  b1: { kind: "block", at: [4, 0] },
};

/** The band's indicator, or `null` while it is clean. */
function indicator(shell: TcApp): Element | null {
  const all = [...band(shell).querySelectorAll("look-chip")];
  return all.find((one) => one.textContent!.trim() === "invalid drawing") ?? null;
}

/** An edit of the drawing, as the canvas reports one. */
function edit(shell: TcApp): void {
  edited(shell);
}

describe("what the band says about the drawing", () => {
  it("marks a drawing the store refused as invalid, its title the refusal", async () => {
    const shell = await holding(APART);

    store.review = () => Promise.resolve(REFUSED);
    edit(shell);
    await settled(shell);

    expect(chips(shell)).toContain("invalid drawing");
    expect(indicator(shell)?.getAttribute("title")).toBe(REFUSED.refused);
  });
});
