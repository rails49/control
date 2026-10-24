// @vitest-environment happy-dom

/**
 * The throttle view, end to end through the app (ui/THROTTLE.md, #207): take a
 * train from the picker (#853), drive it, give it back, and the gestures that
 * ride the bus while you do, in a row of throttles each holding at most one
 * train (ADR-0089).
 *
 * A DOM suite because none of it is a model's. What each train is, who holds
 * it and what it is reading are `cabs`'s answer, tested with no DOM in
 * `cabs.test.ts`; what only mounting the app can see is whether this view
 * asked — that taking a train writes one `take_wanted` under the panel's
 * throttle id, that the view waits for `state/taken` before it says a train is
 * taken, that a train another throttle holds is taken only once a person
 * confirms it (#967), that the number on screen is the number that went out,
 * and that nothing at all leaves the view while the rails have no power.
 *
 * The session is the app's whichever view is current, so this joins the
 * same one every other suite does (`support/session.ts`).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../src/ui/tc-app.js";
import type { TcApp } from "../src/ui/tc-app.js";
import { Session } from "../src/model/session.js";
import type { Cab } from "../src/model/throttle.js";
import type { TcDriving } from "../src/ui/tc-driving.js";
import type { TcTrainPicker } from "../src/ui/tc-train-picker.js";
import {
  serving,
  settled,
  shows,
  throttling,
  type Answers,
} from "./support/shell.js";
import {
  Broker,
  brokering,
  DERIVES,
  joined,
  said,
  STOCK,
  stored,
  unbrokered,
  written as everything,
} from "./support/session.js";
import { FakeLock } from "./support/wake.js";
import { STALL_MS } from "../src/model/picture.js";
import { photoUrl, pictureUrl, RETRY_MS, type Fn } from "../src/model/store.js";
import { drivingStyles, TRACK_PAD_PX } from "../src/ui/tc-driving.styles.js";

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
  return everything().filter(
    (one) => (one as { topic: string }).topic !== ALIVE,
  );
}
const THROTTLE_WANTED = "tc49/layout/throttle_wanted";

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

/** The driving controls of each train the view shows, in the order it
 *  shows them. */
function columns(shell: TcApp): TcDriving[] {
  return [
    ...throttling(shell).renderRoot.querySelectorAll<TcDriving>("tc-driving"),
  ];
}

/** One part of the view, by selector: the view's own, or else the first
 *  driving controls'. */
function part<T extends Element>(shell: TcApp, selector: string): T | null {
  return (
    throttling(shell).renderRoot.querySelector<T>(selector) ??
    columns(shell)[0]?.renderRoot.querySelector<T>(selector) ??
    null
  );
}

/** Every match for a selector, the view's own and in every driving column. */
function parts<T extends Element>(shell: TcApp, selector: string): T[] {
  return [
    ...throttling(shell).renderRoot.querySelectorAll<T>(selector),
    ...columns(shell).flatMap((one) => [
      ...one.renderRoot.querySelectorAll<T>(selector),
    ]),
  ];
}

/** The train selector, `null` while the view shows the driving controls
 *  alone. */
function picker(shell: TcApp): TcTrainPicker | null {
  return part<TcTrainPicker>(shell, "tc-train-picker");
}

/** One part of the picker, by selector. */
function onPicker<T extends Element>(shell: TcApp, selector: string): T | null {
  return picker(shell)?.renderRoot.querySelector<T>(selector) ?? null;
}

/** The trains the picker has a card for, in the order it shows them. */
function offered(shell: TcApp): string[] {
  return [
    ...(picker(shell)?.renderRoot.querySelectorAll(".card > span.name") ?? []),
  ].map((one) => one.textContent!.trim());
}

/** One train's card. */
function card(shell: TcApp, train: string): HTMLElement | null {
  return onPicker<HTMLElement>(shell, `.card[data-train="${train}"]`);
}

/** Press a train's card, the way a pointer does. */
async function taking(shell: TcApp, train: string): Promise<void> {
  card(shell, train)!.click();
  await settled(shell);
}

/** The press on the driving controls' picture, which opens the selector. */
function pictured(shell: TcApp): HTMLButtonElement | null {
  return columns(shell)[0]?.renderRoot.querySelector<HTMLButtonElement>(
    "button.view",
  ) ?? null;
}

/** Open the selector from the picture, where it is not open already. */
async function choosing(shell: TcApp): Promise<void> {
  if (picker(shell) !== null) return;
  pictured(shell)!.click();
  await settled(shell);
}

/** The selector's Release, the selector opened from the picture first. */
async function release(shell: TcApp): Promise<HTMLButtonElement> {
  await choosing(shell);
  return onPicker<HTMLButtonElement>(shell, "button.release")!;
}

/** One of the confirmation's two presses, `null` while it is not open. */
function asked(shell: TcApp, which: "cancel" | "confirmed"): HTMLButtonElement | null {
  return onPicker<HTMLButtonElement>(shell, `.confirm button.${which}`);
}

async function pressed(shell: TcApp, selector: string): Promise<void> {
  part<HTMLButtonElement>(shell, selector)!.click();
  await settled(shell);
}

/** The speed control, `null` while the view is not offering one. */
function lever(shell: TcApp): HTMLElement | null {
  return part<HTMLElement>(shell, ".track");
}

/** Where the slider stands, 0 to 1, as it says it does. */
function standing(track: HTMLElement): number {
  return Number(track.getAttribute("aria-valuenow"));
}

/** How tall a track is drawn here: happy-dom lays nothing out, so every
 *  track says it is this tall, which leaves `TRACK` pixels of travel. */
const TRACK = 200;
const TRACK_HEIGHT = TRACK + 2 * TRACK_PAD_PX;

/** Drag a track by `dy` pixels upward, the way a finger does: down, moved,
 *  up. A drag of 0 is a touch. */
async function dragged(
  shell: TcApp,
  track: HTMLElement,
  dy: number,
  pointerId = 1,
): Promise<void> {
  track.getBoundingClientRect = () =>
    ({ height: TRACK_HEIGHT, width: 100, top: 0, left: 0, right: 100, bottom: TRACK_HEIGHT, x: 0, y: 0 }) as DOMRect;
  const at = 300;
  track.dispatchEvent(new PointerEvent("pointerdown", { clientY: at, pointerId, bubbles: true }));
  if (dy !== 0) {
    track.dispatchEvent(new PointerEvent("pointermove", { clientY: at - dy, pointerId, bubbles: true }));
  }
  track.dispatchEvent(new PointerEvent("pointerup", { clientY: at - dy, pointerId, bubbles: true }));
  await settled(shell);
}

/** Move the first panel's slider to `to`, the way a hand does: a drag from
 *  where it stands by the distance that takes. */
async function moved(shell: TcApp, to: number): Promise<void> {
  const track = lever(shell)!;
  await dragged(shell, track, Math.round((to - standing(track)) * TRACK));
}

/** Which way the reverser is set, as the line under the speed says. */
function reverser(shell: TcApp): "forward" | "reverse" {
  const motion = part(shell, ".motion")!.textContent!.trim();
  expect(["Forward", "Reverse"]).toContain(motion);
  return motion === "Forward" ? "forward" : "reverse";
}

/** Set the reverser to Reverse, the slider at 0: the button under it. */
async function reversed(shell: TcApp): Promise<void> {
  expect(reverser(shell)).toBe("forward");
  await pressed(shell, "button.go.reverser");
  expect(reverser(shell)).toBe("reverse");
}

/** The throttle id the first panel named itself by, read off the first
 *  frame that carried it. */
function mine(): string {
  const frame = written().find(
    (one) =>
      typeof (one as { payload: { throttle?: unknown } }).payload.throttle ===
      "string",
  ) as { payload: { throttle: string } } | undefined;
  return frame!.payload.throttle;
}

/** The dispatcher's picture with `goods` granted the move from `a` to `b`:
 *  crossing the transit, the request behind it running its route. */
const GRANTED = {
  trains: { goods: "a" },
  crossing: { goods: "j.over" },
  locks: { a: "goods", "j.over": "goods", b: "goods" },
  requests: [
    {
      id: "goods-1",
      train: "goods",
      depart: "a.B",
      dest: ["b.A"],
      route: ["a", "j.over", "b"],
    },
  ],
};

/** A train, taken and nothing granted: the gesture and `layout`'s answer. */
async function held(shell: TcApp, train = "goods"): Promise<void> {
  await taking(shell, train);
  await said(shell, TAKEN, { taken: { [train]: mine() } });
}

