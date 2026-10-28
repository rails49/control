// @vitest-environment happy-dom

/**
 * The run view joined to the railroad the broker runs, end to end through the
 * app: the picture the bus feeds, and the band's driving control, which draws
 * the mode `layout` published and publishes the press on the topic that names
 * it (ADR-0079, #828).
 *
 * A DOM test because it crosses three components and the broker. The session
 * itself — the toy railroad, the broker double and the app joined to it — is
 * `support/session.ts`, shared with the other suites that need one.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { LookBandPress, LookCommand } from "@rails49/look";
import { press } from "@rails49/look/testing";

import "../src/ui/tc-app.js";
import type { Drawing } from "../src/model/drawing.js";
import { centreOf } from "../src/model/geometry.js";
import { photoUrl, RETRY_MS, type Explained, type Layout } from "../src/model/store.js";
import type { TcApp } from "../src/ui/tc-app.js";
import { APPS, brokerAt, gone } from "../src/model/session.js";
import { VIEWS } from "../src/model/views.js";
import {
  band,
  chips,
  CLEAN,
  mounted,
  named,
  rail,
  running,
  serving,
  settled,
  shows,
} from "./support/shell.js";
import {
  Broker,
  brokering,
  DERIVES,
  joined,
  loads,
  RAILROAD,
  said,
  STOCK,
  stored,
  unbrokered,
  written,
} from "./support/session.js";

beforeEach(brokering);

/** What the band says while the broker is not answering, read off the module
 *  for the address this page asks. */
const GONE = gone(brokerAt(location));

afterEach(unbrokered);

/** The driving control on the band. */
function steering(shell: TcApp): LookBandPress {
  return band(shell).querySelector<LookBandPress>("look-band-press[data-driving]")!;
}

/** The fault the band is showing, `null` while it shows none. */
function health(shell: TcApp): string | null {
  return chips(shell)[0] ?? null;
}

describe("where the broker is", () => {
  /** A page served over TLS must ask for `wss://`. A plain `ws://` from it is
   *  mixed content, which the browser refuses outright, so the page would
   *  never connect on the layout server at all (ADR-0042). */
  it("follows the page's own scheme", () => {
    expect(brokerAt({ protocol: "https:", host: "control.gleis49.org", search: "" })).toBe(
      "wss://control.gleis49.org/mqtt",
    );
    expect(brokerAt({ protocol: "http:", host: "localhost:5173", search: "" })).toBe(
      "ws://localhost:5173/mqtt",
    );
  });

  /** One path on the app's own origin either way: vite proxies it in
   *  development and the reverse proxy strips it in front of a layout server,
   *  so nothing in the panel knows which of the two it is talking to. */
  it("is a path on the page's own origin", () => {
    expect(brokerAt({ protocol: "http:", host: "192.168.1.9:5173", search: "" })).toBe(
      "ws://192.168.1.9:5173/mqtt",
    );
  });

  /** `?broker=` is the whole of the browser's configuration, and it names a
   *  broker somewhere else outright. The railroad is not part of it: one
   *  broker runs one railroad and says which (ADR-0059, decision 2). */
  it("gives way to the one a query names", () => {
    expect(
      brokerAt({
        protocol: "https:",
        host: "control.gleis49.org",
        search: "?broker=ws://127.0.0.1:9001",
      }),
    ).toBe("ws://127.0.0.1:9001");
  });
});

