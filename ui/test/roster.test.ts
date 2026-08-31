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
import type { Point } from "../src/model/geometry.js";
import type { RosterRow } from "../src/model/panel.js";
import type { TcApp } from "../src/ui/tc-app.js";
import type { TcRoster } from "../src/ui/tc-roster.js";
import { running, settled, surface } from "./support/shell.js";
import {
  bridging,
  joined,
  loads,
  MIDDLE,
  said,
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
  it("says a train that stands in no block is crossing a transit", async () => {
    const roster = await pane([
      { train: "goods", block: null, length: 400, placed: true },
    ]);
    expect(rows(roster)).toEqual([["goods", "400", "crossing a transit"]]);
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

  /** The loaded railroad is the session (#171), so loading another is how a
   *  session ends. Where the last one's trains stood goes with it: this run
   *  has said nothing yet, and a pane still showing block `a` would be
   *  another railroad's picture under this railroad's roster. */
  it("forgets where the last railroad's trains stood when another is loaded", async () => {
    const shell = await joined();
    await said(shell, "tc49/dispatch/state/allocation", {
      trains: { goods: "a" },
      locks: { a: "goods" },
      requests: [],
    });

    await loads(shell, "other");

    expect(rows(paneOf(shell))).toEqual([
      ["goods", "400", "off the layout"],
      ["shunter", "200", "off the layout"],
    ]);
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

  /** Where the two parts of the view sit, which is what says whether a
   *  release landed on the sheet or on the pane. happy-dom gives every element
   *  a zero box, so the suite states the layout the browser would: the pane
   *  beside the sheet, and the blocks of the toy drawing inside the sheet. */
  function laid(shell: TcApp): void {
    const boxes: [Element, DOMRect][] = [
      [paneOf(shell), { left: 500, right: 600, top: 0, bottom: 800 } as DOMRect],
      [
        running(shell).renderRoot.querySelector("tc-canvas")!,
        { left: 0, right: 400, top: 0, bottom: 800 } as DOMRect,
      ],
    ];
    for (const [part, box] of boxes) part.getBoundingClientRect = () => box;
  }

  /** One row of the pane, by the train it is about. */
  function row(shell: TcApp, train: string): HTMLElement {
    const index = paneOf(shell).trains.findIndex((one) => one.train === train);
    return [...paneOf(shell).renderRoot.querySelectorAll("li")][index]!;
  }

  /** A drag of a row, let go at a client point. */
  async function dragRow(shell: TcApp, train: string, at: Point): Promise<void> {
    laid(shell);
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
   *  The pane sits beside the sheet, so where the drag ended is what decides
   *  what it meant. */
  async function dragMarker(shell: TcApp, from: Point, to: Point): Promise<void> {
    laid(shell);
    const sheet = surface(shell);
    for (const [name, at] of [
      ["pointerdown", from],
      ["pointermove", to],
      ["pointerup", to],
    ] as const) {
      sheet.dispatchEvent(
        new PointerEvent(name, { bubbles: true, clientX: at.x, clientY: at.y }),
      );
    }
    await settled(shell);
  }

  it("places a train dragged out of the pane onto a block", async () => {
    const shell = await held();

    await dragRow(shell, "shunter", MIDDLE.b);

    expect(written()).toContainEqual({
      topic: "tc49/dispatch/placement_wanted",
      payload: { train: "shunter", block: "b" },
    });
  });

  /** Over bare paper: on the sheet, and no block under the pointer. */
  it("writes nothing for a row let go where no block is", async () => {
    const shell = await held();

    await dragRow(shell, "shunter", { x: 300, y: 700 });

    expect(written()).toEqual([]);
  });

  /** Off the sheet: how a drag started by mistake is abandoned. Whether the
   *  release was on the sheet is read off the surface's own box and never off
   *  the drawing, because the drawing runs past the viewport: the transform
   *  below is a pan that parks block `b` behind the pane's own pixels, and a
   *  release read through it alone would place the train in a block nobody
   *  can see. */
  it("writes nothing for a row let go back on the pane", async () => {
    const shell = await held();
    const at = { x: 550, y: 400 };
    surface(shell).getScreenCTM = () =>
      new DOMMatrix([1, 0, 0, 1, at.x - MIDDLE.b.x, at.y - MIDDLE.b.y]);

    await dragRow(shell, "shunter", at);

    expect(written()).toEqual([]);
  });

  /** The other direction of the one gesture: `block: null` is off the layout,
   *  and the key is always written — the dispatcher reads it for presence. */
  it("takes a train off the layout when its marker is dropped on the pane", async () => {
    const shell = await held();

    await dragMarker(shell, MIDDLE.a, { x: 550, y: 400 });

    expect(written()).toEqual([
      {
        topic: "tc49/dispatch/placement_wanted",
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

    await dragRow(shell, "shunter", MIDDLE.b);
    await dragMarker(shell, MIDDLE.a, { x: 550, y: 400 });

    expect(written()).toEqual([]);
    expect(paneOf(shell).renderRoot.querySelector(".hint")!.textContent).toContain(
      "the run is running",
    );
  });
});