/** `goods`, taken and granted a move: the gesture, `layout`'s answer on the
 *  state topic, and the picture with the move the lever is live within. */
async function taken(shell: TcApp): Promise<void> {
  await held(shell);
  await said(shell, ALLOCATION, GRANTED);
}

/** `shunter` placed beside `goods`, in `b`: two trains to pick from. */
const BOTH = {
  trains: { goods: "a", shunter: "b" },
  locks: { a: "goods", b: "shunter" },
  requests: [],
};

describe("the picker", () => {
  /** The trains the railroad has placed, and nothing else about the layout:
   *  `shunter` is on the roster and off the layout, so there is nothing here
   *  for a throttle to move (ADR-0039). */
  it("has a card for each train the run has placed, and no list", async () => {
    const shell = await driving();
    expect(offered(shell)).toEqual(["goods"]);

    await said(shell, ALLOCATION, BOTH);

    expect(offered(shell)).toEqual(["goods", "shunter"]);
    expect(part(shell, "nav.trains")).toBeNull();
    expect(lever(shell)).toBeNull();
    expect(picker(shell)!.renderRoot.textContent).toContain("Choose a train");
    expect(onPicker(shell, ".sub")!.textContent!.trim()).toBe(
      "2 trains on the layout",
    );
    expect(onPicker(shell, "button.close")).toBeNull();
  });

  it("says where each train stands", async () => {
    const shell = await driving();
    expect(
      card(shell, "goods")!.querySelector(".where")!.textContent!.trim(),
    ).toBe("at a");
    await said(shell, ALLOCATION, GRANTED);
    expect(
      card(shell, "goods")!.querySelector(".where")!.textContent!.trim(),
    ).toBe("crossing a transit");
  });

  it("shows the photo of each train's first locomotive", async () => {
    const shell = await driving();
    expect(
      card(shell, "goods")!.querySelector("img")!.getAttribute("src"),
    ).toBe("/catalogue/BR%20218/photo");
  });

  /** A model with no photo filed answers 404, and the name stands in, as it
   *  does for a train with no locomotive. */
  it("shows the train's name where the photo does not load or there is none", async () => {
    const shell = await driving();
    await said(shell, ALLOCATION, BOTH);

    card(shell, "goods")!
      .querySelector("img")!
      .dispatchEvent(new Event("error"));
    await settled(shell);

    for (const train of ["goods", "shunter"]) {
      expect(card(shell, train)!.querySelector("img")).toBeNull();
      expect(
        card(shell, train)!.querySelector(".thumbnail")!.textContent!.trim(),
      ).toBe(train);
    }
  });

  it("says so when no train is on the layout", async () => {
    const shell = await joined("throttle");
    await said(shell, POWER, { power: "on" });
    expect(picker(shell)!.renderRoot.textContent).toContain(
      "no train is on the layout — place one in the run view",
    );
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

    await taking(shell, "goods");

    const frames = written();
    expect(frames).toHaveLength(1);
    expect(frames[0]).toEqual({
      topic: TAKE_WANTED,
      payload: { train: "goods", throttle: mine() },
    });
    expect(mine()).not.toBe("");
  });

  /** The state topic is the truth about who holds a train: a view that showed
   *  the controls on its own press would put a person on a train `layout`
   *  never handed them (ADR-0035). A take `layout` drops changes nothing. */
  it("stays on the picker until state/taken names this throttle", async () => {
    const shell = await driving();

    await taking(shell, "goods");
    expect(offered(shell)).toEqual(["goods"]);
    expect(lever(shell)).toBeNull();

    await said(shell, TAKEN, { taken: { goods: mine() } });
    expect(picker(shell)).toBeNull();
    expect(lever(shell)).not.toBeNull();
    expect(part(shell, ".bar button")).toBeNull();
  });

  /** A throttle holds at most one train (ADR-0089); a row naming one id for
   *  several, which `layout` does not write, drives the first by name. */
  it("drives the first by name where it holds several", async () => {
    const shell = await driving();
    await said(shell, ALLOCATION, BOTH);
    await taking(shell, "goods");
    await said(shell, TAKEN, { taken: { shunter: mine(), goods: mine() } });
    expect(part(shell, ".chip.title")!.textContent!.trim()).toBe("goods");
  });
});

describe("a train another throttle holds", () => {
  it("is faded and says so, and has no Force release", async () => {
    const shell = await driving();
    await said(shell, TAKEN, { taken: { goods: "another-page" } });

    expect(card(shell, "goods")!.classList.contains("faded")).toBe(true);
    expect(card(shell, "goods")!.textContent).toContain(
      "held by another throttle",
    );
    expect(onPicker(shell, "button.force")).toBeNull();
    expect(picker(shell)!.renderRoot.textContent).not.toContain("Force release");
  });

  /** Taking it releases it where it is held, so a person is asked first —
   *  in the panel, not with `window.confirm`. */
  it("opens the dialog and writes nothing, and Cancel writes nothing", async () => {
    const shell = await driving();
    await said(shell, TAKEN, { taken: { goods: "another-page" } });

    await taking(shell, "goods");
    expect(onPicker(shell, ".confirm h3")!.textContent!.trim()).toBe(
      "Take goods?",
    );
    expect(onPicker(shell, ".confirm p")!.textContent).toContain(
      "Another throttle is driving this train.",
    );
    expect(written()).toEqual([]);

    asked(shell, "cancel")!.click();
    await settled(shell);
    expect(asked(shell, "confirmed")).toBeNull();
    expect(written()).toEqual([]);
  });

  /** The release, then the take, in that order: `layout` drops a take of a
   *  train another throttle holds. */
  it("is released there, then taken here, on Take train", async () => {
    const shell = await driving();
    await said(shell, TAKEN, { taken: { goods: "another-page" } });

    await taking(shell, "goods");
    asked(shell, "confirmed")!.click();
    await settled(shell);

    const frames = written();
    expect(frames).toHaveLength(2);
    expect(frames[0]).toEqual({
      topic: TAKE_WANTED,
      payload: { train: "goods", throttle: null },
    });
    expect(frames[1]).toEqual({
      topic: TAKE_WANTED,
      payload: { train: "goods", throttle: mine() },
    });
    expect(asked(shell, "confirmed")).toBeNull();
  });

  /** A throttle holds one train (ADR-0089): the panel's own train is given
   *  back before the chosen one is released there and taken here. */
  it("releases the panel's own train first, on Take train", async () => {
    const shell = await driving();
    await said(shell, ALLOCATION, BOTH);
    await held(shell, "shunter");
    await said(shell, TAKEN, {
      taken: { shunter: mine(), goods: "another-page" },
    });
    const before = written().length;
    await choosing(shell);

    await taking(shell, "goods");
    asked(shell, "confirmed")!.click();
    await settled(shell);

    expect(written().slice(before)).toEqual([
      { topic: TAKE_WANTED, payload: { train: "shunter", throttle: null } },
      { topic: TAKE_WANTED, payload: { train: "goods", throttle: null } },
      { topic: TAKE_WANTED, payload: { train: "goods", throttle: mine() } },
    ]);
  });
});

