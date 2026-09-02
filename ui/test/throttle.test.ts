// @vitest-environment happy-dom

/**
 * The throttle view, end to end through the app (ui/THROTTLE.md, #207): pick a
 * train, take it, drive it, give it back, and the two gestures that ride the
 * bus while you do.
 *
 * A DOM suite because none of it is a model's. What each train is, who drives
 * it and what it is reading are `cabs`'s answer, tested with no DOM in
 * `cabs.test.ts`; what only mounting the app can see is whether this view
 * asked — that taking a train writes one frame and not two, that the view
 * waits for `state/mode` before it says a train is taken, that the number on
 * screen is the number that went out, and that nothing at all leaves the view
 * while the rails have no power.
 *
 * The session is the run view's whichever view is current, so this joins the
 * same one every other suite does (`support/session.ts`).
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-app.js";
import type { TcApp } from "../src/ui/tc-app.js";
import { settled, shows, throttling } from "./support/shell.js";
import {
  Bridge,
  bridging,
  joined,
  said,
  unbridged,
  written,
} from "./support/session.js";

beforeEach(bridging);

afterEach(unbridged);

const ALLOCATION = "tc49/dispatch/state/allocation";
const POWER = "tc49/layout/state/power";
const MODE = "tc49/layout/state/mode";
const FACING = "tc49/schedule/state/facing";
const ASPECTS = "tc49/dispatch/state/aspects";

const MODE_WANTED = "tc49/layout/mode_wanted";
const THROTTLE_WANTED = "tc49/layout/throttle_wanted";
const REVERSAL_WANTED = "tc49/schedule/reversal_wanted";

/** The dispatcher's picture with `goods` standing in `a`. */
const PICTURE = { trains: { goods: "a" }, locks: { a: "goods" }, requests: [] };

/** An app in the throttle view, joined, with `goods` on the layout and the
 *  track live: what every test below starts from. */
async function driving(): Promise<TcApp> {
  const shell = await joined("throttle");
  await said(shell, ALLOCATION, PICTURE);
  await said(shell, POWER, { power: "on" });
  return shell;
}

/** One part of the view, by selector. */
function part<T extends Element>(shell: TcApp, selector: string): T | null {
  return throttling(shell).renderRoot.querySelector<T>(selector);
}

/** The trains the view offers, in the order it offers them. */
function offered(shell: TcApp): string[] {
  return [...throttling(shell).renderRoot.querySelectorAll("button.train .name")].map(
    (one) => one.textContent!.trim(),
  );
}

/** Pick a train, the way a pointer does. */
async function pick(shell: TcApp, train: string): Promise<void> {
  part<HTMLButtonElement>(shell, `button.train[data-train="${train}"]`)!.click();
  await settled(shell);
}

/** The one control that takes a train and gives it back. */
function take(shell: TcApp): HTMLButtonElement {
  return part<HTMLButtonElement>(shell, "button.take")!;
}

async function pressed(shell: TcApp, selector: string): Promise<void> {
  part<HTMLButtonElement>(shell, selector)!.click();
  await settled(shell);
}

/** The speed control, `null` while the view is not offering one. */
function lever(shell: TcApp): HTMLInputElement | null {
  return part<HTMLInputElement>(shell, "input.speed");
}

/** Move it, the way a hand does. */
async function moved(shell: TcApp, to: number): Promise<void> {
  const speed = lever(shell)!;
  speed.value = String(to);
  speed.dispatchEvent(new Event("input", { bubbles: true }));
  await settled(shell);
}

/** `goods`, taken: the gesture, and `layout`'s answer on the state topic. */
async function taken(shell: TcApp): Promise<void> {
  await pick(shell, "goods");
  take(shell).click();
  await settled(shell);
  await said(shell, MODE, { modes: { goods: "manual" } });
}

describe("picking a train", () => {
  /** The trains the railroad has placed, and nothing else about the layout:
   *  `shunter` is on the roster and off the layout, so there is nothing here
   *  for a throttle to move (ADR-0039). */
  it("offers the trains the run has placed", async () => {
    const shell = await driving();
    expect(offered(shell)).toEqual(["goods"]);
  });

  it("says to pick one before anything is picked", async () => {
    const shell = await driving();
    expect(part(shell, "button.take")).toBeNull();
    expect(throttling(shell).renderRoot.textContent).toContain("pick a train");
  });

  /** The throttle is a view of the app like the others, reached from the
   *  band's selector, and the session it draws is the one the run view
   *  joined (ADR-0038). */
  it("is reachable from the band without leaving the session", async () => {
    const shell = await joined();
    await said(shell, ALLOCATION, PICTURE);
    await shows(shell, "throttle");
    expect(offered(shell)).toEqual(["goods"]);
  });
});