describe("joining the railroad the broker runs", () => {
  /** One client per page, subscribing everything of ours, and the retained row
   *  is the whole of the choice of railroad (#371, ADR-0059 decision 2): the
   *  app loads what it names and the band shows it. */
  it("loads the railroad the retained row names", async () => {
    const shell = await joined();
    expect(Broker.opened).toHaveLength(1);
    expect(Broker.last!.url).toMatch(/\/mqtt$/);
    expect(Broker.last!.subscriptions).toEqual(["tc49/#"]);
    expect(named(shell)).toBe("toy");
  });

  /** Retained values arrive as the subscription lands (ADR-0032): the rows
   *  the apps left on the broker before this page existed are the picture it
   *  opens with. */
  it("is fed what was on the broker before it connected", async () => {
    const shell = await mounted("run");
    const broker = Broker.last!;
    broker.retains(RAILROAD, { name: "toy" });
    broker.retains("tc49/layout/state/driving", { driving: "automatic" });
    broker.retains("tc49/dispatch/state/allocation", {
      trains: { goods: "a" },
      locks: { a: "goods" },
      requests: [],
    });
    broker.opens();
    await settled(shell);

    expect(steering(shell).icon).toBe("robot");
    expect(
      running(shell)
        .renderRoot.querySelector("tc-canvas")!
        .renderRoot.querySelector('g[data-symbol="a"] > title')!
        .textContent!.trim(),
    ).toBe("goods");
  });

  /** The broker going is a container restarting or a network that dropped.
   *  What it was saying is no longer being said, so the page holds no session:
   *  the band drops the badge, and nothing is said to have been heard — that a
   *  press in between publishes nothing is the session's (session.test.ts).
   *
   *  Getting back in is the client's own. It reconnects and resubscribes, and
   *  the fresh subscription is answered with every retained row, so the same
   *  client comes back with the picture on it. */
  it("lets the session go when the broker goes, and is fed again when it is back", async () => {
    const shell = await joined();
    const broker = Broker.last!;
    await said(shell, "tc49/layout/state/driving", { driving: "automatic" });

    broker.closes();
    await settled(shell);

    // The band has no word for the link either way since #517: a broker that
    // has gone says so in the trouble line, in words naming what to look at.
    expect(health(shell)).toBe(GONE);
    expect(written()).toEqual([]);

    broker.opens();
    await settled(shell);

    expect(Broker.opened).toHaveLength(1);
    expect(health(shell)).toBeNull();
    expect(steering(shell).icon).toBe("robot");
  });

  /** The connection is the page's and not a view's (ADR-0059, decision 4):
   *  the app holds the one session (#756), so going through every view and
   *  another railroad arriving open nothing more. */
  it("opens one connection for the life of the page", async () => {
    const shell = await joined();
    for (const view of VIEWS) await shows(shell, view.id);
    await loads(shell, "yard");

    expect(named(shell)).toBe("yard");
    expect(Broker.opened).toHaveLength(1);
  });

  /** The session keeps the status and the cabs the same objects across a
   *  frame that moves neither, and that is what keeps the app from redrawing
   *  the whole page on every event the bus carries. */
  it("does not redraw the app on a frame that changes nothing it shows", async () => {
    const shell = await joined();
    await said(shell, "tc49/layout/state/driving", { driving: "manual" });
    const drawing = vi.spyOn(
      shell as unknown as { render(): unknown },
      "render",
    );

    await said(shell, "tc49/dispatch/state/aspects", { aspects: {} });
    expect(drawing).not.toHaveBeenCalled();

    await said(shell, "tc49/layout/state/driving", { driving: "automatic" });
    expect(drawing).toHaveBeenCalled();
  });

  /** Nothing at the address at all: the band names where it looked, which is
   *  the only answer a page gets when there is no broker to answer it, and
   *  asks the one question a person can act on (#517). */
  it("says where it looked when nothing is there", async () => {
    const shell = await mounted("run");
    Broker.last!.fails();
    await settled(shell);

    expect(health(shell)).toBe(GONE);
  });
});

/**
 * The store not answering for the roster the railroad arrived with
 * ([#183](https://github.com/rails49/control/issues/183)).
 *
 * Getting back onto the broker is the client's own, so the only retry left
 * here is the store's: what stock a railroad owns is its asset and no topic
 * carries it (ADR-0039), so a read that failed is made again every `RETRY_MS`
 * until it lands. The interval is read off the module rather than written
 * here, a suite spelling 3000 being one that stops holding what the view does.
 *
 * Fake timers throughout: what is being held is which try happens, not how
 * long a suite is willing to sit.
 */
