// @vitest-environment happy-dom

/**
 * Holding the run and releasing it, end to end through the app: the bar draws
 * the word the dispatcher published, the press goes out on the socket the run
 * view holds, and a release with disputes outstanding says what was accepted
 * (ADR-0037, #152, #153).
 *
 * A DOM test because it crosses three components and the bridge. The session
 * itself — the toy railroad, the fake bridge and the app joined to it — is
 * `support/session.ts`, shared with the other suites that need one.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../src/ui/tc-app.js";
import type { Drawing } from "../src/model/drawing.js";
import { centreOf } from "../src/model/geometry.js";
import type { Explained, Layout } from "../src/model/store.js";
import type { TcApp } from "../src/ui/tc-app.js";
import { bridgeAt, RETRY_MS } from "../src/ui/tc-panel.js";
import {
  band,
  bar,
  CLEAN,
  mounted,
  running,
  serving,
  settled,
} from "./support/shell.js";
import {
  Bridge,
  bridging,
  DERIVES,
  joined,
  loads,
  said,
  STOCK,
  stored,
  unbridged,
  written,
} from "./support/session.js";

beforeEach(bridging);

afterEach(unbridged);

/** The HOLD/GO button on the bar. */
function press(shell: TcApp): HTMLButtonElement {
  return bar(shell).renderRoot.querySelector<HTMLButtonElement>("button.run")!;
}

/** What the run view is saying about the release, `null` while it says
 *  nothing. */
function notice(shell: TcApp): string | null {
  const said = running(shell).renderRoot.querySelector(".released");
  return said === null ? null : said.textContent!.trim();
}

/** What the band's health area is reporting, `null` while it reports
 *  nothing. */
function health(shell: TcApp): string | null {
  const said = band(shell).renderRoot.querySelector(".trouble");
  return said === null ? null : said.textContent!.trim();
}

/** What the band says about the bridge, `null` while it says nothing. The
 *  badge is drawn only while a session is joined, so a page that has let one
 *  go says nothing here rather than saying it is not connected. */
function link(shell: TcApp): string | null {
  const said = band(shell).renderRoot.querySelector(".link");
  return said === null ? null : said.textContent!.trim();
}

describe("where the bridge is", () => {
  /** A page served over TLS must ask for `wss://`. A plain `ws://` from it is
   *  mixed content, which the browser refuses outright, so the run view would
   *  never connect on the layout server at all (ADR-0042). */
  it("follows the page's own scheme", () => {
    expect(bridgeAt({ protocol: "https:", host: "layout.rails49.org", search: "" })).toBe(
      "wss://layout.rails49.org/live",
    );
    expect(bridgeAt({ protocol: "http:", host: "localhost:5173", search: "" })).toBe(
      "ws://localhost:5173/live",
    );
  });

  /** One path on the app's own origin either way: vite proxies it in
   *  development and the reverse proxy strips it in front of a layout server,
   *  so nothing in the panel knows which of the two it is talking to. */
  it("is a path on the page's own origin", () => {
    expect(bridgeAt({ protocol: "http:", host: "192.168.1.9:5173", search: "" })).toBe(
      "ws://192.168.1.9:5173/live",
    );
  });

  /** `?bridge=` is the whole of the browser's configuration, and it still
   *  names a session somewhere else outright (#148). */
  it("gives way to the one a query names", () => {
    expect(
      bridgeAt({
        protocol: "https:",
        host: "layout.rails49.org",
        search: "?bridge=ws://127.0.0.1:8766",
      }),
    ).toBe("ws://127.0.0.1:8766");
  });
});

