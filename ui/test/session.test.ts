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
 * while the broker is not answering, the rows held until the documents land,
 * a row naming no railroad (#727), and `status` and `cabs` keeping their
 * identity across a frame that moves neither — which is what keeps the app
 * from redrawing on every frame.
 */

import { beforeEach, describe, expect, it } from "vitest";

import { HELD, Session, type Client } from "../src/model/session.js";
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
    stood.session.pressMode("goods", "manual");
    stood.session.pressThrottle("goods", 40);
    stood.session.pressReversal("goods");

    expect(written(stood)).toEqual([]);
    expect(stood.session.released).toBeNull();
    expect(stood.session.status.linked).toBe(false);
    expect(stood.session.status.joined).toBe(false);
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
