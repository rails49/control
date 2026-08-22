// @vitest-environment happy-dom

/**
 * The roster pane in the run view's half of the shell's left-pane slot (#169).
 *
 * Two halves. The pane itself works nothing out, so what is asked of it is
 * what it draws for the rows it is handed and what it says when it is handed
 * none. Then one walk of the path that fills it: a picture off the bus for
 * where the trains are, and the session's scenario for how long each is, which
 * is where the stock of a run is written down until the store serves a roster
 * ([#170](https://github.com/rails49/control/issues/170)).
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-roster.js";
import "../src/ui/tc-app.js";
import type { TcApp } from "../src/ui/tc-app.js";
import type { RosterRow, TcRoster } from "../src/ui/tc-roster.js";
import { running } from "./support/shell.js";
import { bridging, joined, said, unbridged } from "./support/session.js";

/** The pane, holding the rows it was handed. */
async function pane(trains: RosterRow[]): Promise<TcRoster> {
  const roster = document.createElement("tc-roster");
  roster.trains = trains;
  document.body.append(roster);
  await roster.updateComplete;
  return roster;
}

/** What the pane reads, one row at a time: the name, the length and where the
 *  train is. */
function rows(roster: TcRoster): string[][] {
  return [...roster.renderRoot.querySelectorAll("li")].map((row) =>
    [".name", ".length", ".where"].map(
      (part) => row.querySelector(part)!.textContent!.trim(),
    ),
  );
}

/** The pane the run view is drawing. */
function paneOf(shell: TcApp): TcRoster {
  return running(shell).renderRoot.querySelector("tc-roster")!;
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("what the pane lists", () => {
  it("gives each train its name, its length and the block it stands in", async () => {
    const roster = await pane([
      { train: "goods", block: "a", length: 400 },
      { train: "express", block: "b", length: 1100 },
    ]);
    expect(rows(roster)).toEqual([
      ["goods", "400", "a"],
      ["express", "1100", "b"],
    ]);
  });

  /** The order is the model's (`Panel.placed`), so the pane draws what it is
   *  handed and never sorts: two parties ordering the list is one of them
   *  reshuffling it under the reader. */
  it("keeps the order it was handed", async () => {
    const roster = await pane([
      { train: "z", block: "a", length: 1 },
      { train: "a", block: "b", length: 2 },
    ]);
    expect(rows(roster).map(([name]) => name)).toEqual(["z", "a"]);
  });

  /** A train between two blocks stands in none and is on the layout all the
   *  same, holding the transit that is taking it out of the last one. */
  it("says a crossing train stands in no block", async () => {
    const roster = await pane([{ train: "goods", block: null, length: 400 }]);
    expect(rows(roster)).toEqual([["goods", "400", "crossing"]]);
  });

  /** Nothing the page has read names the length of a train the run has, which
   *  is a blank rather than a nought: a train with no length is not one of
   *  length zero. */
  it("leaves the length blank where nothing names one", async () => {
    const roster = await pane([{ train: "goods", block: "a", length: null }]);
    expect(rows(roster)).toEqual([["goods", "", "a"]]);
  });

  /** Empty is the ordinary state of a railroad with its stock away, not a
   *  fault (ADR-0039), so it reads as the palette's hints do. */
  it("says the layout is empty when nothing is placed", async () => {
    const roster = await pane([]);
    expect(roster.renderRoot.querySelectorAll("li")).toHaveLength(0);
    expect(roster.renderRoot.querySelector(".hint")!.textContent!.trim()).toBe(
      "no trains on the layout",
    );
  });
});

describe("what fills it in a live session", () => {
  beforeEach(bridging);

  afterEach(unbridged);

  it("draws the run's placed train, with the length the scenario gives it", async () => {
    const shell = await joined();
    expect(rows(paneOf(shell))).toEqual([]);

    await said(shell, "tc49/dispatch/state/allocation", {
      trains: { goods: "a" },
      locks: { a: "goods" },
      requests: [],
    });

    expect(rows(paneOf(shell))).toEqual([["goods", "400", "a"]]);
  });
});
