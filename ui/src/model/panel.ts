/**
 * The panel model: bus payloads in, render state out (ui/PANEL.md, #70).
 *
 * No DOM anywhere. The component paints what this class answers — block
 * states, direction arrows, signal aspects, request markers, the lit route —
 * and a trace replay or the live bridge feed the same `apply`, which is what
 * lets the live panel consume this model unchanged.
 *
 * Everything is derived the way the dispatcher derives it: occupancy events
 * are anonymous, so an occupied block's train is the holder of its lock.
 * Nothing here computes topology — which legs a transit's way takes comes
 * from the store's `/review`, handed in at construction, and which wires it
 * runs over from the rule `inspect.wiresOn` transcribes from the store.
 *
 * It holds **no scheduler state**
 * ([ADR-0036](../../../docs/adr/0036-the-scheduler-is-an-app-the-panel-is-a-view.md)):
 * facing arrives on `tc49/schedule/state/facing` and ids arrive on
 * `request_submitted`, both written by an app that is always running, so
 * there is no cold start to seed and nothing two tabs can disagree about.
 */

import type { Reason } from "../rejection.generated.js";
import type { Aspect } from "../render/artwork.js";
import type { Position } from "../symbols.generated.js";
import type { Wire } from "./drawing.js";
import { WHOLE, wiresOn } from "./inspect.js";
import type { Explained, Layout } from "./store.js";
import type { Gesture, Power, Run, Submission, TraceEvent } from "./trace.js";

/** A block end, written `<block>.<end>` as the bus writes it. */
export type EndRef = string;

/**
 * How strong a claim the dispatcher has on a resource a route runs over:
 * `locked` where it holds the lock and the train may move, `planned` where
 * the route is chosen and the claim has not been made yet. The same two words
 * a block view uses, so blocks, transits and wires take their colour from one
 * rule (ui/PANEL.md).
 */
export type Held = "locked" | "planned";

/** What a committed route lights: the legs of each symbol its transits cross,
 *  the wires those transits are drawn over, and how strong a claim each
 *  carries. One answer, because a route reads as one run and the component
 *  paints it as one. */
export interface LitRoute {
  /** symbol → the legs of it the route takes, `WHOLE` for a symbol with no
   *  legs of its own. */
  legs: Map<string, Set<string>>;
  /** symbol → the strongest claim any transit through it carries. */
  state: Map<string, Held>;
  /** wire, as `wireKey` names it → the claim its transit carries. */
  wires: Map<string, Held>;
}

export type { Aspect };


/**
 * A train between two blocks: the transit it is crossing, read off the run's
 * picture, given as the two block ends that transit joins. That pair is where
 * it is drawn, the connection being what holds them (ui/PANEL.md, #154).
 */
export interface Crossing {
  train: string;
  between: [EndRef, EndRef];
}

export interface BlockView {
  state: "free" | "occupied" | "locked" | "planned";
  /** The train standing, holding or heading here, where one is. */
  train?: string;
  /** The end the occupying train faces, as the scheduler says. */
  toward?: string;
  /** What the detectors say about this block where the dispatcher has said
   *  that contradicts its own placement (#153): `clear` under a train
   *  standing here, `occupied` with nothing claiming it. Absent otherwise,
   *  which covers both agreement and a block nothing has reported on. */
  dispute?: "clear" | "occupied";
}

/** One endpoint of a request still worth marking: a pending or rejected
 *  request renders as endpoints only, never as a predicted path. */
export interface Marker {
  id: string;
  train: string;
  at: EndRef;
  role: "depart" | "arrival" | "pruned" | "rejected";
  /** The reason in words, on a rejection's departure and on pruned ends. */
  note?: string;
}

interface Request {
  id: string;
  train: string;
  depart: EndRef;
  dest: EndRef[];
  pruned: { end: EndRef; reason: string }[];
  phase: "requested" | "admitted" | "committed" | "rejected";
  reason?: string;
  route?: string[];
}

/** A rejection reason spelled out, as the spec words them (#67). The last
 *  three answer a payload the dispatcher could not read as a request at all
 *  (ADR-0034); an honest drag cannot produce one, so what they are here for
 *  is a stale page, a race or a buggy client — which is exactly the reader
 *  who needs to be told plainly. */
