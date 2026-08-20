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

function panel(page = "p1"): Panel {
  return new Panel(LAYOUT, EXPLAIN, page);
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

  it("spells out a payload the dispatcher could not read (#107)", () => {
    const spelled = {
      unknown_train: "the session has no such train",
      unknown_block: "the layout has no such block",
      malformed: "the request could not be read",
    };
    for (const [reason, note] of Object.entries(spelled)) {
      const model = panel();
      placed(model);
      feed(model, submitted, { event: "request_rejected", id: "t1-1", reason });
      expect(model.markers()[0]).toEqual({
        id: "t1-1",
        train: "t1",
        at: "a.B",
        role: "rejected",
        note,
      });
    }
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

/**
 * Joining a running session (#106, ADR-0032). The dispatcher publishes its
 * picture on `state/allocation` and the relay hands a connecting client each
 * state topic's last value, so the page opens on where the railroad *is*
 * rather than on where the scenario says it started.
 */
describe("the run's picture", () => {
  const PICTURE = {
    event: "allocation",
    trains: { t1: "b" },
    locks: { b: "t1", "jt.back": "t1", c: "t1" },
    requests: [
      {
        id: "t1-7",
        train: "t1",
        depart: "b.B",
        dest: ["c.B"],
        route: ["b", "jt.back", "c"],
      },
    ],
  };

  it("stands the trains where it says, and holds what it says is held", () => {
    const model = panel();
    feed(model, PICTURE);
    expect(model.blocks().get("b")).toMatchObject({ state: "occupied", train: "t1" });
    expect(model.blocks().get("c")).toMatchObject({ state: "reserved", train: "t1" });
    expect(model.blocks().get("a")).toMatchObject({ state: "free" });
  });

  it("draws a committed route from the request that owns it", () => {
    const model = panel();
    feed(model, PICTURE);
    expect(model.litLegs()).toEqual(new Map([["p2", new Set([WHOLE])]]));
  });

  it("marks a live request that has not been committed", () => {
    const model = panel();
    feed(model, {
      event: "allocation",
      trains: { t1: "a" },
      locks: { a: "t1" },
      requests: [{ id: "t1-7", train: "t1", depart: "a.B", dest: ["b.A", "c.A"] }],
    });
    expect(model.markers()).toEqual([
      { id: "t1-7", train: "t1", at: "a.B", role: "depart" },
      { id: "t1-7", train: "t1", at: "b.A", role: "arrival" },
      { id: "t1-7", train: "t1", at: "c.A", role: "arrival" },
    ]);
  });

  it("supersedes the scenario, which says where the railroad started", () => {
    // The page reads the scenario before the socket opens, so the picture
    // arrives second and has the last word: a train the run has moved is
    // drawn where it now stands, and a drag departs from there.
    const model = panel();
    model.place({ t1: { at: "a", facing: "B" } });
    feed(model, PICTURE);
    expect(model.blocks().get("a")).toMatchObject({ state: "free" });
    expect(model.blocks().get("b")).toMatchObject({ train: "t1", toward: "B" });
    expect(model.request("t1", ["c.A"])).toMatchObject({ depart: "b.B" });
  });

  it("keeps a grant the sensor has not caught up with", () => {
    // The picture is published at the end of the grant phase, so it reaches
    // the page before the occupancy the phase's own grants cause. A train
    // still faces the end it is leaving through until then, and the facing
    // the grant promised has to survive the picture that overtakes it.
    const model = panel();
    model.place({ t1: { at: "a", facing: "B" } });
    feed(
      model,
      { event: "move_granted", id: "t1-1", train: "t1", transit: "sw.main", into: "b" },
      {
        event: "allocation",
        trains: { t1: "a" },
        locks: { a: "t1", "sw.main": "t1", b: "t1" },
        requests: [],
      },
      { event: "block_occupied", block: "b" },
      { event: "block_vacated", block: "a" },
    );
    expect(model.blocks().get("b")).toMatchObject({ train: "t1", toward: "B" });
    expect(model.request("t1", ["c.A"])).toMatchObject({ depart: "b.B" });
  });

  it("leaves a rejection standing, the picture never carrying one", () => {
    // A rejection is the panel's whole answer to a filter-free drag, and the
    // dispatcher does not hold the request it refused. Letting the next
    // picture wipe the marker would take the reason off the screen the moment
    // anything else on the railroad moved.
    const model = panel();
    feed(
      model,
      { event: "request_submitted", id: "t1-9", train: "t1", depart: "a.B", dest: ["b.A"] },
      { event: "request_rejected", id: "t1-9", reason: "unreachable" },
      PICTURE,
    );
    expect(model.markers().filter((marker) => marker.id === "t1-9")).toEqual([
      { id: "t1-9", train: "t1", at: "a.B", role: "rejected", note: "no path exists" },
      { id: "t1-9", train: "t1", at: "b.A", role: "rejected" },
    ]);
  });

  it("forgets a request the picture no longer carries", () => {
    const model = panel();
    feed(model, PICTURE, { ...PICTURE, requests: [] });
    expect(model.markers()).toEqual([]);
    expect(model.litLegs().size).toBe(0);
  });

  it("does not read a lock after it as a placement", () => {
    // The picture is the placement a joining page gets, so what follows is
    // an ordinary reservation — the same rule the first tick sets in a
    // replay.
    const model = panel();
    feed(model, PICTURE, {
      event: "lock_granted",
      train: "t1",
      resources: ["sw.main", "a"],
    });
    expect(model.blocks().get("a")).toMatchObject({ state: "reserved" });
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
      id: "t1-p1-1",
      train: "t1",
      depart: "a.B",
      dest: ["b.A", "b.B"],
    });
    expect(model.request("t1", ["c.A"])?.id).toBe("t1-p1-2");
    expect(model.request("t2", ["b.A"])?.id).toBe("t2-p1-1");
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

/**
 * Request ids (ADR-0033). Uniqueness is the whole contract: both readers use
 * the id as a key and neither reads it, so what a page mints has only to be
 * its own.
 */
describe("request ids", () => {
  const STOCK = { t1: { at: "a", facing: "B" } };

  it("mints from the page's own nonce, counting per train", () => {
    const model = panel("7fa2");
    model.place(STOCK);
    expect(model.request("t1", ["b.A"])?.id).toBe("t1-7fa2-1");
    expect(model.request("t1", ["c.A"])?.id).toBe("t1-7fa2-2");
  });

  it("mints nothing a reloaded page could mint again", () => {
    // #73's own reproduction: submit, reload, drag the same train. The
    // counter lived in the page, so a reload started it at one, the
    // dispatcher dropped the duplicate at the top of admission before any
    // check ran, and no answer of any kind came back — the marker sat in
    // "requested" for good. A fresh page is a fresh nonce, so there is
    // nothing left to re-use.
    const first = panel();
    first.place(STOCK);
    const before = first.request("t1", ["b.A"])!.id;

    const reloaded = new Panel(LAYOUT, EXPLAIN);
    reloaded.place(STOCK);
    expect(reloaded.request("t1", ["b.A"])!.id).not.toBe(before);
  });

  it("gives two pages of one session different ids", () => {
    const one = new Panel(LAYOUT, EXPLAIN);
    const other = new Panel(LAYOUT, EXPLAIN);
    one.place(STOCK);
    other.place(STOCK);
    expect(one.request("t1", ["b.A"])!.id).not.toBe(other.request("t1", ["b.A"])!.id);
  });

  it("does not read an id off the bus, whatever shape it has", () => {
    // The relay echoes every request back, the file scheduler's included.
    // Parsing an ordinal out of one was the third reader the shape never
    // promised to have, and the page's own count is unaffected by it.
    const model = panel("7fa2");
    model.place(STOCK);
    feed(model, {
      event: "request_submitted",
      id: "t1-4",
      train: "t1",
      depart: "a.B",
      dest: ["b.A"],
    });
    expect(model.request("t1", ["b.A"])?.id).toBe("t1-7fa2-1");
  });
});

/**
 * Where each point lies, as the alignment command says (ADR-0022, #98). The
 * panel works nothing out: the dispatcher sends the addresses and positions
 * the transit's way needs, and this is the ledger of what it last said.
 */
describe("point positions", () => {
  it("reads them off the alignment command, address by address", () => {
    const model = panel();
    feed(model, {
      event: "align",
      connection: "sw",
      transit: "side",
      points: [
        { addr: "12", position: "thrown" },
        { addr: "13", position: "closed" },
      ],
    });
    expect(model.positions()).toEqual(
      new Map([
        ["12", "thrown"],
        ["13", "closed"],
      ]),
    );
  });

  it("leaves a point where the last command naming it left it", () => {
    // A point stays thrown until something throws it back: `align` names the
    // points one transit needs, and says nothing about the rest of them.
    const model = panel();
    feed(
      model,
      {
        event: "align",
        connection: "sw",
        transit: "side",
        points: [{ addr: "12", position: "thrown" }],
      },
      {
        event: "align",
        connection: "jt",
        transit: "back",
        points: [{ addr: "13", position: "closed" }],
      },
      {
        event: "align",
        connection: "sw",
        transit: "main",
        points: [{ addr: "12", position: "closed" }],
      },
    );
    expect(model.positions()).toEqual(
      new Map([
        ["12", "closed"],
        ["13", "closed"],
      ]),
    );
  });

  it("forgets where they lie when a replay starts over", () => {
    // A run's points belong to that run: replaying from the top shows a
    // railroad nothing has commanded yet, not the last run's last word.
    const model = panel();
    feed(model, {
      event: "align",
      connection: "sw",
      transit: "side",
      points: [{ addr: "12", position: "thrown" }],
    });
    model.reset();
    expect(model.positions()).toEqual(new Map());
  });

  it("takes a transit needing nothing thrown as saying nothing", () => {
    const model = panel();
    feed(
      model,
      {
        event: "align",
        connection: "sw",
        transit: "side",
        points: [{ addr: "12", position: "thrown" }],
      },
      { event: "align", connection: "jt", transit: "back", points: [] },
    );
    expect(model.positions()).toEqual(new Map([["12", "thrown"]]));
  });
});
