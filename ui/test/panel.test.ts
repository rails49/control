/**
 * The panel model, driven as the trace replay drives it: bus payloads in,
 * render state out (ui/PANEL.md, #70). No DOM anywhere — block states,
 * signal aspects and request markers are data the component only paints.
 */

import { describe, expect, it } from "vitest";

import type { Wire } from "../src/model/drawing.js";
import { WHOLE } from "../src/model/inspect.js";
import { outstanding, Panel, roster } from "../src/model/panel.js";
import type { Explained, Layout } from "../src/model/store.js";
import type { TraceEvent } from "../src/model/trace.js";

/**
 * A toy railroad: block `a` faces a turnout `sw1` whose two ways lead to `b`
 * and `c`, and `b` and `c` are joined at their far ends by a joint routed
 * through a bend. On the bus its resources are `a`, `b`, `c`, `sw.main`,
 * `sw.side`, `jt.back`.
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

/**
 * The drawing the layout above derives from, as far as its wires go: what
 * `sw.side` runs over inside the throat, and the two wires of the joint —
 * which crosses no symbol declaring a transit and so lights nothing but its
 * wires.
 */
const WIRES: Wire[] = [
  ["a.B", "sw1.toe"],
  ["sw1.straight", "b.A"],
  ["sw1.diverging", "p1.P"],
  ["p1.P", "c.A"],
  ["b.B", "p2.P"],
  ["p2.P", "c.B"],
];

const wire = (one: string, two: string) => [one, two].sort().join(" ");

function panel(): Panel {
  return new Panel(LAYOUT, EXPLAIN, WIRES);
}

/** The scheduler's facing topic, which is where every arrow comes from: one
 *  run across a block per train, `t1` first (#241). */
function facing(...runs: string[]): Partial<TraceEvent> {
  return {
    event: "facing",
    facing: Object.fromEntries(
      runs.map((run, at) => [`t${at + 1}`, run] as const),
    ),
  };
}

function feed(model: Panel, ...events: Partial<TraceEvent>[]): void {
  for (const event of events) model.apply({ event: "?", ...event } as TraceEvent);
}

/** The placement locks a run opens with, then the opening picture. */
function placed(model: Panel): void {
  feed(
    model,
    { event: "lock_granted", train: "t1", resources: ["a"] },
    { event: "allocation", trains: { t1: "a" }, locks: { a: "t1" }, requests: [] },
  );
}