/** The selector opened from the picture of the train a panel holds (#967). */
describe("the train selector", () => {
  it("opens from the picture with a close button, and Close writes nothing", async () => {
    const shell = await driving();
    await held(shell);
    const before = written().length;

    await choosing(shell);
    expect(picker(shell)).not.toBeNull();
    expect(onPicker(shell, "button.close")).not.toBeNull();
    expect(lever(shell)).not.toBeNull();

    onPicker<HTMLButtonElement>(shell, "button.close")!.click();
    await settled(shell);
    expect(picker(shell)).toBeNull();
    expect(written().length).toBe(before);
  });

  it("outlines the panel's own train, and closes when it is pressed", async () => {
    const shell = await driving();
    await held(shell);
    const before = written().length;
    await choosing(shell);

    expect(card(shell, "goods")!.classList.contains("mine")).toBe(true);
    expect(card(shell, "goods")!.textContent).toContain("driving here");

    await taking(shell, "goods");
    expect(picker(shell)).toBeNull();
    expect(written().length).toBe(before);
  });

  /** A throttle holds one train (ADR-0089): the one held is given back
   *  before the next is taken. */
  it("releases the panel's train, then takes a free one, in that order", async () => {
    const shell = await driving();
    await said(shell, ALLOCATION, BOTH);
    await held(shell);
    const before = written().length;
    await choosing(shell);

    await taking(shell, "shunter");

    expect(written().slice(before)).toEqual([
      { topic: TAKE_WANTED, payload: { train: "goods", throttle: null } },
      { topic: TAKE_WANTED, payload: { train: "shunter", throttle: mine() } },
    ]);
  });

  /** The press is not the take: `state/taken` is (ADR-0035). */
  it("stays open after the press, and closes when state/taken names this panel for the train", async () => {
    const shell = await driving();
    await said(shell, ALLOCATION, BOTH);
    await held(shell);
    await choosing(shell);

    await taking(shell, "shunter");
    expect(picker(shell)).not.toBeNull();

    // A third throttle took it between the two frames: the take is dropped.
    await said(shell, TAKEN, { taken: { shunter: "another-page" } });
    expect(picker(shell)).not.toBeNull();

    await said(shell, TAKEN, { taken: { shunter: mine() } });
    expect(picker(shell)).toBeNull();
    expect(columns(shell)[0]!.cab!.train).toBe("shunter");
  });

  it("releases the panel's train with one null take_wanted", async () => {
    const shell = await driving();
    await held(shell);
    const before = written().length;

    const button = await release(shell);
    expect(button.textContent!.trim()).toBe("Release goods");
    button.click();
    await settled(shell);

    expect(written().slice(before)).toEqual([
      { topic: TAKE_WANTED, payload: { train: "goods", throttle: null } },
    ]);
  });

  it("has Release disabled, and no close button, with no train", async () => {
    const shell = await driving();
    const button = onPicker<HTMLButtonElement>(shell, "button.release")!;
    expect(button.disabled).toBe(true);
    expect(onPicker(shell, "button.close")).toBeNull();

    button.click();
    await settled(shell);
    expect(written()).toEqual([]);
  });
});

describe("the slider", () => {
  /** A throttle drives the train it holds at any time, granted move or not
   *  (ADR-0081). */
  it("drives a held train with no move outstanding", async () => {
    const shell = await driving();
    await held(shell);
    const before = written().length;

    expect(lever(shell)!.getAttribute("aria-disabled")).toBe("false");
    await moved(shell, 0.35);

    expect(written().slice(before)).toEqual([
      {
        topic: THROTTLE_WANTED,
        payload: { train: "goods", speed: 0.35, throttle: mine() },
      },
    ]);
  });

  /** Unsigned: which way is the reverser's. */
  it("runs from 0 at the bottom to 1 at the top", async () => {
    const shell = await driving();
    await held(shell);
    expect(lever(shell)!.getAttribute("role")).toBe("slider");
    expect(lever(shell)!.getAttribute("aria-valuemin")).toBe("0");
    expect(lever(shell)!.getAttribute("aria-valuemax")).toBe("1");
    expect(standing(lever(shell)!)).toBe(0);
  });

  /** A native range jumps to where it is touched; this one moves by the
   *  distance the finger travels over the track's usable height, so a
   *  touch moves nothing and a drag moves the value by as much, in
   *  hundredths. */
  it("moves by the distance dragged, in steps of 0.01, and not on a touch", async () => {
    const shell = await driving();
    await held(shell);
    const track = lever(shell)!;
    const before = written().length;

    await dragged(shell, track, 0);
    expect(written().length).toBe(before);
    expect(standing(track)).toBe(0);

    await dragged(shell, track, 2);
    expect(standing(track)).toBe(0.01);
    await dragged(shell, track, 1);
    expect(standing(track)).toBe(0.02);
    await dragged(shell, track, 70);
    expect(standing(track)).toBe(0.37);
    await dragged(shell, track, -20);
    expect(standing(track)).toBe(0.27);

    expect(
      written()
        .slice(before)
        .map((one) => (one as { payload: { speed: number } }).payload.speed),
    ).toEqual([0.01, 0.02, 0.37, 0.27]);
  });

  /** Held at the ends: a drag past the top is full speed, and back past the
   *  bottom is 0. */
  it("stops at 0 and at 1", async () => {
    const shell = await driving();
    await held(shell);
    const track = lever(shell)!;
    await dragged(shell, track, 3 * TRACK);
    expect(standing(track)).toBe(1);
    await dragged(shell, track, -3 * TRACK);
    expect(standing(track)).toBe(0);
  });

  it("moves a hundredth on the arrows and a tenth on PageUp and PageDown", async () => {
    const shell = await driving();
    await held(shell);
    const track = lever(shell)!;
    const key = async (key: string) => {
      track.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
      await settled(shell);
    };

    await key("PageUp");
    await key("PageUp");
    await key("ArrowUp");
    await key("ArrowDown");
    await key("ArrowDown");
    expect(standing(track)).toBe(0.19);
    await key("PageDown");
    await key("PageDown");
    expect(standing(track)).toBe(0);
  });

  /** The move ends at its sensor and `layout` writes `0.0` there, so the
   *  slider goes back to rest, and the reverser stays where the person put
   *  it. */
  it("goes to rest when the granted move ends, the reverser unchanged", async () => {
    const shell = await driving();
    await taken(shell);
    await reversed(shell);
    await moved(shell, 0.5);

    await said(shell, ALLOCATION, PICTURE);

    expect(standing(lever(shell)!)).toBe(0);
    expect(lever(shell)!.getAttribute("aria-disabled")).toBe("false");
    expect(reverser(shell)).toBe("reverse");
  });

  /** Only a move ending puts it to rest: a frame that changes something
   *  else about a train with no move leaves it where the hand left it. */
  it("stays where it was on a frame that leaves no move where there was none", async () => {
    const shell = await driving();
    await held(shell);
    await moved(shell, 0.35);
    expect(written().at(-1)).toMatchObject({ payload: { speed: 0.35 } });

    await said(shell, ALLOCATION, {
      ...PICTURE,
      requests: [
        { id: "goods-1", train: "goods", depart: "a.B", dest: ["b.A"] },
      ],
    });

    expect(standing(lever(shell)!)).toBe(0.35);
  });

  it("goes to rest when the track power reads off", async () => {
    const shell = await driving();
    await held(shell);
    await moved(shell, 0.35);

    await said(shell, POWER, { power: "off" });

    expect(standing(lever(shell)!)).toBe(0);
  });

  /** The marks every 5 %, those at or below the value lit. */
  it("has 21 marks, lit up to the value", async () => {
    const shell = await driving();
    await held(shell);
    expect(parts(shell, ".track .tick")).toHaveLength(21);
    await moved(shell, 0.35);
    expect(parts(shell, ".track .tick.lit")).toHaveLength(8);
  });

  it("reads as a whole percentage and which way the reverser is set", async () => {
    const shell = await driving();
    await held(shell);
    expect(part(shell, ".reading")!.textContent!.trim()).toBe("0%");
    expect(reverser(shell)).toBe("forward");

    await reversed(shell);
    await moved(shell, 0.35);
    expect(written().at(-1)).toMatchObject({ payload: { speed: -0.35 } });
    expect(part(shell, ".reading")!.textContent!.trim()).toBe("35%");
    expect(reverser(shell)).toBe("reverse");
  });
});

/**
 * The one button under the slider (#968), which is STOP while the slider is
 * above 0 and the reverser at 0: a reverser moves only with the lever at 0
 * (ADR-0084), so the two never want the same press.
 */
describe("the button under the slider", () => {
  it("publishes 0 above 0 and leaves the reverser", async () => {
    const shell = await driving();
    await held(shell);
    await reversed(shell);
    await moved(shell, 0.8);
    expect(part(shell, "button.go")!.getAttribute("aria-label")).toBe("Stop");

    await pressed(shell, "button.go");

    expect(written().at(-1)).toEqual({
      topic: THROTTLE_WANTED,
      payload: { train: "goods", speed: 0, throttle: mine() },
    });
    expect(standing(lever(shell)!)).toBe(0);
    expect(reverser(shell)).toBe("reverse");
  });

  /** The next slider input carries the new sign, and nothing before it. */
  it("flips the reverser at 0 and publishes nothing, the next move signed the other way", async () => {
    const shell = await driving();
    await held(shell);
    const before = written().length;

    await pressed(shell, "button.go");
    expect(reverser(shell)).toBe("reverse");
    await pressed(shell, "button.go");
    expect(reverser(shell)).toBe("forward");
    await pressed(shell, "button.go");

    expect(written().length).toBe(before);
    expect(reverser(shell)).toBe("reverse");
    await moved(shell, 0.35);
    expect(written().slice(before)).toEqual([
      {
        topic: THROTTLE_WANTED,
        payload: { train: "goods", speed: -0.35, throttle: mine() },
      },
    ]);
  });

  it("is the stop above 0 and the reverser at 0", async () => {
    const shell = await driving();
    await held(shell);
    expect(part(shell, "button.go.reverser")).not.toBeNull();
    await moved(shell, 0.2);
    expect(part(shell, "button.go.stop")).not.toBeNull();
    expect(part(shell, "button.go.reverser")).toBeNull();
  });

  it("is Forward on every take", async () => {
    const shell = await driving();
    await held(shell);
    await reversed(shell);

    await said(shell, TAKEN, { taken: {} });
    await held(shell);

    expect(reverser(shell)).toBe("forward");
  });
});

