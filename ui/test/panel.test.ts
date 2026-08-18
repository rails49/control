/**
 * The panel model, driven as the trace replay drives it: bus payloads in,
 * render state out (ui/PANEL.md, #70). No DOM anywhere — block states,
 * signal aspects and request markers are data the component only paints.
 */

import { describe, expect, it } from "vitest";

import { WHOLE } from "../src/model/inspect.js";
import { Panel } from "../src/model/panel.js";
import type { Explained, Layout } from "../src/model/store.js";
import type { TraceEvent } from "../src/model/trace.js";

/**
 * A toy railroad: block `a` faces a turnout `sw1` whose two ways lead to `b`
 * and `c`. On the bus its resources are `a`, `b`, `c`, `sw.main`, `sw.side`.
 */
const LAYOUT: Layout = {
  layout: "toy",
  blocks: { a: { length: 1000 }, b: { length: 1000 }, c: { length: 1000 } },
  connections: {
    sw: {
      transits: { main: ["a.B", "b.A"], side: ["a.B", "c.A"] },
    },
    jt: {
      transits: { back: ["b.B", "c.B"] },
    },
  },
};

const EXPLAIN: Explained = {
  layout: "toy",
  connections: {
    sw: {
      transits: {
        main: { ends: ["a.B", "b.A"], way: [["sw1", "straight"]] },
        side: { ends: ["a.B", "c.A"], way: [["sw1", "diverging"], ["p1", ""]] },
      },
      exclusive: [],
    },
    jt: {
      transits: { back: { ends: ["b.B", "c.B"], way: [["p2", ""]] } },
      exclusive: [],
    },
  },
};

function panel(): Panel {
  return new Panel(LAYOUT, EXPLAIN);
}

function feed(model: Panel, ...events: Partial<TraceEvent>[]): void {
  for (const event of events) model.apply({ tick: 0, event: "?", ...event } as TraceEvent);
}

/** The placement locks a trace opens with, then the first tick. */
function placed(model: Panel): void {
  feed(
    model,
    { event: "lock_granted", train: "t1", resources: ["a"] },
    { event: "tick" },
  );
}

describe("occupancy", () => {
  it("stands a train where its pre-tick lock says", () => {
    const model = panel();
    placed(model);
    expect(model.blocks().get("a")).toMatchObject({
      state: "occupied",
      train: "t1",
    });
    expect(model.blocks().get("b")).toMatchObject({ state: "free" });
  });

  it("names an occupied block's train from the lock ledger", () => {
    const model = panel();
    placed(model);
    feed(
      model,
      { event: "lock_granted", train: "t1", resources: ["sw.main", "b"] },
      { event: "block_occupied", block: "b" },
    );
    expect(model.blocks().get("b")).toMatchObject({
      state: "occupied",
      train: "t1",
    });
  });

  it("shades a locked but empty block as reserved, a vacated one too", () => {
    const model = panel();
    placed(model);
    feed(
      model,
      { event: "lock_granted", train: "t1", resources: ["sw.main", "b"] },
    );
    expect(model.blocks().get("b")).toMatchObject({
      state: "reserved",
      train: "t1",
    });
    feed(
      model,
      { event: "block_occupied", block: "b" },
      { event: "block_vacated", block: "a" },
    );
    expect(model.blocks().get("a")).toMatchObject({
      state: "reserved",
      train: "t1",
    });
    feed(model, { event: "lock_released", train: "t1", resources: ["a", "sw.main"] });
    expect(model.blocks().get("a")).toMatchObject({ state: "free" });
  });

  it("points the arrow away from the entry end of a granted move", () => {
    const model = panel();
    placed(model);
    feed(
      model,
      { event: "lock_granted", train: "t1", resources: ["sw.main", "b"] },
      { event: "move_granted", id: "t1-1", train: "t1", transit: "sw.main", into: "b" },
      { event: "block_occupied", block: "b" },
      { event: "block_vacated", block: "a" },
    );
    // sw.main joins a.B to b.A, so t1 entered b through A and faces B.
    expect(model.blocks().get("b")).toMatchObject({
      state: "occupied",
      train: "t1",
      toward: "B",
    });
  });

  it("faces a standing train down its chosen route before any move", () => {
    const model = panel();
    placed(model);
    feed(
      model,
      {
        event: "request_submitted",
        id: "t1-1",
        train: "t1",
        depart: "a.B",
        dest: ["b.A"],
      },
      { event: "route_chosen", id: "t1-1", route: ["a", "sw.main", "b"] },
    );
    expect(model.blocks().get("a")).toMatchObject({
      state: "occupied",
      train: "t1",
      toward: "B",
    });
  });
});