describe("taking a train", () => {
  it("publishes exactly one mode_wanted naming that train and manual", async () => {
    const shell = await driving();
    await pick(shell, "goods");

    take(shell).click();
    await settled(shell);

    expect(written()).toEqual([
      { topic: MODE_WANTED, payload: { train: "goods", mode: "manual" } },
    ]);
  });

  /** The state topic is the truth about who is driving: a view that marked a
   *  train taken on its own press would show a person holding a train
   *  `layout` never handed them (ADR-0035). */
  it("shows the train as taken only when state/mode says so", async () => {
    const shell = await driving();
    await pick(shell, "goods");

    take(shell).click();
    await settled(shell);
    expect(take(shell).textContent!.trim()).toBe("Take");
    expect(lever(shell)).toBeNull();

    await said(shell, MODE, { modes: { goods: "manual" } });
    expect(take(shell).textContent!.trim()).toBe("Release");
    expect(lever(shell)).not.toBeNull();
  });

  /** A train another tab has taken reads as taken here too: *manual* is
   *  `layout`'s word about the train, not about this page. */
  it("marks a train the mode topic says is manual, whoever took it", async () => {
    const shell = await driving();
    await said(shell, MODE, { modes: { goods: "manual" } });
    expect(part(shell, "button.train .taken")!.textContent!.trim()).toBe("manual");
  });
});

describe("driving it", () => {
  it("publishes the value the lever shows", async () => {
    const shell = await driving();
    await taken(shell);

    await moved(shell, 0.6);

    expect(written().at(-1)).toEqual({
      topic: THROTTLE_WANTED,
      payload: { train: "goods", speed: 0.6 },
    });
    expect(part(shell, ".reading")!.textContent!.trim()).toBe("0.60");
  });

  /** `+` is the way the train points, so the same lever drives it either way
   *  along the track and the view sends one signed number for the train
   *  (CONTEXT.md, **Throttle**). */
  it("sends one signed number and never a direction", async () => {
    const shell = await driving();
    await taken(shell);

    await moved(shell, -0.4);

    expect(written().at(-1)).toEqual({
      topic: THROTTLE_WANTED,
      payload: { train: "goods", speed: -0.4 },
    });
  });

  /** Centre is stop, and it is the control a person reaches for when
   *  something is wrong, so it is one press and not a slide back through
   *  every speed between. */
  it("centres the lever in one gesture and publishes zero", async () => {
    const shell = await driving();
    await taken(shell);
    await moved(shell, 0.8);

    await pressed(shell, "button.stop");

    expect(written().at(-1)).toEqual({
      topic: THROTTLE_WANTED,
      payload: { train: "goods", speed: 0 },
    });
    expect(lever(shell)!.value).toBe("0");
  });

  /** The way the lever's `+` runs, drawn before anything moves: the
   *  scheduler's facing, which is the end the train would leave by. */
  it("shows which way the train points", async () => {
    const shell = await driving();
    await said(shell, FACING, { facing: { goods: "a.A-to-B" } });
    await pick(shell, "goods");
    expect(part(shell, ".facing")!.textContent).toContain("a.B");
  });

  /** A person driving by hand reads the signal, and this is where they read
   *  it (ADR-0025). */
  it("shows the aspect at the end the train would leave by", async () => {
    const shell = await driving();
    await said(shell, FACING, { facing: { goods: "a.A-to-B" } });
    await said(shell, ASPECTS, { aspects: { "a.B": "caution" } });
    await pick(shell, "goods");
    expect(part(shell, ".aspect")!.textContent!.trim()).toBe("caution");
  });
});

describe("turning it round", () => {
  it("publishes reversal_wanted while the lever is at rest", async () => {
    const shell = await driving();
    await taken(shell);

    await pressed(shell, "button.turn");

    expect(written().at(-1)).toEqual({
      topic: REVERSAL_WANTED,
      payload: { train: "goods" },
    });
  });

  /** Flipping the facing under a moving train would reverse it on the spot,
   *  so the control is offered only at zero. */
  it("is dead while the train is moving", async () => {
    const shell = await driving();
    await taken(shell);
    await moved(shell, 0.5);

    expect(part<HTMLButtonElement>(shell, "button.turn")!.disabled).toBe(true);

    await pressed(shell, "button.stop");
    expect(part<HTMLButtonElement>(shell, "button.turn")!.disabled).toBe(false);
  });
});

