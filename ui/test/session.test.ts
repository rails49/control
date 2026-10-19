/**
 * The session, driven by the broker alone (#756): frames in off the broker
 * double, frames out onto it, and nothing mounted.
 *
 * The OFF drain is a small state machine with a history (#406, #441), and its
 * rules are here rather than behind the band: OFF asks the run to drain,
 * watches `tc49/dispatch/state/run` reach `held` with `moving` false, and
 * removes the supply only then (ADR-0062, ADR-0074). The wait is dropped by
 * news about the run word and not by news about `moving`: a row whose word has
 * *changed* to `running` is a drain somebody abandoned, where one repeating
 * the word the press was made against is the drain still outstanding. A row
 * that says nothing about `moving` never ends the wait. `power.test.ts` keeps
 * the presses end to end through the band.
 *
 * Beside it: HOLD and GO with the release notice (#153), nothing published
 * while the broker is not answering but the railroad press it owes (#803), the
 * rows held until the documents land, a row naming no railroad (#727), and
 * `status` and `cabs` keeping their identity across a frame that moves
 * neither — which is what keeps the app from redrawing on every frame.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ALIVE_MS, HELD, Session, type Client } from "../src/model/session.js";
import { Broker, DERIVES, RAILROAD, STOCK, stored } from "./support/session.js";

const URL = "ws://localhost:5173/mqtt";

const POWER_WANTED = "tc49/layout/power_wanted";
const RUN_WANTED = "tc49/dispatch/run_wanted";
const STATE_RUN = "tc49/dispatch/state/run";
const STATE_POWER = "tc49/layout/state/power";
const DISPUTED = "tc49/dispatch/state/disputed";
const ALLOCATION = "tc49/dispatch/state/allocation";

/** A session over the broker double, and what it told the app. `answering`
 *  says whether the app hands the documents back as soon as the row names a
 *  railroad, which is what a store that answers at once looks like from
 *  here. */
interface Stood {
  session: Session;
  broker: Broker;
  names: string[];
  answering: boolean;
}

function standing(): Stood {
  const stood = { names: [] as string[], answering: true } as Stood;
  stood.session = new Session(URL, (url): Client => new Broker(url), {
    notify: () => {},
    named: (railroad) => {
      stood.names.push(railroad);
      if (stood.answering) answer(stood, railroad);
    },
  });
  stood.broker = Broker.last!;
  return stood;
}

/** The app handing over the documents of the railroad the row named, or none
 *  for a row naming none. */
function answer(stood: Stood, railroad: string): void {
  if (railroad === "") stood.session.documents(null, null, {});
  else stood.session.documents(stored(railroad), DERIVES, STOCK);
}

/** A session joined to the toy railroad, the broker answering. */
function joined(): Stood {
  const stood = standing();
  stood.broker.retains(RAILROAD, { name: "toy" });
  stood.broker.opens();
  return stood;
}

/** A joined session whose supply stands at `on`, as the station has said. */
function powered(): Stood {
  const stood = joined();
  stood.broker.says(STATE_POWER, { power: "on" });
  return stood;
}

/** What the session published, each payload parsed. */
function written(stood: Stood): unknown[] {
  return stood.broker.published.map(({ topic, payload }) => ({
    topic,
    payload: JSON.parse(payload) as unknown,
  }));
}

const DRAIN = { topic: RUN_WANTED, payload: { run: "draining" } };
const CUT = { topic: POWER_WANTED, payload: { power: "off" } };

beforeEach(() => {
  Broker.last = null;
  Broker.opened = [];
});