const REJECTED: Record<Reason, string> = {
  no_fit: "the train doesn't fit",
  no_entry: "no arrival end is enterable",
  unreachable: "no path exists",
  wrong_origin: "the train is elsewhere",
  unknown_train: "the session has no such train",
  unknown_block: "the layout has no such block",
  malformed: "the request could not be read",
};

/** A pruned arrival end's reason, short enough to sit at the end it marks.
 *  Only the reasons that drop one arrival end and leave the others standing:
 *  a whole-request rejection has no end of its own to sit at. */
const PRUNED: Partial<Record<Reason, string>> = {
  no_fit: "doesn't fit",
  no_entry: "not enterable",
  unreachable: "unreachable",
};

/** A reason in the words a table gives it, or the raw token where the
 *  dispatcher answering is newer than the page reading it. Neither table is
 *  indexed directly: what arrives on the bus is a string, and only the
 *  generated set says which strings are reasons. */
function spell(table: Partial<Record<Reason, string>>, reason: string): string {
  const wordings: Record<string, string | undefined> = table;
  return wordings[reason] ?? reason;
}

/**
 * What is still disputed, in the words the marks on the blocks use, or `null`
 * where the detectors and the placement agree.
 *
 * Each entry says which of the two contradictions it is rather than only that
 * something is wrong, which is what the mark under the block says too — so the
 * sentence a release leaves behind reads as what was on screen a moment
 * before (#153).
 */
export function outstanding(disputes: { trains: string[]; blocks: string[] }): string | null {
  const said = [
    ...disputes.trains.map((train) => `${train} in a block that reads clear`),
    ...disputes.blocks.map((block) => `${block} reads occupied`),
  ];
  return said.length === 0 ? null : `released with ${said.join(", ")}`;
}

/** The two halves of an end ref, `<block>.<end>`. */
export function blockOf(end: EndRef): string {
  return end.slice(0, end.lastIndexOf("."));
}

export function endOf(end: EndRef): string {
  return end.slice(end.lastIndexOf(".") + 1);
}

export class Panel {
  /** resource → holding train: blocks and transits alike, the lock ledger. */
  private locks = new Map<string, string>();
  /** block end → the aspect its signal shows, last as the dispatcher said. */
  private shown = new Map<EndRef, Aspect>();
  /** address → the position the last `align` naming it commanded. Commanded,
   *  not measured: nothing on the bus reports where a point actually lies. */
  private lyingByAddress = new Map<string, Position>();
  /** block → the train standing in it. */
  private standing = new Map<string, string>();
  /** train → the transit it is crossing, as the picture says. A train in it
   *  is between two blocks and stands in none: `trains` goes on naming the
   *  block the sensors last confirmed it in, and this is the whole of what
   *  says it has left (#154). */
  private crossing = new Map<string, string>();
  /** train → the block it faces out of and the end it faces, as the
   *  scheduler last said. Read, never derived: facing is scheduler state
   *  (ADR-0019), and the topic carries it whole. */
  private heading = new Map<string, { block: string; toward: string }>();
  /** The trains and the blocks the detectors dispute, as the dispatcher last
   *  said (#153). Read and never derived: which blocks the layout has
   *  reported on at all is knowledge only the dispatcher holds, and a panel
   *  working it out would call every unreported block clear. */
  private disputed = { trains: new Set<string>(), blocks: new Set<string>() };
  /** How the run stands, as the dispatcher last said, `null` before it has
   *  said anything (ADR-0037). Read and never derived: a held run is a
   *  decision the dispatcher publishes, not something a picture shows. */
  private state: Run | null = null;
  /** Whether the layout says a train may move at all, `null` before it has
   *  said anything (ADR-0041). The layout states it from its constructor, so
   *  a session that has joined has been told; silence is a page that has not
   *  joined one, and not a claim that the rails are dead. */
  private supply: Power | null = null;
  private requests = new Map<string, Request>();
  /** Whether the first boundary has passed: a lock on a block before it is
   *  the trace's opening placement, there being no occupancy event for a
   *  train that never moved. */
  private started = false;

