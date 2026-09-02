/**
 * What the throttle is handed: who drives each train, which way it points,
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
import { cabs } from "../src/model/throttle.js";
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

/** What the model answers, put together the way the run view does. */
function drive(model: Panel, stock = {}) {
  return cabs({
    placed: model.placed(),
    modes: model.modes(),
    noses: model.noses(),
    aspects: model.aspects(),
    ahead: model.ahead(),
    stock,
  });
}

describe("who drives a train", () => {
  /** `automatic` is the resting value, so a train the map does not name is
   *  automatic rather than unknown (CONTEXT.md). */
  it("reads every train as automatic before anything has said", () => {
    const model = panel();
    standing(model);
    expect(drive(model)[0]).toMatchObject({ train: "t1", mode: "automatic" });
  });

  it("takes the mode topic's word for who is driving", () => {
    const model = panel();
    standing(model);
    feed(model, { event: "mode", modes: { t1: "manual" } });
    expect(model.modes().get("t1")).toBe("manual");
  });

  /** Last value wins, so a train the map stops naming is back to the resting
   *  value: releasing is a map without it in. */
  it("puts a train the map stops naming back to automatic", () => {
    const model = panel();
    standing(model);
    feed(model, { event: "mode", modes: { t1: "manual" } }, { event: "mode", modes: {} });
    expect(drive(model)[0]).toMatchObject({ mode: "automatic" });
  });

  /** Falling to `manual` would hand a train to a person who is not there,
   *  and falling to `automatic` would take one out of the hands of a person
   *  who is (SYSTEM.md, `layout`). */
  it("drops an entry it cannot read and leaves that train where it was", () => {
    const model = panel();
    standing(model);
    feed(
      model,
      { event: "mode", modes: { t1: "manual" } },
      { event: "mode", modes: { t1: "sideways" } },
    );
    expect(drive(model)[0]).toMatchObject({ mode: "manual" });
  });

  it("forgets who was driving when the page starts over", () => {
    const model = panel();
    standing(model);
    feed(model, { event: "mode", modes: { t1: "manual" } });
    model.reset();
    expect(model.modes().size).toBe(0);
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
        functions: [
          { name: "headlights", values: ["off", "on"] },
          { name: "vacuum", values: ["off", "low", "high"] },
        ],
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