describe("request layers", () => {
  const submitted: Partial<TraceEvent> = {
    event: "request_submitted",
    id: "t1-1",
    train: "t1",
    depart: "a.B",
    dest: ["b.A", "c.A"],
  };

  it("renders a submitted request as endpoints only", () => {
    const model = panel();
    placed(model);
    feed(model, submitted);
    expect(model.markers()).toEqual([
      { id: "t1-1", train: "t1", at: "a.B", role: "depart" },
      { id: "t1-1", train: "t1", at: "b.A", role: "arrival" },
      { id: "t1-1", train: "t1", at: "c.A", role: "arrival" },
    ]);
    expect(model.litLegs().size).toBe(0);
  });

  it("keeps surviving ends and words the pruned ones at admission", () => {
    const model = panel();
    placed(model);
    feed(model, submitted, {
      event: "request_admitted",
      id: "t1-1",
      dest: ["b.A"],
      pruned: [{ end: "c.A", reason: "no_entry" }],
    });
    expect(model.markers()).toEqual([
      { id: "t1-1", train: "t1", at: "a.B", role: "depart" },
      { id: "t1-1", train: "t1", at: "b.A", role: "arrival" },
      { id: "t1-1", train: "t1", at: "c.A", role: "pruned", note: "not enterable" },
    ]);
    expect(model.litLegs().size).toBe(0);
  });

  it("lights the chosen route and drops the endpoint markers", () => {
    const model = panel();
    placed(model);
    feed(model, submitted, {
      event: "route_chosen",
      id: "t1-1",
      route: ["a", "sw.side", "c"],
    });
    expect(model.markers()).toEqual([]);
    expect(model.litLegs().get("sw1")).toEqual(new Set(["diverging"]));
    expect(model.litLegs().get("p1")).toEqual(new Set([WHOLE]));
    expect(model.blocks().get("c")).toMatchObject({ state: "planned", train: "t1" });
  });

  it("clears the route's lighting when the request completes", () => {
    const model = panel();
    placed(model);
    feed(
      model,
      submitted,
      { event: "route_chosen", id: "t1-1", route: ["a", "sw.main", "b"] },
      { event: "request_completed", id: "t1-1" },
    );
    expect(model.litLegs().size).toBe(0);
  });

  it("spells a rejection out at the request's endpoints", () => {
    const model = panel();
    placed(model);
    feed(model, submitted, {
      event: "request_rejected",
      id: "t1-1",
      reason: "unreachable",
    });
    expect(model.markers()).toEqual([
      {
        id: "t1-1",
        train: "t1",
        at: "a.B",
        role: "rejected",
        note: "no path exists",
      },
      { id: "t1-1", train: "t1", at: "b.A", role: "rejected" },
      { id: "t1-1", train: "t1", at: "c.A", role: "rejected" },
    ]);
  });

  it("clears a rejection when the train asks again", () => {
    const model = panel();
    placed(model);
    feed(
      model,
      submitted,
      { event: "request_rejected", id: "t1-1", reason: "no_fit" },
      { ...submitted, id: "t1-2", dest: ["b.A"] },
    );
    expect(model.markers().every((marker) => marker.id === "t1-2")).toBe(true);
  });
});

describe("signals", () => {
  it("shows green exactly while the resource beyond is locked to the standing train", () => {
    const model = panel();
    placed(model);
    expect(model.greenEnds().size).toBe(0);
    feed(model, { event: "lock_granted", train: "t1", resources: ["sw.main", "b"] });
    expect(model.greenEnds()).toEqual(new Set(["a.B"]));
    feed(model, { event: "lock_released", train: "t1", resources: ["sw.main"] });
    expect(model.greenEnds().size).toBe(0);
  });

  it("stays red when the resource beyond is another train's", () => {
    const model = panel();
    placed(model);
    feed(model, { event: "lock_granted", train: "t2", resources: ["sw.side", "c"] });
    expect(model.greenEnds().size).toBe(0);
  });

  it("keeps the signal behind a crossed transit red", () => {
    const model = panel();
    placed(model);
    feed(
      model,
      {
        event: "request_submitted",
        id: "t1-1",
        train: "t1",
        depart: "a.B",
        dest: ["b.A"],
      },
      { event: "route_chosen", id: "t1-1", route: ["a", "sw.main", "b"] },
      { event: "lock_granted", train: "t1", resources: ["sw.main", "b"] },
      { event: "move_granted", id: "t1-1", train: "t1", transit: "sw.main", into: "b" },
      { event: "block_occupied", block: "b" },
      { event: "block_vacated", block: "a" },
    );
    // t1 stands in b facing B; sw.main behind it at b.A is still locked to
    // it, but a green there would promise a departure no grant allows.
    expect(model.greenEnds().has("b.A")).toBe(false);
    feed(model, { event: "lock_granted", train: "t1", resources: ["jt.back"] });
    expect(model.greenEnds()).toEqual(new Set(["b.B"]));
  });
});

describe("reset", () => {
  it("forgets everything, placement rule included", () => {
    const model = panel();
    placed(model);
    model.reset();
    expect(model.blocks().get("a")).toMatchObject({ state: "free" });
    feed(model, { event: "lock_granted", train: "t1", resources: ["a"] });
    expect(model.blocks().get("a")).toMatchObject({ state: "occupied" });
  });
});
