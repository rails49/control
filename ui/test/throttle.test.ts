// @vitest-environment happy-dom

/**
 * The throttle view, end to end through the app (ui/THROTTLE.md, #207): take a
 * train from the picker (#853), drive it, give it back, take it back, and the
 * gestures that ride the bus while you do.
 *
 * A DOM suite because none of it is a model's. What each train is, who holds
 * it and what it is reading are `cabs`'s answer, tested with no DOM in
 * `cabs.test.ts`; what only mounting the app can see is whether this view
 * asked — that taking a train writes one `take_wanted` under this page's
 * throttle id, that the view waits for `state/taken` before it says a train is
 * taken, that a train another throttle holds cannot be taken and can be
 * force released, that the train last held comes back as Take back, that the number on
 * screen is the number that went out, and that nothing at all leaves the view
 * while the rails have no power.
 *
 * The session is the app's whichever view is current, so this joins the
 * same one every other suite does (`support/session.ts`).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../src/ui/tc-app.js";
import type { TcApp } from "../src/ui/tc-app.js";
import type { TcDriving } from "../src/ui/tc-driving.js";
import type { TcTrainPicker } from "../src/ui/tc-train-picker.js";
import { serving, settled, shows, throttling, type Answers } from "./support/shell.js";
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
import { photoUrl, pictureUrl, RETRY_MS } from "../src/model/store.js";
import { drivingStyles } from "../src/ui/tc-driving.styles.js";

beforeEach(brokering);

afterEach(() => {
  unbrokered();
  sessionStorage.clear();
});

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

/** The driving controls of each train the view shows, in the order it
 *  shows them. */
function columns(shell: TcApp): TcDriving[] {
  return [...throttling(shell).renderRoot.querySelectorAll<TcDriving>("tc-driving")];
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
    ...columns(shell).flatMap((one) => [...one.renderRoot.querySelectorAll<T>(selector)]),
  ];
}

/** The picker, `null` while the view shows the driving controls. */
function picker(shell: TcApp): TcTrainPicker | null {
  return part<TcTrainPicker>(shell, "tc-train-picker");
}

/** One part of the picker, by selector. */
function onPicker<T extends Element>(shell: TcApp, selector: string): T | null {
  return picker(shell)?.renderRoot.querySelector<T>(selector) ?? null;
}

/** The trains the picker has a card for, in the order it shows them. */
function offered(shell: TcApp): string[] {
  return [...(picker(shell)?.renderRoot.querySelectorAll(".card > span.name") ?? [])].map(
    (one) => one.textContent!.trim(),
  );
}

/** One train's card. */
function card(shell: TcApp, train: string): HTMLElement | null {
  return onPicker<HTMLElement>(shell, `.card[data-train="${train}"]`);
}

/** The press on one train's card, by its class: `take`, `back` or `force`. */
function press(shell: TcApp, train: string, kind: string): HTMLButtonElement | null {
  return card(shell, train)?.querySelector<HTMLButtonElement>(`button.${kind}`) ?? null;
}

/** Press Take on a train's card, the way a pointer does. */
async function taking(shell: TcApp, train: string): Promise<void> {
  press(shell, train, "take")!.click();
  await settled(shell);
}

/** The driving controls' Release. */
function release(shell: TcApp): HTMLButtonElement {
  return part<HTMLButtonElement>(shell, "button.release")!;
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

/** Which way the reverser is pressed: the one press of the two that says so. */
function reverser(shell: TcApp): "forward" | "reverse" {
  const forward = part(shell, "button.forward")!.getAttribute("aria-pressed") === "true";
  const reverse = part(shell, "button.reverse")!.getAttribute("aria-pressed") === "true";
  expect(forward).not.toBe(reverse);
  return forward ? "forward" : "reverse";
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
    expect(picker(shell)!.renderRoot.textContent).toContain("Take a train");
  });

  it("says where each train stands", async () => {
    const shell = await driving();
    expect(card(shell, "goods")!.querySelector(".where")!.textContent!.trim()).toBe("a");
  });

  it("shows the photo of each train's first locomotive", async () => {
    const shell = await driving();
    expect(card(shell, "goods")!.querySelector("img")!.getAttribute("src")).toBe(
      "/catalogue/BR%20218/photo",
    );
  });

  /** A model with no photo filed answers 404, and the name stands in, as it
   *  does for a train with no locomotive. */
  it("shows the train's name where the photo does not load or there is none", async () => {
    const shell = await driving();
    await said(shell, ALLOCATION, BOTH);

    card(shell, "goods")!.querySelector("img")!.dispatchEvent(new Event("error"));
    await settled(shell);

    for (const train of ["goods", "shunter"]) {
      expect(card(shell, train)!.querySelector("img")).toBeNull();
      expect(card(shell, train)!.querySelector(".thumbnail")!.textContent!.trim()).toBe(train);
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
    expect(release(shell).textContent!.trim()).toBe("Release");
  });

  /** Several at once are #855's; until then, the first by name. */
  it("drives the first by name where it holds several", async () => {
    const shell = await driving();
    await said(shell, ALLOCATION, BOTH);
    await taking(shell, "goods");
    await said(shell, TAKEN, { taken: { shunter: mine(), goods: mine() } });
    expect(part(shell, ".bar h2")!.textContent!.trim()).toBe("goods");
  });
});