describe("reading a roster the store would not answer for", () => {
  /** The toy railroad with its roster reads counted, and a switch for the
   *  store going quiet on that one route. The other routes keep answering, so
   *  what stops is the read and not the railroad on screen. */
  function counting(): { reads: number; answering: boolean } {
    const store = { reads: 0, answering: true };
    serving({
      drawings: ["toy"],
      rosterOf: () => {
        store.reads += 1;
        if (!store.answering) throw new Error("no store");
        return STOCK;
      },
      read: stored,
      review: () => Promise.resolve(DERIVES),
    });
    return store;
  }

  /** A page joined to a broker whose store is not answering. */
  async function quiet(store: { answering: boolean }): Promise<TcApp> {
    store.answering = false;
    const shell = await mounted("run");
    await loads(shell, "toy");
    return shell;
  }

  it("says so, and makes one try when the interval is up", async () => {
    vi.useFakeTimers();
    try {
      const store = counting();
      const shell = await quiet(store);

      expect(store.reads).toBe(1);
      expect(health(shell)).toBe("the store is not answering — run `tc49 serve`");

      store.answering = true;
      await vi.advanceTimersByTimeAsync(RETRY_MS);
      // The apps behind the broker are running, and say so (#1113): what
      // the band would name otherwise is them, not the store.
      for (const topic of APPS.keys()) Broker.last!.says(topic, {});
      await settled(shell);

      expect(store.reads).toBe(2);
      expect(health(shell)).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  /** One try per interval and never a run of them behind each other: a
   *  failure while one is already waiting finds it there and leaves it. */
  it("keeps one try waiting at a time", async () => {
    vi.useFakeTimers();
    try {
      const store = counting();
      const shell = await quiet(store);
      store.reads = 0;

      await vi.advanceTimersByTimeAsync(RETRY_MS);
      await settled(shell);
      expect(store.reads).toBe(1);

      await vi.advanceTimersByTimeAsync(RETRY_MS);
      await settled(shell);
      expect(store.reads).toBe(2);
    } finally {
      vi.useRealTimers();
    }
  });

  /** A read that lands is the end of it: nothing will republish a roster, and
   *  nothing has to. */
  it("stops trying once the roster has been read", async () => {
    vi.useFakeTimers();
    try {
      const store = counting();
      const shell = await quiet(store);
      store.answering = true;

      await vi.advanceTimersByTimeAsync(RETRY_MS);
      await settled(shell);
      expect(store.reads).toBe(2);

      await vi.advanceTimersByTimeAsync(RETRY_MS * 3);
      await settled(shell);
      expect(store.reads).toBe(2);
    } finally {
      vi.useRealTimers();
    }
  });
});

/**
 * What the run view shows, now that it shows it on the shared canvas (#168).
 *
 * The view draws none of the picture itself: it hands `tc-canvas` the overlay
 * the panel model worked out and the canvas paints it in run mode. So the one
 * thing worth walking end to end is that the picture still arrives — a frame
 * off the bus, through the model, onto the sheet.
 */
describe("the picture on the shared canvas", () => {
  /** The drawing surface the run view is rendering through. */
  function sheet(shell: TcApp): ParentNode {
    return running(shell).renderRoot.querySelector("tc-canvas")!.renderRoot;
  }

  it("stands the train the dispatcher's picture places, and marks its block", async () => {
    const shell = await joined();
    await said(shell, "tc49/dispatch/state/allocation", {
      trains: { goods: "a" },
      locks: { a: "goods" },
      requests: [],
    });

    const drawn = sheet(shell);
    expect([...drawn.querySelector('g[data-symbol="a"]')!.classList]).toContain(
      "occupied",
    );
    expect(drawn.querySelector('g[data-symbol="a"] > title')!.textContent!.trim()).toBe(
      "goods",
    );
    // Drawn as its first locomotive, the roster naming one (#1018).
    expect(drawn.querySelector("image.photo")!.getAttribute("href")).toBe(
      photoUrl("BR 218"),
    );
    // The editor's marks are not on a run's sheet, whatever it is showing.
    expect(drawn.querySelectorAll("circle.pin")).toHaveLength(0);
  });

  /**
   * The drag, driven the way the canvas drives it. `Drag` answers the same
   * `Machine` the editor's `Gesture` does now, so the press, the move and the
   * release all arrive through the shared surface — and what the drop is worth
   * is one frame on the bus, which is what this walks (#168).
   *
   * happy-dom's `getScreenCTM` is the identity, so a client pixel reads as a
   * grid square and a block's centre is the point to press at. The two
   * centres are only four pixels apart, within a click's slop, so the pointer
   * goes by way of a point further off: a press released within the slop is
   * a tap and drops nothing (#1018).
   */
  it("submits the request a drag across the canvas asks for", async () => {
    const shell = await joined();
    await said(shell, "tc49/dispatch/state/allocation", {
      trains: { goods: "a" },
      locks: { a: "goods" },
      requests: [],
    });

    const drawing = stored("toy");
    const from = centreOf(drawing.symbols.a!);
    const to = centreOf(drawing.symbols.b!);
    const surface = sheet(shell).querySelector("svg")!;
    for (const [name, at] of [
      ["pointerdown", from],
      ["pointermove", { x: to.x, y: to.y + 10 }],
      ["pointermove", to],
      ["pointerup", to],
    ] as const) {
      surface.dispatchEvent(
        new PointerEvent(name, { bubbles: true, clientX: at.x, clientY: at.y }),
      );
    }
    await settled(shell);

    expect(written()).toEqual([
      {
        topic: "tc49/schedule/request_wanted",
        payload: { train: "goods", dest: ["b.A", "b.B"] },
      },
    ]);
  });

  /**
   * A route the run holds, drawn on the sheet: the model says which wires the
   * way runs over and in what colour, and the canvas emits the lit ones last
   * so a crossing unlit one cannot half hide one (#140, #142).
   *
   * `inspect.wiresOn` and `inspect.litLast` are each tested at their own seam
   * and the canvas's ordering at its; what only this walk can see is that the
   * run view hands its `lit()` through to the surface, the answer arriving as
   * a lock off the bus rather than as a hand-written overlay.
   *
   * The toy railroad has no connection to light, so this one has: two blocks
   * through a turnout, and a third off its diverging road to own a wire that
   * the way does not run over. That unlit wire is written **between** the two
   * lit ones, so emitting them in the order they are written would leave it
   * drawn over the second — which is the whole of what the rule is for.
   */
  it("draws a locked route's wires last, in the colour the claim reads in", async () => {
    const YARD: Drawing = {
      drawing: "yard",
      symbols: {
        a: { kind: "block", at: [0, 0], length: 1000 },
        sw: { kind: "turnout", at: [7, 0] },
        b: { kind: "block", at: [10, 0], length: 1000 },
        north: { kind: "block", at: [10, 3], length: 1000 },
      },
      wires: [
        ["a.B", "sw.toe"],
        ["sw.diverging", "north.A"],
        ["sw.straight", "b.A"],
      ],
    };
    const LAYOUT: Layout = {
      layout: "yard",
      blocks: { a: { length: 1000 }, b: { length: 1000 }, north: { length: 1000 } },
      connections: { c: { transits: { t: ["a.B", "b.A"] } } },
    };
    const EXPLAIN: Explained = {
      layout: "yard",
      connections: {
        c: {
          transits: { t: { ends: ["a.B", "b.A"], way: [["sw", "straight"]] } },
          exclusive: [],
        },
      },
    };
    serving({
      drawings: ["yard"],
      rosterOf: () => ({ goods: { length: 400 } }),
      read: () => structuredClone(YARD),
      review: () =>
        Promise.resolve({ ...CLEAN, layout: LAYOUT, explain: EXPLAIN }),
    });

    const shell = await mounted("run");
    await loads(shell, "yard");
    await said(shell, "tc49/dispatch/state/allocation", {
      trains: { goods: "a" },
      locks: { a: "goods", "c.t": "goods" },
      requests: [],
    });

    expect(
      [...sheet(shell).querySelectorAll("line.wire")].map((line) =>
        [...line.classList].join(" "),
      ),
    ).toEqual(["wire", "wire lit locked", "wire lit locked"]);
  });
});

/**
 * The viewport the run view never had (#168). It draws on the editor's canvas
 * now, so zoom, pan and fit are the same three commands on the same bar
 * buttons and the same keys — and a railroad arriving is fitted, however it
 * arrived.
 */
describe("the viewport the run view gained", () => {
  /** What the run view's canvas is looking at. */
  function looking(shell: TcApp): number[] {
    return running(shell)
      .renderRoot.querySelector("tc-canvas")!
      .renderRoot.querySelector("svg")!
      .getAttribute("viewBox")!
      .split(" ")
      .map(Number);
  }

  /** One of the rail's commands, by the label it carries. */
  function tool(shell: TcApp, label: string): LookCommand {
    return [...rail(shell).querySelectorAll<LookCommand>("look-command[data-command]")].find(
      (one) => one.label === label,
    )!;
  }

  it("fits the railroad it was handed, and zooms from the rail", async () => {
    const shell = await joined();
    // The two blocks span 0 to 8 across, so a fit frames at least that much.
    const [x, , w] = looking(shell);
    expect(x!).toBeLessThanOrEqual(0);
    expect(x! + w!).toBeGreaterThanOrEqual(8);

    press(tool(shell, "Zoom in"));
    await settled(shell);
    expect(looking(shell)[2]).toBeLessThan(w!);

    press(tool(shell, "Fit"));
    await settled(shell);
    expect(looking(shell)[2]).toBeCloseTo(w!);
  });

  /** The same keys the editor has, and they reach the view that is current. */
  it("zooms on the keyboard while the run view is showing", async () => {
    const shell = await joined();
    const [, , w] = looking(shell);
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "-", bubbles: true }));
    await settled(shell);
    expect(looking(shell)[2]).toBeGreaterThan(w!);
  });
});

