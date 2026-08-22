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

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-app.js";
import { centreOf } from "../src/model/geometry.js";
import type { TcApp } from "../src/ui/tc-app.js";
import { band, bar, running, settled } from "./support/shell.js";
import {
  Bridge,
  bridging,
  joined,
  said,
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

describe("joining a session", () => {
  /** The run view names the session and the app holds the railroad, so the
   *  scenario's layout is asked for rather than read a second time (#167). */
  it("loads the railroad the scenario names", async () => {
    const shell = await joined();
    expect(Bridge.last!.url).toMatch(/toy\/test$/);
    const named = band(shell).renderRoot.querySelector(".drawing")!;
    expect(named.textContent!.trim()).toBe("toy");
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