describe("a train another throttle holds", () => {
  /** `layout` drops a take of a train another throttle holds, so the picker
   *  does not offer one (ADR-0079). */
  it("is faded, says so, and has no Take", async () => {
    const shell = await driving();
    await said(shell, TAKEN, { taken: { goods: "another-page" } });

    expect(card(shell, "goods")!.classList.contains("faded")).toBe(true);
    expect(card(shell, "goods")!.textContent).toContain("held by another throttle");
    expect(press(shell, "goods", "take")).toBeNull();
  });

  /** The force release is the release: `null` frees the train whoever holds
   *  it (BUS.md, `take_wanted`). */
  it("is force released with take_wanted null, and then has Take", async () => {
    const shell = await driving();
    await said(shell, TAKEN, { taken: { goods: "another-page" } });

    press(shell, "goods", "force")!.click();
    await settled(shell);

    expect(written()).toEqual([
      { topic: TAKE_WANTED, payload: { train: "goods", throttle: null } },
    ]);

    await said(shell, TAKEN, { taken: {} });
    expect(card(shell, "goods")!.classList.contains("faded")).toBe(false);
    expect(press(shell, "goods", "take")).not.toBeNull();
    expect(press(shell, "goods", "force")).toBeNull();
  });
});

describe("taking it back", () => {
  /** The train this throttle held, freed: by its Release here. */
  async function heldThenFreed(shell: TcApp): Promise<void> {
    await held(shell);
    release(shell).click();
    await settled(shell);
    await said(shell, TAKEN, { taken: {} });
  }

  it("offers the last train first, as Take back, once nobody holds it", async () => {
    const shell = await driving();
    await said(shell, ALLOCATION, BOTH);
    await held(shell, "shunter");
    release(shell).click();
    await settled(shell);
    await said(shell, TAKEN, { taken: {} });
    const before = written().length;

    expect(offered(shell)).toEqual(["shunter", "goods"]);
    expect(card(shell, "shunter")!.textContent).toContain("You held this one");
    press(shell, "shunter", "back")!.click();
    await settled(shell);

    expect(written().slice(before)).toEqual([
      { topic: TAKE_WANTED, payload: { train: "shunter", throttle: mine() } },
    ]);
  });

  it("is an ordinary faded card while another throttle holds it", async () => {
    const shell = await driving();
    await heldThenFreed(shell);

    await said(shell, TAKEN, { taken: { goods: "another-page" } });

    expect(press(shell, "goods", "back")).toBeNull();
    expect(card(shell, "goods")!.classList.contains("faded")).toBe(true);
    expect(card(shell, "goods")!.textContent).not.toContain("You held this one");
  });

  it("has no card once the train is off the layout", async () => {
    const shell = await driving();
    await heldThenFreed(shell);

    await said(shell, ALLOCATION, { trains: {}, locks: {}, requests: [] });

    expect(offered(shell)).toEqual([]);
  });

  /** The same tab, a second app: `sessionStorage` carries the last train,
   *  and the new page's id is not the old one, so the old hold reads as
   *  another throttle's until it is freed. */
  it("is found by a second app in the same tab, once the train is free", async () => {
    const first = await driving();
    await held(first);
    const old = mine();
    unbrokered();
    brokering();

    const shell = await driving();
    await said(shell, TAKEN, { taken: { goods: old } });
    expect(press(shell, "goods", "back")).toBeNull();

    await said(shell, TAKEN, { taken: {} });
    expect(press(shell, "goods", "back")).not.toBeNull();
  });

  it("is not found by a second app with sessionStorage cleared", async () => {
    const first = await driving();
    await held(first);
    unbrokered();
    brokering();
    sessionStorage.clear();

    const shell = await driving();
    expect(press(shell, "goods", "back")).toBeNull();
    expect(press(shell, "goods", "take")).not.toBeNull();
  });

  /** Storage that throws leaves Take back to the page's own memory. */
  it("works for the life of the page where sessionStorage throws", async () => {
    const getItem = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("refused");
    });
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("refused");
    });
    try {
      const shell = await driving();
      await heldThenFreed(shell);
      expect(press(shell, "goods", "back")).not.toBeNull();
    } finally {
      getItem.mockRestore();
      setItem.mockRestore();
    }
  });
});