describe("occupancy", () => {
  it("stands a train where its pre-picture lock says", () => {
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

  it("shades a locked but empty block as locked, a vacated one too", () => {
    const model = panel();
    placed(model);
    feed(
      model,
      { event: "lock_granted", train: "t1", resources: ["sw.main", "b"] },
    );
    expect(model.blocks().get("b")).toMatchObject({
      state: "locked",
      train: "t1",
    });
    feed(
      model,
      { event: "block_occupied", block: "b" },
      { event: "block_vacated", block: "a" },
    );
    expect(model.blocks().get("a")).toMatchObject({
      state: "locked",
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
    expect(model.lit().legs.size).toBe(0);
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
    expect(model.lit().legs.size).toBe(0);
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
    // The dispatcher publishes the picture as it admits, and does not hold
    // the pruning — an admission-time fact. The panel does, so a republish
    // must not wipe the note off the end it marks.
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
    expect(model.lit().legs.get("sw1")).toEqual(new Set(["diverging"]));
    expect(model.lit().legs.get("p1")).toEqual(new Set([WHOLE]));
    expect(model.blocks().get("c")).toMatchObject({ state: "committed", train: "t1" });
  });

  it("lights the wires the route's transits run over, junction and all", () => {
    // The wire between the frog and the bend is inside the throat, and it is
    // what makes the route read as one run rather than as scattered lit frogs.
    const model = panel();
    placed(model);
    feed(model, submitted, {
      event: "route_chosen",
      id: "t1-1",
      route: ["a", "sw.side", "c"],
    });
    expect([...model.lit().wires.keys()].sort()).toEqual(
      [
        wire("a.B", "sw1.toe"),
        wire("sw1.diverging", "p1.P"),
        wire("p1.P", "c.A"),
      ].sort(),
    );
  });

  it("lights every wire of a joint's chain, which lights nothing else", () => {
    // A joint crosses no symbol declaring a transit, so it has no leg to
    // light: before the wires it was a dark gap between two lit blocks.
    // Routed round a corner it is several wires, and all of them are on it.
    const model = panel();
    placed(model);
    feed(model, submitted, {
      event: "route_chosen",
      id: "t1-1",
      route: ["b", "jt.back", "c"],
    });
    expect([...model.lit().wires.keys()].sort()).toEqual(
      [wire("b.B", "p2.P"), wire("p2.P", "c.B")].sort(),
    );
  });

  it("leaves the wires of the road not taken dark", () => {
    const model = panel();
    placed(model);
    feed(model, submitted, {
      event: "route_chosen",
      id: "t1-1",
      route: ["a", "sw.main", "b"],
    });
    expect([...model.lit().wires.keys()].sort()).toEqual(
      [wire("a.B", "sw1.toe"), wire("sw1.straight", "b.A")].sort(),
    );
  });

  /**
   * The two colours (#143): green where the dispatcher holds the lock and the
   * train may move, cyan where the route is chosen and the claim has not been
   * made yet. Both are read off resources the model already holds — the lock
   * ledger and the committed route — so nothing here is derived twice.
   */
  it("locks what the ledger holds and plans the rest of the route", () => {
    const model = panel();
    placed(model);
    feed(
      model,
      submitted,
      { event: "route_chosen", id: "t1-1", route: ["a", "sw.side", "c"] },
      { event: "lock_granted", train: "t1", resources: ["sw.side"] },
    );
    const lit = model.lit();
    expect(lit.state.get("sw1")).toBe("locked");
    expect(lit.state.get("p1")).toBe("locked");
    expect(lit.wires.get(wire("a.B", "sw1.toe"))).toBe("locked");
    expect(model.blocks().get("c")).toMatchObject({ state: "committed" });
  });

  it("lights a committed route the dispatcher has not claimed yet", () => {
    const model = panel();
    placed(model);
    feed(model, submitted, {
      event: "route_chosen",
      id: "t1-1",
      route: ["a", "sw.side", "c"],
    });
    const lit = model.lit();
    expect(lit.state.get("sw1")).toBe("committed");
    expect([...lit.wires.values()]).toEqual(["committed", "committed", "committed"]);
  });

  it("advances the lock along the route, and drops it when released", () => {
    // Locking is incremental (ADR-0026), so the locked stretch creeping
    // forward along a committed one is a reading of how far the train may go.
    const model = panel();
    placed(model);
    feed(model, submitted, {
      event: "route_chosen",
      id: "t1-1",
      route: ["a", "sw.side", "c"],
    });
    expect(model.lit().state.get("sw1")).toBe("committed");
    feed(model, { event: "lock_granted", train: "t1", resources: ["sw.side"] });
    expect(model.lit().state.get("sw1")).toBe("locked");
    feed(model, { event: "lock_released", train: "t1", resources: ["sw.side"] });
    expect(model.lit().state.get("sw1")).toBe("committed");
  });

  it("keeps a lock the dispatcher still holds after its request completes", () => {
    // Green is the ledger's answer, not the route's intersected with it, so
    // the picture never claims the railroad is freer than it is.
    const model = panel();
    placed(model);
    feed(
      model,
      submitted,
      { event: "route_chosen", id: "t1-1", route: ["a", "sw.side", "c"] },
      { event: "lock_granted", train: "t1", resources: ["sw.side"] },
      { event: "request_completed", id: "t1-1" },
    );
    expect(model.lit().state.get("sw1")).toBe("locked");
    feed(model, { event: "lock_released", train: "t1", resources: ["sw.side"] });
    expect(model.lit().legs.size).toBe(0);
  });

  it("reports a symbol two transits cross at the stronger of the two", () => {
    // The turnout is on both ways out of `a`. One train holds its lock and
    // the other only has it committed; the stronger claim is the true one.
    const model = panel();
    placed(model);
    feed(
      model,
      submitted,
      { event: "route_chosen", id: "t1-1", route: ["a", "sw.side", "c"] },
      { event: "request_submitted", id: "t2-1", train: "t2", depart: "a.B", dest: ["b.A"] },
      { event: "route_chosen", id: "t2-1", route: ["a", "sw.main", "b"] },
      { event: "lock_granted", train: "t2", resources: ["sw.main"] },
    );
    expect(model.lit().state.get("sw1")).toBe("locked");
    expect(model.lit().wires.get(wire("a.B", "sw1.toe"))).toBe("locked");
    // The leg the committed way takes is still lit; only the colour is shared.
    expect(model.lit().legs.get("sw1")).toEqual(
      new Set(["diverging", "straight"]),
    );
  });

  it("keeps the block a train stands in occupied while its route runs", () => {
    const model = panel();
    placed(model);
    feed(
      model,
      submitted,
      { event: "route_chosen", id: "t1-1", route: ["a", "sw.side", "c"] },
      { event: "lock_granted", train: "t1", resources: ["sw.side", "c"] },
    );
    expect(model.blocks().get("a")).toMatchObject({
      state: "occupied",
      train: "t1",
    });
    expect(model.blocks().get("c")).toMatchObject({ state: "locked" });
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
    expect(model.lit().legs.size).toBe(0);
    expect(model.lit().wires.size).toBe(0);
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
      aspects: { "a.B": "clear", "b.A": "stop", "b.B": "caution" },
    });
    expect(shown(model)).toEqual({
      "a.B": "clear",
      "b.A": "stop",
      "b.B": "caution",
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
      { event: "aspects", aspects: { "a.B": "stop", "b.A": "caution" } },
    );
    expect(shown(model)).toEqual({ "a.B": "stop", "b.A": "caution" });
  });

  it("derives no aspect of its own from the lock ledger", () => {
    // The locks below would have lit a.B green under the old locked-ahead
    // derivation. One authority publishes aspects now (ADR-0025), so the
    // panel waits to be told and shows nothing meanwhile.
    const model = panel();
    placed(model);
    feed(model, { event: "lock_granted", train: "t1", resources: ["sw.main", "b"] });
    expect(model.aspects().size).toBe(0);

    feed(model, { event: "aspects", aspects: { "a.B": "caution" } });
    expect(shown(model)).toEqual({ "a.B": "caution" });
    feed(model, { event: "lock_released", train: "t1", resources: ["sw.main"] });
    expect(shown(model)).toEqual({ "a.B": "caution" });
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
    expect(model.blocks().get("c")).toMatchObject({ state: "locked", train: "t1" });
    expect(model.blocks().get("a")).toMatchObject({ state: "free" });
  });

  it("draws a committed route from the request that owns it", () => {
    const model = panel();
    feed(model, PICTURE);
    expect(model.lit().legs).toEqual(new Map([["p2", new Set([WHOLE])]]));
  });

  /** A joining page is served the same picture a replay would have built, so
   *  it must open on the same two colours (ADR-0032). The picture holds the
   *  joint's lock, so the whole of this route is locked. */
  it("opens on the colours the events that built it would have given", () => {
    const model = panel();
    feed(model, PICTURE);
    expect(model.lit().state.get("p2")).toBe("locked");
    expect([...model.lit().wires.values()]).toEqual(["locked", "locked"]);

    const replayed = panel();
    placed(replayed);
    feed(
      replayed,
      { event: "request_submitted", id: "t1-7", train: "t1", depart: "b.B", dest: ["c.B"] },
      { event: "route_chosen", id: "t1-7", route: ["b", "jt.back", "c"] },
      { event: "lock_granted", train: "t1", resources: ["jt.back", "c"] },
    );
    expect(replayed.lit()).toEqual(model.lit());
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
    feed(model, facing("b.A-to-B"), PICTURE);
    expect(model.blocks().get("a")).toMatchObject({ state: "free" });
    expect(model.blocks().get("b")).toMatchObject({ train: "t1", toward: "B" });

    const other = panel();
    feed(other, PICTURE, facing("b.A-to-B"));
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
    // What the picture still holds keeps its colour: green is read from the
    // ledger, and the dispatcher really does still hold these locks.
    expect(model.lit().state.get("p2")).toBe("locked");
    feed(model, { ...PICTURE, requests: [], locks: { b: "t1" } });
    expect(model.lit().legs.size).toBe(0);
    expect(model.lit().wires.size).toBe(0);
  });

  it("does not read a lock after it as a placement", () => {
    // The picture is the placement a joining page gets, so what follows is
    // an ordinary reservation — the same rule the opening picture sets in a
    // replay.
    const model = panel();
    feed(model, PICTURE, {
      event: "lock_granted",
      train: "t1",
      resources: ["sw.main", "a"],
    });
    expect(model.blocks().get("a")).toMatchObject({ state: "locked" });
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
    feed(model, facing("a.A-to-B"));
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
      facing("a.A-to-B", "c.A-to-B"),
      { event: "facing", facing: { t1: "a.B-to-A" } },
    );
    expect(model.blocks().get("a")).toMatchObject({ train: "t1", toward: "A" });
    expect(model.blocks().get("c")?.toward).toBeUndefined();
  });

  it("draws no arrow while facing names a block the train is not in yet", () => {
    // A grant names the next block before the sensor does, and the
    // scheduler follows the grant. Until the sensor speaks the train is drawn
    // where it stands, with no arrow — rather than with the next block's
    // arrow on this one.
    const model = panel();
    placed(model);
    feed(model, facing("b.A-to-B"));
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
    feed(model, facing("a.A-to-B"));
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

  it("says whether a train still stands where it was clicked", () => {
    // A menu opened over a parked train outlives the train: the request it
    // was greyed for completes, and the train is somewhere else by the time
    // the item ungreys.
    const model = panel();
    placed(model);
    expect(model.standsIn("t1", "a")).toBe(true);
    feed(
      model,
      { event: "lock_granted", train: "t1", resources: ["sw.main", "b"] },
      { event: "block_occupied", block: "b" },
      { event: "block_vacated", block: "a" },
    );
    expect(model.standsIn("t1", "a")).toBe(false);
    expect(model.standsIn("t1", "b")).toBe(true);
    expect(model.standsIn("t2", "b")).toBe(false);
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

/**
 * A train between two blocks (#154). The picture carries `crossing`, train →
 * the transit taking it out of the block `trains` still names — the block the
 * sensors last confirmed it in. So the panel draws it on that transit's
 * connection rather than in a block, which is what sends a person to look at
 * a train a restarted session cannot place on its own.
 */
describe("a crossing train", () => {
  const CROSSING = {
    event: "allocation",
    trains: { t1: "a" },
    crossing: { t1: "sw.main" },
    locks: { a: "t1", "sw.main": "t1", b: "t1" },
    requests: [],
  };

  it("is drawn on the connection, between the two ends its transit joins", () => {
    const model = panel();
    feed(model, CROSSING);
    expect(model.crossings()).toEqual([{ train: "t1", between: ["a.B", "b.A"] }]);
  });

  it("stands in no block while it is crossing", () => {
    // `trains` goes on naming the block the sensors last confirmed, and the
    // lock is still held there — but the train is not standing in it, so the
    // block wears the lock's colour and neither the name nor the arrow.
    const model = panel();
    feed(model, facing("a.A-to-B"), CROSSING);
    expect(model.blocks().get("a")).toEqual({ state: "locked", train: "t1" });
    expect(model.blocks().get("b")).toMatchObject({ state: "locked" });
  });

  it("stands in one again as soon as a sensor says it arrived", () => {
    // The same rule the dispatcher clears its own entry on: the mark is
    // written at the grant and dropped when the sensor answers. Waiting for
    // the next picture would draw the train on the connection for a frame
    // after it had plainly got there.
    const model = panel();
    feed(model, CROSSING, { event: "block_occupied", block: "b" });
    expect(model.crossings()).toEqual([]);
    expect(model.blocks().get("b")).toMatchObject({ state: "occupied", train: "t1" });
  });

  it("leaves a picture without one standing every train it names", () => {
    const model = panel();
    feed(model, CROSSING, { ...CROSSING, crossing: {} });
    expect(model.crossings()).toEqual([]);
    expect(model.blocks().get("a")).toMatchObject({ state: "occupied", train: "t1" });
  });

  it("is dropped where the drawing on screen has no such transit", () => {
    // The picture is a railroad's, and a page can be showing another one:
    // one train the panel cannot place, rather than a panel that cannot draw.
    // Either half of the resource can be the one this layout does not have.
    const model = panel();
    feed(model, { ...CROSSING, crossing: { t1: "elsewhere.main" } });
    expect(model.crossings()).toEqual([]);

    feed(model, { ...CROSSING, crossing: { t1: "sw.elsewhere" } });
    expect(model.crossings()).toEqual([]);
  });

  it("is forgotten when a replay starts over", () => {
    const model = panel();
    feed(model, CROSSING);
    model.reset();
    expect(model.crossings()).toEqual([]);
  });
});

/**
 * What the detectors dispute (#153). While the run is held the dispatcher
 * compares its placement against the occupancy the layout has reported and
 * publishes the two contradictions; the panel marks them, because they are
 * where a person is sent first. It judges none of it — which blocks were
 * reported on at all is knowledge only the dispatcher has.
 */
/**
 * Which trains are on the layout, and where each of them stands (#169).
 *
 * The roster pane lists them and the freeze rule counts them, and both read
 * this one answer: **placed** is presence in the run's picture, and a train
 * that is not in it is off the layout
 * ([ADR-0039](../../docs/adr/0039-a-train-may-be-off-the-layout.md)).
 */
describe("the trains the run has placed", () => {
  it("names each with the block it stands in, in one order", () => {
    const model = panel();
    feed(model, {
      event: "allocation",
      trains: { t2: "b", t1: "a" },
      locks: { a: "t1", b: "t2" },
      requests: [],
    });
    expect(model.placed()).toEqual([
      { train: "t1", block: "a" },
      { train: "t2", block: "b" },
    ]);
  });

  /** A train between two blocks is on the layout as much as a standing one —
   *  it is holding a transit — and stands in none, which is what the pane
   *  says of it and what the freeze counts. */
  it("keeps a crossing train, standing in no block", () => {
    const model = panel();
    feed(model, {
      event: "allocation",
      trains: { t1: "a" },
      crossing: { t1: "sw.main" },
      locks: { a: "t1", "sw.main": "t1", b: "t1" },
      requests: [],
    });
    expect(model.placed()).toEqual([{ train: "t1", block: null }]);
  });

  /** A train whose head is in the next block and whose tail has not cleared
   *  the last one is in two blocks at once, and is one train: the pane draws
   *  it one row, in the block it is arriving in. */
  it("draws a train holding two blocks once, in the newer of them", () => {
    const model = panel();
    feed(
      model,
      { event: "lock_granted", train: "t1", resources: ["a"] },
      { event: "allocation", trains: { t1: "a" }, locks: { a: "t1" }, requests: [] },
      { event: "lock_granted", train: "t1", resources: ["b"] },
      { event: "block_occupied", block: "b" },
    );
    expect(model.placed()).toEqual([{ train: "t1", block: "b" }]);
  });

  it("has nothing to say about an empty layout", () => {
    const model = panel();
    expect(model.placed()).toEqual([]);
    feed(model, { event: "allocation", trains: {}, locks: {}, requests: [] });
    expect(model.placed()).toEqual([]);
  });
});

/**
 * The roster pane's rows: what the railroad owns joined to what the run has
 * (#170). Two sources because they are two things — the store says what stock
 * there is, the bus says where it stands (ADR-0010).
 */
describe("the roster's rows", () => {
  const STOCK = { goods: { length: 400 }, shunter: { length: 200 } };

  it("marks the placed trains and leaves the rest off the layout", () => {
    expect(roster(STOCK, [{ train: "goods", block: "a" }])).toEqual([
      { train: "goods", block: "a", length: 400, placed: true },
      { train: "shunter", block: null, length: 200, placed: false },
    ]);
  });

  /** A railroad at rest says what stock it has without saying where any of it
   *  stands (ADR-0039). */
  it("lists the whole roster with nothing on the layout", () => {
    expect(roster(STOCK, []).map((row) => row.placed)).toEqual([false, false]);
  });

  /** A train the picture has and the roster does not is on the layout, and a
   *  pane that hid it would hide what the operator can see. Its length is
   *  blank rather than nought: nothing the page has read names one. */
  it("keeps a placed train the roster does not name", () => {
    expect(roster({}, [{ train: "ghost", block: null }])).toEqual([
      { train: "ghost", block: null, length: null, placed: true },
    ]);
  });
});

describe("the detectors' dispute", () => {
  const STANDING = {
    event: "allocation",
    trains: { t1: "a" },
    crossing: {},
    locks: { a: "t1" },
    requests: [],
  };

  it("says the block under a disputed train reads clear", () => {
    const model = panel();
    feed(model, STANDING, { event: "disputed", trains: ["t1"], blocks: [] });
    expect(model.blocks().get("a")).toMatchObject({
      state: "occupied",
      train: "t1",
      dispute: "clear",
    });
  });

  it("says a disputed block reads occupied, with nothing in it", () => {
    const model = panel();
    feed(model, STANDING, { event: "disputed", trains: [], blocks: ["b"] });
    expect(model.blocks().get("b")).toEqual({ state: "free", dispute: "occupied" });
  });

  it("marks nothing else on the railroad", () => {
    const model = panel();
    feed(model, STANDING, { event: "disputed", trains: ["t1"], blocks: ["b"] });
    expect(model.blocks().get("c")?.dispute).toBeUndefined();
  });

  it("replaces the whole set, the topic being last-value", () => {
    // Which is how it empties as the railroad is walked: each placement
    // republishes what is left, and an entry resolved simply is not in it.
    const model = panel();
    feed(
      model,
      STANDING,
      { event: "disputed", trains: ["t1"], blocks: ["b"] },
      { event: "disputed", trains: [], blocks: [] },
    );
    expect(model.blocks().get("a")?.dispute).toBeUndefined();
    expect(model.blocks().get("b")?.dispute).toBeUndefined();
  });

  it("is forgotten when the model starts over", () => {
    const model = panel();
    feed(model, STANDING, { event: "disputed", trains: ["t1"], blocks: ["b"] });
    model.reset();
    expect(model.blocks().get("a")?.dispute).toBeUndefined();
    expect(model.blocks().get("b")?.dispute).toBeUndefined();
  });

  /** The same set in one answer, which is what a release reads: the marks go
   *  with the hold, so the words are the only record of what was outstanding
   *  when it was let go (#153). */
  it("hands back what is outstanding, trains and blocks apart", () => {
    const model = panel();
    feed(model, STANDING, { event: "disputed", trains: ["t1"], blocks: ["b"] });
    expect(model.disputes()).toEqual({ trains: ["t1"], blocks: ["b"] });
  });

  it("is outstanding in nothing where the two agree", () => {
    expect(panel().disputes()).toEqual({ trains: [], blocks: [] });
  });
});

/**
 * What a release leaves behind in words (#153). Releasing the hold with
 * disputes outstanding is allowed — the person decides, not the check — and
 * the amber marks go with the hold, `state/disputed` being empty while the run
 * is running. The sentence is what is left to say what was accepted.
 */
describe("what is still disputed, in words", () => {
  it("says nothing where the detectors and the placement agree", () => {
    expect(outstanding({ trains: [], blocks: [] })).toBeNull();
  });

  /** The same two words the marks under the blocks use, so the sentence reads
   *  as what was on screen a moment before. */
  it("says which of the two contradictions each one is", () => {
    expect(outstanding({ trains: ["t1"], blocks: [] })).toBe(
      "released with t1 in a block that reads clear",
    );
    expect(outstanding({ trains: [], blocks: ["b"] })).toBe(
      "released with b reads occupied",
    );
  });

  it("names every one of them", () => {
    expect(outstanding({ trains: ["t1", "t2"], blocks: ["b"] })).toBe(
      "released with t1 in a block that reads clear, " +
        "t2 in a block that reads clear, b reads occupied",
    );
  });
});

/** Whether a train may move at all (ADR-0041): the layout's own value, read
 *  and never derived. The layout states it from its constructor, so a joined
 *  session has been told, and silence is a page that has joined none. */
describe("whether the rails have power", () => {
  it("says nothing before the layout has", () => {
    expect(panel().power).toBeNull();
  });

  it("takes the value the topic carries, either way of standing still", () => {
    const model = panel();
    feed(model, { event: "power", power: "off" });
    expect(model.power).toBe("off");
    feed(model, { event: "power", power: "stopped" });
    expect(model.power).toBe("stopped");
    feed(model, { event: "power", power: "on" });
    expect(model.power).toBe("on");
  });

  it("is forgotten when the model starts over", () => {
    const model = panel();
    feed(model, { event: "power", power: "off" });
    model.reset();
    expect(model.power).toBeNull();
  });
});

/** How the run stands (ADR-0037): the dispatcher's own value, read and never
 *  derived. The button that moves it draws what this says, so a press that
 *  did not land leaves the value where it was. */
describe("whether the run is held", () => {
  it("says nothing before the dispatcher has", () => {
    expect(panel().run).toBeNull();
  });

  it("takes the value the topic carries", () => {
    const model = panel();
    feed(model, { event: "run", run: "held" });
    expect(model.run).toBe("held");
    feed(model, { event: "run", run: "running" });
    expect(model.run).toBe("running");
  });

  it("is forgotten when the model starts over", () => {
    const model = panel();
    feed(model, { event: "run", run: "running" });
    model.reset();
    expect(model.run).toBeNull();
  });
});

/** Whether anything the dispatcher granted is under way, beside the run word
 *  and orthogonal to it (ADR-0062, #406). `held` alone does not say the
 *  railroad is still: the dispatcher writes that word when a drain completes,
 *  and a person's HOLD writes the same word with trains still rolling. What
 *  waits on it before cutting power is the OFF button (#408); here it is
 *  parsed, a row that carries no such field saying nothing rather than
 *  saying false. */
describe("whether anything is moving", () => {
  it("says nothing at all before the dispatcher has said", () => {
    expect(panel().moving).toBe(null);
  });

  it("takes the boolean the row carries, beside the word", () => {
    const model = panel();
    feed(model, { event: "run", run: "held", moving: true });
    expect(model.run).toBe("held");
    expect(model.moving).toBe(true);
    feed(model, { event: "run", run: "held", moving: false });
    expect(model.run).toBe("held");
    expect(model.moving).toBe(false);
  });

  it("reads a row without the field as nothing said", () => {
    // An older dispatcher publishes the word alone. The three answers are
    // kept apart rather than collapsed here: what a silence means is the
    // reader's, and the panel's OFF and `layout`'s guard differ on it (#408).
    const model = panel();
    feed(model, { event: "run", run: "running", moving: true });
    feed(model, { event: "run", run: "held" });
    expect(model.run).toBe("held");
    expect(model.moving).toBe(null);
  });

  it("is forgotten when the model starts over", () => {
    const model = panel();
    feed(model, { event: "run", run: "running", moving: true });
    model.reset();
    expect(model.moving).toBe(null);
  });
});

/** The stamp every state payload carries (#240): a page is a consumer of
 *  state topics like any other, and two values of one topic can come off the
 *  wire in the order they were not published in. */
describe("a state value that arrives out of order", () => {
  it("keeps the later of two the wire handed over backwards", () => {
    const model = panel();
    // The supply went off, then came back on; the two arrive the other way
    // about. Showing a person the `off` would be the failure the stamp is
    // for — a page saying the rails are dead over live track.
    feed(
      model,
      { event: "power", at: 20, power: "on" },
      { event: "power", at: 10, power: "off" },
    );
    expect(model.power).toBe("on");
  });

  it("lets an equal stamp replace", () => {
    const model = panel();
    feed(
      model,
      { event: "power", at: 10, power: "on" },
      { event: "power", at: 10, power: "off" },
    );
    expect(model.power).toBe("off");
  });

  it("takes an unstamped value and starts ordering again", () => {
    const model = panel();
    feed(
      model,
      { event: "power", at: 20, power: "on" },
      { event: "power", power: "stopped" },
      { event: "power", at: 1, power: "off" },
    );
    expect(model.power).toBe("off");
  });

  it("orders each state topic against itself alone", () => {
    const model = panel();
    feed(
      model,
      { event: "power", at: 20, power: "off" },
      { event: "run", at: 1, run: "held" },
    );
    expect(model.run).toBe("held");
  });

  it("orders no event, however late", () => {
    // Gated on the leaf being a state topic's and never on a payload
    // carrying a number: an event reports something that happened, and the
    // second of these two must land whatever it says about when it was sent.
    const model = panel();
    placed(model);
    feed(
      model,
      { event: "lock_granted", at: 20, train: "t1", resources: ["b"] },
      { event: "lock_released", at: 1, train: "t1", resources: ["b"] },
    );
    expect(model.blocks().get("b")).toMatchObject({ state: "free" });
  });

  it("forgets the stamps when the model starts over", () => {
    const model = panel();
    feed(model, { event: "power", at: 20, power: "off" });
    model.reset();
    // A rejoined page meets a session whose clock starts where that session
    // did, so a stamp from the last one must not refuse what this one says.
    feed(model, { event: "power", at: 1, power: "on" });
    expect(model.power).toBe("on");
  });
});
