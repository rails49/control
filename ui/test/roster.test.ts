// @vitest-environment happy-dom

/**
 * The roster pane in the run view's half of the shell's left-pane slot
 * ([#169](https://github.com/rails49/control/issues/169),
 * [#170](https://github.com/rails49/control/issues/170)).
 *
 * Three parts. The pane itself works nothing out, so what is asked of it is
 * what it draws for the rows it is handed. Then the path that fills it: the
 * store's roster for what the railroad owns, the bus's picture for where each
 * train is. Then its two drags — a row onto a block places a train, a marker
 * onto the pane takes one off the layout — which are the whole point of
 * listing trains that are not on the rails.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-roster.js";
import "../src/ui/tc-app.js";
import { centreOf, type Point } from "../src/model/geometry.js";
import type { RosterRow } from "../src/model/panel.js";
import type { TcApp } from "../src/ui/tc-app.js";
import type { TcRoster } from "../src/ui/tc-roster.js";
import { running, settled } from "./support/shell.js";
import {
  bridging,
  joined,
  said,
  stored,
  unbridged,
  written,
} from "./support/session.js";

/** The pane, holding the rows it was handed, with the run held so its rows
 *  can be picked up. */
async function pane(
  trains: RosterRow[],
  run: "held" | "running" | null = "held",
): Promise<TcRoster> {
  const roster = document.createElement("tc-roster");
  roster.trains = trains;
  roster.run = run;
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
      { train: "goods", block: "a", length: 400, placed: true },
      { train: "express", block: "b", length: 1100, placed: true },
    ]);
    expect(rows(roster)).toEqual([
      ["goods", "400", "a"],
      ["express", "1100", "b"],
    ]);
  });

  /** The order is the model's (`panel.roster`), so the pane draws what it is
   *  handed and never sorts: two parties ordering the list is one of them
   *  reshuffling it under the reader. */
  it("keeps the order it was handed", async () => {
    const roster = await pane([
      { train: "z", block: "a", length: 1, placed: true },
      { train: "a", block: "b", length: 2, placed: true },
    ]);
    expect(rows(roster).map(([name]) => name)).toEqual(["z", "a"]);
  });

  /** A train between two blocks stands in none and is on the layout all the
   *  same, holding the transit that is taking it out of the last one. */
  it("says a crossing train stands in no block", async () => {
    const roster = await pane([
      { train: "goods", block: null, length: 400, placed: true },
    ]);
    expect(rows(roster)).toEqual([["goods", "400", "crossing"]]);
  });

  /** Nothing the page has read names the length of a train the run has, which
   *  is a blank rather than a nought: a train with no length is not one of
   *  length zero. */
  it("leaves the length blank where nothing names one", async () => {
    const roster = await pane([
      { train: "goods", block: "a", length: null, placed: true },
    ]);
    expect(rows(roster)).toEqual([["goods", "", "a"]]);
  });

  /** A train off the layout is on the roster and not on the rails, which is
   *  an ordinary state and not a fault (ADR-0039). It keeps its row, because
   *  the row is what there is to drag onto a block. */
  it("says a train that is not placed is off the layout", async () => {
    const roster = await pane([
      { train: "shunter", block: null, length: 200, placed: false },
    ]);
    expect(rows(roster)).toEqual([["shunter", "200", "off the layout"]]);
  });

  /** A railroad with no roster and a page with no session look the same from
   *  here: nothing has been named. */
  it("says so when it is handed no trains at all", async () => {
    const roster = await pane([]);
    expect(roster.renderRoot.querySelectorAll("li")).toHaveLength(0);
    expect(roster.renderRoot.querySelector(".hint")!.textContent!.trim()).toBe(
      "no trains on the roster",
    );
  });
});

describe("what fills it in a live session", () => {
  beforeEach(bridging);

  afterEach(unbridged);

  /** Two sources, one list: the store says what the railroad owns and how
   *  long each train is, the bus says which of them are on the layout
   *  (ADR-0010, ADR-0039). Joining is enough for the first half. */
  it("lists the whole roster, marking which trains the run has", async () => {
    const shell = await joined();
    expect(rows(paneOf(shell))).toEqual([
      ["goods", "400", "off the layout"],
      ["shunter", "200", "off the layout"],
    ]);

    await said(shell, "tc49/dispatch/state/allocation", {
      trains: { goods: "a" },
      locks: { a: "goods" },
      requests: [],
    });

    expect(rows(paneOf(shell))).toEqual([
      ["goods", "400", "a"],
      ["shunter", "200", "off the layout"],
    ]);
  });

  /** The roster belongs to a joined session as much as the picture does. A
   *  page that has left one is being told nothing, so the pane says nothing
   *  rather than listing the trains of a run it is no longer watching — and
   *  claiming every one of them is off the layout, which it cannot know. */
  it("empties when the session is left", async () => {
    const shell = await joined();
    await said(shell, "tc49/dispatch/state/allocation", {
      trains: { goods: "a" },
      locks: { a: "goods" },
      requests: [],
    });

    running(shell).renderRoot.querySelector<HTMLElement>("sl-button")!.click();
    await settled(shell);

    expect(rows(paneOf(shell))).toEqual([]);
  });
});