  /** transit resource → the legs its way takes and the wires it is drawn
   *  over. Worked out once, at construction: neither answer can change while
   *  a railroad is on screen, and both are the store's — the wires through
   *  the rule `inspect.wiresOn` transcribes from it. */
  private readonly ways = new Map<
    string,
    { legs: [string, string][]; wires: string[] }
  >();

  constructor(
    private readonly layout: Layout,
    explain: Explained,
    wires: readonly Wire[],
  ) {
    for (const [connection, { transits }] of Object.entries(layout.connections)) {
      for (const transit of Object.keys(transits)) {
        const crossing = explain.connections[connection]?.transits[transit];
        if (crossing === undefined) continue;
        this.ways.set(`${connection}.${transit}`, {
          legs: crossing.way,
          wires: wiresOn(crossing, wires),
        });
      }
    }
  }

  reset(): void {
    this.locks.clear();
    this.lyingByAddress.clear();
    this.standing.clear();
    this.crossing.clear();
    this.heading.clear();
    this.disputed = { trains: new Set(), blocks: new Set() };
    this.state = null;
    this.supply = null;
    this.requests.clear();
    this.started = false;
  }

  /**
   * What a drag means on the bus: the gesture, and nothing else.
   *
   * A gesture is not a request. It names a train and where to put it; the id
   * and the departure end are the two fields the scheduler owns and supplies
   * (ADR-0036), so there is nothing here to mint, nothing to look up, and no
   * drop this can refuse — the panel judging a request is the one thing it
   * must never do (#67).
   */
  compose(train: string, dest: EndRef[]): Gesture {
    return { train, dest };
  }

