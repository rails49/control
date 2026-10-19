/**
 * What the throttle is handed: which throttle holds each train, whether it
 * has a move outstanding, which way it points,
 * what it is reading and what is in front of it (ui/THROTTLE.md, #207).
 *
 * No DOM. The three readings the panel model grew for this view are driven
 * the way every other one is — bus payloads in, an answer out — and `cabs`
 * puts them beside the railroad's roster.
 */

import { describe, expect, it } from "vitest";

import type { Wire } from "../src/model/drawing.js";
import { Panel } from "../src/model/panel.js";
import type { Explained, Layout } from "../src/model/store.js";
import { cabs, driveRefusal } from "../src/model/throttle.js";
import type { TraceEvent } from "../src/model/trace.js";

/** Two blocks joined by one transit: enough for a train to stand, face an
 *  end, be granted a route and have a block ahead of it. */
const LAYOUT: Layout = {
  layout: "toy",
  blocks: { a: { length: 1000 }, b: { length: 1000 } },
  connections: { j: { transits: { over: ["a.B", "b.A"] } } },
};

const EXPLAIN: Explained = {
  layout: "toy",
  connections: {
    j: { transits: { over: { ends: ["a.B", "b.A"], way: [["p1", ""]] } }, exclusive: [] },
  },
};

const WIRES: Wire[] = [
  ["a.B", "p1.P"],
  ["p1.P", "b.A"],
];

function panel(): Panel {
  return new Panel(LAYOUT, EXPLAIN, WIRES);
}

function feed(model: Panel, ...events: Partial<TraceEvent>[]): void {
  for (const event of events) model.apply({ event: "?", ...event } as TraceEvent);
}

/** A train standing in `a`, facing B, as a run opens with it. */
function standing(model: Panel): void {
  feed(
    model,
    { event: "lock_granted", train: "t1", resources: ["a"] },
    { event: "allocation", trains: { t1: "a" }, locks: { a: "t1" }, requests: [] },
    { event: "facing", facing: { t1: "a.A-to-B" } },
  );
}

/** This page's throttle id, and another page's. */
const HERE = "th-here";
const ELSEWHERE = "th-elsewhere";

/** What the model answers, put together the way the session does. */
function drive(model: Panel, stock = {}) {
  const placed = model.placed();
  return cabs({
    placed,
    taken: model.taken(),
    throttle: HERE,
    granted: model.granted(),
    noses: model.noses(),
    aspects: model.aspects(),
    ahead: model.ahead(),
    inFlight: new Set(
      placed.filter(({ train }) => model.inFlight(train)).map(({ train }) => train),
    ),
    stock,
  });
}

describe("who holds a train", () => {
  /** A train the map does not name, no throttle holds (BUS.md). */
  it("reads every train as held by nobody before anything has said", () => {
    const model = panel();
    standing(model);
    expect(drive(model)[0]).toMatchObject({ train: "t1", taken: null });
  });

  it("says a train this throttle holds is held here", () => {
    const model = panel();
    standing(model);
    feed(model, { event: "taken", taken: { t1: HERE } });
    expect(drive(model)[0]).toMatchObject({ taken: "here" });
  });

  /** Another tab's id is a train this page cannot take. */
  it("says a train another throttle holds is held elsewhere", () => {
    const model = panel();
    standing(model);
    feed(model, { event: "taken", taken: { t1: ELSEWHERE } });
    expect(model.taken().get("t1")).toBe(ELSEWHERE);
    expect(drive(model)[0]).toMatchObject({ taken: "elsewhere" });
  });

  /** Last value wins, so a train the map stops naming is released. */
  it("releases a train the map stops naming", () => {
    const model = panel();
    standing(model);
    feed(model, { event: "taken", taken: { t1: HERE } }, { event: "taken", taken: {} });
    expect(drive(model)[0]).toMatchObject({ taken: null });
  });

  /** Read an entry at a time: an unreadable entry leaves its train held by
   *  nobody, and an unreadable payload holds nothing (BUS.md). */
  it("holds nothing for an entry or a payload it cannot read", () => {
    const model = panel();
    standing(model);
    feed(model, { event: "taken", taken: { t1: HERE } }, { event: "taken", taken: { t1: 7 } });
    expect(drive(model)[0]).toMatchObject({ taken: null });
    feed(model, { event: "taken", taken: { t1: HERE } }, { event: "taken", taken: "t1" });
    expect(model.taken().size).toBe(0);
  });

  it("forgets who held what when the page starts over", () => {
    const model = panel();
    standing(model);
    feed(model, { event: "taken", taken: { t1: HERE } });
    model.reset();
    expect(model.taken().size).toBe(0);
  });
});