describe("the slider", () => {
  /** A throttle drives the train it holds at any time, granted move or not
   *  (ADR-0081). */
  it("drives a held train with no move outstanding", async () => {
    const shell = await driving();
    await held(shell);
    const before = written().length;

    expect(lever(shell)!.disabled).toBe(false);
    await moved(shell, 0.35);

    expect(written().slice(before)).toEqual([
      { topic: THROTTLE_WANTED, payload: { train: "goods", speed: 0.35, throttle: mine() } },
    ]);
  });

  /** Unsigned: which way is the reverser's. */
  it("runs from 0 at the bottom to 1 at the top", async () => {
    const shell = await driving();
    await held(shell);
    expect(lever(shell)!.min).toBe("0");
    expect(lever(shell)!.max).toBe("1");
  });

  /** The move ends at its sensor and `layout` writes `0.0` there, so the
   *  slider goes back to rest, and the reverser stays where the person put
   *  it. */
  it("goes to rest when the granted move ends, the reverser unchanged", async () => {
    const shell = await driving();
    await taken(shell);
    await pressed(shell, "button.reverse");
    await moved(shell, 0.5);

    await said(shell, ALLOCATION, PICTURE);

    expect(lever(shell)!.value).toBe("0");
    expect(lever(shell)!.disabled).toBe(false);
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
      requests: [{ id: "goods-1", train: "goods", depart: "a.B", dest: ["b.A"] }],
    });

    expect(lever(shell)!.value).toBe("0.35");
  });

  it("goes to rest when the track power reads off", async () => {
    const shell = await driving();
    await held(shell);
    await moved(shell, 0.35);

    await said(shell, POWER, { power: "off" });

    expect(lever(shell)!.value).toBe("0");
  });

  it("reads as a whole percentage and which end leads", async () => {
    const shell = await driving();
    await held(shell);
    expect(part(shell, ".reading")!.textContent!.trim()).toBe("0 %");
    expect(part(shell, ".motion")!.textContent!.trim()).toBe("at rest");

    await moved(shell, 0.35);
    expect(part(shell, ".motion")!.textContent!.trim()).toBe("nose first");

    await pressed(shell, "button.stop");
    await pressed(shell, "button.reverse");
    await moved(shell, 0.35);
    expect(written().at(-1)).toMatchObject({ payload: { speed: -0.35 } });
    expect(part(shell, ".reading")!.textContent!.trim()).toBe("35 %");
    expect(part(shell, ".motion")!.textContent!.trim()).toBe("tail first");
  });
});

describe("the reverser", () => {
  it("signs the slider's value: Reverse runs the train tail first", async () => {
    const shell = await driving();
    await held(shell);

    await pressed(shell, "button.reverse");
    await moved(shell, 0.35);

    expect(written().at(-1)).toEqual({
      topic: THROTTLE_WANTED,
      payload: { train: "goods", speed: -0.35, throttle: mine() },
    });
  });

  /** A flip at speed would reverse a rolling train (ADR-0084). */
  it("is dead with the slider off 0", async () => {
    const shell = await driving();
    await held(shell);
    await moved(shell, 0.35);

    expect(part<HTMLButtonElement>(shell, "button.forward")!.disabled).toBe(true);
    expect(part<HTMLButtonElement>(shell, "button.reverse")!.disabled).toBe(true);
  });

  /** The next slider input carries the new sign, and nothing before it. */
  it("sends nothing when switched", async () => {
    const shell = await driving();
    await held(shell);
    const before = written().length;

    await pressed(shell, "button.reverse");
    await pressed(shell, "button.forward");
    await pressed(shell, "button.reverse");

    expect(written().length).toBe(before);
    expect(reverser(shell)).toBe("reverse");
    await moved(shell, 0.35);
    expect(written().slice(before)).toEqual([
      { topic: THROTTLE_WANTED, payload: { train: "goods", speed: -0.35, throttle: mine() } },
    ]);
  });

  it("is Forward on every take", async () => {
    const shell = await driving();
    await held(shell);
    await pressed(shell, "button.reverse");

    await said(shell, TAKEN, { taken: {} });
    await held(shell);

    expect(reverser(shell)).toBe("forward");
  });

  /** STOP is the slider's, and leaves the way the train was going. */
  it("stays where it is through STOP", async () => {
    const shell = await driving();
    await held(shell);
    await pressed(shell, "button.reverse");
    await moved(shell, 0.8);

    await pressed(shell, "button.stop");

    expect(written().at(-1)).toEqual({
      topic: THROTTLE_WANTED,
      payload: { train: "goods", speed: 0, throttle: mine() },
    });
    expect(lever(shell)!.value).toBe("0");
    expect(reverser(shell)).toBe("reverse");
  });

  /** The signal a person reads is the one at the end the train would leave
   *  by, which the reverser decides (ADR-0025). */
  it("picks the aspect shown: the facing end's for Forward, the other's for Reverse", async () => {
    const shell = await driving();
    await said(shell, FACING, { facing: { goods: "a.A-to-B" } });
    await said(shell, ASPECTS, { aspects: { "a.B": "caution", "a.A": "clear" } });
    await held(shell);
    expect(part(shell, ".aspect")!.textContent!.trim()).toBe("caution");

    await pressed(shell, "button.reverse");

    expect(part(shell, ".aspect")!.textContent!.trim()).toBe("clear");
  });
});

