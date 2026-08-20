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

/** The scheduler's facing topic, which is where every arrow comes from. */
function facing(...ends: string[]): Partial<TraceEvent> {
  return {
    event: "facing",
    facing: Object.fromEntries(
      ends.map((end, at) => [`t${at + 1}`, end] as const),
    ),
  };
}

function feed(model: Panel, ...events: Partial<TraceEvent>[]): void {
  for (const event of events)
    model.apply({ boundary: 0, event: "?", ...event } as TraceEvent);
}

/** The placement locks a trace opens with, then the first boundary. */
function placed(model: Panel): void {
  feed(
    model,
    { event: "lock_granted", train: "t1", resources: ["a"] },
    { event: "boundary" },
  );
}

describe("occupancy", () => {
  it("stands a train where its pre-boundary lock says", () => {
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

  it("derives no direction of its own from a granted move", () => {
    // The move below would have turned the arrow under the old derivation.
    // Facing is the scheduler's, on its own topic (ADR-0036), and a second
    // party working it out is a second authority to disagree with.
    const model = panel();
    placed(model);
    feed(
      model,
      { event: "lock_granted", train: "t1", resources: ["sw.main", "b"] },
      { event: "move_granted", id: "t1-1", train: "t1", transit: "sw.main", into: "b" },
      { event: "block_occupied", block: "b" },
      { event: "block_vacated", block: "a" },
    );
    expect(model.blocks().get("b")).toMatchObject({ state: "occupied", train: "t1" });
    expect(model.blocks().get("b")?.toward).toBeUndefined();
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

  it("keeps a pruned end's reason when the picture is republished", () => {
    const model = panel();
    placed(model);
    feed(model, submitted, {
      event: "request_admitted",
      id: "t1-1",
      dest: ["b.A"],
      pruned: [{ end: "c.A", reason: "no_entry" }],
    });
    // The dispatcher publishes the picture in the same boundary it admits, and
    // does not hold the pruning — an admission-time fact. The panel does, so a
    // republish must not wipe the note off the end it marks.
    feed(model, {
      event: "allocation",
      trains: { t1: "a" },
      locks: { a: "t1" },
      requests: [{ id: "t1-1", train: "t1", depart: "a.B", dest: ["b.A"] }],
    });
    expect(model.markers()).toEqual([
      { id: "t1-1", train: "t1", at: "a.B", role: "depart" },
      { id: "t1-1", train: "t1", at: "b.A", role: "arrival" },
      { id: "t1-1", train: "t1", at: "c.A", role: "pruned", note: "not enterable" },
    ]);
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

  it("is where a joining page opens, whatever order the two topics arrive", () => {
    // Both are last values the relay hands a connecting client before any
    // live frame (ADR-0032), and neither writes the other's half: the
    // picture stands the trains, the scheduler's topic turns them.
    const model = panel();
    feed(model, facing("b.B"), PICTURE);
    expect(model.blocks().get("a")).toMatchObject({ state: "free" });
    expect(model.blocks().get("b")).toMatchObject({ train: "t1", toward: "B" });

    const other = panel();
    feed(other, PICTURE, facing("b.B"));
    expect(other.blocks().get("b")).toMatchObject({ train: "t1", toward: "B" });
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
    // an ordinary reservation — the same rule the first boundary sets in a
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
 * Facing, which the panel reads and never derives (ADR-0036). The scheduler
 * holds it and publishes the whole map on a last-value topic, so a train that
 * has never moved has an arrow for the same reason a moved one does — and two
 * tabs cannot disagree about one, neither of them holding it.
 */
describe("facing", () => {
  it("turns each train where the topic says, on the block it names", () => {
    const model = panel();
    placed(model);
    feed(model, facing("a.B"));
    expect(model.blocks().get("a")).toMatchObject({
      state: "occupied",
      train: "t1",
      toward: "B",
    });
  });

  it("replaces the whole map, the topic being last-value", () => {
    const model = panel();
    feed(
      model,
      { event: "allocation", trains: { t1: "a", t2: "c" }, locks: {}, requests: [] },
      facing("a.B", "c.B"),
      { event: "facing", facing: { t1: "a.A" } },
    );
    expect(model.blocks().get("a")).toMatchObject({ train: "t1", toward: "A" });
    expect(model.blocks().get("c")?.toward).toBeUndefined();
  });

  it("draws no arrow while facing names a block the train is not in yet", () => {
    // A grant names the next block a boundary before the sensor does, and
    // scheduler follows the grant. Until the sensor speaks the train is drawn
    // where it stands, with no arrow — rather than with the next block's
    // arrow on this one.
    const model = panel();
    placed(model);
    feed(model, facing("b.B"));
    expect(model.blocks().get("a")).toMatchObject({ state: "occupied", train: "t1" });
    expect(model.blocks().get("a")?.toward).toBeUndefined();
    feed(
      model,
      { event: "lock_granted", train: "t1", resources: ["sw.main", "b"] },
      { event: "block_occupied", block: "b" },
      { event: "block_vacated", block: "a" },
    );
    expect(model.blocks().get("b")).toMatchObject({ train: "t1", toward: "B" });
  });

  it("forgets it on reset, as it forgets everything else", () => {
    const model = panel();
    placed(model);
    feed(model, facing("a.B"));
    model.reset();
    feed(model, { event: "lock_granted", train: "t1", resources: ["a"] });
    expect(model.blocks().get("a")?.toward).toBeUndefined();
  });
});

/**
 * What a drag puts on the bus (ADR-0036). A gesture is not a request: it
 * names a train and where to put it, and the scheduler adds the id it mints
 * and the departure end it holds. The panel keeps neither, so there is
 * nothing here a reload could re-use and nothing a second tab could diverge
 * from.
 */
describe("gestures", () => {
  it("names the train and the ends, and carries nothing else", () => {
    const model = panel();
    placed(model);
    expect(model.compose("t1", ["b.A", "b.B"])).toEqual({
      train: "t1",
      dest: ["b.A", "b.B"],
    });
  });

  it("composes for a train it has been shown nothing about", () => {
    // Filter-free to the end (#67): the panel refusing a drop would be the
    // panel judging a request, and the scheduler drops what it cannot
    // compose — in silence, and to the trace.
    expect(panel().compose("ghost", ["b.A"])).toEqual({
      train: "ghost",
      dest: ["b.A"],
    });
  });

  it("does not read an id off the bus, whatever shape it has", () => {
    // The relay echoes every request back. Parsing an ordinal out of one was
    // a third reader the shape never promised to have (ADR-0033), and there
    // is no counter left here for it to move.
    const model = panel();
    placed(model);
    feed(model, {
      event: "request_submitted",
      id: "t1-4",
      train: "t1",
      depart: "a.B",
      dest: ["b.A"],
    });
    expect(model.compose("t1", ["b.A"])).toEqual({ train: "t1", dest: ["b.A"] });
  });
});

/**
 * Whether a train has a request in flight, which is the one thing the panel
 * pre-judges a gesture on (#124): "Turn around" is offered greyed while it
 * has, because a disabled item says *this train is busy* where silence says
 * nothing.
 */
describe("a request in flight", () => {
  const submitted: Partial<TraceEvent> = {
    event: "request_submitted",
    id: "t1-1",
    train: "t1",
    depart: "a.B",
    dest: ["b.A"],
  };

  it("is nothing at all before a train is dragged", () => {
    const model = panel();
    placed(model);
    expect(model.inFlight("t1")).toBe(false);
  });

  it("holds from submit through admission and commitment", () => {
    const model = panel();
    placed(model);
    feed(model, submitted);
    expect(model.inFlight("t1")).toBe(true);
    feed(model, { event: "request_admitted", id: "t1-1", dest: ["b.A"], pruned: [] });
    expect(model.inFlight("t1")).toBe(true);
    feed(model, { event: "route_chosen", id: "t1-1", route: ["a", "sw.main", "b"] });
    expect(model.inFlight("t1")).toBe(true);
  });

  it("ends when the request completes", () => {
    const model = panel();
    placed(model);
    feed(model, submitted, { event: "request_completed", id: "t1-1" });
    expect(model.inFlight("t1")).toBe(false);
  });

  /** A rejected request's marker stays on screen until the train is dragged
   *  again, and that is precisely when you want to turn around. */
  it("ends on a rejection, whose marker is still shown", () => {
    const model = panel();
    placed(model);
    feed(model, submitted, {
      event: "request_rejected",
      id: "t1-1",
      reason: "no_entry",
    });
    expect(model.inFlight("t1")).toBe(false);
    expect(model.markers().map((marker) => marker.role)).toContain("rejected");
  });

  it("is asked of one train and answered for that one", () => {
    const model = panel();
    placed(model);
    feed(model, submitted);
    expect(model.inFlight("t2")).toBe(false);
  });

  /** A page joining a running session is served the dispatcher's picture,
   *  and every request in it is one the train is busy with. */
  it("is read off the run's picture a joining page is served", () => {
    const model = panel();
    feed(model, {
      event: "allocation",
      trains: { t1: "a" },
      locks: {},
      requests: [{ id: "t1-9", train: "t1", depart: "a.B", dest: ["b.A"] }],
    });
    expect(model.inFlight("t1")).toBe(true);
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
    expect(model.positionsByAddress()).toEqual(
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
    expect(model.positionsByAddress()).toEqual(
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
    expect(model.positionsByAddress()).toEqual(new Map());
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
    expect(model.positionsByAddress()).toEqual(new Map([["12", "thrown"]]));
  });
});
