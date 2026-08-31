// @vitest-environment happy-dom

/**
 * Turning a train around: the right-click over the block it stands in, and the
 * one frame choosing *Turn around* writes
 * ([#124](https://github.com/rails49/control/issues/124),
 * [ui/PANEL.md](../../docs/ui/PANEL.md)).
 *
 * A DOM suite because none of it is a model's. `Drag.trainAt` answers which
 * train was clicked and `Panel.standsIn` and `Panel.inFlight` answer what the
 * item is worth, each tested at its own seam; what only mounting `tc-panel`
 * can see is whether the component asked — that the offer is made over a train
 * and nowhere else, that the browser's own menu is suppressed either way, that
 * choosing sends one frame and no more, and that a menu the run has outlived
 * comes down ([#157](https://github.com/rails49/control/issues/157)).
 *
 * The last of those is the shape both bugs #124 found in Chrome took: a menu
 * that outlives what it is about — the train leaving the block, or the session
 * going — and then acts on a railroad that has moved.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-app.js";
import type { Point } from "../src/model/geometry.js";
import type { TcApp } from "../src/ui/tc-app.js";
import { band, chose, running, settled } from "./support/shell.js";
import {
  Bridge,
  bridging,
  joined,
  MIDDLE,
  PAPER,
  said,
  unbridged,
  written,
} from "./support/session.js";

beforeEach(bridging);

afterEach(unbridged);

const ALLOCATION = "tc49/dispatch/state/allocation";

/** The dispatcher's picture with `goods` standing in `a`, and whatever
 *  requests it has for the train. */
function picture(requests: unknown[] = []): Record<string, unknown> {
  return { trains: { goods: "a" }, locks: { a: "goods" }, requests };
}

/** A right-click on the drawing surface, and whether the browser was left to
 *  put its own menu up. Cancellable, so `defaultPrevented` means the view
 *  suppressed it rather than the event never having been suppressible. */
async function clicked(shell: TcApp, at: Point): Promise<{ native: boolean }> {
  const event = new MouseEvent("contextmenu", {
    bubbles: true,
    cancelable: true,
    clientX: at.x,
    clientY: at.y,
  });
  running(shell)
    .renderRoot.querySelector("tc-canvas")!
    .renderRoot.querySelector("svg")!
    .dispatchEvent(event);
  await settled(shell);
  return { native: !event.defaultPrevented };
}

/** What the run view's menu is offering, and whether each row can be chosen. */
function offered(shell: TcApp): { label: string; greyed: boolean }[] {
  const menu = running(shell).renderRoot.querySelector("tc-menu")!;
  return [...menu.renderRoot.querySelectorAll("li button")].map((row) => ({
    label: row.querySelector("span")!.textContent!.trim(),
    greyed: (row as HTMLButtonElement).disabled,
  }));
}

/** A joined session with `goods` standing in `a` and the run held, which is
 *  where a train is turned around. */
async function standing(requests: unknown[] = []): Promise<TcApp> {
  const shell = await joined();
  await said(shell, "tc49/dispatch/state/run", { run: "held" });
  await said(shell, ALLOCATION, picture(requests));
  return shell;
}

describe("what the right-click offers", () => {
  it("offers Turn around over the block a train stands in", async () => {
    const shell = await standing();
    expect(await clicked(shell, MIDDLE.a)).toEqual({ native: false });
    expect(offered(shell)).toEqual([{ label: "Turn around", greyed: false }]);
  });

  it("offers nothing over a block no train stands in", async () => {
    const shell = await standing();
    expect(await clicked(shell, MIDDLE.b)).toEqual({ native: false });
    expect(offered(shell)).toEqual([]);
  });

  it("offers nothing over paper", async () => {
    const shell = await standing();
    expect(await clicked(shell, PAPER)).toEqual({ native: false });
    expect(offered(shell)).toEqual([]);
  });

  /** A railroad on screen that no session is feeding: the picture the last
   *  session left is still painted, so the train is there to click, and there
   *  is nowhere to gesture at. The band's picker is what gets back in
   *  (#171). */
  it("offers nothing over a train with no session joined", async () => {
    const shell = await standing();
    Bridge.last!.close();
    await settled(shell);

    expect(await clicked(shell, MIDDLE.a)).toEqual({ native: false });
    expect(offered(shell)).toEqual([]);
  });

  /** The panel's one pre-judgement of a gesture, against the filter-free drag
   *  (ui/PANEL.md): turning a train around while a request of its own is
   *  queued would flip the arrow under it. Greyed rather than absent, a still
   *  row saying *this train is busy* where silence says nothing. */
  it("greys it while that train has a request in flight", async () => {
    const shell = await standing([
      { id: "r1", train: "goods", depart: "a.B", dest: ["b.A"] },
    ]);
    await clicked(shell, MIDDLE.a);
    expect(offered(shell)).toEqual([{ label: "Turn around", greyed: true }]);
  });
});

describe("choosing Turn around", () => {
  it("writes one reversal_wanted naming the train, and no more", async () => {
    const shell = await standing();
    await clicked(shell, MIDDLE.a);
    await chose(shell, "Turn around");

    expect(written()).toEqual([
      { topic: "tc49/schedule/reversal_wanted", payload: { train: "goods" } },
    ]);
    expect(offered(shell)).toEqual([]);
  });
});

/**
 * The menu is about one train in one block, and the run can end both. Both
 * bugs #124 found running a live session were here: a menu that stayed up over
 * a railroad that had moved, and one left up over a socket that had gone.
 */
describe("a menu the run has outlived", () => {
  it("takes it down when the train leaves the block it was opened over", async () => {
    const shell = await standing();
    await clicked(shell, MIDDLE.a);
    expect(offered(shell)).toHaveLength(1);

    await said(shell, ALLOCATION, {
      trains: { goods: "b" },
      locks: { b: "goods" },
      requests: [],
    });
    expect(offered(shell)).toEqual([]);

    // Taken down and not merely filtered out of the render: a menu still held
    // in state springs back the moment that train stands there again, and
    // nothing was ever left on screen to dismiss.
    await said(shell, ALLOCATION, picture());
    expect(offered(shell)).toEqual([]);
  });

  it("takes it down when the session goes", async () => {
    const shell = await standing();
    await clicked(shell, MIDDLE.a);
    expect(offered(shell)).toHaveLength(1);

    Bridge.last!.close();
    await settled(shell);

    expect(offered(shell)).toEqual([]);
  });

  /** A railroad swapped under an open menu is the same thing again: the app
   *  loads another and the menu is about a train on the one that went. */
  it("takes it down when the app loads another railroad", async () => {
    const shell = await standing();
    await clicked(shell, MIDDLE.a);
    expect(offered(shell)).toHaveLength(1);

    band(shell).dispatchEvent(
      new CustomEvent<string>("railroad-wanted", {
        detail: "other",
        bubbles: true,
        composed: true,
      }),
    );
    await settled(shell);

    expect(offered(shell)).toEqual([]);
  });
});