  apply(event: TraceEvent): void {
    switch (event.event) {
      case "boundary":
        this.started = true;
        return;
      case "lock_granted": {
        const { train, resources } = event as unknown as {
          train: string;
          resources: string[];
        };
        for (const resource of resources) {
          this.locks.set(resource, train);
          if (!this.started && resource in this.layout.blocks) {
            this.standing.set(resource, train);
          }
        }
        return;
      }
      case "lock_released": {
        const { train, resources } = event as unknown as {
          train: string;
          resources: string[];
        };
        for (const resource of resources) {
          if (this.locks.get(resource) === train) this.locks.delete(resource);
        }
        return;
      }
      case "block_occupied": {
        const { block } = event as unknown as { block: string };
        const holder = this.locks.get(block);
        if (holder === undefined) return;
        this.standing.set(block, holder);
        // Arrived, so no longer crossing: the same sensor the dispatcher
        // drops its own mark on. Waiting for the next picture instead would
        // draw the train on the connection for a frame after it plainly got
        // there.
        this.crossing.delete(holder);
        return;
      }
      case "block_vacated": {
        const { block } = event as unknown as { block: string };
        this.standing.delete(block);
        return;
      }
      case "align": {
        const { points } = event as unknown as {
          points: { addr: string; position: Position }[];
        };
        for (const { addr, position } of points)
          this.lyingByAddress.set(addr, position);
        return;
      }
      case "allocation": {
        // The run's picture, as the dispatcher holds it (ADR-0032): standing
        // trains, the lock table, and every request still alive. A train's
        // facing is not in it and stays where the scheduler's own topic put
        // it — facing is scheduler state and on no dispatcher topic at all
        // (ADR-0019).
        const { trains, crossing, locks, requests } = event as unknown as {
          trains: Record<string, string>;
          crossing?: Record<string, string>;
          locks: Record<string, string>;
          requests: {
            id: string;
            train: string;
            depart: EndRef;
            dest: EndRef[];
            route?: string[];
          }[];
        };
        this.locks = new Map(Object.entries(locks));
        // A crossing train is named in both maps and stands in neither block:
        // `trains` says which one the sensors last confirmed, `crossing` says
        // it has left it, and the panel draws it on the connection.
        this.crossing = new Map(Object.entries(crossing ?? {}));
        this.standing = new Map(
          Object.entries(trains)
            .filter(([train]) => !this.crossing.has(train))
            .map(([train, block]) => [block, train]),
        );
        // A rejection is not in the picture — the dispatcher does not hold
        // the request it refused — and stays until the train is dragged
        // again, so the reason does not leave the screen the moment anything
        // else on the railroad moves.
        const refused = [...this.requests].filter(
          ([, request]) => request.phase === "rejected",
        );
        this.requests = new Map([
          ...refused,
          ...requests.map((request): [string, Request] => [
            request.id,
            {
              ...request,
              // Which ends were pruned is an admission-time fact the
              // dispatcher does not keep, so it is in no picture and this
              // page's own copy is the only one there is. A client that
              // joined later has none and shows none, which is what ADR-0032
              // means by rejoining not being recovery.
              pruned: this.requests.get(request.id)?.pruned ?? [],
              // A request the dispatcher still holds has passed admission;
              // one it has given a route is running it.
              phase: request.route === undefined ? "admitted" : "committed",
            },
          ]),
        ]);
        this.started = true;
        return;
      }
      case "run": {
        // Held or running, whole from the topic. The button that moves it
        // reads this, so what it offers is the run's own answer rather than
        // the last press's.
        const { run } = event as unknown as { run: Run };
        this.state = run;
        return;
      }
      case "power": {
        // What the layout says about the supply, whole from the topic. The
        // dispatcher reads the same word and holds the run on anything but
        // `on`; the panel says which of the two it is, the person recovering
        // clearing an emergency stop or switching a supply back on.
        const { power } = event as unknown as { power: Power };
        this.supply = power;
        return;
      }
      case "disputed": {
        // Where the placement and the detectors contradict each other, while
        // the run is held (#153). Last-value like every other state topic, so
        // this replaces the set rather than adding to it — which is how it
        // empties as a person walks the railroad placing trains, and how a
        // release clears it.
        const { trains, blocks } = event as unknown as {
          trains: string[];
          blocks: string[];
        };
        this.disputed = { trains: new Set(trains), blocks: new Set(blocks) };
        return;
      }
      case "aspects": {
        const { aspects } = event as unknown as {
          aspects: Record<EndRef, Aspect>;
        };
        this.shown = new Map(Object.entries(aspects));
        return;
      }
      case "facing": {
        // The scheduler's whole answer, last-value-wins: which end of which
        // block each train would depart through nose-first. The panel renders
        // it as the direction arrow and derives none of it — a train that has
        // never moved has an arrow for the same reason a moved one does
        // (ADR-0036).
        const { facing } = event as unknown as { facing: Record<string, EndRef> };
        this.heading = new Map(
          Object.entries(facing).map(([train, end]) => [
            train,
            { block: blockOf(end), toward: endOf(end) },
          ]),
        );
        return;
      }
      case "request_submitted": {
        const { id, train, depart, dest } = event as unknown as Submission;
        for (const [old, request] of this.requests) {
          if (request.train === train && request.phase === "rejected") {
            this.requests.delete(old);
          }
        }
        this.requests.set(id, {
          id,
          train,
          depart,
          dest,
          pruned: [],
          phase: "requested",
        });
        return;
      }
      case "request_admitted": {
        const { id, dest, pruned } = event as unknown as {
          id: string;
          dest: EndRef[];
          pruned: { end: EndRef; reason: string }[];
        };
        const request = this.requests.get(id);
        if (request === undefined || request.phase === "rejected") return;
        request.phase = "admitted";
        request.dest = dest;
        request.pruned = pruned ?? [];
        return;
      }
      case "request_rejected": {
        const { id, reason } = event as unknown as { id: string; reason: string };
        const request = this.requests.get(id);
        if (request === undefined) return;
        request.phase = "rejected";
        request.reason = reason;
        return;
      }
      case "route_chosen": {
        const { id, route } = event as unknown as { id: string; route: string[] };
        const request = this.requests.get(id);
        if (request === undefined) return;
        request.phase = "committed";
        request.route = route;
        return;
      }
      case "request_completed": {
        const { id } = event as unknown as { id: string };
        this.requests.delete(id);
        return;
      }
      default:
        return; // boundaries aside, the panel reads a subset of the bus
    }
  }

