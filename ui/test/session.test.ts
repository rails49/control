/**
 * The session, driven by the broker alone (#756): frames in off the broker
 * double, frames out onto it, and nothing mounted.
 *
 * Power and the driving mode are each one frame naming where they should
 * stand, and the page keeps no wait of its own: `layout` does the drain
 * (ADR-0078). `power.test.ts` keeps the presses end to end through the band.
 *
 * Beside them: nothing published
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
const DRIVING_WANTED = "tc49/layout/driving_wanted";
const STATE_RUN = "tc49/dispatch/state/run";
const STATE_POWER = "tc49/layout/state/power";
const STATE_DRIVING = "tc49/layout/state/driving";
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

beforeEach(() => {
  Broker.last = null;
  Broker.opened = [];
});

/** Each press is one frame naming where power or the driving mode should
 *  stand, and the session waits on nothing after it (ADR-0078, ADR-0079). */
describe("the presses", () => {
  it.each(["on", "draining", "off"] as const)(
    "asks for power %s and nothing else",
    (power) => {
      const stood = powered();

      stood.session.pressPower(power);

      expect(written(stood)).toEqual([
        { topic: POWER_WANTED, payload: { power } },
      ]);
    },
  );

  /** The drain is `layout`'s: nothing the dispatcher says afterwards makes the
   *  page cut the supply itself. */
  it("leaves the drain to layout", () => {
    const stood = powered();
    stood.session.pressPower("draining");

    stood.broker.says("tc49/dispatch/state/moving", { moving: false });
    stood.broker.says(STATE_RUN, { run: "held", moving: false });

    expect(written(stood)).toEqual([
      { topic: POWER_WANTED, payload: { power: "draining" } },
    ]);
  });

  it.each(["manual", "automatic"] as const)(
    "asks for driving %s",
    (driving) => {
      const stood = joined();

      stood.session.pressDriving(driving);

      expect(written(stood)).toEqual([
        { topic: DRIVING_WANTED, payload: { driving } },
      ]);
    },
  );

  /** What the rail draws is `layout`'s answer and not the press. */
  it("reads the driving mode off state/driving", () => {
    const stood = joined();
    expect(stood.session.status.driving).toBeNull();

    stood.session.pressDriving("automatic");
    expect(stood.session.status.driving).toBeNull();

    stood.broker.says(STATE_DRIVING, { driving: "automatic" });
    expect(stood.session.status.driving).toBe("automatic");
  });
});