describe("a move outstanding", () => {
  const MOVE = { event: "move", train: "t1", connection: "j", transit: "over", into: "b", speed: 0.6 };

  it("has none before a move is granted", () => {
    const model = panel();
    standing(model);
    expect(drive(model)[0]).toMatchObject({ granted: false });
  });

  /** From the move the dispatcher sends `layout` to the sensor it ends at:
   *  the span `layout` applies a throttle's speed in (BUS.md). */
  it("has one from the move until the block it enters is occupied", () => {
    const model = panel();
    standing(model);
    feed(model, { event: "lock_granted", train: "t1", resources: ["j", "b"] }, MOVE);
    expect(drive(model)[0]).toMatchObject({ granted: true });

    feed(model, { event: "block_occupied", block: "b" });
    expect(drive(model)[0]).toMatchObject({ granted: false });
  });

  it("forgets the move of a train taken off the layout", () => {
    const model = panel();
    standing(model);
    feed(model, MOVE, { event: "allocation", trains: {}, locks: {}, requests: [] });
    expect(model.granted().size).toBe(0);
  });
});

describe("what the train faces", () => {
  /** The scheduler's facing, in the form the aspects are keyed by: the end
   *  the train would depart through nose-first (CONTEXT.md, **Facing**). */
  it("names the end the train points at", () => {
    const model = panel();
    standing(model);
    expect(drive(model)[0]).toMatchObject({ nose: "a.B" });
  });

  it("shows the aspect at that end and no other", () => {
    const model = panel();
    standing(model);
    feed(model, { event: "aspects", aspects: { "a.B": "caution", "a.A": "clear" } });
    expect(drive(model)[0]).toMatchObject({ aspect: "caution" });
  });

  /** An end that leads nowhere carries no signal and the dispatcher names
   *  none, so there is nothing to read rather than a dark lamp. */
  it("shows no aspect where none has been named", () => {
    const model = panel();
    standing(model);
    expect(drive(model)[0]).toMatchObject({ aspect: null });
  });

  it("has no facing for a train the scheduler has not said one for", () => {
    const model = panel();
    feed(
      model,
      { event: "lock_granted", train: "t1", resources: ["a"] },
      { event: "allocation", trains: { t1: "a" }, locks: { a: "t1" }, requests: [] },
    );
    expect(drive(model)[0]).toMatchObject({ nose: null, aspect: null });
  });
});

describe("the road in front", () => {
  it("has nothing ahead of a train with no committed route", () => {
    const model = panel();
    standing(model);
    expect(drive(model)[0]).toMatchObject({ ahead: [] });
  });

  /** The two words the picture lights a route in: green where the dispatcher
   *  holds the lock and the train may move, cyan where it does not
   *  (ui/PANEL.md). */
  it("lists the route's blocks past the one the train stands in", () => {
    const model = panel();
    standing(model);
    feed(
      model,
      { event: "request_submitted", id: "r1", train: "t1", depart: "a.B", dest: ["b.A"] },
      { event: "route_chosen", id: "r1", route: ["a", "j.over", "b"] },
    );
    expect(drive(model)[0]!.ahead).toEqual([{ block: "b", claim: "committed" }]);
  });

  it("says which of them the dispatcher has locked", () => {
    const model = panel();
    standing(model);
    feed(
      model,
      { event: "request_submitted", id: "r1", train: "t1", depart: "a.B", dest: ["b.A"] },
      { event: "route_chosen", id: "r1", route: ["a", "j.over", "b"] },
      { event: "lock_granted", train: "t1", resources: ["j.over", "b"] },
    );
    expect(drive(model)[0]!.ahead).toEqual([{ block: "b", claim: "locked" }]);
  });
});