/** The signal a person reads is the one at the end the train would leave
 *  by, which the reverser decides (ADR-0025): a three-lamp head, green over
 *  red over amber. */
describe("the signal", () => {
  /** The lamps lit, top to bottom. */
  function lit(shell: TcApp): string[] {
    return parts(shell, ".signal .lamp.lit").map(
      (one) => [...one.classList].find((name) => name !== "lamp" && name !== "lit")!,
    );
  }

  it("has three lamps, green, red and amber from the top", async () => {
    const shell = await driving();
    await held(shell);
    expect(
      parts(shell, ".signal .lamp").map((one) => one.classList[1]),
    ).toEqual(["green", "red", "amber"]);
  });

  it("lights the aspect at the facing end at Forward and at the other at Reverse", async () => {
    const shell = await driving();
    await said(shell, FACING, { facing: { goods: "a.A-to-B" } });
    await said(shell, ASPECTS, {
      aspects: { "a.B": "caution", "a.A": "clear" },
    });
    await held(shell);
    expect(lit(shell)).toEqual(["green", "amber"]);

    await reversed(shell);
    expect(lit(shell)).toEqual(["green"]);

    await said(shell, ASPECTS, {
      aspects: { "a.B": "caution", "a.A": "stop" },
    });
    expect(lit(shell)).toEqual(["red"]);
  });

  it("lights nothing with no aspect", async () => {
    const shell = await driving();
    await held(shell);
    expect(lit(shell)).toEqual([]);
    expect(part(shell, ".signal")!.getAttribute("aria-label")).toBe(
      "no signal ahead",
    );
  });
});

/** Where the train is and where it is going: at, next and to. */
describe("the blocks", () => {
  /** The three rows' values, in order. */
  function rows(shell: TcApp): string[] {
    return ["at", "next", "to"].map(
      (row) => part(shell, `.blocks .block.${row}`)!.textContent!.trim(),
    );
  }

  /** A cab as the session would hand one in, with the blocks a test names:
   *  the toy railroad has none of these, and what the rows read is the
   *  component's alone. */
  async function mounted(cab: Partial<Cab>): Promise<TcDriving> {
    const controls = document.createElement("tc-driving");
    controls.cab = {
      train: "e10",
      block: "C2",
      holder: "here",
      granted: false,
      nose: null,
      aspect: null,
      tailAspect: null,
      locomotive: null,
      camera: false,
      ahead: [],
      functions: [],
      ...cab,
    };
    controls.throttle = "here";
    controls.power = "on";
    controls.linked = true;
    document.body.append(controls);
    await controls.updateComplete;
    return controls;
  }

  it("read at, next and to off the block and the road ahead", async () => {
    const controls = await mounted({
      ahead: [
        { block: "CE2", claim: "locked" },
        { block: "X", claim: "locked" },
        { block: "A2", claim: "committed" },
      ],
    });
    const row = (name: string) =>
      controls.renderRoot.querySelector(`.blocks .block.${name}`)!;
    expect(["at", "next", "to"].map((name) => row(name).textContent!.trim())).toEqual(
      ["C2", "CE2", "A2"],
    );
    expect(row("next").classList).toContain("locked");
    expect(row("to").classList).toContain("committed");
    controls.remove();
  });

  it("read the one block ahead as both next and to", async () => {
    const controls = await mounted({ ahead: [{ block: "CE2", claim: "committed" }] });
    const row = (name: string) =>
      controls.renderRoot.querySelector(`.blocks .block.${name}`)!.textContent!.trim();
    expect([row("next"), row("to")]).toEqual(["CE2", "CE2"]);
    controls.remove();
  });

  it("read crossing a transit with no block, and — with nothing ahead", async () => {
    const shell = await driving();
    await held(shell);
    expect(rows(shell)).toEqual(["a", "—", "—"]);

    await said(shell, ALLOCATION, {
      trains: { goods: "a" },
      crossing: { goods: "j.over" },
      locks: { a: "goods", "j.over": "goods" },
      requests: [],
    });
    expect(part(shell, ".blocks")!.textContent).toContain("crossing a transit");
  });
});

describe("the train's thumbnail", () => {
  it("is the photo of its first locomotive's model", async () => {
    const shell = await driving();
    await held(shell);
    expect(
      part<HTMLImageElement>(shell, "img.thumbnail")!.getAttribute("src"),
    ).toBe(photoUrl("BR 218"));
  });

  /** The name in a chip over the photo, Trains saying the picture opens the
   *  selector, and LIVE only once the camera car's picture shows. */
  it("has the train's name and Trains over it, and no LIVE", async () => {
    const shell = await driving();
    await held(shell);
    expect(part(shell, "button.view .chip.title")!.textContent!.trim()).toBe(
      "goods",
    );
    expect(part(shell, "button.view .chip.trains")!.textContent!.trim()).toBe(
      "Trains",
    );
    expect(part(shell, ".chip.live")).toBeNull();
  });

  /** The icon has the name under it, and no second name over it. */
  it("is a train and its name where there is no photo, with no name chip", async () => {
    const shell = await driving();
    await held(shell);
    part(shell, "img.thumbnail")!.dispatchEvent(new Event("error"));
    await settled(shell);

    expect(part(shell, ".thumbnail.name svg.icon")).not.toBeNull();
    expect(part(shell, ".thumbnail.name")!.textContent!.trim()).toBe("goods");
    expect(part(shell, ".chip.title")).toBeNull();
    expect(part(shell, ".chip.trains")).not.toBeNull();
  });

  /** A model with no photo filed answers 404, and the name stands in. */
  it("is the train's name where the photo does not load", async () => {
    const shell = await driving();
    await held(shell);

    part(shell, "img.thumbnail")!.dispatchEvent(new Event("error"));
    await settled(shell);

    expect(part(shell, "img.thumbnail")).toBeNull();
    expect(part(shell, ".thumbnail")!.textContent!.trim()).toBe("goods");
  });

  it("is the train's name where it has no locomotive", async () => {
    const shell = await driving();
    await said(shell, ALLOCATION, {
      trains: { shunter: "b" },
      locks: { b: "shunter" },
      requests: [],
    });
    await held(shell, "shunter");
    expect(part(shell, "img.thumbnail")).toBeNull();
    expect(part(shell, ".thumbnail")!.textContent!.trim()).toBe("shunter");
  });
});

/** The camera app's side of one read of its route: the path it was asked
 *  on, the frames a test sends down it, and whether the page aborted it. */
class Feed {
  aborted = false;
  readonly body: ReadableStream<Uint8Array>;
  private sending!: ReadableStreamDefaultController<Uint8Array>;

  constructor(
    readonly path: string,
    signal: AbortSignal,
  ) {
    this.body = new ReadableStream({
      start: (sending) => (this.sending = sending),
    });
    signal.addEventListener("abort", () => {
      this.aborted = true;
      this.fail();
    });
  }

  /** One part, as the camera app writes it. */
  send(): void {
    const jpeg = [0xff, 0xd8, 0xff, 0xd9];
    const head = `--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ${jpeg.length}\r\n\r\n`;
    this.sending.enqueue(
      new Uint8Array([...new TextEncoder().encode(head), ...jpeg, 13, 10]),
    );
  }

  /** The closing boundary, and the body over. */
  end(): void {
    this.sending.enqueue(new TextEncoder().encode("--frame--\r\n"));
    this.sending.close();
  }

  /** The connection gone, as a reset or an abort ends it. */
  fail(): void {
    try {
      this.sending.error(new Error("connection lost"));
    } catch {
      // already over
    }
  }
}