describe("joining a session", () => {
  /** The loaded railroad is the session (#171): the band's picker loads it,
   *  the socket path names it, and there is no second choice to disagree
   *  with. */
  it("opens the socket on the railroad the band loaded", async () => {
    const shell = await joined();
    expect(Bridge.last!.url).toMatch(/\/toy$/);
    const named = band(shell).renderRoot.querySelector(".drawing")!;
    expect(named.textContent!.trim()).toBe("toy");
  });

  /** The bridge closes a client when the session switches railroads under one
   *  operator, and the process can simply go. The view has no session select
   *  to re-pick any more (#171) and the band says nothing about a railroad it
   *  is already showing, so the view lets the session go and tries it again
   *  itself — and a press in between must not pretend to have been heard:
   *  sending on a closed socket is discarded, not thrown. */
  it("lets the session go when the bridge closes it, and tries it again", async () => {
    vi.useFakeTimers();
    try {
      const shell = await joined();
      const dropped = Bridge.last!;
      await said(shell, "tc49/dispatch/state/run", { run: "held" });

      dropped.close();
      await settled(shell);

      running(shell).press("running");
      expect(written()).toEqual([]);
      expect(notice(shell)).toBeNull();

      await vi.advanceTimersByTimeAsync(RETRY_MS);
      await settled(shell);

      expect(Bridge.last).not.toBe(dropped);
      expect(Bridge.opened.filter((one) => !one.closed)).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });

  /** A press away and back while the store is still answering: the join the
   *  first press started must not go on to open a socket of its own. Two on
   *  one run applies every frame twice, and the older one's close would flip a
   *  live session to disconnected.
   *
   *  The roster reads are held open so the joins genuinely overlap — released
   *  one at a time, each press settles before the next and there is never a
   *  second join in flight to overtake. */
  it("leaves one socket open when the picker is pressed away and back", async () => {
    const shell = await mounted("run");
    const answering = globalThis.fetch;
    const holding: (() => void)[] = [];
    globalThis.fetch = ((path: string, init?: RequestInit) => {
      const answer = answering(path, init);
      if (!String(path).startsWith("/rosters/")) return answer;
      return new Promise((resolve) => holding.push(() => resolve(answer)));
    }) as typeof fetch;

    for (const railroad of ["toy", "other", "toy"]) {
      band(shell).dispatchEvent(
        new CustomEvent<string>("railroad-wanted", {
          detail: railroad,
          bubbles: true,
          composed: true,
        }),
      );
      await settled(shell);
    }
    expect(holding).toHaveLength(3);
    for (const release of holding) release();
    await settled(shell);

    expect(Bridge.opened.filter((one) => !one.closed)).toHaveLength(1);
    expect(Bridge.last!.url).toMatch(/\/toy$/);
  });

  /** The relay's one frame that is not an event: `{error}`, a gesture it will
   *  not carry or a socket path naming no railroad (#148). It is the only
   *  answer a gesture or a join ever gets when it goes wrong, so it is shown
   *  in the band rather than swallowed — and the session is not a session that
   *  ended, so the picture stays up and the button stays live. */
  it("shows what the session refused rather than swallowing it", async () => {
    const shell = await joined();
    await said(shell, "tc49/dispatch/state/run", { run: "held" });
    await said(shell, "tc49/dispatch/state/allocation", {
      trains: { goods: "a" },
      locks: { a: "goods" },
      requests: [],
    });

    Bridge.last!.raise("message", {
      data: JSON.stringify({ error: "cannot publish tc49/dispatch/request" }),
    });
    await settled(shell);

    expect(health(shell)).toBe("cannot publish tc49/dispatch/request");
    // Live and not merely labelled: the word and whether it can be pressed are
    // two bindings, and a refusal must move neither.
    expect(press(shell).textContent!.trim()).toBe("GO");
    expect(press(shell).disabled).toBe(false);
    expect(
      running(shell)
        .renderRoot.querySelector("tc-canvas")!
        .renderRoot.querySelector("text.name.train")!
        .textContent!.trim(),
    ).toBe("goods");
  });
});

/**
 * The session going away, and the page getting back into it on its own
 * ([#183](https://github.com/rails49/control/issues/183)).
 *
 * The loaded railroad *is* the session (#171), so a page with a railroad on it
 * wants to be joined to that railroad and there is nothing left for a person
 * to press: the view tries the same `join` every `RETRY_MS`, and only ever one
 * try. The interval is read off the module rather than written here, a suite
 * spelling 3000 being one that stops holding what the view does.
 *
 * Fake timers throughout: what is being held is which try happens, not how
 * long a suite is willing to sit.
 */
describe("trying a session that went away", () => {
  /** The toy railroad with its roster reads counted, and a switch for the
   *  store going quiet on that one route. One read is one try at the session:
   *  every way into one runs the same `join`, and the roster is what `join`
   *  asks the store for first. The other routes keep answering, so what stops
   *  is the try and not the railroad on screen. */
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

  /** The band's picker pressed on the railroad already loaded, which is what
   *  an operator watching a dropped page does. `loads` cannot serve here: it
   *  opens the socket the press produced, and a press that finds no store
   *  produces none. */
  async function picks(shell: TcApp, railroad: string): Promise<void> {
    band(shell).dispatchEvent(
      new CustomEvent<string>("railroad-wanted", {
        detail: railroad,
        bubbles: true,
        composed: true,
      }),
    );
    await settled(shell);
  }

  /** The process going: a browser fails the connection before it closes it,
   *  so the band has something to say while the session is gone. */
  function went(socket: Bridge): void {
    socket.raise("error", {});
    socket.close();
  }

  it("makes one try when the interval is up, on the railroad that is loaded", async () => {
    vi.useFakeTimers();
    try {
      const store = counting();
      const shell = await joined();
      const dropped = Bridge.last!;
      store.reads = 0;

      went(dropped);
      await settled(shell);

      // While it is gone the band drops the badge rather than saying the page
      // is not connected: the badge belongs to a joined session and the page
      // holds none. What stands is the trouble line, naming what to run.
      expect(link(shell)).toBeNull();
      expect(health(shell)).toBe(`no session at ${dropped.url} — run \`tc49 live\``);
      expect(store.reads).toBe(0);

      await vi.advanceTimersByTimeAsync(RETRY_MS);
      await settled(shell);

      expect(store.reads).toBe(1);
      expect(Bridge.last).not.toBe(dropped);
      expect(Bridge.last!.url).toMatch(/\/toy$/);

      Bridge.last!.raise("open", {});
      await settled(shell);
      expect(link(shell)).toBe("connected");
      expect(Bridge.opened.filter((one) => !one.closed)).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });

  /** Two things asking for a try inside one interval — the drop, and an
   *  operator pressing the picker on the name already showing, which was the
   *  way back in before this existed (#171). The second finds a try already
   *  waiting and leaves it there.
   *
   *  The store stays quiet throughout, which is what makes a second try
   *  visible at all: a try that gets in leaves nothing for a later one to do,
   *  so only a run of failing tries can be counted. The press lands a
   *  millisecond into the interval, so a try it scheduled of its own would
   *  come round a millisecond after the waiting one and be seen. */
  it("keeps one try waiting when a second is asked for inside the interval", async () => {
    vi.useFakeTimers();
    try {
      const store = counting();
      const shell = await joined();
      const dropped = Bridge.last!;
      store.answering = false;

      went(dropped);
      await settled(shell);
      await vi.advanceTimersByTimeAsync(1);
      await picks(shell, "toy");

      // The press is a try of its own, and it failed: the store is what is not
      // answering now, and the band says so.
      expect(health(shell)).toBe("the store is not answering — run `tc49 serve`");
      store.reads = 0;

      await vi.advanceTimersByTimeAsync(RETRY_MS);
      await settled(shell);

      // The one waiting try, and no second one behind it.
      expect(store.reads).toBe(1);
      expect(Bridge.opened.filter((one) => !one.closed)).toHaveLength(0);
    } finally {
      vi.useRealTimers();
    }
  });

  /** The picker getting in first. The try that was waiting still comes round,
   *  and a session joined by then is one it must leave alone: a second join
   *  would open a second socket on the same run. */
  it("does not try once a session has been joined another way", async () => {
    vi.useFakeTimers();
    try {
      const store = counting();
      const shell = await joined();
      store.reads = 0;

      went(Bridge.last!);
      await settled(shell);
      await loads(shell, "toy");
      expect(store.reads).toBe(1);
      expect(link(shell)).toBe("connected");

      await vi.advanceTimersByTimeAsync(RETRY_MS);
      await settled(shell);

      expect(store.reads).toBe(1);
      expect(Bridge.opened.filter((one) => !one.closed)).toHaveLength(1);
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
    expect(drawn.querySelector("text.name.train")!.textContent!.trim()).toBe(
      "goods",
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
   * grid square and a block's centre is the point to press at.
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
        topic: "tc49/ui/request_wanted",
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

  /** One of the bar's pinned buttons, by the command it carries. */
  function tool(shell: TcApp, label: string): HTMLButtonElement {
    return [...bar(shell).renderRoot.querySelectorAll<HTMLButtonElement>("button.tool")].find(
      (one) => one.getAttribute("aria-label")!.startsWith(label),
    )!;
  }

  it("fits the railroad it was handed, and zooms from the bar", async () => {
    const shell = await joined();
    // The two blocks span 0 to 8 across, so a fit frames at least that much.
    const [x, , w] = looking(shell);
    expect(x!).toBeLessThanOrEqual(0);
    expect(x! + w!).toBeGreaterThanOrEqual(8);

    tool(shell, "Zoom in").click();
    await settled(shell);
    expect(looking(shell)[2]).toBeLessThan(w!);

    tool(shell, "Fit").click();
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

describe("the word on the button", () => {
  it("is dead until the session says where the run stands", async () => {
    const shell = await joined();
    expect(press(shell).disabled).toBe(true);
  });

  it("offers GO on a held run and HOLD on a running one", async () => {
    const shell = await joined();

    await said(shell, "tc49/dispatch/state/run", { run: "held" });
    expect(press(shell).textContent!.trim()).toBe("GO");

    await said(shell, "tc49/dispatch/state/run", { run: "running" });
    expect(press(shell).textContent!.trim()).toBe("HOLD");
  });

  /** One press, no confirmation: a clearly labelled button is the explicit
   *  GO. */
  it("writes the gesture the word names", async () => {
    const shell = await joined();
    await said(shell, "tc49/dispatch/state/run", { run: "held" });

    press(shell).click();

    expect(written()).toEqual([
      { topic: "tc49/ui/run_wanted", payload: { run: "running" } },
    ]);
  });
});

/**
 * The layout's half of the same button (ADR-0041, #159). The dispatcher drops
 * a release while the rails are dead, so the page does not offer one — and the
 * band says which of the two ways of standing still it is, which is what the
 * person recovering acts on.
 */
describe("what the rails say about the button", () => {
  /** What the band says about power, `null` while it says nothing. */
  function supply(shell: TcApp): string | null {
    const said = band(shell).renderRoot.querySelector(".power");
    return said === null ? null : said.textContent!.trim();
  }

  it("greys GO and says why, and lets go of both when the power returns", async () => {
    const shell = await joined();
    await said(shell, "tc49/dispatch/state/run", { run: "held" });
    await said(shell, "tc49/layout/state/power", { power: "on" });
    expect(press(shell).disabled).toBe(false);
    expect(supply(shell)).toBe("power on");

    await said(shell, "tc49/layout/state/power", { power: "off" });
    expect(press(shell).textContent!.trim()).toBe("GO");
    expect(press(shell).disabled).toBe(true);
    expect(supply(shell)).toBe("power off");

    await said(shell, "tc49/layout/state/power", { power: "on" });
    expect(press(shell).disabled).toBe(false);
  });

  /** An emergency stop is the other word, and the band tells them apart. */
  it("names an emergency stop as one", async () => {
    const shell = await joined();
    await said(shell, "tc49/dispatch/state/run", { run: "held" });
    await said(shell, "tc49/layout/state/power", { power: "stopped" });

    expect(supply(shell)).toBe("emergency stop");
    expect(press(shell).disabled).toBe(true);
  });

  /** HOLD asks for less, and the dispatcher honours it whatever the supply is
   *  doing. */
  it("leaves HOLD pressable with the rails dead", async () => {
    const shell = await joined();
    await said(shell, "tc49/dispatch/state/run", { run: "running" });
    await said(shell, "tc49/layout/state/power", { power: "off" });

    expect(press(shell).textContent!.trim()).toBe("HOLD");
    expect(press(shell).disabled).toBe(false);

    press(shell).click();
    expect(written()).toEqual([
      { topic: "tc49/ui/run_wanted", payload: { run: "held" } },
    ]);
  });
});

/**
 * #153's other half. Releasing with disputes outstanding is allowed — the
 * person decides, not the check — and the panel says what is still disputed at
 * the moment of release. The amber marks go with the hold, so the words are
 * what is left of them.
 */
describe("releasing with disputes outstanding", () => {
  async function held(): Promise<TcApp> {
    const shell = await joined();
    await said(shell, "tc49/dispatch/state/run", { run: "held" });
    return shell;
  }

  it("says what is disputed, and lets the release through", async () => {
    const shell = await held();
    await said(shell, "tc49/dispatch/state/disputed", {
      trains: ["t1"],
      blocks: ["b"],
    });

    press(shell).click();
    await settled(shell);

    expect(notice(shell)).toBe(
      "released with t1 in a block that reads clear, b reads occupied",
    );
    expect(written()).toEqual([
      { topic: "tc49/ui/run_wanted", payload: { run: "running" } },
    ]);
  });

  it("says nothing where nothing is disputed", async () => {
    const shell = await held();
    await said(shell, "tc49/dispatch/state/disputed", { trains: [], blocks: [] });

    press(shell).click();
    await settled(shell);

    expect(notice(shell)).toBeNull();
  });

  /** The notice stands through the run it was a decision about, and a fresh
   *  hold is a fresh decision. Not the value but the transition: the run is
   *  still `held` between the press and the dispatcher's answer. */
  it("stands while that run runs, and goes with the next hold", async () => {
    const shell = await held();
    await said(shell, "tc49/dispatch/state/disputed", { trains: ["t1"], blocks: [] });
    press(shell).click();
    await settled(shell);

    await said(shell, "tc49/dispatch/state/run", { run: "running" });
    expect(notice(shell)).not.toBeNull();

    await said(shell, "tc49/dispatch/state/run", { run: "held" });
    expect(notice(shell)).toBeNull();
  });

  /** Holding is not a decision about anything outstanding. */
  it("says nothing when the run is held rather than released", async () => {
    const shell = await held();
    await said(shell, "tc49/dispatch/state/disputed", { trains: ["t1"], blocks: [] });
    await said(shell, "tc49/dispatch/state/run", { run: "running" });

    press(shell).click();
    await settled(shell);

    expect(notice(shell)).toBeNull();
  });
});