describe("giving it back", () => {
  it("publishes automatic and stops offering the speed control", async () => {
    const shell = await driving();
    await taken(shell);
    await moved(shell, 0.5);

    take(shell).click();
    await settled(shell);
    await said(shell, MODE, { modes: {} });

    expect(written().at(-1)).toEqual({
      topic: MODE_WANTED,
      payload: { train: "goods", mode: "automatic" },
    });
    expect(lever(shell)).toBeNull();
    expect(take(shell).textContent!.trim()).toBe("Take");
  });

  /** One gesture per press. `layout` writes the speed the train's current
   *  grant implies on the way back to automatic, so a zero of this view's own
   *  would be a second party deciding how fast the railroad drives it
   *  (SYSTEM.md, `layout`). */
  it("sends no speed of its own with the release", async () => {
    const shell = await driving();
    await taken(shell);
    await moved(shell, 0.5);
    const before = written().length;

    take(shell).click();
    await settled(shell);

    expect(written().length).toBe(before + 1);
  });

  /** Given back by another tab, or by `layout` itself: the lever is not a
   *  person's any more, and must not go on showing a speed nobody is asking
   *  for. */
  it("puts the lever back at rest when the train is released elsewhere", async () => {
    const shell = await driving();
    await taken(shell);
    await moved(shell, 0.5);

    await said(shell, MODE, { modes: {} });
    await said(shell, MODE, { modes: { goods: "manual" } });

    expect(lever(shell)!.value).toBe("0");
  });

  /** The train came off the layout under the person holding it. There is
   *  nothing for the lever to move, so the throttle is on no train rather
   *  than on the name of one that is gone. */
  it("lets go of a train the run takes off the layout", async () => {
    const shell = await driving();
    await taken(shell);

    await said(shell, ALLOCATION, { trains: {}, locks: {}, requests: [] });

    expect(offered(shell)).toEqual([]);
    expect(part(shell, "button.take")).toBeNull();
  });
});

describe("what a person can switch", () => {
  /** By the names the catalogue gives them and by no number: which DCC
   *  function a name sits on is a decoder detail no view shows (ADR-0045). */
  it("draws the selected train's functions, by catalogue name", async () => {
    const shell = await driving();
    await pick(shell, "goods");
    expect(
      [...throttling(shell).renderRoot.querySelectorAll("button.function")].map((one) =>
        one.textContent!.trim(),
      ),
    ).toEqual(["headlights", "vacuum"]);
  });

  it("draws none for a train whose cars declare none", async () => {
    const shell = await driving();
    await said(shell, ALLOCATION, {
      trains: { shunter: "b" },
      locks: { b: "shunter" },
      requests: [],
    });
    await pick(shell, "shunter");
    expect(throttling(shell).renderRoot.querySelectorAll("button.function")).toHaveLength(
      0,
    );
  });
});

describe("with the rails dead", () => {
  /** The view is disabled with the reason shown whenever `state/power` is not
   *  `on`, and the two ways of standing still ask for different actions by a
   *  person (ADR-0041). */
  it("sends nothing at all, and says why", async () => {
    const shell = await driving();
    await taken(shell);
    await said(shell, POWER, { power: "stopped" });
    const before = written().length;

    take(shell).click();
    part<HTMLButtonElement>(shell, "button.stop")!.click();
    part<HTMLButtonElement>(shell, "button.turn")!.click();
    await moved(shell, 0.7);
    await settled(shell);

    expect(written().length).toBe(before);
    expect(part(shell, ".still")!.textContent).toContain("emergency stop");
  });

  it("says the supply is off where that is what it is", async () => {
    const shell = await driving();
    await pick(shell, "goods");
    await said(shell, POWER, { power: "off" });
    expect(part(shell, ".still")!.textContent).toContain("no power");
    expect(take(shell).disabled).toBe(true);
  });

  /** A gesture into a socket that is not there is swallowed, so the view says
   *  so rather than letting a press look like it landed. A session that went
   *  takes the picture with it, exactly as it does in the run view. */
  it("is dead with no session joined", async () => {
    const shell = await driving();
    await pick(shell, "goods");

    Bridge.last!.close();
    await settled(shell);

    expect(offered(shell)).toEqual([]);
    expect(throttling(shell).renderRoot.textContent).toContain("no session");
  });
});
