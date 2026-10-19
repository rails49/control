// @vitest-environment happy-dom

/**
 * The throttle view, end to end through the app (ui/THROTTLE.md, #207): pick a
 * train, take it, drive it, give it back, and the two gestures that ride the
 * bus while you do.
 *
 * A DOM suite because none of it is a model's. What each train is, who holds
 * it and what it is reading are `cabs`'s answer, tested with no DOM in
 * `cabs.test.ts`; what only mounting the app can see is whether this view
 * asked — that taking a train writes one `take_wanted` under this page's
 * throttle id, that the view waits for `state/taken` before it says a train is
 * taken, that a train another throttle holds cannot be taken and can be
 * force released, that the lever is live only with a move granted, that the number on
 * screen is the number that went out, and that nothing at all leaves the view
 * while the rails have no power.
 *
 * The session is the app's whichever view is current, so this joins the
 * same one every other suite does (`support/session.ts`).
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-app.js";
import type { TcApp } from "../src/ui/tc-app.js";
import { settled, shows, throttling } from "./support/shell.js";
import {
  Broker,
  brokering,
  joined,
  said,
  unbrokered,
  written as everything,
} from "./support/session.js";

beforeEach(brokering);

afterEach(unbrokered);

const ALLOCATION = "tc49/dispatch/state/allocation";
const POWER = "tc49/layout/state/power";
const TAKEN = "tc49/layout/state/taken";
const FACING = "tc49/schedule/state/facing";
const ASPECTS = "tc49/dispatch/state/aspects";

const TAKE_WANTED = "tc49/layout/take_wanted";
const ALIVE = "tc49/layout/throttle_alive";

/** What the view's presses published. The session's `throttle_alive` beat
 *  runs on a real clock here and is left out; its timing is
 *  `session.test.ts`'s, on a fake one. */
function written(): unknown[] {
  return everything().filter((one) => (one as { topic: string }).topic !== ALIVE);
}
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

/** The throttle id this page named itself by, read off the first frame that
 *  carried it. */
function mine(): string {
  const frame = written().find(
    (one) => typeof (one as { payload: { throttle?: unknown } }).payload.throttle === "string",
  ) as { payload: { throttle: string } } | undefined;
  return frame!.payload.throttle;
}

/** The dispatcher's picture with `goods` granted the move from `a` to `b`:
 *  crossing the transit, the request behind it running its route. */
const GRANTED = {
  trains: { goods: "a" },
  crossing: { goods: "j.over" },
  locks: { a: "goods", "j.over": "goods", b: "goods" },
  requests: [{ id: "goods-1", train: "goods", depart: "a.B", dest: ["b.A"], route: ["a", "j.over", "b"] }],
};

/** `goods`, taken and granted a move: the gesture, `layout`'s answer on the
 *  state topic, and the picture with the move the lever is live within. */
async function taken(shell: TcApp): Promise<void> {
  await pick(shell, "goods");
  take(shell).click();
  await settled(shell);
  await said(shell, TAKEN, { taken: { goods: mine() } });
  await said(shell, ALLOCATION, GRANTED);
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
   *  band's selector, and the session it draws is the app's, the same one
   *  the run view paints from (ADR-0038). */
  it("is reachable from the band without leaving the session", async () => {
    const shell = await joined();
    await said(shell, ALLOCATION, PICTURE);
    await shows(shell, "throttle");
    expect(offered(shell)).toEqual(["goods"]);
  });
});

describe("taking a train", () => {
  it("publishes exactly one take_wanted naming that train and this throttle", async () => {
    const shell = await driving();
    await pick(shell, "goods");

    take(shell).click();
    await settled(shell);

    const frames = written();
    expect(frames).toHaveLength(1);
    expect(frames[0]).toEqual({
      topic: TAKE_WANTED,
      payload: { train: "goods", throttle: mine() },
    });
    expect(mine()).not.toBe("");
  });

  /** The state topic is the truth about who holds a train: a view that marked
   *  a train taken on its own press would show a person holding a train
   *  `layout` never handed them (ADR-0035). */
  it("shows the train as taken only when state/taken says so", async () => {
    const shell = await driving();
    await pick(shell, "goods");

    take(shell).click();
    await settled(shell);
    expect(take(shell).textContent!.trim()).toBe("Take");
    expect(lever(shell)).toBeNull();

    await said(shell, TAKEN, { taken: { goods: mine() } });
    expect(take(shell).textContent!.trim()).toBe("Release");
    expect(lever(shell)).not.toBeNull();
    expect(part(shell, "button.train .taken")!.textContent!.trim()).toBe("yours");
  });
});

describe("a train another throttle holds", () => {
  /** `layout` drops a take of a train another throttle holds, so the view
   *  does not offer one, and says the train is taken (ADR-0079). */
  it("shows as taken and cannot be taken", async () => {
    const shell = await driving();
    await said(shell, TAKEN, { taken: { goods: "another-page" } });
    await pick(shell, "goods");

    expect(part(shell, "button.train .taken")!.textContent!.trim()).toBe("taken");
    expect(take(shell).disabled).toBe(true);
    take(shell).click();
    await settled(shell);
    expect(written()).toEqual([]);
    expect(lever(shell)).toBeNull();
  });

  /** The force release is the release: `null` frees the train whoever holds
   *  it (BUS.md, `take_wanted`). */
  it("is force released with take_wanted null", async () => {
    const shell = await driving();
    await said(shell, TAKEN, { taken: { goods: "another-page" } });
    await pick(shell, "goods");

    await pressed(shell, "button.force");

    expect(written()).toEqual([
      { topic: TAKE_WANTED, payload: { train: "goods", throttle: null } },
    ]);
  });
});