describe("the broker not answering", () => {
  /** MQTT.js queues a publish made while it is reconnecting, so a press in
   *  between must not pretend to have been heard. */
  it("publishes nothing while the broker has gone", () => {
    const stood = joined();
    stood.broker.says(STATE_DRIVING, { driving: "manual" });
    stood.broker.closes();

    stood.session.pressPower("draining");
    stood.session.pressDriving("automatic");
    stood.session.pressRailroad("toy");
    stood.session.pressTake("goods", stood.session.throttleFor(0));
    stood.session.pressRelease("goods");
    stood.session.pressThrottle("goods", 40, stood.session.throttleFor(0));
    stood.session.pressReversal("goods");

    expect(written(stood)).toEqual([]);
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
  const WANTED = {
    topic: "tc49/layout/railroad_wanted",
    payload: { railroad: "toy" },
  };

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

/**
 * ON over a drawing being saved: `on` sent only once the save has landed and
 * the row comes back from a build after it (ADR-0085, decision 2). A row
 * stamped no later than the one held when the save landed is the build
 * before it, replayed on a reconnect. Naming the railroad is the save's own,
 * so the session names nothing here.
 */
describe("ON waiting for the build", () => {
  const ON = { topic: POWER_WANTED, payload: { power: "on" } };

  /** `toy` loaded at stamp 5, power off, and ON pressed over a save that
   *  answers when the test says. */
  function waiting(): Stood & { landed: (reached: boolean) => Promise<void> } {
    const stood = standing();
    stood.broker.retains(RAILROAD, { name: "toy", at: 5, built: true });
    stood.broker.opens();
    stood.broker.says(STATE_POWER, { power: "off", at: 5 });
    let answer: (reached: boolean) => void = () => {};
    stood.session.pressOnSaved(
      "toy",
      new Promise<boolean>((resolve) => (answer = resolve)),
    );
    return {
      ...stood,
      landed: async (reached) => {
        answer(reached);
        for (let turn = 0; turn < 5; turn++) await Promise.resolve();
      },
    };
  }

  /** `waiting`, with the save landed. */
  async function saved(): Promise<Stood> {
    const stood = waiting();
    await stood.landed(true);
    return stood;
  }

  it("names nothing, and sends on only once a later build names it", async () => {
    const stood = waiting();
    stood.broker.says(RAILROAD, { name: "toy", at: 6, built: true });
    expect(written(stood)).toEqual([]);

    await stood.landed(true);
    expect(written(stood)).toEqual([]);
    stood.broker.says(RAILROAD, { name: "toy", at: 7, built: true });

    expect(written(stood)).toEqual([ON]);
  });

  it("reads a row with no built as built", async () => {
    const stood = await saved();
    stood.broker.says(RAILROAD, { name: "toy", at: 6 });
    expect(written(stood)).toEqual([ON]);
  });

  it("does not take the build before it, replayed, for the build", async () => {
    const stood = await saved();
    stood.broker.closes();
    stood.broker.opens();
    expect(written(stood)).toEqual([]);

    stood.broker.says(RAILROAD, { name: "toy", at: 6 });

    expect(written(stood)).toEqual([ON]);
  });

  it("sends nothing on a build that built nothing", async () => {
    const stood = await saved();
    stood.broker.says(RAILROAD, { name: "toy", at: 6, built: false });
    stood.broker.says(RAILROAD, { name: "toy", at: 7, built: true });
    expect(written(stood)).toEqual([]);
  });

  it("sends nothing where the save answers false", async () => {
    const stood = waiting();
    await stood.landed(false);
    stood.broker.says(RAILROAD, { name: "toy", at: 6, built: true });
    expect(written(stood)).toEqual([]);
  });

  it("sends nothing on after a power press during the write", async () => {
    const stood = waiting();
    stood.session.pressPower("off");
    await stood.landed(true);
    stood.broker.says(RAILROAD, { name: "toy", at: 6, built: true });
    expect(written(stood)).toEqual([
      { topic: POWER_WANTED, payload: { power: "off" } },
    ]);
  });

  it("sends nothing on after a power press during the build", async () => {
    const stood = await saved();
    stood.session.pressPower("off");
    stood.broker.says(RAILROAD, { name: "toy", at: 6, built: true });
    expect(written(stood)).toEqual([
      { topic: POWER_WANTED, payload: { power: "off" } },
    ]);
  });

  it("sends nothing where the row names another railroad first", async () => {
    const stood = await saved();
    stood.broker.says(RAILROAD, { name: "other", at: 6 });
    stood.broker.says(RAILROAD, { name: "toy", at: 7 });
    expect(written(stood)).toEqual([]);
  });
});

/** An invalid drawing builds no panel model, and the page still
 *  reads the supply: it is what says whether the editor may save
 *  (ADR-0085). */
describe("power with no panel model", () => {
  it("is read off the row all the same", () => {
    const stood = standing();
    stood.answering = false;
    stood.broker.retains(RAILROAD, { name: "toy" });
    stood.broker.opens();
    stood.session.documents(stored("toy"), null, STOCK);

    stood.broker.says(STATE_POWER, { power: "off" });

    expect(stood.session.panel).toBeNull();
    expect(stood.session.status.power).toBe("off");
  });
});

/** A railroad whose drawing is not a valid drawing stays named, the row
 *  saying nothing was built from it (ADR-0085, decision 4, #885). */
describe("a railroad named and not built", () => {
  it("is joined, and says it is not built", () => {
    const stood = standing();
    stood.broker.retains(RAILROAD, { name: "toy", at: 5, built: false });
    stood.broker.opens();

    expect(stood.names).toEqual(["toy"]);
    expect(stood.session.status.railroad).toBe("toy");
    expect(stood.session.status.built).toBe(false);
  });

  it("reads a row with no built, or another built, as built", () => {
    const stood = standing();
    stood.broker.retains(RAILROAD, { name: "toy", at: 5 });
    stood.broker.opens();
    expect(stood.session.status.built).toBe(true);

    stood.broker.says(RAILROAD, { name: "toy", at: 6, built: false });
    expect(stood.session.status.built).toBe(false);

    stood.broker.says(RAILROAD, { name: "toy", at: 7, built: true });
    expect(stood.session.status.built).toBe(true);
  });

  it("reads a row naming none as built: there is nothing to fix", () => {
    const stood = standing();
    stood.broker.retains(RAILROAD, { name: "toy", built: false });
    stood.broker.opens();

    stood.broker.says(RAILROAD, { name: "" });

    expect(stood.session.status.railroad).toBe("");
    expect(stood.session.status.built).toBe(true);
  });
});

describe("the rows that arrive before the documents", () => {
  /** The broker replays the retained rows in an order the contract does not
   *  fix (ADR-0032), so the picture may land before the row that names the
   *  railroad, and the documents later still. */
  it("applies them once the documents arrive", () => {
    const stood = standing();
    stood.answering = false;
    stood.broker.retains(STATE_DRIVING, { driving: "automatic" });
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

    expect(stood.session.status.driving).toBe("automatic");
    expect(stood.session.status.placed).toEqual(["goods"]);
  });

  /** A page whose documents never arrive must not hold the bus without
   *  bound. */
  it("holds no more than HELD of them", () => {
    const stood = standing();
    stood.answering = false;
    stood.broker.opens();
    for (let i = 0; i < HELD; i++)
      stood.broker.says(STATE_DRIVING, { driving: "manual" });
    stood.broker.says(STATE_DRIVING, { driving: "automatic" });
    stood.broker.says(RAILROAD, { name: "toy" });

    answer(stood, "toy");

    expect(stood.session.status.driving).toBe("manual");
  });
});

describe("a row naming no railroad", () => {
  /** A broker with no railroad loaded (#727): the session goes, and the app
   *  is told none is, which is not the same as not having said. */
  it("leaves the session and says so", () => {
    const stood = joined();
    stood.broker.says(STATE_DRIVING, { driving: "manual" });

    stood.broker.says(RAILROAD, { name: "" });

    expect(stood.names).toEqual(["toy", ""]);
    expect(stood.session.status.joined).toBe(false);
    expect(stood.session.status.railroad).toBe("");
    expect(stood.session.status.driving).toBeNull();
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

    stood.broker.says(STATE_DRIVING, { driving: "automatic" });

    expect(stood.session.status).not.toBe(status);
    expect(stood.session.cabs).toBe(cabs);
  });
});

/**
 * The throttles' ids and what rides on them
 * ([ADR-0079](../../docs/adr/0079-the-railroad-has-one-driving-mode-and-a-train-one-throttle.md),
 * [ADR-0089](../../docs/adr/0089-a-throttle-holds-one-train.md)): the page
 * mints one per panel slot, takes and releases with `take_wanted`, names the
 * panel's on every speed and function, and says `throttle_alive` once a
 * second for each id `state/taken` names for a train.
 */
describe("the throttle", () => {
  const TAKE_WANTED = "tc49/layout/take_wanted";
  const THROTTLE_WANTED = "tc49/layout/throttle_wanted";
  const ALIVE = "tc49/layout/throttle_alive";
  const TAKEN = "tc49/layout/state/taken";
  const PICTURE = {
    trains: { goods: "a" },
    locks: { a: "goods" },
    requests: [],
  };

  afterEach(() => {
    vi.useRealTimers();
  });

  /** A joined session with `goods` on the layout. */
  function placing(): Stood {
    const stood = powered();
    stood.broker.says(ALLOCATION, PICTURE);
    return stood;
  }

  /** `placing`, with `shunter` standing in `b` beside `goods`. */
  function both(): Stood {
    const stood = powered();
    stood.broker.says(ALLOCATION, {
      trains: { goods: "a", shunter: "b" },
      locks: { a: "goods", b: "shunter" },
      requests: [],
    });
    return stood;
  }

  /** How many `throttle_alive` frames have gone out naming `id`; every one
   *  is checked to name one of this page's ids. */
  function beats(stood: Stood, id: string): number {
    const alive = written(stood).filter(
      (frame) => (frame as { topic: string }).topic === ALIVE,
    ) as { payload: { throttle: string } }[];
    for (const frame of alive)
      expect(stood.session.ours(frame.payload.throttle)).toBe(true);
    return alive.filter((frame) => frame.payload.throttle === id).length;
  }

  it("mints one id per panel slot, kept for the life of the page", () => {
    const { session } = standing();
    const first = session.throttleFor(0);
    expect(first).not.toBe("");
    expect(session.throttleFor(0)).toBe(first);
    expect(session.throttleFor(1)).not.toBe(first);
  });

  it("mints a different id for each page", () => {
    expect(standing().session.throttleFor(0)).not.toBe(
      standing().session.throttleFor(0),
    );
  });

  it("knows its own ids from another page's", () => {
    const { session } = standing();
    expect(session.ours(session.throttleFor(1))).toBe(true);
    expect(session.ours("elsewhere")).toBe(false);
    expect(session.ours(null)).toBe(false);
  });

  it("takes a train under the id it was pressed with", () => {
    const stood = placing();
    const id = stood.session.throttleFor(1);
    stood.session.pressTake("goods", id);
    expect(written(stood)).toEqual([
      { topic: TAKE_WANTED, payload: { train: "goods", throttle: id } },
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

  /** By name and under the panel's id: which car and which number the name
   *  reaches is `layout`'s (#849). */
  it("switches a function under the id it was pressed with", () => {
    const stood = placing();
    const id = stood.session.throttleFor(1);
    stood.session.pressFunction("goods", id, "headlights", true);
    expect(written(stood)).toEqual([
      {
        topic: "tc49/layout/function_wanted",
        payload: {
          train: "goods",
          throttle: id,
          function: "headlights",
          on: true,
        },
      },
    ]);
  });

  it("names the id it was pressed with on every speed", () => {
    const stood = placing();
    const id = stood.session.throttleFor(1);
    stood.session.pressThrottle("goods", 0.4, id);
    expect(written(stood)).toEqual([
      {
        topic: THROTTLE_WANTED,
        payload: { train: "goods", speed: 0.4, throttle: id },
      },
    ]);
  });

  it("says it is alive once a second while state/taken names it", () => {
    vi.useFakeTimers();
    const stood = placing();
    const id = stood.session.throttleFor(0);
    stood.session.pressTake("goods", id);
    vi.advanceTimersByTime(3 * ALIVE_MS);
    // Not on the press: `layout` has not handed it the train yet.
    expect(beats(stood, id)).toBe(0);

    stood.broker.says(TAKEN, { taken: { goods: id } });
    vi.advanceTimersByTime(ALIVE_MS - 1);
    expect(beats(stood, id)).toBe(0);
    vi.advanceTimersByTime(1);
    expect(beats(stood, id)).toBe(1);
    vi.advanceTimersByTime(2 * ALIVE_MS);
    expect(beats(stood, id)).toBe(3);

    // A second row naming it again does not start a second beat.
    stood.broker.says(TAKEN, { taken: { goods: id } });
    vi.advanceTimersByTime(ALIVE_MS);
    expect(beats(stood, id)).toBe(4);
  });

  /** Two panels, each holding a train: one frame for each id on each tick,
   *  and an id the row drops goes quiet while the other goes on (ADR-0089). */
  it("says it is alive for each id state/taken names, and stops for one it drops", () => {
    vi.useFakeTimers();
    const stood = both();
    const one = stood.session.throttleFor(0);
    const other = stood.session.throttleFor(1);
    stood.session.throttleFor(2);
    stood.broker.says(TAKEN, { taken: { goods: one, shunter: other } });
    vi.advanceTimersByTime(ALIVE_MS);
    expect(
      written(stood).filter(
        (frame) => (frame as { topic: string }).topic === ALIVE,
      ),
    ).toHaveLength(2);
    vi.advanceTimersByTime(2 * ALIVE_MS);
    expect([beats(stood, one), beats(stood, other)]).toEqual([3, 3]);

    stood.broker.says(TAKEN, { taken: { shunter: other } });
    vi.advanceTimersByTime(2 * ALIVE_MS);
    expect([beats(stood, one), beats(stood, other)]).toEqual([3, 5]);
  });

  it("stops once it holds nothing", () => {
    vi.useFakeTimers();
    const stood = placing();
    const id = stood.session.throttleFor(0);
    stood.broker.says(TAKEN, { taken: { goods: id } });
    vi.advanceTimersByTime(ALIVE_MS);
    expect(beats(stood, id)).toBe(1);

    stood.broker.says(TAKEN, { taken: {} });
    vi.advanceTimersByTime(5 * ALIVE_MS);
    expect(beats(stood, id)).toBe(1);
  });

  /** A train held by another throttle is that throttle's to keep alive. */
  it("says nothing for a train another throttle holds", () => {
    vi.useFakeTimers();
    const stood = placing();
    stood.session.throttleFor(0);
    stood.broker.says(TAKEN, { taken: { goods: "elsewhere" } });
    vi.advanceTimersByTime(5 * ALIVE_MS);
    expect(beats(stood, "elsewhere")).toBe(0);
    expect(written(stood)).toEqual([]);
  });

  it("stops when the broker goes", () => {
    vi.useFakeTimers();
    const stood = placing();
    const id = stood.session.throttleFor(0);
    stood.broker.says(TAKEN, { taken: { goods: id } });
    stood.broker.closes();
    vi.advanceTimersByTime(5 * ALIVE_MS);
    expect(beats(stood, id)).toBe(0);
  });

  /** Who holds a train is the id `state/taken` names; a cab compares it with
   *  no panel's (ADR-0089). */
  it("hands each cab the id state/taken names for its train", () => {
    const stood = both();
    const id = stood.session.throttleFor(0);
    stood.broker.says(TAKEN, { taken: { goods: id, shunter: "elsewhere" } });
    expect(
      stood.session.cabs.map(({ train, holder }) => [train, holder]),
    ).toEqual([
      ["goods", id],
      ["shunter", "elsewhere"],
    ]);
  });
});

/** Whether the dispatcher has said its picture since the row named the
 *  railroad: what the settings dialog waits on before it closes on a pick
 *  (#902). */
describe("the allocation since the row", () => {
  const PICTURE = { trains: {}, locks: {}, requests: [] };

  it("is not there until the dispatcher says it", () => {
    const stood = joined();
    expect(stood.session.status.allocated).toBe(false);

    stood.broker.says(ALLOCATION, PICTURE);

    expect(stood.session.status.allocated).toBe(true);
  });

  it("is kept where it landed before the row, on a fresh connection", () => {
    const stood = standing();
    stood.broker.retains(ALLOCATION, PICTURE);
    stood.broker.retains(RAILROAD, { name: "toy" });
    stood.broker.opens();

    expect(stood.session.status.allocated).toBe(true);
  });

  it("goes when the row names another railroad, and comes with its picture", () => {
    const stood = joined();
    stood.broker.says(ALLOCATION, PICTURE);

    stood.broker.says(RAILROAD, { name: "other" });
    expect(stood.session.status.allocated).toBe(false);

    stood.broker.says(ALLOCATION, PICTURE);
    expect(stood.session.status.allocated).toBe(true);
  });

  it("is there while its panel model is not built", () => {
    const stood = standing();
    stood.answering = false;
    stood.broker.retains(RAILROAD, { name: "toy" });
    stood.broker.opens();

    stood.broker.says(ALLOCATION, PICTURE);

    expect(stood.session.panel).toBeNull();
    expect(stood.session.status.allocated).toBe(true);
  });
});
