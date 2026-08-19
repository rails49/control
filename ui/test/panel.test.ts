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

  it("spells a stale departure out, so a joining panel sees why (#73)", () => {
    const model = panel();
    placed(model);
    feed(model, submitted, {
      event: "request_rejected",
      id: "t1-1",
      reason: "wrong_origin",
    });
    expect(model.markers()[0]).toEqual({
      id: "t1-1",
      train: "t1",
      at: "a.B",
      role: "rejected",
      note: "the train is elsewhere",
    });
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
  const shown = (model: ReturnType<typeof panel>) =>
    Object.fromEntries(model.aspects());

  it("shows nothing until the dispatcher has said anything", () => {
    const model = panel();
    placed(model);
    expect(model.aspects().size).toBe(0);
  });

  it("shows what it is told, and nothing it was not told", () => {
    const model = panel();
    placed(model);
    feed(model, {
      event: "aspects",
      aspects: { "a.B": "clear", "b.A": "stop", "b.B": "approach" },
    });
    expect(shown(model)).toEqual({
      "a.B": "clear",
      "b.A": "stop",
      "b.B": "approach",
    });
    // a.A was never named: nothing ever leaves it, so it carries no signal
    // and is absent rather than dark.
    expect(model.aspects().has("a.A")).toBe(false);
  });

  it("replaces the whole picture, the topic being last-value", () => {
    const model = panel();
    placed(model);
    feed(
      model,
      { event: "aspects", aspects: { "a.B": "clear", "b.A": "stop" } },
      { event: "aspects", aspects: { "a.B": "stop", "b.A": "approach" } },
    );
    expect(shown(model)).toEqual({ "a.B": "stop", "b.A": "approach" });
  });

  it("derives no aspect of its own from the lock ledger", () => {
    // The locks below would have lit a.B green under the old locked-ahead
    // derivation. One authority publishes aspects now (ADR-0025), so the
    // panel waits to be told and shows nothing meanwhile.
    const model = panel();
    placed(model);
    feed(model, { event: "lock_granted", train: "t1", resources: ["sw.main", "b"] });
    expect(model.aspects().size).toBe(0);

    feed(model, { event: "aspects", aspects: { "a.B": "approach" } });
    expect(shown(model)).toEqual({ "a.B": "approach" });
    feed(model, { event: "lock_released", train: "t1", resources: ["sw.main"] });
    expect(shown(model)).toEqual({ "a.B": "approach" });
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

/**
 * The scheduler half (#72): a live session's placement and facing come from
 * the scenario, since the bridge relays the bus and the placement locks were
 * published before any browser connected. Facing is then fully determined —
 * a train faces away from the end it entered through (ADR-0019).
 */
describe("facing", () => {
  const STOCK = {
    t1: { length: 900, at: "a", facing: "B" },
    t2: { length: 900, at: "c", facing: "B" },
  };

  it("stands the scenario's trains where it places them, facing as it says", () => {
    const model = panel();
    model.place(STOCK);
    expect(model.blocks().get("a")).toMatchObject({
      state: "occupied",
      train: "t1",
      toward: "B",
    });
    expect(model.blocks().get("c")).toMatchObject({ train: "t2", toward: "B" });
  });

  it("does not read a later lock as a second placement", () => {
    const model = panel();
    model.place(STOCK);
    feed(model, { event: "lock_granted", train: "t1", resources: ["sw.main", "b"] });
    expect(model.blocks().get("b")).toMatchObject({ state: "reserved" });
  });

  it("composes a request departing through the train's facing end", () => {
    const model = panel();
    model.place(STOCK);
    expect(model.request("t1", ["b.A", "b.B"])).toEqual({
      id: "t1-1",
      train: "t1",
      depart: "a.B",
      dest: ["b.A", "b.B"],
    });
    expect(model.request("t1", ["c.A"])?.id).toBe("t1-2");
    expect(model.request("t2", ["b.A"])?.id).toBe("t2-1");
  });

  it("has nothing to submit for a train that stands nowhere it knows", () => {
    expect(panel().request("ghost", ["b.A"])).toBeNull();
  });

  it("still departs from the block it stands in while a route runs", () => {
    // A grant names the next block a tick before the train is in it. Facing
    // has to keep naming the block the train actually stands in, or a drag
    // mid-route composes nothing and the drop is silently swallowed — which
    // is the panel judging a request, the one thing it must never do (#67).
    const model = panel();
    model.place(STOCK);
    feed(
      model,
      { event: "lock_granted", train: "t1", resources: ["sw.main", "b"] },
      { event: "move_granted", id: "t1-1", train: "t1", transit: "sw.main", into: "b" },
    );
    expect(model.blocks().get("a")).toMatchObject({ train: "t1", toward: "B" });
    expect(model.request("t1", ["c.A"])).toMatchObject({ depart: "a.B" });
  });

  it("never overwrites what the bus has shown with what the scenario says", () => {
    // Rejoining re-reads the scenario, but the railroad has moved on since it
    // was written. Re-seeding would put the train back where it started, and
    // a drag would then state a departure block the dispatcher knows is
    // wrong — rejected as `wrong_origin` (#73), so the train would be
    // undraggable until the bus showed it moving again.
    const model = panel();
    model.place(STOCK);
    feed(
      model,
      { event: "lock_granted", train: "t1", resources: ["sw.main", "b"] },
      { event: "move_granted", id: "t1-1", train: "t1", transit: "sw.main", into: "b" },
      { event: "block_occupied", block: "b" },
      { event: "block_vacated", block: "a" },
    );
    model.place(STOCK);
    expect(model.blocks().get("b")).toMatchObject({ train: "t1", toward: "B" });
    expect(model.blocks().get("a")).toMatchObject({ state: "free" });
    expect(model.request("t1", ["c.A"])).toMatchObject({ depart: "b.B" });
  });

  it("numbers a rejoined session's ids on from the ones it has seen", () => {
    // Leaving and rejoining re-places the trains, but the session on the
    // other side of the bridge is the same one and remembers the ids it was
    // given. Minting `t1-1` twice would hand it a duplicate.
    const model = panel();
    model.place(STOCK);
    expect(model.request("t1", ["b.A"])?.id).toBe("t1-1");
    model.place(STOCK);
    expect(model.request("t1", ["b.A"])?.id).toBe("t1-2");
  });

  it("counts an id it merely overheard, so a second panel does not clash", () => {
    const model = panel();
    model.place(STOCK);
    feed(model, {
      event: "request_submitted",
      id: "t1-4",
      train: "t1",
      depart: "a.B",
      dest: ["b.A"],
    });
    expect(model.request("t1", ["b.A"])?.id).toBe("t1-5");
  });

  it("flips facing away from the entry end once a route has run", () => {
    const model = panel();
    model.place(STOCK);
    feed(
      model,
      { event: "request_submitted", id: "t1-1", train: "t1", depart: "a.B", dest: ["b.B"] },
      { event: "route_chosen", id: "t1-1", route: ["a", "sw.main", "b"] },
      { event: "lock_granted", train: "t1", resources: ["sw.main", "b"] },
      { event: "move_granted", id: "t1-1", train: "t1", transit: "sw.main", into: "b" },
      { event: "block_occupied", block: "b" },
      { event: "block_vacated", block: "a" },
      { event: "request_completed", id: "t1-1" },
    );
    // sw.main joins a.B to b.A: t1 entered b through A, so it now faces B and
    // its next drag departs nose-first from there.
    expect(model.request("t1", ["c.A"])).toMatchObject({ depart: "b.B" });
  });
});