describe("the lever and the move", () => {
  /** `layout` applies a throttle's speed only within a granted move, so the
   *  lever is live only then (ADR-0079). */
  it("is dead until the train has a move outstanding", async () => {
    const shell = await driving();
    await pick(shell, "goods");
    take(shell).click();
    await settled(shell);
    await said(shell, TAKEN, { taken: { goods: mine() } });
    const before = written().length;

    expect(lever(shell)!.disabled).toBe(true);
    await moved(shell, 0.5);
    expect(written().length).toBe(before);

    await said(shell, ALLOCATION, GRANTED);
    expect(lever(shell)!.disabled).toBe(false);
  });

  /** The move ends at its sensor and `layout` writes `0.0` there, so the
   *  lever goes back to rest and dead with it. */
  it("goes to rest when the move ends at its sensor", async () => {
    const shell = await driving();
    await taken(shell);
    await moved(shell, 0.5);

    await said(shell, "tc49/layout/block_occupied", { block: "b" });

    expect(lever(shell)!.value).toBe("0");
    expect(lever(shell)!.disabled).toBe(true);
  });
});

describe("driving it", () => {
  it("publishes the value the lever shows", async () => {
    const shell = await driving();
    await taken(shell);

    await moved(shell, 0.6);

    expect(written().at(-1)).toEqual({
      topic: THROTTLE_WANTED,
      payload: { train: "goods", speed: 0.6, throttle: mine() },
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
      payload: { train: "goods", speed: -0.4, throttle: mine() },
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
      payload: { train: "goods", speed: 0, throttle: mine() },
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
    await pick(shell, "goods");
    take(shell).click();
    await settled(shell);
    await said(shell, TAKEN, { taken: { goods: mine() } });

    await pressed(shell, "button.turn");

    expect(written().at(-1)).toEqual({
      topic: REVERSAL_WANTED,
      payload: { train: "goods" },
    });
  });

  /** Flipping the facing under a moving train would reverse it on the spot,
   *  so the control is offered only at zero, and not while the move it is
   *  making is still in flight: a train stopped on the transit stands
   *  between two blocks. */
  it("is dead while the train is moving", async () => {
    const shell = await driving();
    await taken(shell);
    await moved(shell, 0.5);

    expect(part<HTMLButtonElement>(shell, "button.turn")!.disabled).toBe(true);

    await pressed(shell, "button.stop");
    expect(part<HTMLButtonElement>(shell, "button.turn")!.disabled).toBe(true);

    await said(shell, "tc49/layout/block_occupied", { block: "b" });
    await said(shell, ALLOCATION, { trains: { goods: "b" }, locks: { b: "goods" }, requests: [] });
    expect(part<HTMLButtonElement>(shell, "button.turn")!.disabled).toBe(false);
  });
});

describe("giving it back", () => {
  it("publishes take_wanted null and stops offering the speed control", async () => {
    const shell = await driving();
    await taken(shell);
    await moved(shell, 0.5);

    take(shell).click();
    await settled(shell);
    await said(shell, TAKEN, { taken: {} });

    expect(written().at(-1)).toEqual({
      topic: TAKE_WANTED,
      payload: { train: "goods", throttle: null },
    });
    expect(lever(shell)).toBeNull();
    expect(take(shell).textContent!.trim()).toBe("Take");
  });

  /** One gesture per press. `layout` writes the speed a release implies, so
   *  a zero of this view's own
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

  /** Force released by another tab, or by `layout` itself: the lever is not
   *  a person's any more, and must not go on showing a speed nobody is asking
   *  for. */
  it("puts the lever back at rest when the train is released elsewhere", async () => {
    const shell = await driving();
    await taken(shell);
    await moved(shell, 0.5);

    await said(shell, TAKEN, { taken: {} });
    await said(shell, TAKEN, { taken: { goods: mine() } });

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
   *  `on`, and a drain asks a person to switch it back on (ADR-0078). */
  it("sends nothing at all, and says why", async () => {
    const shell = await driving();
    await taken(shell);
    await said(shell, POWER, { power: "draining" });
    const before = written().length;

    take(shell).click();
    part<HTMLButtonElement>(shell, "button.stop")!.click();
    part<HTMLButtonElement>(shell, "button.turn")!.click();
    await moved(shell, 0.7);
    await settled(shell);

    expect(written().length).toBe(before);
    expect(part(shell, ".still")!.textContent).toContain("draining");
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
  it("is dead with no broker answering", async () => {
    const shell = await driving();
    await pick(shell, "goods");

    Broker.last!.closes();
    await settled(shell);

    expect(offered(shell)).toEqual([]);
    expect(throttling(shell).renderRoot.textContent).toContain(
      "no broker answering — is the bus running?",
    );
  });
});