describe("the train's thumbnail", () => {
  it("is the photo of its first locomotive's model", async () => {
    const shell = await driving();
    await held(shell);
    expect(part<HTMLImageElement>(shell, "img.thumbnail")!.getAttribute("src")).toBe(
      photoUrl("BR 218"),
    );
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
    this.body = new ReadableStream({ start: (sending) => (this.sending = sending) });
    signal.addEventListener("abort", () => {
      this.aborted = true;
      this.fail();
    });
  }

  /** One part, as the camera app writes it. */
  send(): void {
    const jpeg = [0xff, 0xd8, 0xff, 0xd9];
    const head = `--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ${jpeg.length}\r\n\r\n`;
    this.sending.enqueue(new Uint8Array([...new TextEncoder().encode(head), ...jpeg, 13, 10]));
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

  /** In the thumbnail's place rather than over it, so the picture's own
   *  frame sets the box and a short photo does not crop it (#953), with
   *  nothing laid over it but LIVE (#956). */
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
    const view = part(shell, ".top .view")!;
    expect([...view.children].map((one) => one.className)).toEqual(["picture", "live"]);
    const rules = drivingStyles.cssText
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .match(/[^{}]*\.picture[^{}]*\{[^{}]*\}/g);
    expect(rules?.some((rule) => /object-fit:\s*contain/.test(rule))).toBe(true);
    expect(rules?.some((rule) => /position:\s*absolute/.test(rule))).toBe(false);
    expect(part(shell, ".top .live")!.textContent!.trim()).toBe("LIVE");
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
  ])("goes when %s, and is back after RETRY_MS with a new try", async (_, lose) => {
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
  });

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
    ["state/taken drops the train", (shell: TcApp) => said(shell, TAKEN, { taken: {} })],
    [
      "another train is taken",
      async (shell: TcApp) => {
        await said(shell, ALLOCATION, BOTH);
        await said(shell, TAKEN, { taken: { shunter: mine() } });
      },
    ],
    [
      "the train leaves state/allocation",
      (shell: TcApp) => said(shell, ALLOCATION, { trains: {}, locks: {}, requests: [] }),
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
    expect(feeds.map((one) => one.path)).toEqual(["/picture/toy/goods", "/picture/toy/goods"]);
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
    expect(part(shell, ".reading")!.textContent!.trim()).toBe("60 %");
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

  /** A person driving by hand reads the signal, and this is where they read
   *  it (ADR-0025). */
  it("shows the aspect at the end the train would leave by", async () => {
    const shell = await driving();
    await said(shell, FACING, { facing: { goods: "a.A-to-B" } });
    await said(shell, ASPECTS, { aspects: { "a.B": "caution" } });
    await held(shell);
    expect(part(shell, ".aspect")!.textContent!.trim()).toBe("caution");
  });
});

describe("turning it round", () => {
  it("publishes reversal_wanted while the slider is at rest", async () => {
    const shell = await driving();
    await held(shell);

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
  /** Back to the picker once `state/taken` no longer names this throttle,
   *  and not before: the release is `layout`'s to answer. */
  it("publishes take_wanted null and goes back to the picker, the train first as Take back", async () => {
    const shell = await driving();
    await taken(shell);
    await moved(shell, 0.5);

    release(shell).click();
    await settled(shell);
    expect(written().at(-1)).toEqual({
      topic: TAKE_WANTED,
      payload: { train: "goods", throttle: null },
    });
    expect(picker(shell)).toBeNull();

    await said(shell, TAKEN, { taken: {} });

    expect(lever(shell)).toBeNull();
    expect(offered(shell)[0]).toBe("goods");
    expect(press(shell, "goods", "back")).not.toBeNull();
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

    release(shell).click();
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
    expect(lever(shell)).toBeNull();
  });
});

describe("what a person can switch", () => {
  const FUNCTIONS = "tc49/layout/state/functions";
  const FUNCTION_WANTED = "tc49/layout/function_wanted";

  /** The toy roster with `goods` declaring these functions, by name. */
  function declaring(...names: string[]): void {
    serving({
      drawings: ["toy"],
      rosterOf: () => ({
        ...STOCK,
        goods: { ...STOCK.goods, functions: names.map((name) => ({ name })) },
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
    return parts<HTMLButtonElement>(shell, "button.function").find((one) => one.textContent!.trim() === name)!;
  }

  function more(shell: TcApp): HTMLButtonElement | null {
    return part<HTMLButtonElement>(shell, "button.more");
  }

  /** The `function_wanted` frames the view's presses wrote. */
  function switched(): unknown[] {
    return written().filter((one) => (one as { topic: string }).topic === FUNCTION_WANTED);
  }

  /** By the names the catalogue gives them and by no number: which DCC
   *  function a name sits on is a decoder detail no view shows (ADR-0045). */
  it("draws the held train's functions, by catalogue name", async () => {
    const shell = await driving();
    await held(shell);
    expect(buttons(shell)).toEqual(["headlights", "vacuum"]);
  });

  it("draws no function and no >> for a train whose cars declare none", async () => {
    const shell = await driving();
    await said(shell, ALLOCATION, {
      trains: { shunter: "b" },
      locks: { b: "shunter" },
      requests: [],
    });
    await held(shell, "shunter");
    expect(buttons(shell)).toEqual([]);
    expect(more(shell)).toBeNull();
  });

  it("shows one or two with no >>", async () => {
    declaring("headlights");
    let shell = await driving();
    await held(shell);
    expect(buttons(shell)).toEqual(["headlights"]);
    expect(more(shell)).toBeNull();

    unbrokered();
    brokering();
    declaring("headlights", "horn");
    shell = await driving();
    await held(shell);
    expect(buttons(shell)).toEqual(["headlights", "horn"]);
    expect(more(shell)).toBeNull();
  });

  /** The first two always; `>>` opens the rest below, in the roster's
   *  order, and closes them again. */
  it("shows two of three and >>, which opens and closes the third", async () => {
    declaring("headlights", "horn", "bell");
    const shell = await driving();
    await held(shell);
    expect(buttons(shell)).toEqual(["headlights", "horn"]);

    more(shell)!.click();
    await settled(shell);
    expect(buttons(shell)).toEqual(["headlights", "horn", "bell"]);
    expect(part(shell, ".functions.rest")!.textContent).toContain("bell");

    more(shell)!.click();
    await settled(shell);
    expect(buttons(shell)).toEqual(["headlights", "horn"]);
  });

  it("closes >> when a train is taken", async () => {
    declaring("headlights", "horn", "bell");
    const shell = await driving();
    await held(shell);
    more(shell)!.click();
    await settled(shell);
    release(shell).click();
    await settled(shell);
    await said(shell, TAKEN, { taken: {} });
    await held(shell);
    expect(buttons(shell)).toEqual(["headlights", "horn"]);
  });

  /** The press asks; `layout` answers on `state/functions`, and only that
   *  moves the button (#849). */
  it("asks for on from an off button, and reads on only once state/functions says so", async () => {
    const shell = await driving();
    await held(shell);
    expect(button(shell, "headlights").getAttribute("aria-pressed")).toBe("false");

    button(shell, "headlights").click();
    await settled(shell);

    expect(switched()).toEqual([
      {
        topic: FUNCTION_WANTED,
        payload: { train: "goods", throttle: mine(), function: "headlights", on: true },
      },
    ]);
    expect(button(shell, "headlights").getAttribute("aria-pressed")).toBe("false");

    await said(shell, FUNCTIONS, { functions: { goods: { headlights: true } } });
    expect(button(shell, "headlights").getAttribute("aria-pressed")).toBe("true");
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
        payload: { train: "goods", throttle: mine(), function: "vacuum", on: false },
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
    await said(shell, FUNCTIONS, { functions: { goods: { headlights: true } } });
    await said(shell, POWER, { power: "off" });

    button(shell, "headlights").click();
    button(shell, "vacuum").click();
    await settled(shell);

    expect(switched()).toEqual([]);
    expect(button(shell, "headlights").getAttribute("aria-pressed")).toBe("true");
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

    release(shell).click();
    part<HTMLButtonElement>(shell, "button.stop")!.click();
    part<HTMLButtonElement>(shell, "button.turn")!.click();
    part<HTMLButtonElement>(shell, "button.reverse")!.click();
    await moved(shell, 0.7);
    await settled(shell);

    expect(written().length).toBe(before);
    expect(part(shell, ".still")!.textContent).toContain("draining");
  });

  it("says the supply is off where that is what it is", async () => {
    const shell = await driving();
    await held(shell);
    await said(shell, POWER, { power: "off" });
    expect(part(shell, ".still")!.textContent).toContain("no power");
    expect(release(shell).disabled).toBe(true);
  });

  /** On the picker: Take, Take back and Force release publish nothing, and
   *  the reason is on screen. */
  it("takes nothing from the picker, and says why", async () => {
    const shell = await driving();
    await said(shell, ALLOCATION, {
      trains: { goods: "a", shunter: "b" },
      locks: { a: "goods", b: "shunter" },
      requests: [],
    });
    await held(shell, "shunter");
    release(shell).click();
    await settled(shell);
    await said(shell, TAKEN, { taken: { goods: "another-page" } });
    await said(shell, POWER, { power: "off" });
    const before = written().length;

    for (const [train, kind] of [
      ["shunter", "back"],
      ["goods", "force"],
    ] as const) {
      expect(press(shell, train, kind)!.disabled).toBe(true);
      press(shell, train, kind)!.click();
    }
    await said(shell, TAKEN, { taken: {} });
    press(shell, "goods", "take")!.click();
    await settled(shell);

    expect(written().length).toBe(before);
    expect(onPicker(shell, ".still")!.textContent).toContain("no power");
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
 * A tablet drives several trains side by side (#855): one column of driving
 * controls per train this page holds, as many across as the view's own width
 * fits (`columns`), and a take column on the right with the page's one clock
 * and the trains to take. All of it under the page's one throttle id.
 *
 * The width is the view's, read with a `ResizeObserver`, so the observer is
 * stood in for and told the width a test wants.
 */
describe("side by side", () => {
  /** The observers the page has made, each with what it watches. */
  const watching: { report: ResizeObserverCallback; targets: Element[] }[] = [];

  class Watcher {
    private readonly entry: { report: ResizeObserverCallback; targets: Element[] };
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
      const entry = { target: view, contentRect: { width } } as unknown as ResizeObserverEntry;
      report([entry], {} as ResizeObserver);
    }
    await settled(shell);
  }

  beforeEach(() => {
    watching.length = 0;
    vi.stubGlobal("ResizeObserver", Watcher);
  });

  afterEach(() => {
    // Every frame these tests saw that names a throttle names this page's
    // one: there is no id per column.
    const ids = new Set(
      written()
        .map((one) => (one as { payload: { throttle?: unknown } }).payload.throttle)
        .filter((id) => typeof id === "string"),
    );
    expect(ids.size).toBeLessThanOrEqual(1);
    vi.unstubAllGlobals();
  });

  /** `goods` in `a`, `shunter` in `b` and `coal` in `c`. `coal` is on no
   *  roster: it is on the layout all the same, so it gets a cab. */
  const THREE = {
    trains: { goods: "a", shunter: "b", coal: "c" },
    locks: { a: "goods", b: "shunter", c: "coal" },
    requests: [],
  };

  /** The app at `width`, holding `trains` in the order `state/taken` first
   *  named this page for each. */
  async function holding(width: number, ...trains: string[]): Promise<TcApp> {
    const shell = await driving();
    await said(shell, ALLOCATION, THREE);
    await wide(shell, width);
    await taking(shell, trains[0]!);
    const taken: Record<string, string> = {};
    for (const train of trains) {
      taken[train] = mine();
      await said(shell, TAKEN, { taken: { ...taken } });
    }
    return shell;
  }

  /** The trains the view has driving controls for, in the order shown. */
  function driven(shell: TcApp): string[] {
    return columns(shell).map((one) => one.cab!.train);
  }

  /** One train's driving controls. */
  function column(shell: TcApp, train: string): TcDriving {
    return columns(shell).find((one) => one.cab?.train === train)!;
  }

  function within<T extends Element>(shell: TcApp, train: string, selector: string): T {
    return column(shell, train).renderRoot.querySelector<T>(selector)!;
  }

  /** The take column, `null` where the view has none. */
  function take(shell: TcApp): HTMLElement | null {
    return throttling(shell).renderRoot.querySelector<HTMLElement>("aside.take");
  }

  /** The trains the take column offers, in its order. */
  function listed(shell: TcApp): string[] {
    const list = take(shell)?.querySelector<TcTrainPicker>("tc-train-picker");
    return [...(list?.renderRoot.querySelectorAll(".card > span.name") ?? [])].map(
      (one) => one.textContent!.trim(),
    );
  }

  /** How many clocks the whole view draws. */
  function clocks(shell: TcApp): number {
    return parts(shell, "tc-clock").length;
  }

  const FULL = "no room for another train — release one";

  it("draws a column per train held, in the order taken, and one clock", async () => {
    const shell = await holding(1180, "goods", "coal");
    expect(driven(shell)).toEqual(["goods", "coal"]);
    expect(clocks(shell)).toBe(1);
    expect(take(shell)!.querySelector("tc-clock")).not.toBeNull();
    expect(take(shell)!.textContent).toContain("Take another train");
  });

  /** Not by name: `shunter` comes before `goods` only because it was taken
   *  first. */
  it("keeps the order state/taken first named this page for each", async () => {
    const shell = await holding(1180, "shunter", "goods");
    expect(driven(shell)).toEqual(["shunter", "goods"]);
  });

  /** The issue's 1180 px is two columns, which two trains fill: the list is
   *  read where there is room for it. */
  it("lists the other placed trains in the take column, as compact rows", async () => {
    const shell = await holding(1920, "goods", "coal");
    expect(listed(shell)).toEqual(["shunter"]);
    expect(take(shell)!.querySelector("tc-train-picker")!.hasAttribute("compact")).toBe(true);
  });

  it("STOP in one column stops that column's train only", async () => {
    const shell = await holding(1180, "goods", "coal");
    const before = written().length;

    within<HTMLButtonElement>(shell, "coal", "button.stop").click();
    await settled(shell);

    expect(written().slice(before)).toEqual([
      { topic: THROTTLE_WANTED, payload: { train: "coal", speed: 0, throttle: mine() } },
    ]);
  });

  it("moving one column's lever drives its train only", async () => {
    const shell = await holding(1180, "goods", "coal");
    const lever = (train: string) => within<HTMLInputElement>(shell, train, "input.speed");
    lever("goods").value = "0.3";
    lever("goods").dispatchEvent(new Event("input", { bubbles: true }));
    await settled(shell);
    const before = written().length;

    lever("coal").value = "0.6";
    lever("coal").dispatchEvent(new Event("input", { bubbles: true }));
    await settled(shell);

    expect(written().slice(before)).toEqual([
      { topic: THROTTLE_WANTED, payload: { train: "coal", speed: 0.6, throttle: mine() } },
    ]);
    expect(within(shell, "goods", ".reading").textContent!.trim()).toBe("30 %");
    expect(within(shell, "coal", ".reading").textContent!.trim()).toBe("60 %");
  });

  it("Release in one column gives that train back, and its column goes once taken back", async () => {
    const shell = await holding(1180, "goods", "coal");
    const before = written().length;

    within<HTMLButtonElement>(shell, "goods", "button.release").click();
    await settled(shell);

    expect(written().slice(before)).toEqual([
      { topic: TAKE_WANTED, payload: { train: "goods", throttle: null } },
    ]);
    expect(driven(shell)).toEqual(["goods", "coal"]);

    await said(shell, TAKEN, { taken: { coal: mine() } });

    expect(driven(shell)).toEqual(["coal"]);
    expect(listed(shell)).toContain("goods");
  });

  it("says there is no room, and offers no Take, once the columns are full", async () => {
    const shell = await holding(1180, "goods", "coal");
    expect(take(shell)!.textContent).toContain(FULL);
    expect(take(shell)!.querySelector("tc-train-picker")).toBeNull();
    expect(listed(shell)).toEqual([]);
  });

  it("at 820 px holding one, says there is no room", async () => {
    const shell = await holding(820, "goods");
    expect(take(shell)!.textContent).toContain(FULL);
  });

  /** A phone: no take column, and the train's own controls carry the clock. */
  it("at 390 px holding one, has no take column", async () => {
    const shell = await holding(390, "goods");
    expect(take(shell)).toBeNull();
    expect(driven(shell)).toEqual(["goods"]);
    expect(clocks(shell)).toBe(1);
    expect(within(shell, "goods", "tc-clock")).not.toBeNull();
  });

  /** Nothing is released or hidden because the view narrowed. */
  it("narrowing to a phone publishes nothing and shows both, one below the other", async () => {
    const shell = await holding(1180, "goods", "coal");
    const before = written().length;

    await wide(shell, 390);

    expect(written().length).toBe(before);
    expect(driven(shell)).toEqual(["goods", "coal"]);
    expect(take(shell)).toBeNull();
    expect(throttling(shell).renderRoot.querySelector("main.stacked")).not.toBeNull();
    // The first train's controls carry the clock, the others do not.
    expect(clocks(shell)).toBe(1);
    expect(within(shell, "goods", "tc-clock")).not.toBeNull();
  });

  /** Where one train's controls stand: its slider and its reverser. */
  function positions(shell: TcApp, train: string): { slider: string; reverse: boolean } {
    return {
      slider: within<HTMLInputElement>(shell, train, "input.speed").value,
      reverse: within(shell, train, "button.reverse").getAttribute("aria-pressed") === "true",
    };
  }

  /** Reverse pressed, then the slider moved: a train running tail first. */
  async function running(shell: TcApp, train: string, speed: number, reverse: boolean) {
    if (reverse) within<HTMLButtonElement>(shell, train, "button.reverse").click();
    await settled(shell);
    const lever = within<HTMLInputElement>(shell, train, "input.speed");
    lever.value = String(speed);
    lever.dispatchEvent(new Event("input", { bubbles: true }));
    await settled(shell);
  }

  /** A rotated phone keeps the train's controls where they were: recreated,
   *  they would show Forward under a train running tail first (#876). */
  it("keeps a train's controls, slider and reverser through a width change", async () => {
    const shell = await holding(390, "goods");
    await running(shell, "goods", 0.5, true);
    const before = written().length;
    const same = column(shell, "goods");

    await wide(shell, 844);
    expect(take(shell)).not.toBeNull();
    expect(column(shell, "goods")).toBe(same);
    expect(positions(shell, "goods")).toEqual({ slider: "0.5", reverse: true });

    await wide(shell, 390);
    expect(take(shell)).toBeNull();
    expect(column(shell, "goods")).toBe(same);
    expect(positions(shell, "goods")).toEqual({ slider: "0.5", reverse: true });
    expect(written().length).toBe(before);
  });

  it("keeps each train's positions on its own column through a phone and back", async () => {
    const shell = await holding(1180, "goods", "coal");
    await running(shell, "goods", 0.3, true);
    await running(shell, "coal", 0.6, false);

    await wide(shell, 390);
    await wide(shell, 1180);

    expect(driven(shell)).toEqual(["goods", "coal"]);
    expect(positions(shell, "goods")).toEqual({ slider: "0.3", reverse: true });
    expect(positions(shell, "coal")).toEqual({ slider: "0.6", reverse: false });
  });

  it("puts trains beyond the columns that fit on a further row", async () => {
    const shell = await holding(820, "goods", "coal");
    expect(driven(shell)).toEqual(["goods", "coal"]);
    const trains = throttling(shell).renderRoot.querySelector<HTMLElement>(".trains")!;
    expect(trains.style.getPropertyValue("--columns")).toBe("1");
  });

  it("is the picker, full width, while it holds no train", async () => {
    const shell = await driving();
    await wide(shell, 1920);
    expect(take(shell)).toBeNull();
    expect(picker(shell)!.hasAttribute("compact")).toBe(false);
  });
});

describe("the screen kept awake", () => {
  /** A `navigator.wakeLock` for the app to find, which happy-dom has not:
   *  set before the app mounts, since it reads it then. */
  let lock: FakeLock;

  function woken(): void {
    lock = new FakeLock();
    Object.defineProperty(navigator, "wakeLock", { value: lock, configurable: true });
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
    release(shell).click();
    await settled(shell);
    await said(shell, TAKEN, { taken: {} });
    return written().map((one) => {
      const frame = one as { topic: string; payload: Record<string, unknown> };
      return "throttle" in frame.payload
        ? { ...frame, payload: { ...frame.payload, throttle: frame.payload.throttle && "mine" } }
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