  /** How the run stands, `null` before the dispatcher has said (ADR-0037). */
  get run(): Run | null {
    return this.state;
  }

  /** Whether a train may move at all, as the layout last said, `null` before
   *  it has said anything (ADR-0041). What GO reads: releasing into dead
   *  rails is refused by the dispatcher, so the button that would ask for it
   *  is greyed. */
  get power(): Power | null {
    return this.supply;
  }

  /** What the detectors dispute, as the dispatcher last said (#153): trains
   *  standing in a block that reads clear, and blocks that read occupied with
   *  nothing claiming them. Empty unless the run is held, so a release is
   *  where this is worth reading — it is what the person is deciding to
   *  accept, and the marks go with the hold. */
  disputes(): { trains: string[]; blocks: string[] } {
    return { trains: [...this.disputed.trains], blocks: [...this.disputed.blocks] };
  }

  /** Every block of the layout, at the strongest state that holds for it:
   *  a train standing there, a lock holding it, a committed route heading
   *  through it, or nothing. Occupancy outranks both route states — a
   *  standing train is still a lock, and the picture must never lose which
   *  block a train is actually in (ui/PANEL.md). */
  blocks(): Map<string, BlockView> {
    const planned = new Map<string, string>();
    for (const request of this.requests.values()) {
      if (request.phase !== "committed") continue;
      for (const resource of request.route ?? []) {
        if (resource in this.layout.blocks) planned.set(resource, request.train);
      }
    }
    const views = new Map<string, BlockView>();
    for (const block of Object.keys(this.layout.blocks)) {
      const train = this.standing.get(block);
      // What the detectors dispute rides on the block whatever else is true
      // of it, rather than being a fifth state: a dispute is about the block
      // being other than the picture says, so hiding the picture behind it
      // would take away the half a person is checking. Never both readings —
      // one detector says one thing.
      const dispute: Pick<BlockView, "dispute"> = this.disputed.blocks.has(block)
        ? { dispute: "occupied" }
        : train !== undefined && this.disputed.trains.has(train)
          ? { dispute: "clear" }
          : {};
      if (train !== undefined) {
        const heading = this.heading.get(train);
        views.set(block, {
          state: "occupied",
          train,
          ...(heading?.block === block ? { toward: heading.toward } : {}),
          ...dispute,
        });
        continue;
      }
      const holder = this.locks.get(block);
      if (holder !== undefined) {
        views.set(block, { state: "locked", train: holder, ...dispute });
        continue;
      }
      const expecting = planned.get(block);
      if (expecting !== undefined) {
        views.set(block, { state: "planned", train: expecting, ...dispute });
        continue;
      }
      views.set(block, { state: "free", ...dispute });
    }
    return views;
  }

  /**
   * Every train the picture says is between two blocks, with the pair of
   * block ends its transit joins: where the connection is, and so where the
   * train is drawn (#154).
   *
   * A transit the drawing on screen has no such connection for is left out.
   * The picture belongs to a railroad and a page can be showing another one,
   * which is one train the panel cannot place rather than a panel that
   * cannot draw — the rule `positionsBySymbol` already follows for an address
   * no symbol wears.
   */
  crossings(): Crossing[] {
    const found: Crossing[] = [];
    for (const [train, resource] of this.crossing) {
      const [at, name] = resource.split(".");
      const between = this.layout.connections[at]?.transits[name];
      if (between !== undefined) found.push({ train, between });
    }
    return found;
  }

  /**
   * What each signalled block end is showing, exactly as the dispatcher said
   * (ADR-0025). The panel derives nothing here: an aspect is a function of
   * locks the dispatcher holds and routes it committed, and a second party
   * working it out is a second authority to disagree with.
   *
   * An end the dispatcher did not name carries no signal — a siding's blind
   * end can only ever show `stop` — and is absent rather than dark.
   */
  aspects(): ReadonlyMap<EndRef, Aspect> {
    return this.shown;
  }