describe("OFF is the drain trigger", () => {
  /** OFF asks for a drain from a held run too: it is the moving that decides,
   *  and a person's HOLD writes `held` with trains still rolling. */
  it("asks a held run to drain and waits while it is moving", () => {
    const stood = powered();
    stood.broker.says(STATE_RUN, { run: "held", moving: true });

    stood.session.pressPower("off");
    expect(written(stood)).toEqual([DRAIN]);

    stood.broker.says(STATE_RUN, { run: "held", moving: false });

    expect(written(stood)).toEqual([DRAIN, CUT]);
  });

  /** The dispatcher answering a held run with `held` publishes no frame, so
   *  the wait would never end — and there is nothing left to drain anyway. */
  it("removes it at once where the run is held and nothing moves", () => {
    const stood = powered();
    stood.broker.says(STATE_RUN, { run: "held", moving: false });

    stood.session.pressPower("off");

    expect(written(stood)).toEqual([DRAIN, CUT]);
    expect(stood.session.status.draining).toBe(false);
  });

  /** An older dispatcher publishes the word alone, and a row that says
   *  nothing about what is under way never lets this button cut. */
  it("never cuts on a row that says nothing about moving", () => {
    const stood = powered();
    stood.broker.says(STATE_RUN, { run: "running", moving: true });
    stood.session.pressPower("off");

    stood.broker.says(STATE_RUN, { run: "held" });

    expect(written(stood)).toEqual([DRAIN]);
    expect(stood.session.status.draining).toBe(true);
  });

  /** The same silence at the press. */
  it("waits where a held run says nothing about moving", () => {
    const stood = powered();
    stood.broker.says(STATE_RUN, { run: "held" });

    stood.session.pressPower("off");

    expect(written(stood)).toEqual([DRAIN]);
    expect(stood.session.status.draining).toBe(true);
  });

  /** A drain that never lands leaves the railroad powered, and a frame about
   *  anything else leaves the wait alone. */
  it("leaves the railroad powered while the run never settles", () => {
    const stood = powered();
    stood.broker.says(STATE_RUN, { run: "running", moving: true });
    stood.session.pressPower("off");

    stood.broker.says("tc49/dispatch/state/aspects", { aspects: {} });
    stood.broker.says(STATE_RUN, { run: "draining", moving: true });

    expect(written(stood)).toEqual([DRAIN]);
    expect(stood.session.status.draining).toBe(true);
  });

  /** The run word changing back to `running` is a drain somebody abandoned,
   *  and the wait goes with it (ADR-0062). */
  it("drops the wait when the run is released", () => {
    const stood = powered();
    stood.broker.says(STATE_RUN, { run: "running", moving: true });
    stood.session.pressPower("off");

    stood.broker.says(STATE_RUN, { run: "draining", moving: true });
    stood.broker.says(STATE_RUN, { run: "running", moving: true });
    expect(stood.session.status.draining).toBe(false);

    stood.broker.says(STATE_RUN, { run: "held", moving: false });

    expect(written(stood)).toEqual([DRAIN]);
    expect(stood.session.status.draining).toBe(false);
  });

  /** The last train arriving republishes the run word the press was made
   *  against (#406): the drain is still outstanding (#441). */
  it("keeps the wait where the last train arrives under a running run", () => {
    const stood = powered();
    stood.broker.says(STATE_RUN, { run: "running", moving: true });
    stood.session.pressPower("off");

    stood.broker.says(STATE_RUN, { run: "running", moving: false });
    expect(written(stood)).toEqual([DRAIN]);
    expect(stood.session.status.draining).toBe(true);

    stood.broker.says(STATE_RUN, { run: "held", moving: false });

    expect(written(stood)).toEqual([DRAIN, CUT]);
    expect(stood.session.status.draining).toBe(false);
  });

  /** `draining` with nothing moving is the drain answered and not the drain
   *  landed: the dispatcher writes the `held` this waits for itself. */
  it("keeps the wait where the drain is answered with nothing moving", () => {
    const stood = powered();
    stood.broker.says(STATE_RUN, { run: "running", moving: true });
    stood.session.pressPower("off");

    stood.broker.says(STATE_RUN, { run: "draining", moving: false });

    expect(written(stood)).toEqual([DRAIN]);
    expect(stood.session.status.draining).toBe(true);
  });

  /** The person has said what they want the supply to do, so the cut the
   *  earlier press would have made later is abandoned. */
  it("abandons the wait when ON is pressed instead", () => {
    const stood = powered();
    stood.broker.says(STATE_RUN, { run: "running", moving: true });
    stood.session.pressPower("off");

    stood.session.pressPower("on");
    stood.broker.says(STATE_RUN, { run: "held", moving: false });

    expect(written(stood)).toEqual([DRAIN, { topic: POWER_WANTED, payload: { power: "on" } }]);
    expect(stood.session.status.draining).toBe(false);
  });
});