/**
 * The pane's two drags (ADR-0039). **The source decides what a drag means**:
 * a row picked up in the pane places its train, a marker picked up on the
 * canvas asks for a request, and dropping a marker back on the pane takes the
 * train off the layout. Never the run's state — one motion cannot mean two
 * things depending on a word in the band.
 *
 * happy-dom's `getScreenCTM` is the identity, so a client pixel reads as a
 * grid square and a block's centre is the point to let go over.
 */
describe("its drags", () => {
  beforeEach(bridging);

  afterEach(unbridged);

  /** The run held, with `goods` standing in `a` and `shunter` off the layout:
   *  the state both drags are made from. */
  async function held(): Promise<TcApp> {
    const shell = await joined();
    await said(shell, "tc49/dispatch/state/run", { run: "held" });
    await said(shell, "tc49/dispatch/state/allocation", {
      trains: { goods: "a" },
      locks: { a: "goods" },
      requests: [],
    });
    return shell;
  }

  /** One row of the pane, by the train it is about. */
  function row(shell: TcApp, train: string): HTMLElement {
    const index = paneOf(shell).trains.findIndex((one) => one.train === train);
    return [...paneOf(shell).renderRoot.querySelectorAll("li")][index]!;
  }

  /** A drag of a row, let go at a client point. */
  async function dragRow(shell: TcApp, train: string, at: Point): Promise<void> {
    for (const [name, point] of [
      ["pointerdown", at],
      ["pointerup", at],
    ] as const) {
      row(shell, train).dispatchEvent(
        new PointerEvent(name, {
          bubbles: true,
          composed: true,
          clientX: point.x,
          clientY: point.y,
        }),
      );
    }
    await settled(shell);
  }

  /** A drag of a train's marker across the canvas, let go at a client point.
   *  The pane is put somewhere the blocks are not, so that where the drag
   *  ended is what decides what it meant. */
  async function dragMarker(shell: TcApp, from: Point, to: Point): Promise<void> {
    paneOf(shell).getBoundingClientRect = () =>
      ({ left: 500, right: 600, top: 0, bottom: 800 }) as DOMRect;
    const surface = running(shell)
      .renderRoot.querySelector("tc-canvas")!
      .renderRoot.querySelector("svg")!;
    for (const [name, at] of [
      ["pointerdown", from],
      ["pointermove", to],
      ["pointerup", to],
    ] as const) {
      surface.dispatchEvent(
        new PointerEvent(name, { bubbles: true, clientX: at.x, clientY: at.y }),
      );
    }
    await settled(shell);
  }

  it("places a train dragged out of the pane onto a block", async () => {
    const shell = await held();

    await dragRow(shell, "shunter", centreOf(stored("toy").symbols.b!));

    expect(written()).toContainEqual({
      topic: "tc49/ui/placement_wanted",
      payload: { train: "shunter", block: "b" },
    });
  });

  /** A row let go over the pane, or over bare paper: there is no block under
   *  it, so the drag was about nothing and says nothing. */
  it("writes nothing for a row let go where no block is", async () => {
    const shell = await held();

    await dragRow(shell, "shunter", { x: 500, y: 500 });

    expect(written()).toEqual([]);
  });

  /** The other direction of the one gesture: `block: null` is off the layout,
   *  and the key is always written — the dispatcher reads it for presence. */
  it("takes a train off the layout when its marker is dropped on the pane", async () => {
    const shell = await held();

    await dragMarker(shell, centreOf(stored("toy").symbols.a!), { x: 550, y: 400 });

    expect(written()).toEqual([
      {
        topic: "tc49/ui/placement_wanted",
        payload: { train: "goods", block: null },
      },
    ]);
  });

  /** Both are refused while the run is running: the dispatcher would drop
   *  them, granting against the picture the whole time, and the pane says so
   *  rather than letting a drag be swallowed. */
  it("is still while the run is running, and says why", async () => {
    const shell = await joined();
    await said(shell, "tc49/dispatch/state/run", { run: "running" });
    await said(shell, "tc49/dispatch/state/allocation", {
      trains: { goods: "a" },
      locks: { a: "goods" },
      requests: [],
    });

    await dragRow(shell, "shunter", centreOf(stored("toy").symbols.b!));
    await dragMarker(shell, centreOf(stored("toy").symbols.a!), { x: 550, y: 400 });

    expect(written()).toEqual([]);
    expect(paneOf(shell).renderRoot.querySelector(".hint")!.textContent).toContain(
      "the run is running",
    );
  });
});