describe("a request in flight", () => {
  /** The same pre-judgement the run view's menu makes, and for the reason it
   *  makes it: the request departs the end the facing named when it was
   *  composed (#295). */
  it("is marked on the train, from submission until it is answered", () => {
    const model = panel();
    standing(model);
    expect(drive(model)[0]).toMatchObject({ inFlight: false });
    feed(model, {
      event: "request_submitted",
      id: "r1",
      train: "t1",
      depart: "a.B",
      dest: ["b.A"],
    });
    expect(drive(model)[0]).toMatchObject({ inFlight: true });
    feed(model, { event: "request_completed", id: "r1" });
    expect(drive(model)[0]).toMatchObject({ inFlight: false });
  });
});

describe("the trains there are to drive", () => {
  /** A throttle moves a train that is on the layout; a train off it has
   *  nothing to move (ADR-0039), and placing one is the run view's pane. */
  it("offers the trains the railroad has placed and no others", () => {
    const model = panel();
    standing(model);
    expect(drive(model, { t1: { length: 400 }, spare: { length: 200 } }).map((cab) => cab.train)).toEqual([
      "t1",
    ]);
  });

  it("offers a crossing train, which stands in no block", () => {
    const model = panel();
    standing(model);
    feed(model, {
      event: "allocation",
      trains: { t1: "a" },
      crossing: { t1: "j.over" },
      locks: { a: "t1" },
      requests: [],
    });
    expect(drive(model)[0]).toMatchObject({ train: "t1", block: null });
  });

  it("orders them by name, so the list does not reshuffle as the railroad moves", () => {
    const model = panel();
    feed(model, {
      event: "allocation",
      trains: { zulu: "a", alpha: "b" },
      locks: {},
      requests: [],
    });
    expect(drive(model).map((cab) => cab.train)).toEqual(["alpha", "zulu"]);
  });
});

describe("what a person can switch", () => {
  it("hands over the functions the roster gives the train, by name", () => {
    const model = panel();
    standing(model);
    const stock = {
      t1: {
        length: 400,
        functions: [{ name: "headlights" }, { name: "vacuum" }],
      },
    };
    expect(drive(model, stock)[0]!.functions).toEqual(stock.t1.functions);
  });

  /** Most of the stock a railroad owns declares none, and a train the
   *  picture has and the roster does not is the other way to have none. */
  it("has none where the cars declare none, and none for a train off the roster", () => {
    const model = panel();
    standing(model);
    expect(drive(model, { t1: { length: 400 } })[0]!.functions).toEqual([]);
    expect(drive(model)[0]!.functions).toEqual([]);
  });
});

/** Why nothing can be driven: a session that is not answering first, then
 *  the track as the layout last said it (ui/THROTTLE.md, ADR-0041). */
describe("why a train cannot be driven", () => {
  it.each(["on", "draining", "stopped", "off", null] as const)(
    "is refused with no broker answering, power %s",
    (power) => {
      expect(driveRefusal(false, power)).toBe("no broker answering — is the bus running?");
    },
  );

  it.each([
    ["on", null],
    ["draining", "the railroad is draining — switch it on to drive"],
    ["stopped", "emergency stop — clear it before driving"],
    ["off", "the track has no power — switch it on to drive"],
    [null, "the layout has not said whether the track is live"],
  ] as const)("with a session and power %s says %s", (power, said) => {
    expect(driveRefusal(true, power)).toBe(said);
  });
});