describe("holding the run and releasing it", () => {
  function held(): Stood {
    const stood = joined();
    stood.broker.says(STATE_RUN, { run: "held" });
    return stood;
  }

  it("says what is disputed, and lets the release through", () => {
    const stood = held();
    stood.broker.says(DISPUTED, { trains: ["t1"], blocks: ["b"] });

    stood.session.press("running");

    expect(stood.session.released).toBe(
      "released with t1 in a block that reads clear, b reads occupied",
    );
    expect(written(stood)).toEqual([{ topic: RUN_WANTED, payload: { run: "running" } }]);
  });

  it("says nothing where nothing is disputed", () => {
    const stood = held();
    stood.broker.says(DISPUTED, { trains: [], blocks: [] });

    stood.session.press("running");

    expect(stood.session.released).toBeNull();
  });

  /** A fresh hold is a fresh decision. Not the value but the transition: the
   *  run is still `held` between the press and the dispatcher's answer. */
  it("stands while that run runs, and goes with the next hold", () => {
    const stood = held();
    stood.broker.says(DISPUTED, { trains: ["t1"], blocks: [] });
    stood.session.press("running");

    stood.broker.says(STATE_RUN, { run: "running" });
    expect(stood.session.released).not.toBeNull();

    stood.broker.says(STATE_RUN, { run: "held" });
    expect(stood.session.released).toBeNull();
  });

  it("says nothing when the run is held rather than released", () => {
    const stood = held();
    stood.broker.says(DISPUTED, { trains: ["t1"], blocks: [] });
    stood.broker.says(STATE_RUN, { run: "running" });

    stood.session.press("held");

    expect(stood.session.released).toBeNull();
    expect(written(stood)).toEqual([{ topic: RUN_WANTED, payload: { run: "held" } }]);
  });
});

describe("the broker not answering", () => {
  /** MQTT.js queues a publish made while it is reconnecting, so a press in
   *  between must not pretend to have been heard. */
  it("publishes nothing while the broker has gone", () => {
    const stood = joined();
    stood.broker.says(STATE_RUN, { run: "held" });
    stood.broker.closes();

    stood.session.press("running");
    stood.session.pressPower("off");
    stood.session.pressRailroad("toy");
    stood.session.pressTake("goods");
    stood.session.pressRelease("goods");
    stood.session.pressThrottle("goods", 40);
    stood.session.pressReversal("goods");

    expect(written(stood)).toEqual([]);
    expect(stood.session.released).toBeNull();
    expect(stood.session.status.linked).toBe(false);
    expect(stood.session.status.joined).toBe(false);
  });
});

/**
 * A Save in progress when the broker drops finishes after the connection has
 * gone, and its `railroad_wanted` could not be sent. Nothing else would name
 * the railroad again — the row coming back names the same one — so the press
 * is owed, and sent once the broker is back, the row names the same railroad
 * and power reads off: `layout` drops the request otherwise (#803).
 */
describe("a railroad press made while the broker has gone", () => {
  const WANTED = { topic: "tc49/layout/railroad_wanted", payload: { railroad: "toy" } };

  /** Joined with power off, the broker gone, and `toy` pressed meanwhile. */
  function owing(): Stood {
    const stood = joined();
    stood.broker.says(STATE_POWER, { power: "off" });
    stood.broker.closes();
    stood.session.pressRailroad("toy");
    return stood;
  }

  it("is sent once the broker is back with the same railroad and power off", () => {
    const stood = owing();
    expect(written(stood)).toEqual([]);

    stood.broker.opens();

    expect(written(stood)).toEqual([WANTED]);
  });

  it("is sent once and not again on the next reconnect", () => {
    const stood = owing();
    stood.broker.opens();
    stood.broker.closes();
    stood.broker.opens();

    expect(written(stood)).toEqual([WANTED]);
  });

  it("waits for power to read off", () => {
    const stood = owing();
    stood.broker.retains(STATE_POWER, { power: "on" });
    stood.broker.opens();
    expect(written(stood)).toEqual([]);

    stood.broker.says(STATE_POWER, { power: "off" });

    expect(written(stood)).toEqual([WANTED]);
  });

  it("is dropped where the row names another railroad", () => {
    const stood = owing();
    stood.broker.retains(RAILROAD, { name: "other" });
    stood.broker.opens();
    stood.broker.says(STATE_POWER, { power: "off" });
    expect(written(stood)).toEqual([]);

    stood.broker.says(RAILROAD, { name: "toy" });
    stood.broker.says(STATE_POWER, { power: "off" });

    expect(written(stood)).toEqual([]);
  });

  it("is dropped where the row names no railroad", () => {
    const stood = owing();
    stood.broker.retains(RAILROAD, { name: "" });
    stood.broker.opens();

    expect(written(stood)).toEqual([]);
  });
});