  /**
   * Where each point lies, by the address its motor answers to
   * ([ADR-0022](../../../docs/adr/0022-a-symbol-carries-its-hardware-address.md)).
   *
   * The dispatcher sends the points a transit's way needs with the alignment
   * command, so this is a ledger of what it last said rather than anything
   * derived: the panel neither knows which points a transit traverses nor
   * works out how each must lie. An address stays where the last command
   * naming it left it — `align` speaks for one transit and says nothing about
   * the rest of the railroad.
   */
  positionsByAddress(): ReadonlyMap<string, Position> {
    return this.lyingByAddress;
  }

  /**
   * What the committed routes light: the legs of the symbols their transits
   * cross, in the shape `inspect.lit` gives the canvas — `""` from the store
   * means the symbol has no legs of its own and lights whole — the wires
   * those transits are drawn over, and how strong a claim each carries.
   *
   * `locked` is read from the lock ledger alone, not from a route intersected
   * with it, which is how the block view already works. Its consequence is
   * intended: a lock the dispatcher still holds after the request completes
   * stays locked until it is released, because the dispatcher really does
   * still hold it.
   *
   * Where a throat symbol is carried by a locked transit and a committed one
   * at the same time, locked wins — the strongest claim that holds, as the
   * block view rules it. That slightly overstates the committed route's leg
   * on a shared symbol (ui/PANEL.md).
   */
  lit(): LitRoute {
    const legs = new Map<string, Set<string>>();
    const state = new Map<string, Held>();
    const wires = new Map<string, Held>();
    const light = (resource: string, held: Held) => {
      const way = this.ways.get(resource);
      if (way === undefined) return; // a block, or a transit off this drawing
      for (const [symbol, leg] of way.legs) {
        const taken = legs.get(symbol) ?? new Set<string>();
        taken.add(leg === "" ? WHOLE : leg);
        legs.set(symbol, taken);
        if (held === "locked" || !state.has(symbol)) state.set(symbol, held);
      }
      for (const wire of way.wires) {
        if (held === "locked" || !wires.has(wire)) wires.set(wire, held);
      }
    };
    for (const resource of this.locks.keys()) light(resource, "locked");
    for (const request of this.requests.values()) {
      if (request.phase !== "committed") continue;
      for (const resource of request.route ?? []) light(resource, "planned");
    }
    return { legs, state, wires };
  }

  /** Whether that train still stands in that block. The right-click menu is
   *  about one train in one block, and a menu left open outlives both: a
   *  train that has moved on is turned around somewhere else entirely
   *  (ui/PANEL.md). */
  standsIn(train: string, block: string): boolean {
    return this.standing.get(block) === train;
  }

  /**
   * Whether the train has a request in flight: submitted, admitted or
   * committed, but not one already answered with a rejection.
   *
   * The panel pre-judges one gesture on this and no other (ui/PANEL.md).
   * Turning a train around while a request of its own is queued would flip
   * the arrow under it: the request still departs the old end, and
   * `route_chosen` turns the arrow back when it launches. A rejected request
   * leaves the train idle — its marker stays on screen, but nothing is going
   * to move it — and that is precisely when the operator wants to turn it
   * around.
   */
  inFlight(train: string): boolean {
    for (const request of this.requests.values()) {
      if (request.train === train && request.phase !== "rejected") return true;
    }
    return false;
  }

  /** The endpoints worth marking: pending requests as endpoints only — never
   *  a predicted path — and rejections with their reason in words. */
  markers(): Marker[] {
    const found: Marker[] = [];
    for (const request of this.requests.values()) {
      const { id, train } = request;
      if (request.phase === "requested" || request.phase === "admitted") {
        found.push({ id, train, at: request.depart, role: "depart" });
        for (const end of request.dest) {
          found.push({ id, train, at: end, role: "arrival" });
        }
        for (const { end, reason } of request.pruned) {
          found.push({
            id,
            train,
            at: end,
            role: "pruned",
            note: spell(PRUNED, reason),
          });
        }
      } else if (request.phase === "rejected") {
        found.push({
          id,
          train,
          at: request.depart,
          role: "rejected",
          note: spell(REJECTED, request.reason ?? ""),
        });
        for (const end of request.dest) {
          found.push({ id, train, at: end, role: "rejected" });
        }
      }
    }
    return found;
  }
}