describe("the camera car's picture", () => {
  /** What the camera app has been asked, one read of its route each. */
  let feeds: Feed[] = [];

  /** What the shell answers, which a test may change between reads. */
  let answers: Answers;

  /** The toy roster with `goods` carrying a camera, as the trains route
   *  says (#850): `shunter` carries none. The camera app answers every read
   *  with a stream the test writes into, unless a test says otherwise. */
  beforeEach(() => {
    feeds = [];
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    answers = serving({
      drawings: ["toy"],
      rosterOf: () => ({ ...STOCK, goods: { ...STOCK.goods, camera: true } }),
      read: stored,
      review: () => Promise.resolve(DERIVES),
      picture: (path, signal) => {
        const feed = new Feed(path, signal);
        feeds.push(feed);
        return { status: 200, body: feed.body };
      },
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  /** The picture as drawn, `null` where the thumbnail shows alone. */
  function live(shell: TcApp): HTMLImageElement | null {
    return part<HTMLImageElement>(shell, "img.picture");
  }

  /** The thumbnail, the photo or the name, `null` while the picture is
   *  drawn in its place. */
  function thumbnail(shell: TcApp): Element | null {
    return part(shell, ".thumbnail");
  }

  /** The newest read of the route. */
  function feed(): Feed {
    return feeds.at(-1)!;
  }

  /** A frame sent on the newest read, and drawn. */
  async function framed(shell: TcApp): Promise<void> {
    feed().send();
    await settled(shell);
  }

  /** A train held here with a camera, on the view, its picture drawn. */
  async function watching(): Promise<TcApp> {
    const shell = await driving();
    await held(shell);
    await framed(shell);
    return shell;
  }

  /** In the thumbnail's place rather than over it, and shown whole (#956),
   *  with LIVE, the train's name and Trains laid over it (#968). */
  it("is drawn in the thumbnail's place once a frame comes, marked LIVE", async () => {
    const shell = await driving();
    await held(shell);
    expect(feeds.map((one) => one.path)).toEqual(["/picture/toy/goods"]);
    expect(live(shell)).toBeNull();
    expect(thumbnail(shell)).not.toBeNull();

    await framed(shell);

    expect(live(shell)!.getAttribute("src")).toMatch(/^blob:/);
    expect(live(shell)!.getAttribute("alt")).toBe("");
    expect(thumbnail(shell)).toBeNull();
    const view = part(shell, "button.view")!;
    expect([...view.children].map((one) => one.className)).toEqual([
      "picture",
      "chip live",
      "chip title",
      "chip trains",
    ]);
    const rules = drivingStyles.cssText
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .match(/[^{}]*\.picture[^{}]*\{[^{}]*\}/g);
    expect(rules?.some((rule) => /object-fit:\s*contain/.test(rule))).toBe(
      true,
    );
    expect(rules?.some((rule) => /position:\s*absolute/.test(rule))).toBe(
      false,
    );
    expect(part(shell, ".chip.live")!.textContent!.trim()).toBe("LIVE");
  });

  it("draws each frame as it comes", async () => {
    const shell = await watching();
    const first = live(shell)!.getAttribute("src");
    await framed(shell);
    expect(live(shell)!.getAttribute("src")).not.toBe(first);
  });

  it("names the railroad and the train, each URL-encoded", () => {
    expect(pictureUrl("my road", "a/b")).toBe("/picture/my%20road/a%2Fb");
    expect(pictureUrl("toy", "goods", 3)).toBe("/picture/toy/goods?try=3");
  });

  /** Track power does not matter: the picture is the train's, not a move's. */
  it("is drawn with the track off", async () => {
    const shell = await watching();
    await said(shell, POWER, { power: "off" });
    expect(live(shell)).not.toBeNull();
  });

  it("is not asked for for a train held here with no camera", async () => {
    const shell = await driving();
    await said(shell, ALLOCATION, BOTH);
    await held(shell, "shunter");
    expect(feeds).toEqual([]);
    expect(part(shell, ".live")).toBeNull();
    expect(thumbnail(shell)!.textContent!.trim()).toBe("shunter");
  });

  /** Held elsewhere or by nobody, the view is the picker, whose thumbnails
   *  are photos and never the camera's. */
  it.each([
    ["held elsewhere", { goods: "another-page" }],
    ["held by nobody", {}],
  ])("is not asked for for a train %s", async (_, holders) => {
    const shell = await driving();
    await said(shell, TAKEN, { taken: holders });
    expect(feeds).toEqual([]);
    expect(card(shell, "goods")!.querySelector("img.picture")).toBeNull();
    expect(card(shell, "goods")!.querySelector(".thumbnail")).not.toBeNull();
  });

  /** Each of these is the picture lost: the thumbnail alone, and the route
   *  asked again `RETRY_MS` later under a new `try`. An end and a stall fire
   *  no `error` on an image, which is why the page reads the stream (#950). */
  it.each([
    ["the stream ends", () => feed().end()],
    ["the connection fails", () => feed().fail()],
    ["no frame comes for STALL_MS", () => vi.advanceTimersByTime(STALL_MS)],
  ])(
    "goes when %s, and is back after RETRY_MS with a new try",
    async (_, lose) => {
      const shell = await watching();

      lose();
      await settled(shell);
      expect(live(shell)).toBeNull();
      expect(thumbnail(shell)).not.toBeNull();

      vi.advanceTimersByTime(RETRY_MS);
      await settled(shell);
      expect(feed().path).toBe("/picture/toy/goods?try=1");
      await framed(shell);
      expect(live(shell)).not.toBeNull();
    },
  );

  it("is asked again after RETRY_MS where the camera app answers no stream", async () => {
    answers.picture = () => ({ status: 502 });
    const shell = await driving();
    await held(shell);
    expect(live(shell)).toBeNull();

    answers.picture = (path, signal) => {
      const again = new Feed(path, signal);
      feeds.push(again);
      return { status: 200, body: again.body };
    };
    vi.advanceTimersByTime(RETRY_MS);
    await settled(shell);
    expect(feed().path).toBe("/picture/toy/goods?try=1");
  });

  it("is not asked again once the train is released", async () => {
    const shell = await watching();
    feed().end();
    await settled(shell);
    await said(shell, TAKEN, { taken: {} });

    vi.advanceTimersByTime(RETRY_MS);
    await settled(shell);
    expect(feeds).toHaveLength(1);
    expect(live(shell)).toBeNull();
  });

  /** Each of these ends the page's read of the route: the picture goes,
   *  and nothing puts it back. */
  it.each([
    [
      "state/taken drops the train",
      (shell: TcApp) => said(shell, TAKEN, { taken: {} }),
    ],
    [
      "another train is taken",
      async (shell: TcApp) => {
        await said(shell, ALLOCATION, BOTH);
        await said(shell, TAKEN, { taken: { shunter: mine() } });
      },
    ],
    [
      "the train leaves state/allocation",
      (shell: TcApp) =>
        said(shell, ALLOCATION, { trains: {}, locks: {}, requests: [] }),
    ],
    ["the run view is shown", (shell: TcApp) => shows(shell, "run")],
  ])("is gone once %s", async (_, then) => {
    const shell = await watching();
    expect(live(shell)).not.toBeNull();

    await then(shell);

    expect(live(shell)).toBeNull();
    expect(feed().aborted).toBe(true);
  });

  /** Back on the throttle view the train is still held, and the picture
   *  is asked for again. */
  it("is back when the throttle view is shown again", async () => {
    const shell = await watching();
    await shows(shell, "run");
    await shows(shell, "throttle");
    expect(feeds.map((one) => one.path)).toEqual([
      "/picture/toy/goods",
      "/picture/toy/goods",
    ]);
  });
});

/** Facing is the scheduler's, set where requests are composed, in the run
 *  view's menu: the throttle does not turn a train round (#968). */
describe("turning it round", () => {
  it("is not the throttle's: no Turn around, and no pressReversal", async () => {
    const shell = await driving();
    await held(shell);
    const said = parts(shell, "button").map((one) => one.textContent!.trim());
    expect(said).not.toContain("Turn around");
    expect(part(shell, "button.turn")).toBeNull();
    expect("pressReversal" in Session.prototype).toBe(false);
  });
});

describe("giving it back", () => {
  /** Back to the picker once `state/taken` no longer names this throttle,
   *  and not before: the release is `layout`'s to answer. */
  it("publishes take_wanted null and goes back to the picker, the train free to take", async () => {
    const shell = await driving();
    await taken(shell);
    await moved(shell, 0.5);

    (await release(shell)).click();
    await settled(shell);
    expect(written().at(-1)).toEqual({
      topic: TAKE_WANTED,
      payload: { train: "goods", throttle: null },
    });
    expect(lever(shell)).not.toBeNull();

    await said(shell, TAKEN, { taken: {} });

    expect(lever(shell)).toBeNull();
    expect(offered(shell)).toEqual(["goods"]);
    expect(card(shell, "goods")!.className).toBe("card free");
    expect(onPicker(shell, "button.close")).toBeNull();
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

    (await release(shell)).click();
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

    expect(standing(lever(shell)!)).toBe(0);
  });

  /** The train came off the layout under the person holding it. There is
   *  nothing for the lever to move, so the throttle is on no train rather
   *  than on the name of one that is gone. */
  it("lets go of a train the run takes off the layout", async () => {
    const shell = await driving();
    await taken(shell);

    await said(shell, ALLOCATION, { trains: {}, locks: {}, requests: [] });

    expect(offered(shell)).toEqual([]);
    expect(lever(shell)).toBeNull();
  });
});

describe("what a person can switch", () => {
  const FUNCTIONS = "tc49/layout/state/functions";
  const FUNCTION_WANTED = "tc49/layout/function_wanted";

  /** The toy roster with `goods` declaring these functions, by name, or by
   *  name and mode as the trains route gives them. */
  function declaring(...declared: (string | Fn)[]): void {
    serving({
      drawings: ["toy"],
      rosterOf: () => ({
        ...STOCK,
        goods: {
          ...STOCK.goods,
          functions: declared.map((one) =>
            typeof one === "string" ? { name: one } : one,
          ),
        },
      }),
      read: stored,
      review: () => Promise.resolve(DERIVES),
    });
  }

  /** The function buttons on screen, by name, in the order they show. */
  function buttons(shell: TcApp): string[] {
    return parts(shell, "button.function").map((one) =>
      one.textContent!.trim(),
    );
  }

  function button(shell: TcApp, name: string): HTMLButtonElement {
    return parts<HTMLButtonElement>(shell, "button.function").find(
      (one) => one.textContent!.trim() === name,
    )!;
  }

  /** The body of a rule of the driving controls' sheet, by its selector. */
  function rule(selector: string): string {
    const sheet = drivingStyles.cssText.replace(/\/\*[\s\S]*?\*\//g, "");
    const at = sheet.search(new RegExp(`(^|\\})\\s*${selector.replace(/[.]/g, "\\.")}\\s*\\{`));
    expect(at, `no rule for ${selector}`).not.toBe(-1);
    const body = sheet.slice(sheet.indexOf("{", at + 1) + 1);
    return body.slice(0, body.indexOf("}"));
  }

  /** The `function_wanted` frames the view's presses wrote. */
  function switched(): unknown[] {
    return written().filter(
      (one) => (one as { topic: string }).topic === FUNCTION_WANTED,
    );
  }

  /** By the names the catalogue gives them and by no number: which DCC
   *  function a name sits on is a decoder detail no view shows (ADR-0045). */
  it("draws the held train's functions, by catalogue name", async () => {
    const shell = await driving();
    await held(shell);
    expect(buttons(shell)).toEqual(["headlights", "vacuum"]);
  });

  it("draws no function for a train whose cars declare none", async () => {
    const shell = await driving();
    await said(shell, ALLOCATION, {
      trains: { shunter: "b" },
      locks: { b: "shunter" },
      requests: [],
    });
    await held(shell, "shunter");
    expect(buttons(shell)).toEqual([]);
  });

  /** Every one of them, two across, and no `>>` to open the rest: only the
   *  function area scrolls where they do not fit (#968). */
  it("shows all five of five, and no >>", async () => {
    declaring("headlights", "horn", "bell", "doors", "cab light");
    const shell = await driving();
    await held(shell);
    expect(buttons(shell)).toEqual([
      "headlights",
      "horn",
      "bell",
      "doors",
      "cab light",
    ]);
    expect(part(shell, "button.more")).toBeNull();
    expect(parts(shell, ".functions")).toHaveLength(1);
    expect(rule(".functions")).toMatch(/overflow-y:\s*auto/);
    expect(rule(".functions")).toMatch(/grid-template-columns:\s*1fr 1fr/);
    expect(rule("button.function")).toMatch(/min-height:\s*50px/);
  });

  /** The press asks; `layout` answers on `state/functions`, and only that
   *  moves the button (#849). */
  it("asks for on from an off button, and reads on only once state/functions says so", async () => {
    const shell = await driving();
    await held(shell);
    expect(button(shell, "headlights").getAttribute("aria-pressed")).toBe(
      "false",
    );

    button(shell, "headlights").click();
    await settled(shell);

    expect(switched()).toEqual([
      {
        topic: FUNCTION_WANTED,
        payload: {
          train: "goods",
          throttle: mine(),
          function: "headlights",
          on: true,
        },
      },
    ]);
    expect(button(shell, "headlights").getAttribute("aria-pressed")).toBe(
      "false",
    );

    await said(shell, FUNCTIONS, {
      functions: { goods: { headlights: true } },
    });
    expect(button(shell, "headlights").getAttribute("aria-pressed")).toBe(
      "true",
    );
  });

  it("asks for off from an on button", async () => {
    const shell = await driving();
    await held(shell);
    await said(shell, FUNCTIONS, { functions: { goods: { vacuum: true } } });

    button(shell, "vacuum").click();
    await settled(shell);

    expect(switched()).toEqual([
      {
        topic: FUNCTION_WANTED,
        payload: {
          train: "goods",
          throttle: mine(),
          function: "vacuum",
          on: false,
        },
      },
    ]);
  });

  /** `held` grants no move: the functions want only the hold. */
  it("switches a held train with no move granted", async () => {
    const shell = await driving();
    await held(shell);
    button(shell, "headlights").click();
    await settled(shell);
    expect(switched()).toHaveLength(1);
  });

  /** The `on` of each `function_wanted` the view wrote, in order. */
  function asks(): boolean[] {
    return switched().map(
      (one) => (one as { payload: { on: boolean } }).payload.on,
    );
  }

  function pointer(target: Element, type: string, pointerId = 1): void {
    target.dispatchEvent(new PointerEvent(type, { pointerId, bubbles: true }));
  }

  function key(target: Element, type: string, key: string, repeat = false): void {
    target.dispatchEvent(new KeyboardEvent(type, { key, repeat, bubbles: true }));
  }

  /** A horn: on while the finger is down, off when it lifts — and the
   *  click that follows the lift is no second press (#981). */
  it("holds a momentary function on while its button is held", async () => {
    declaring({ name: "horn", mode: "momentary" });
    const shell = await driving();
    await held(shell);
    const horn = button(shell, "horn");

    pointer(horn, "pointerdown");
    await settled(shell);
    expect(switched()).toEqual([
      {
        topic: FUNCTION_WANTED,
        payload: { train: "goods", throttle: mine(), function: "horn", on: true },
      },
    ]);

    pointer(horn, "pointerup");
    pointer(horn, "lostpointercapture");
    horn.click();
    await settled(shell);
    expect(asks()).toEqual([true, false]);
  });

  /** The button captures the pointer, so a finger sliding off ends the hold
   *  by losing the capture, and a cancelled touch ends it too. */
  it("lets a momentary function go on a pointer cancel or a lost capture", async () => {
    declaring({ name: "horn", mode: "momentary" });
    const shell = await driving();
    await held(shell);
    const horn = button(shell, "horn");

    pointer(horn, "pointerdown");
    pointer(horn, "pointercancel");
    pointer(horn, "pointerdown", 2);
    pointer(horn, "lostpointercapture", 2);
    await settled(shell);

    expect(asks()).toEqual([true, false, true, false]);
  });

  /** Space or Enter held on the focused button, the key's repeat ignored. */
  it("holds a momentary function on while Space or Enter is held", async () => {
    declaring({ name: "horn", mode: "momentary" });
    const shell = await driving();
    await held(shell);
    const horn = button(shell, "horn");

    key(horn, "keydown", " ");
    key(horn, "keydown", " ", true);
    key(horn, "keydown", " ", true);
    key(horn, "keyup", " ");
    key(horn, "keydown", "Enter");
    key(horn, "keyup", "Enter");
    key(horn, "keydown", "a");
    await settled(shell);

    expect(asks()).toEqual([true, false, true, false]);
  });

  /** It draws what `state/functions` says, as a latching button does. */
  it("draws a momentary button by state/functions and not by the press", async () => {
    declaring({ name: "horn", mode: "momentary" });
    const shell = await driving();
    await held(shell);

    pointer(button(shell, "horn"), "pointerdown");
    await settled(shell);
    expect(button(shell, "horn").getAttribute("aria-pressed")).toBe("false");

    await said(shell, FUNCTIONS, { functions: { goods: { horn: true } } });
    expect(button(shell, "horn").getAttribute("aria-pressed")).toBe("true");
  });

  /** `latching` said or nothing said: one press, one ask, the pointer's
   *  down and up asking nothing of their own. */
  it("latches a function whose mode is latching or absent", async () => {
    declaring({ name: "headlights", mode: "latching" }, "vacuum");
    const shell = await driving();
    await held(shell);

    for (const name of ["headlights", "vacuum"]) {
      const one = button(shell, name);
      pointer(one, "pointerdown");
      pointer(one, "pointerup");
      one.click();
    }
    await settled(shell);

    expect(
      switched().map((one) => (one as { payload: { function: string } }).payload.function),
    ).toEqual(["headlights", "vacuum"]);
    expect(asks()).toEqual([true, true]);
  });

  it("holds nothing on a momentary button over dead rails", async () => {
    declaring({ name: "horn", mode: "momentary" });
    const shell = await driving();
    await held(shell);
    await said(shell, POWER, { power: "off" });
    const horn = button(shell, "horn");

    pointer(horn, "pointerdown");
    pointer(horn, "pointerup");
    key(horn, "keydown", " ");
    key(horn, "keyup", " ");
    await settled(shell);

    expect(switched()).toEqual([]);
  });

  /** Each pressed, and not read off `disabled`: a press that writes nothing
   *  is the claim. A button let go of under the pointer — the train gone to
   *  another throttle or to none — is pressed where the person's finger
   *  already was. */
  it("writes nothing for a train held elsewhere or by nobody", async () => {
    const shell = await driving();
    await held(shell);
    const stale = button(shell, "headlights");

    await said(shell, TAKEN, { taken: { goods: "another-page" } });
    stale.click();
    await said(shell, TAKEN, { taken: {} });
    stale.click();
    await settled(shell);

    expect(switched()).toEqual([]);
  });

  it("writes nothing with the power off, and shows the state all the same", async () => {
    const shell = await driving();
    await held(shell);
    await said(shell, FUNCTIONS, {
      functions: { goods: { headlights: true } },
    });
    await said(shell, POWER, { power: "off" });

    button(shell, "headlights").click();
    button(shell, "vacuum").click();
    await settled(shell);

    expect(switched()).toEqual([]);
    expect(button(shell, "headlights").getAttribute("aria-pressed")).toBe(
      "true",
    );
  });

  it("writes nothing with no broker answering", async () => {
    const shell = await driving();
    await held(shell);
    const stale = button(shell, "headlights");

    Broker.last!.closes();
    await settled(shell);
    stale.click();
    await settled(shell);

    expect(switched()).toEqual([]);
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

    (await release(shell)).click();
    await settled(shell);
    onPicker<HTMLButtonElement>(shell, "button.close")!.click();
    await settled(shell);
    part<HTMLButtonElement>(shell, "button.go")!.click();
    await moved(shell, 0.7);
    const track = lever(shell)!;
    track.dispatchEvent(new KeyboardEvent("keydown", { key: "PageUp", bubbles: true }));
    await settled(shell);

    expect(written().length).toBe(before);
    expect(reverser(shell)).toBe("forward");
    expect(part(shell, ".still")!.textContent).toContain("draining");
    expect(part(shell, ".lower")!.classList).toContain("dead");
    expect(track.getAttribute("aria-disabled")).toBe("true");
  });

  it("says the supply is off where that is what it is", async () => {
    const shell = await driving();
    await held(shell);
    await said(shell, POWER, { power: "off" });
    expect(part(shell, ".still")!.textContent).toContain("no power");
    expect((await release(shell)).getAttribute("aria-disabled")).toBe("true");
  });

  /** In the selector: a card, Release and Take train publish nothing, and
   *  the reason is on screen. Checked by pressing, not by reading
   *  `disabled`: a press that got through would be a train moving. */
  it("takes nothing from the selector, and says why", async () => {
    const shell = await driving();
    await said(shell, ALLOCATION, {
      trains: { goods: "a", shunter: "b", coal: "c" },
      locks: { a: "goods", b: "shunter", c: "coal" },
      requests: [],
    });
    await held(shell, "shunter");
    await said(shell, TAKEN, { taken: { shunter: mine(), goods: "another-page" } });
    await choosing(shell);
    await taking(shell, "goods");
    expect(asked(shell, "confirmed")).not.toBeNull();
    await said(shell, POWER, { power: "off" });
    const before = written().length;

    asked(shell, "confirmed")!.click();
    for (const train of ["coal", "goods", "shunter"]) card(shell, train)!.click();
    onPicker<HTMLButtonElement>(shell, "button.release")!.click();
    await settled(shell);

    expect(written().length).toBe(before);
    expect(picker(shell)).not.toBeNull();
    expect(onPicker(shell, ".still")!.textContent).toContain("no power");
  });

  it("takes nothing on Take train with no broker answering", async () => {
    const shell = await driving();
    await said(shell, TAKEN, { taken: { goods: "another-page" } });
    await taking(shell, "goods");
    const before = everything().length;

    Broker.last!.closes();
    await settled(shell);
    asked(shell, "confirmed")!.click();
    await settled(shell);

    expect(everything().length).toBe(before);
  });

  /** A gesture into a socket that is not there is swallowed, so the view says
   *  so rather than letting a press look like it landed. A session that went
   *  takes the picture with it, exactly as it does in the run view. */
  it("is dead with no broker answering", async () => {
    const shell = await driving();

    Broker.last!.closes();
    await settled(shell);

    expect(offered(shell)).toEqual([]);
    expect(picker(shell)!.renderRoot.textContent).toContain(
      "no broker answering — is the bus running?",
    );
  });
});

/**
 * A row of throttles (ADR-0089): each a phone-sized panel with its own
 * throttle id and at most one train, as many across as the view's own width
 * fits (`panels`). A panel holding a train that no longer fits wraps; an
 * empty one is dropped.
 *
 * The width is the view's, read with a `ResizeObserver`, so the observer is
 * stood in for and told the width a test wants.
 */
describe("a row of throttles", () => {
  /** The observers the page has made, each with what it watches. */
  const watching: { report: ResizeObserverCallback; targets: Element[] }[] = [];

  class Watcher {
    private readonly entry: {
      report: ResizeObserverCallback;
      targets: Element[];
    };
    constructor(report: ResizeObserverCallback) {
      this.entry = { report, targets: [] };
      watching.push(this.entry);
    }
    observe(target: Element): void {
      this.entry.targets.push(target);
    }
    unobserve(target: Element): void {
      this.entry.targets = this.entry.targets.filter((one) => one !== target);
    }
    disconnect(): void {
      this.entry.targets = [];
    }
  }

  /** The throttle view laid out `width` pixels wide. Only the view is told:
   *  the other views' observers have nothing to do with it. */
  async function wide(shell: TcApp, width: number): Promise<void> {
    const view = throttling(shell);
    for (const { report, targets } of watching) {
      if (!targets.includes(view)) continue;
      const entry = {
        target: view,
        contentRect: { width, height: 700 },
      } as unknown as ResizeObserverEntry;
      report([entry], {} as ResizeObserver);
    }
    await settled(shell);
  }

  beforeEach(() => {
    watching.length = 0;
    vi.stubGlobal("ResizeObserver", Watcher);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  /** `goods` in `a`, `shunter` in `b` and `coal` in `c`. `coal` is on no
   *  roster: it is on the layout all the same, so it gets a cab. */
  const THREE = {
    trains: { goods: "a", shunter: "b", coal: "c" },
    locks: { a: "goods", b: "shunter", c: "coal" },
    requests: [],
  };

  /** The panels, in the order shown. */
  function panels(shell: TcApp): HTMLElement[] {
    return [
      ...throttling(shell).renderRoot.querySelectorAll<HTMLElement>(
        "section.panel",
      ),
    ];
  }

  /** What each panel shows: its train's name, or `picker`. */
  function shown(shell: TcApp): string[] {
    return panels(shell).map(
      (one) =>
        one.querySelector<TcDriving>("tc-driving")?.cab?.train ?? "picker",
    );
  }

  /** One panel's picker. */
  function pickerIn(panel: HTMLElement): TcTrainPicker {
    return panel.querySelector<TcTrainPicker>("tc-train-picker")!;
  }

  /** One train's card in one panel's picker. */
  function cardIn(panel: HTMLElement, train: string): HTMLElement {
    return pickerIn(panel).renderRoot.querySelector<HTMLElement>(
      `.card[data-train="${train}"]`,
    )!;
  }

  /** `train`'s card pressed in panel `at`, and the id it named. */
  async function takeIn(
    shell: TcApp,
    at: number,
    train: string,
  ): Promise<string> {
    const before = written().length;
    cardIn(panels(shell)[at]!, train).click();
    await settled(shell);
    const frame = written().slice(before)[0] as {
      payload: { throttle: string };
    };
    return frame.payload.throttle;
  }

  /** The app at `width` with `THREE` placed. */
  async function laid(width: number): Promise<TcApp> {
    const shell = await driving();
    await said(shell, ALLOCATION, THREE);
    await wide(shell, width);
    return shell;
  }

  it("at 758 px is two pickers, each taking under its own throttle id", async () => {
    const shell = await laid(758);
    expect(shown(shell)).toEqual(["picker", "picker"]);
    expect(panels(shell).map((one) => one.style.width)).toEqual([
      "361px",
      "361px",
    ]);

    const before = written().length;
    const second = await takeIn(shell, 1, "goods");
    expect(written().slice(before)).toEqual([
      { topic: TAKE_WANTED, payload: { train: "goods", throttle: second } },
    ]);
    const first = await takeIn(shell, 0, "shunter");
    expect(first).not.toBe(second);

    await said(shell, TAKEN, { taken: { goods: second } });

    expect(shown(shell)).toEqual(["picker", "goods"]);
    const held = cardIn(panels(shell)[0]!, "goods");
    expect(held.classList.contains("faded")).toBe(true);
    expect(held.textContent).toContain("held by another throttle");
    const sent = written().length;
    held.click();
    await settled(shell);
    expect(written().length).toBe(sent);
    expect(
      pickerIn(panels(shell)[0]!).renderRoot.querySelector(".confirm"),
    ).not.toBeNull();
  });

  it("at 390 px is one panel, exactly 390 px wide", async () => {
    const shell = await laid(390);
    expect(panels(shell)).toHaveLength(1);
    expect(panels(shell)[0]!.style.width).toBe("390px");
    expect(
      throttling(shell).renderRoot.querySelector("main.single"),
    ).not.toBeNull();
  });

  /** The panel is the size of a phone held upright: the view's height,
   *  clamped. */
  it("is as tall as the view, less the margin side by side", async () => {
    const shell = await laid(758);
    expect(panels(shell)[0]!.style.height).toBe("684px");
    await wide(shell, 390);
    expect(panels(shell)[0]!.style.height).toBe("700px");
  });

  /** Nothing is released because the view narrowed: the empty panel goes,
   *  the holding one stays. */
  it("narrowing 758 → 390 px keeps the panel holding a train, and publishes nothing", async () => {
    const shell = await laid(758);
    const second = await takeIn(shell, 1, "goods");
    await said(shell, TAKEN, { taken: { goods: second } });
    const driven = panels(shell)[1]!.querySelector("tc-driving");
    const before = written().length;

    await wide(shell, 390);

    expect(shown(shell)).toEqual(["goods"]);
    expect(panels(shell)[0]!.querySelector("tc-driving")).toBe(driven);
    expect(written().length).toBe(before);
  });

  it("narrowing 758 → 390 px with both holding keeps both, one below the other", async () => {
    const shell = await laid(758);
    const first = await takeIn(shell, 0, "shunter");
    const second = await takeIn(shell, 1, "goods");
    await said(shell, TAKEN, { taken: { shunter: first, goods: second } });
    const before = written().length;

    await wide(shell, 390);

    expect(shown(shell)).toEqual(["shunter", "goods"]);
    expect(
      throttling(shell).renderRoot.querySelector("main.single"),
    ).not.toBeNull();
    expect(written().length).toBe(before);
  });

  /** Widening again adds the lowest slots not shown, and so the ids they
   *  were minted under. */
  it("widening again adds an empty panel beside the one held", async () => {
    const shell = await laid(758);
    const second = await takeIn(shell, 1, "goods");
    await said(shell, TAKEN, { taken: { goods: second } });
    await wide(shell, 390);

    await wide(shell, 758);

    expect(shown(shell)).toEqual(["goods", "picker"]);
    expect(await takeIn(shell, 1, "coal")).not.toBe(second);
  });

  /** Every panel holding a train has its own clock. */
  it("gives each panel holding a train its own clock", async () => {
    const shell = await laid(1118);
    const first = await takeIn(shell, 0, "shunter");
    const second = await takeIn(shell, 1, "goods");
    await said(shell, TAKEN, { taken: { shunter: first, goods: second } });
    expect(parts(shell, "tc-clock")).toHaveLength(2);
  });

  it("drives each panel's train under its own id", async () => {
    const shell = await laid(758);
    const first = await takeIn(shell, 0, "shunter");
    const second = await takeIn(shell, 1, "goods");
    await said(shell, TAKEN, { taken: { shunter: first, goods: second } });
    const controls = (at: number) =>
      panels(shell)[at]!.querySelector<TcDriving>("tc-driving")!;
    const before = written().length;

    await dragged(
      shell,
      controls(1).renderRoot.querySelector<HTMLElement>(".track")!,
      0.3 * TRACK,
    );

    expect(written().slice(before)).toEqual([
      {
        topic: THROTTLE_WANTED,
        payload: { train: "goods", speed: 0.3, throttle: second },
      },
    ]);
  });

  /** A rotated phone keeps the train's controls where they were: recreated,
   *  they would show Forward under a train running tail first (#876). */
  it("keeps a train's controls, slider and reverser through a width change", async () => {
    const shell = await laid(390);
    const id = await takeIn(shell, 0, "goods");
    await said(shell, TAKEN, { taken: { goods: id } });
    const same = columns(shell)[0]!;
    same.renderRoot.querySelector<HTMLButtonElement>("button.go")!.click();
    await settled(shell);
    const speed = same.renderRoot.querySelector<HTMLElement>(".track")!;
    await dragged(shell, speed, 0.5 * TRACK);
    const before = written().length;

    await wide(shell, 1118);
    expect(columns(shell)[0]).toBe(same);
    await wide(shell, 390);
    expect(columns(shell)[0]).toBe(same);

    expect(standing(speed)).toBe(0.5);
    expect(reverser(shell)).toBe("reverse");
    expect(written().length).toBe(before);
  });
});

describe("the screen kept awake", () => {
  /** A `navigator.wakeLock` for the app to find, which happy-dom has not:
   *  set before the app mounts, since it reads it then. */
  let lock: FakeLock;

  function woken(): void {
    lock = new FakeLock();
    Object.defineProperty(navigator, "wakeLock", {
      value: lock,
      configurable: true,
    });
  }

  afterEach(() => {
    Reflect.deleteProperty(navigator, "wakeLock");
  });

  it("is asked for when state/taken names this throttle", async () => {
    woken();
    const shell = await driving();
    await taken(shell);
    expect(lock.requests).toBe(1);
    expect(lock.held).toBe(1);
  });

  /** A Force release from another throttle hands the train to it. */
  it("is let go when state/taken names another throttle for the train", async () => {
    woken();
    const shell = await driving();
    await taken(shell);
    expect(lock.held).toBe(1);

    await said(shell, TAKEN, { taken: { goods: "another-page" } });

    expect(lock.releases).toBe(1);
    expect(lock.held).toBe(0);
  });

  /** The session has no cabs with no broker, so nothing is held. */
  it("is let go when the broker closes", async () => {
    woken();
    const shell = await driving();
    await taken(shell);
    expect(lock.held).toBe(1);

    Broker.last!.closes();
    await settled(shell);

    expect(lock.held).toBe(0);
  });

  /** Take, drive, give back: what went out on the bus. */
  async function drove(): Promise<unknown[]> {
    const shell = await driving();
    await taken(shell);
    await moved(shell, 0.5);
    (await release(shell)).click();
    await settled(shell);
    await said(shell, TAKEN, { taken: {} });
    return written().map((one) => {
      const frame = one as { topic: string; payload: Record<string, unknown> };
      return "throttle" in frame.payload
        ? {
            ...frame,
            payload: {
              ...frame.payload,
              throttle: frame.payload.throttle && "mine",
            },
          }
        : frame;
    });
  }

  /** A browser with no wake lock changes nothing on the bus. */
  it("is not needed to drive", async () => {
    woken();
    const awake = await drove();
    unbrokered();
    brokering();
    Reflect.deleteProperty(navigator, "wakeLock");

    expect(await drove()).toEqual(awake);
    expect(awake.length).toBeGreaterThan(0);
  });
});
