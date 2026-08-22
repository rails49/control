// @vitest-environment happy-dom

/**
 * What the band says about the drawing itself: it derives, or it does not
 * (#91, ADR-0024).
 *
 * The rule is `Filing`'s and `filing.test.ts` drives it — off the store's
 * refusal and nothing else, an overlap and a missing address deriving fine, a
 * store that goes quiet leaving the last answer standing. What is left here is
 * the one thing a DOM test can say that the module's cannot: the mark the
 * operator sees is the fact the module holds, carried across two components.
 */

import { beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-app.js";
import type { Drawing } from "../src/model/drawing.js";
import type { Review } from "../src/model/store.js";
import type { TcApp } from "../src/ui/tc-app.js";
import type { TcHeader } from "../src/ui/tc-header.js";
import {
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
  session(shell).reset({ drawing: "gotthard", symbols, wires: [] });
  return shell;
}

/** One turnout and one block, neither overlapping the other. */
const APART: Drawing["symbols"] = {
  sw1: { kind: "turnout", at: [0, 0] },
  b1: { kind: "block", at: [4, 0] },
};

function band(shell: TcApp): TcHeader {
  return shell.renderRoot.querySelector("tc-header")!;
}

/** What the band's indicator reads, or `null` while it is clean. */
function indicator(shell: TcApp): string | null {
  const mark = band(shell).renderRoot.querySelector(".refused");
  return mark === null ? null : mark.textContent!.trim();
}

/** An edit of the drawing, as the canvas reports one. */
function edit(shell: TcApp): void {
  edited(shell);
}

describe("what the band says about the drawing", () => {
  it("marks a drawing derivation refused", async () => {
    const shell = await holding(APART);

    store.review = () => Promise.resolve(REFUSED);
    edit(shell);
    await settled(shell);

    expect(indicator(shell)).toBe("does not derive");
  });
});