/**
 * The driving control on the band, next to track power, in every view: the
 * mode is the whole railroad's (ADR-0079, #871). It shows `state/driving` by
 * its glyph and tooltip and publishes `driving_wanted` naming the other mode.
 * What it draws is `layout`'s answer and not the press, and it is live at any
 * power, `layout` accepting the gesture whatever power reads.
 */
describe("the driving control", () => {
  it("is dead until layout says the driving mode", async () => {
    const shell = await joined();
    expect(steering(shell).disabled).toBe(true);
  });

  it("shows the mode layout says by its glyph and tooltip", async () => {
    const shell = await joined();

    await said(shell, "tc49/layout/state/driving", { driving: "manual" });
    expect(steering(shell).icon).toBe("person-fill");
    expect(steering(shell).label).toBe("Driving mode manual: press for automatic");
    expect(steering(shell).word).toBe("");
    expect(steering(shell).disabled).toBe(false);

    await said(shell, "tc49/layout/state/driving", { driving: "automatic" });
    expect(steering(shell).icon).toBe("robot");
    expect(steering(shell).label).toBe("Driving mode automatic: press for manual");
  });

  /** One press, no confirmation, and the press alone changes nothing on
   *  screen. */
  it("asks for automatic from manual", async () => {
    const shell = await joined();
    await said(shell, "tc49/layout/state/driving", { driving: "manual" });

    press(steering(shell));
    await settled(shell);

    expect(written()).toEqual([
      {
        topic: "tc49/layout/driving_wanted",
        payload: { driving: "automatic" },
      },
    ]);
    expect(steering(shell).icon).toBe("person-fill");
  });

  it("asks for manual from automatic", async () => {
    const shell = await joined();
    await said(shell, "tc49/layout/state/driving", { driving: "automatic" });

    press(steering(shell));

    expect(written()).toEqual([
      { topic: "tc49/layout/driving_wanted", payload: { driving: "manual" } },
    ]);
  });

  it.each(["on", "draining", "off"] as const)(
    "is live with power %s",
    async (power) => {
      const shell = await joined();
      await said(shell, "tc49/layout/state/driving", { driving: "manual" });
      await said(shell, "tc49/layout/state/power", { power });

      expect(steering(shell).disabled).toBe(false);
    },
  );

  /** The last of the band's items, just before track power, whichever view
   *  is up. */
  it.each(VIEWS.map((view) => view.id))(
    "sits on the band just before track power in the %s view",
    async (view) => {
      const shell = await joined();
      await shows(shell, view);

      const pressed = steering(shell);
      expect(pressed).not.toBeNull();
      expect(pressed.nextElementSibling?.localName).toBe("look-power");
    },
  );

  /** GO and HOLD are gone, nothing on the page writes `run_wanted`, and the
   *  rail no longer carries the mode. */
  it("is not on the rail", async () => {
    const shell = await joined();
    expect(rail(shell).querySelector("look-command[data-run]")).toBeNull();
    expect(rail(shell).querySelector("[data-driving]")).toBeNull();
    expect(rail(shell).querySelector("look-group[end]")).toBeNull();
  });
});