describe("the rows that arrive before the documents", () => {
  /** The broker replays the retained rows in an order the contract does not
   *  fix (ADR-0032), so the picture may land before the row that names the
   *  railroad, and the documents later still. */
  it("applies them once the documents arrive", () => {
    const stood = standing();
    stood.answering = false;
    stood.broker.retains(STATE_RUN, { run: "held" });
    stood.broker.retains(ALLOCATION, {
      trains: { goods: "a" },
      locks: { a: "goods" },
      requests: [],
    });
    stood.broker.retains(RAILROAD, { name: "toy" });
    stood.broker.opens();

    expect(stood.names).toEqual(["toy"]);
    expect(stood.session.panel).toBeNull();

    answer(stood, "toy");

    expect(stood.session.status.run).toBe("held");
    expect(stood.session.status.placed).toEqual(["goods"]);
  });

  /** A page whose documents never arrive must not hold the bus without
   *  bound. */
  it("holds no more than HELD of them", () => {
    const stood = standing();
    stood.answering = false;
    stood.broker.opens();
    for (let i = 0; i < HELD; i++) stood.broker.says(STATE_RUN, { run: "held" });
    stood.broker.says(STATE_RUN, { run: "running" });
    stood.broker.says(RAILROAD, { name: "toy" });

    answer(stood, "toy");

    expect(stood.session.status.run).toBe("held");
  });
});

describe("a row naming no railroad", () => {
  /** A broker with no railroad loaded (#727): the session goes, and the app
   *  is told none is, which is not the same as not having said. */
  it("leaves the session and says so", () => {
    const stood = joined();
    stood.broker.says(STATE_RUN, { run: "held" });

    stood.broker.says(RAILROAD, { name: "" });

    expect(stood.names).toEqual(["toy", ""]);
    expect(stood.session.status.joined).toBe(false);
    expect(stood.session.status.railroad).toBe("");
    expect(stood.session.status.run).toBeNull();
  });
});

describe("what it answers", () => {
  /** The app redraws only where one of the two is a different object, so a
   *  frame that moves neither must leave both as they were. */
  it("keeps status and cabs across a frame that changes neither", () => {
    const stood = joined();
    stood.broker.says(ALLOCATION, {
      trains: { goods: "a" },
      locks: { a: "goods" },
      requests: [],
    });
    const status = stood.session.status;
    const cabs = stood.session.cabs;
    expect(cabs).toHaveLength(1);

    stood.broker.says("tc49/dispatch/state/aspects", { aspects: {} });
    stood.session.documents(stored("toy"), DERIVES, STOCK);

    expect(stood.session.status).toBe(status);
    expect(stood.session.cabs).toBe(cabs);

    stood.broker.says(STATE_RUN, { run: "held" });

    expect(stood.session.status).not.toBe(status);
    expect(stood.session.cabs).toBe(cabs);
  });
});

/**
 * The throttle's id and what rides on it
 * ([ADR-0079](../../docs/adr/0079-the-railroad-has-one-driving-mode-and-a-train-one-throttle.md)):
 * the page mints one when it opens, takes and releases with `take_wanted`,
 * names itself on every speed, and says `throttle_alive` once a second while
 * `state/taken` names it for a train.
 */