/**
 * #709. A rebuild under the same name places a pictured train again only
 * where its block is still in the drawing and still holds it (ADR-0071), and
 * the dispatcher lists the ones it left off on `state/unfit`. The run view
 * says which, and why, one line per train, for as long as the list stands.
 */
describe("the trains a rebuild took off", () => {
  /** The lines the run view is showing about them, in order. */
  function unfit(shell: TcApp): string[] {
    return [...running(shell).renderRoot.querySelectorAll(".unfit")].map(
      (line) => line.textContent!.trim(),
    );
  }

  it("says one line per listed train, and why", async () => {
    const shell = await joined();
    await said(shell, "tc49/dispatch/state/unfit", {
      trains: [
        { train: "ore", block: "S3", why: "gone" },
        { train: "t1", block: "b", why: "short" },
      ],
    });

    expect(unfit(shell)).toEqual([
      "ore: block S3 is gone",
      "t1: block b is shorter than the train — place it again",
    ]);
  });

  it("says nothing for an empty list", async () => {
    const shell = await joined();
    await said(shell, "tc49/dispatch/state/unfit", { trains: [] });

    expect(unfit(shell)).toEqual([]);
    expect(running(shell).renderRoot.querySelector("header")).toBeNull();
  });

  it("drops a train's line when the list is republished without it", async () => {
    const shell = await joined();
    await said(shell, "tc49/dispatch/state/unfit", {
      trains: [{ train: "ore", block: "S3", why: "gone" }],
    });
    await said(shell, "tc49/dispatch/state/unfit", { trains: [] });

    expect(unfit(shell)).toEqual([]);
  });
});