describe("the throttle", () => {
  const TAKE_WANTED = "tc49/layout/take_wanted";
  const THROTTLE_WANTED = "tc49/layout/throttle_wanted";
  const ALIVE = "tc49/layout/throttle_alive";
  const TAKEN = "tc49/layout/state/taken";
  const PICTURE = { trains: { goods: "a" }, locks: { a: "goods" }, requests: [] };

  afterEach(() => {
    vi.useRealTimers();
  });

  /** A joined session with `goods` on the layout. */
  function placing(): Stood {
    const stood = powered();
    stood.broker.says(ALLOCATION, PICTURE);
    return stood;
  }

  /** How many `throttle_alive` frames have gone out, each checked to name
   *  this page's throttle. */
  function beats(stood: Stood): number {
    const alive = written(stood).filter(
      (frame) => (frame as { topic: string }).topic === ALIVE,
    );
    for (const frame of alive) {
      expect(frame).toEqual({ topic: ALIVE, payload: { throttle: stood.session.throttle } });
    }
    return alive.length;
  }

  it("mints a different non-empty id for each page", () => {
    const one = standing().session.throttle;
    const other = standing().session.throttle;
    expect(one).not.toBe("");
    expect(one).not.toBe(other);
  });

  it("takes a train under its own id", () => {
    const stood = placing();
    stood.session.pressTake("goods");
    expect(written(stood)).toEqual([
      { topic: TAKE_WANTED, payload: { train: "goods", throttle: stood.session.throttle } },
    ]);
  });

  /** A release and a force release are the same frame: `null` frees the
   *  train whoever holds it (BUS.md). */
  it("releases with null", () => {
    const stood = placing();
    stood.session.pressRelease("goods");
    expect(written(stood)).toEqual([
      { topic: TAKE_WANTED, payload: { train: "goods", throttle: null } },
    ]);
  });

  it("names itself on every speed", () => {
    const stood = placing();
    stood.session.pressThrottle("goods", 0.4);
    expect(written(stood)).toEqual([
      {
        topic: THROTTLE_WANTED,
        payload: { train: "goods", speed: 0.4, throttle: stood.session.throttle },
      },
    ]);
  });

  it("says it is alive once a second while state/taken names it", () => {
    vi.useFakeTimers();
    const stood = placing();
    stood.session.pressTake("goods");
    vi.advanceTimersByTime(3 * ALIVE_MS);
    // Not on the press: `layout` has not handed it the train yet.
    expect(beats(stood)).toBe(0);

    stood.broker.says(TAKEN, { taken: { goods: stood.session.throttle } });
    vi.advanceTimersByTime(ALIVE_MS - 1);
    expect(beats(stood)).toBe(0);
    vi.advanceTimersByTime(1);
    expect(beats(stood)).toBe(1);
    vi.advanceTimersByTime(2 * ALIVE_MS);
    expect(beats(stood)).toBe(3);

    // A second row naming it again does not start a second beat.
    stood.broker.says(TAKEN, { taken: { goods: stood.session.throttle } });
    vi.advanceTimersByTime(ALIVE_MS);
    expect(beats(stood)).toBe(4);
  });

  it("stops once it holds nothing", () => {
    vi.useFakeTimers();
    const stood = placing();
    stood.broker.says(TAKEN, { taken: { goods: stood.session.throttle } });
    vi.advanceTimersByTime(ALIVE_MS);
    expect(beats(stood)).toBe(1);

    stood.broker.says(TAKEN, { taken: {} });
    vi.advanceTimersByTime(5 * ALIVE_MS);
    expect(beats(stood)).toBe(1);
  });

  /** A train held by another throttle is that throttle's to keep alive. */
  it("says nothing for a train another throttle holds", () => {
    vi.useFakeTimers();
    const stood = placing();
    stood.broker.says(TAKEN, { taken: { goods: "elsewhere" } });
    vi.advanceTimersByTime(5 * ALIVE_MS);
    expect(beats(stood)).toBe(0);
  });

  it("stops when the broker goes", () => {
    vi.useFakeTimers();
    const stood = placing();
    stood.broker.says(TAKEN, { taken: { goods: stood.session.throttle } });
    stood.broker.closes();
    vi.advanceTimersByTime(5 * ALIVE_MS);
    expect(beats(stood)).toBe(0);
  });
});
