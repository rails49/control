/**
 * The panel model: bus payloads in, render state out (ui/PANEL.md, #70).
 *
 * No DOM anywhere. The component paints what this class answers — block
 * states, direction arrows, signal aspects, request markers, the lit route —
 * and a trace replay or the broker's own feed the same `apply`, which is what
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
import type { Aspect, Reading } from "../render/artwork.js";
import type { Position } from "../symbols.generated.js";
import type { Wire } from "./drawing.js";
import { WHOLE, wiresOn } from "./inspect.js";
import { requestRows, type RequestRow } from "./requests.js";
import type { Explained, Layout } from "./store.js";
import {
  Ordering,
  type DrivingMode,
  type Gesture,
  type PointWanted,
  type Power,
  type Submission,
  type TraceEvent,
} from "./trace.js";

/** A block end, written `<block>.<end>` as the bus writes it. */
export type EndRef = string;

/** A train's facing, written `<block>.A-to-B` or `<block>.B-to-A` as the
 *  scheduler publishes it: the run the train would make across its block,
 *  which says which way it points without a convention to look up (#241). */
export type FacingRef = string;

/**
 * How strong a claim the dispatcher has on a resource a route runs over:
 * `locked` where it holds the lock and the train may move, `committed` where
 * the route is chosen and the claim has not been made yet. The same two words
 * a block view uses, so blocks, transits and wires take their colour from one
 * rule (ui/PANEL.md).
 *
 * Named for the pair and not for one of them: ui/PANEL.md builds a request out
 * of three layers and defines the third as the locked one specifically, so a
 * union spanning the last two must not wear that layer's name.
 */
export type Claim = "locked" | "committed";

/** One block a train has ahead of it on the route it is committed to, and
 *  how strong a claim the dispatcher has on it. The two words a route is lit
 *  in, in a list rather than on a picture: what a person driving by hand
 *  reads off the road in front of them (ui/THROTTLE.md). */
export interface Ahead {
  block: string;
  claim: Claim;
}

/** What a committed route lights: the legs of each symbol its transits cross,
 *  the wires those transits are drawn over, and how strong a claim each
 *  carries. One answer, because a route reads as one run and the component
 *  paints it as one. */
export interface LitRoute {
  /** symbol → the legs of it the route takes, `WHOLE` for a symbol with no
   *  legs of its own. */
  legs: Map<string, Set<string>>;
  /** symbol → the strongest claim any transit through it carries. */
  state: Map<string, Claim>;
  /** wire, as `wireKey` names it → the claim its transit carries. */
  wires: Map<string, Claim>;
}

export type { Aspect, Reading };


/**
 * A train on the layout, and where it is standing: the block, or `null` while
 * it is crossing and standing in none (GLOSSARY.md, **Placed**).
 *
 * Presence in the run's picture is the whole of being placed, absence being
 * off the layout rather than a sentinel
 * ([ADR-0039](../../../docs/adr/0039-a-train-may-be-off-the-layout.md)).
 */
export interface Placed {
  train: string;
  block: string | null;
}

/**
 * One row of the roster pane: a train the railroad owns, how long it is, what
 * it is drawn as, and where the run has it.
 *
 * `placed` is the whole of being on the layout, `block` saying where within
 * it — `null` for a train holding a transit and standing in no block. A train
 * that is not placed is **off the layout**, which is an ordinary state and
 * not a fault ([ADR-0039](../../../docs/adr/0039-a-train-may-be-off-the-layout.md)).
 */
export interface RosterRow extends Placed {
  /** Its length, `null` where nothing the page has read names one — a train
   *  the picture has and the railroad's roster does not. */
  length: number | null;
  /** The model of its first locomotive, whose photo the row shows, as the
   *  throttle's picker does (#1012); `null` where the train has none or
   *  nothing the page has read names it. */
  locomotive: string | null;
  placed: boolean;
}

/**
 * The roster pane's rows: every train the railroad owns, and every train the
 * run has, ordered by name.
 *
 * Two sources because they are two things — the store says which trains the
 * railroad owns, how long each is and the model of its first locomotive
 * (`/rosters/<railroad>/trains`, #866), the bus says where they are
 * (ADR-0010) — and one list, because a person looking at the pane is looking
 * for a train and does not care which half named it. A train the picture has
 * and the roster does not still gets a row: it is on the layout, and a pane
 * that hid it would hide the thing the operator can see.
 */
export function roster(
  stock: Record<string, { length: number; locomotive?: string | null }>,
  placed: readonly Placed[],
): RosterRow[] {
  const where = new Map(placed.map((train) => [train.train, train.block]));
  const names = new Set([...Object.keys(stock), ...where.keys()]);
  return [...names].sort().map((train) => ({
    train,
    length: stock[train]?.length ?? null,
    locomotive: stock[train]?.locomotive ?? null,
    block: where.get(train) ?? null,
    placed: where.has(train),
  }));
}

export interface BlockView {
  state: "free" | "occupied" | "locked" | "committed";
  /** The train standing, holding or heading here, where one is. */
  train?: string;
  /** The train whose name this block carries, whatever its colour: a block
   *  the train holds that reads occupied, or the block it last stood in
   *  where none it holds does (#897). One train can name two blocks while it
   *  passes from one to the next, and a press on either takes hold of it. */
  named?: string;
  /** Set where the train named here is crossing a transit: no block is its
   *  own to be moved from, so a drop on one means nothing (ADR-0069). */
  crossing?: true;
  /** The end the occupying train faces, as the scheduler says. */
  toward?: string;
  /** What the detectors say about this block where the dispatcher has said
   *  that contradicts its own placement (#153): `clear` under a train
   *  standing here, `occupied` with nothing claiming it. Absent otherwise,
   *  which covers both agreement and a block nothing has reported on. */
  dispute?: "clear" | "occupied";
}

/**
 * What a run paints over the drawing: everything the canvas draws in run mode
 * and nothing it works out for itself (ui/PANEL.md, #168).
 *
 * One object because the canvas takes it in one go and because the parts move
 * together — every one of them is the next frame's answer. Point positions,
 * and the throws offered on points, are the entries that are not this model's
 * own: they arrive by address and the drawing is what turns an address back
 * into a symbol (`scene.positionsBySymbol`, `scene.pointsOffered`, ADR-0022).
 */
export interface Overlay {
  blocks: Map<string, BlockView>;
  lit: LitRoute;
  aspects: ReadonlyMap<EndRef, Aspect>;
  /** What each block end's detector reads, by the end (#898). An end no
   *  row has named is absent, and drawn as `unknown`. */
  detected: ReadonlyMap<EndRef, Reading>;
  positions: ReadonlyMap<string, Position>;
  /** symbol → what a click on that point asks for, the points the panel
   *  offers a throw on (`scene.pointsOffered`, ADR-0068). Like positions, the
   *  drawing's answer as much as this model's. */
  offered: ReadonlyMap<string, PointWanted>;
  markers: Marker[];
  /** The widget rows by their whole topic, as the session holds them
   *  (ADR-0087, #929): the session's and not this model's, a widget's topic
   *  naming no railroad. */
  widgets: ReadonlyMap<string, string>;
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
  /** `null` on a request chained `after` an earlier one, whose start is
   *  where that one ends. */
  depart: EndRef | null;
  after?: string;
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
  no_origin: "the train is off the layout",
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
/** Whether a payload value is a map of names: an object, and not a list. */
function mapping(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function spell(table: Partial<Record<Reason, string>>, reason: string): string {
  const wordings: Record<string, string | undefined> = table;
  return wordings[reason] ?? reason;
}

/** A train the last rebuild under the same name took off the layout: the
 *  block it stood in and why it no longer stands there, `gone` from the
 *  drawing or `short` of the train (#709). */
export interface Unfit {
  train: string;
  block: string;
  why: string;
}

/**
 * One line per train a rebuild took off, saying why, for the run view to show
 * while the list stands. A `why` this page does not know is said as it came,
 * the dispatcher answering being newer than the page reading it.
 */
export function takenOff(unfit: Unfit[]): string[] {
  return unfit.map(({ train, block, why }) => {
    const said =
      why === "gone"
        ? "is gone"
        : why === "short"
          ? "is shorter than the train — place it again"
          : why;
    return `${train}: block ${block} ${said}`;
  });
}

/** The two halves of an end ref, `<block>.<end>`. */
export function blockOf(end: EndRef): string {
  return end.slice(0, end.lastIndexOf("."));
}

export function endOf(end: EndRef): string {
  return end.slice(end.lastIndexOf(".") + 1);
}

/** The end of its block a facing points at: the `B` of `<block>.A-to-B`, and
 *  the end the direction arrow reads from. */
export function noseOf(facing: FacingRef): string {
  return endOf(facing).split("-to-")[1];
}

export class Panel {
  /** resource → holding train: blocks and transits alike, the lock ledger. */
  private locks = new Map<string, string>();
  /** block end → the aspect its signal shows, last as the dispatcher said. */
  private shown = new Map<EndRef, Aspect>();
  /** block end → what its detector last read, off its `device/sensor` row
   *  (#898). The reading under `block_occupied` and `block_vacated`, kept
   *  for a person debugging the layout and never folded here: that fold is
   *  `layout`'s. */
  private readings = new Map<EndRef, Reading>();
  /** address → the position its `wanted/point` row last said. Commanded,
   *  not measured: nothing this reads reports where a point actually lies. */
  private lyingByAddress = new Map<string, Position>();
  /** block → the train standing in it. */
  private standing = new Map<string, string>();
  /** train → the transit it is crossing, as the picture says. A train in it
   *  is between two blocks and stands in none: `trains` goes on naming the
   *  block the sensors last confirmed it in, and this is the whole of what
   *  says it has left (#154). */
  private crossing = new Map<string, string>();
  /** The blocks that read occupied, as `block_occupied` and `block_vacated`
   *  last said. A page that joined after a reading has not seen it, and
   *  draws the train where it last stood instead (#897). */
  private reads = new Set<string>();
  /** train → the block it last stood in: `trains` in the picture, and the
   *  block a sensor last confirmed it arriving in. Every train the run has
   *  placed is here, crossing or not, and a train it has taken off is not. */
  private stood = new Map<string, string>();
  /** train → the block it faces out of and the end its facing runs to, as
   *  the scheduler last said. Read, never derived: facing is scheduler state
   *  (ADR-0019), and the topic carries it whole. */
  private heading = new Map<string, { block: string; toward: string }>();
  /** The trains and the blocks the detectors dispute, as the dispatcher last
   *  said (#153). Read and never derived: which blocks the layout has
   *  reported on at all is knowledge only the dispatcher holds, and a panel
   *  working it out would call every unreported block clear. */
  private disputed = { trains: new Set<string>(), blocks: new Set<string>() };
  /** The trains the last rebuild under the same name took off the layout,
   *  as the dispatcher last said (#709). Read and never derived: which
   *  trains the last build had standing is the dispatcher's alone. */
  private unfitRows: Unfit[] = [];
  /** What `state/moving` last said about any train crossing
   *  (ADR-0078), `null` where it said nothing — before the
   *  dispatcher has spoken, and for a row whose `moving` is not a boolean.
   *  The three are kept apart rather than collapsed here, because what a
   *  silence means is the reader's to decide (#408). */
  private movingWord: boolean | null = null;
  /** The railroad's driving mode, as `layout` last said on `state/driving`,
   *  `null` before it has said anything
   *  ([ADR-0079](../../../docs/adr/0079-the-railroad-has-one-driving-mode-and-a-train-one-throttle.md)). */
  private drivingWord: DrivingMode | null = null;
  /** Whether the layout says a train may move at all, `null` before it has
   *  said anything (ADR-0041). The layout states it from its constructor, so
   *  a session that has joined has been told; silence is a page that has not
   *  joined one, and not a claim that the rails are dead. */
  private powerWord: Power | null = null;
  /** What the hardware says is wrong with the supply, in its own words,
   *  `null` where it says nothing (BUS.md, device vocabulary). Read off
   *  `device/track`, which with `device/sensor` is a device row a view reads: `power` there
   *  is folded into `state/power` above and `powerWord` is what the picture
   *  draws, and the free-text `reason` beside it is the only place a tripped
   *  district or a participant that cannot reach the supply can be said — a
   *  district reaches no topic of its own, so that frame reads like a
   *  railroad with nothing wrong with it unless this is read
   *  ([ADR-0050](../../../docs/adr/0050-broken-hardware-is-reported-never-worked-around.md),
   *  [#602](https://github.com/rails49/control/issues/602)). */
  private faultWord: string | null = null;
  /** train → the id of the throttle holding it, as `layout` last said on
   *  `state/taken`. A train the map does not name, no throttle holds
   *  ([ADR-0079](../../../docs/adr/0079-the-railroad-has-one-driving-mode-and-a-train-one-throttle.md)). */
  private holders = new Map<string, string>();
  /** train → function name → whether it is on, as `layout` last said on
   *  `state/functions` ([#849](https://github.com/rails49/control/issues/849)).
   *  A name the map does not give for a train is off. */
  private switched = new Map<string, ReadonlyMap<string, boolean>>();
  private requests = new Map<string, Request>();
  /** Whether the opening picture has arrived: a lock on a block before it is
   *  the run's opening placement, there being no occupancy event for a
   *  train that never moved. The dispatcher publishes `allocation` right
   *  after the standing locks, so the picture is the marker. */
  private started = false;
  /** The stamp held against each state leaf: what keeps the later of two
   *  values of one state topic when the two arrive backwards (#240). A page
   *  is a consumer of state topics like any other, and the frames it is
   *  handed came off the same wire. */
  private readonly ordering = new Ordering();

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
    this.readings.clear();
    this.lyingByAddress.clear();
    this.standing.clear();
    this.crossing.clear();
    this.reads.clear();
    this.stood.clear();
    this.heading.clear();
    this.disputed = { trains: new Set(), blocks: new Set() };
    this.unfitRows = [];
    this.movingWord = null;
    this.drivingWord = null;
    this.powerWord = null;
    this.faultWord = null;
    this.holders.clear();
    this.switched.clear();
    this.requests.clear();
    this.started = false;
    this.ordering.reset();
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
    // A state value older than the one already held is ignored, whoever
    // published it and whatever it says: the wire handed the pair over
    // backwards, and showing a person the older one is the failure the stamp
    // exists for (#240). Events pass straight through — a repeated sensor
    // reading re-asserts a level, and nothing is replayed.
    if (!this.ordering.accepts(event)) return;
    switch (event.event) {
      case "lock_granted": {
        const { train, resources } = event as unknown as {
          train: string;
          resources: string[];
        };
        for (const resource of resources) {
          this.locks.set(resource, train);
          if (!this.started && resource in this.layout.blocks) {
            this.standing.set(resource, train);
            this.stood.set(train, resource);
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
        this.reads.add(block);
        const holder = this.locks.get(block);
        if (holder === undefined) return;
        this.standing.set(block, holder);
        if (this.stood.has(holder)) this.stood.set(holder, block);
        // Arrived, so no longer crossing: the same sensor the dispatcher
        // drops its own mark on. Waiting for the next picture instead would
        // leave the train crossing for a frame after it plainly got there.
        this.crossing.delete(holder);
        return;
      }
      case "block_vacated": {
        const { block } = event as unknown as { block: string };
        this.reads.delete(block);
        this.standing.delete(block);
        return;
      }
      case "wanted/point": {
        // What `layout` asked the point at this address for, on a retained
        // row (ADR-0068): every `align` lands here, a person's throw as much
        // as a route's, and a page opened mid-session is handed the lot.
        const { addr, position } = event as unknown as {
          addr: string;
          position: Position;
        };
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
            depart: EndRef | null;
            dest: EndRef[];
            after?: string;
            route?: string[];
          }[];
        };
        this.locks = new Map(Object.entries(locks));
        // A crossing train is named in both maps and stands in neither block:
        // `trains` says which one the sensors last confirmed, `crossing` says
        // it has left it. Its name is drawn where the detectors say it is,
        // and in that last block where they say nothing (#897).
        this.crossing = new Map(Object.entries(crossing ?? {}));
        this.stood = new Map(Object.entries(trains));
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
      case "moving": {
        // Whether any train is crossing, whole from the
        // dispatcher's own topic (ADR-0078). A row whose `moving` is not a
        // boolean says nothing rather than saying false, and what a reader
        // makes of that silence is the reader's (#408).
        const { moving } = event as unknown as { moving?: unknown };
        this.movingWord = typeof moving === "boolean" ? moving : null;
        return;
      }
      case "driving": {
        // The railroad's driving mode, whole from the topic: `layout` holds
        // it, and the band's driving control draws it rather than its own
        // press (ADR-0035). An unreadable row reads as `manual`, the mode the
        // railroad comes up in (BUS.md).
        const { driving } = event as unknown as { driving?: unknown };
        this.drivingWord = driving === "automatic" ? "automatic" : "manual";
        return;
      }
      case "power": {
        // Power as `layout` says it, whole from the topic: `on`, `draining`
        // or `off` (ADR-0078). The dispatcher reads the same value and routes
        // only while it is `on`, and a word outside the three reads as `off`,
        // as `tc49.lib.payload.power` reads it.
        const { power } = event as unknown as { power?: unknown };
        this.powerWord = power === "on" || power === "draining" ? power : "off";
        return;
      }
      case "device/track": {
        // What the hardware says about the supply, and why where it says
        // why. Only the reason is kept: `power` here is one translator's
        // reading of its own hardware, and what a page draws is the
        // railroad-wide `state/power` that `layout` folds it into (BUS.md).
        //
        // The reason is what nothing else carries. A command station that
        // cuts one district by itself goes on reading `power: on` while the
        // rest of the railroad is powered, and a district reaches no topic,
        // so the sentence is the whole of what says a trip is standing
        // (ADR-0050). It is read whichever way `power` stands, for that
        // reason.
        //
        // Free text, so a reason that is not a sentence is nothing to show:
        // a frame without one is the hardware saying nothing is wrong, an
        // empty string is a chip with nothing in it, and a value that is not
        // a string is a publisher this page cannot read.
        const { reason } = event as unknown as { reason?: unknown };
        this.faultWord = typeof reason === "string" && reason !== "" ? reason : null;
        return;
      }
      case "device/sensor": {
        // One detector's reading at the block end the row is addressed by,
        // which the payload's `addr` repeats (BUS.md). A word outside the
        // three is a detector this page cannot read, which is what `unknown`
        // says; a row naming no end is about nothing on the drawing.
        const { addr, occupancy } = event as unknown as {
          addr?: unknown;
          occupancy?: unknown;
        };
        if (typeof addr !== "string" || addr === "") return;
        this.readings.set(
          addr,
          occupancy === "occupied" || occupancy === "clear" ? occupancy : "unknown",
        );
        return;
      }
      case "taken": {
        // Which throttle holds each train, whole from the topic: `layout`
        // holds it and publishes it, and the throttle view reads it rather
        // than its own gesture — a train is taken when the map says so and
        // not when the person pressed (ui/THROTTLE.md).
        //
        // Read an entry at a time (BUS.md): an entry that is not a non-empty
        // string leaves its train held by nobody, and a payload whose `taken`
        // is not a map holds nothing. Last value wins, so a train the map
        // stops naming is released.
        const { taken } = event as unknown as { taken?: unknown };
        const read = new Map<string, string>();
        if (typeof taken === "object" && taken !== null && !Array.isArray(taken)) {
          for (const [train, throttle] of Object.entries(taken)) {
            if (typeof throttle === "string" && throttle !== "") read.set(train, throttle);
          }
        }
        this.holders = read;
        return;
      }
      case "functions": {
        // Which of each train's functions are on, whole from the topic as
        // `state/taken` is: `layout` writes the device rows and says what it
        // wrote, and the throttle's buttons read this rather than their own
        // press (ui/THROTTLE.md).
        //
        // Read an entry at a time: a value that is not a boolean leaves its
        // function off, a train whose entry is not a map has every function
        // off, and a payload whose `functions` is not a map has them all off.
        const { functions } = event as unknown as { functions?: unknown };
        const read = new Map<string, ReadonlyMap<string, boolean>>();
        if (mapping(functions)) {
          for (const [train, names] of Object.entries(functions)) {
            if (!mapping(names)) continue;
            const on = new Map<string, boolean>();
            for (const [name, value] of Object.entries(names)) {
              if (typeof value === "boolean") on.set(name, value);
            }
            read.set(train, on);
          }
        }
        this.switched = read;
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
      case "unfit": {
        // The trains a rebuild took off, whole from the topic: the
        // dispatcher republishes it without a train a person has placed, so
        // last value wins and the list empties as they are put back (#709).
        const { trains } = event as unknown as { trains?: Unfit[] };
        this.unfitRows = Array.isArray(trains) ? [...trains] : [];
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
        // The scheduler's whole answer, last-value-wins: the run each train
        // would make across the block it stands in, whose far end is the one
        // it would depart through nose-first. The panel renders that as the
        // direction arrow and derives none of it — a train that has never
        // moved has an arrow for the same reason a moved one does
        // (ADR-0036).
        const { facing } = event as unknown as {
          facing: Record<string, FacingRef>;
        };
        this.heading = new Map(
          Object.entries(facing).map(([train, run]) => [
            train,
            { block: blockOf(run), toward: noseOf(run) },
          ]),
        );
        return;
      }
      case "request_submitted": {
        const { id, train, depart, dest, after } = event as unknown as Submission;
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
          ...(after === undefined ? {} : { after }),
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

  /** Whether any train is crossing, so a power cut now would
   *  strand it (GLOSSARY.md, **Moving**), as `state/moving` last said, `null`
   *  where it has said nothing readable. Read and never derived: the picture
   *  a page draws says where trains stand, not what the dispatcher has
   *  granted. */
  get moving(): boolean | null {
    return this.movingWord;
  }

  /** The railroad's driving mode, as `layout` last said, `null` before it has
   *  said anything (ADR-0079). What the rail's driving control draws. */
  get driving(): DrivingMode | null {
    return this.drivingWord;
  }

  /** Whether a train may move at all, as the layout last said, `null` before
   *  it has said anything (ADR-0078). What the band's power control
   *  draws. */
  get power(): Power | null {
    return this.powerWord;
  }

  /** What the hardware says is wrong with the supply, in its own words,
   *  `null` where it says nothing — before it has spoken, and again once it
   *  publishes a frame without a reason (BUS.md, device vocabulary). The band
   *  shows it as a fault, whichever way `power` stands: a trip with the other
   *  districts still powered reads `on`, and the sentence is the whole of
   *  what says so (ADR-0050, #602). Nothing branches on it — it is read by a
   *  person and never by this model. */
  get fault(): string | null {
    return this.faultWord;
  }

  /** What the detectors dispute, as the dispatcher last said (#153): trains
   *  standing in a block that reads clear, and blocks that read occupied with
   *  nothing claiming them. Empty unless the run is held, so a release is
   *  where this is worth reading — it is what the person is deciding to
   *  accept, and the marks go with the hold. */
  disputes(): { trains: string[]; blocks: string[] } {
    return { trains: [...this.disputed.trains], blocks: [...this.disputed.blocks] };
  }

  /** The trains the last rebuild under the same name took off the layout,
   *  each with the block it stood in and why, as the dispatcher last said
   *  (#709). Empty until a rebuild leaves one off, and again once each is
   *  placed. */
  unfit(): Unfit[] {
    return [...this.unfitRows];
  }

  /** Every block of the layout, at the strongest state that holds for it:
   *  a train standing there, a lock holding it, a committed route heading
   *  through it, or nothing. Occupancy outranks both route states — a
   *  standing train is still a lock, and the picture must never lose which
   *  block a train is actually in (ui/PANEL.md). */
  blocks(): Map<string, BlockView> {
    const committed = new Map<string, string>();
    for (const request of this.requests.values()) {
      if (request.phase !== "committed") continue;
      for (const resource of request.route ?? []) {
        if (resource in this.layout.blocks) committed.set(resource, request.train);
      }
    }
    const names = this.names();
    const views = new Map<string, BlockView>();
    for (const block of Object.keys(this.layout.blocks)) {
      const train = this.standing.get(block);
      // The name rides on the block whatever its colour, as the dispute does:
      // a train in a block its route has lit is still the thing worth reading
      // there, and what a press on it takes hold of (#897).
      const named = names.get(block);
      const naming: Pick<BlockView, "named" | "crossing"> =
        named === undefined
          ? {}
          : this.crossing.has(named)
            ? { named, crossing: true }
            : { named };
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
          ...naming, ...dispute,
        });
        continue;
      }
      const holder = this.locks.get(block);
      if (holder !== undefined) {
        views.set(block, { state: "locked", train: holder, ...naming, ...dispute });
        continue;
      }
      const expecting = committed.get(block);
      if (expecting !== undefined) {
        views.set(block, { state: "committed", train: expecting, ...naming, ...dispute });
        continue;
      }
      views.set(block, { state: "free", ...naming, ...dispute });
    }
    return views;
  }

  /**
   * block → the train whose name it carries (ui/PANEL.md, #897).
   *
   * A train is named in every block it holds that reads occupied, so one
   * passing from one block to the next is in the old one, then both, then
   * the new one. Where none it holds reads occupied — a page that joined
   * after the readings, or a detector that has dropped out under it — it is
   * named in the block it last stood in. Only trains the
   * run has placed are named: one it took off keeps its blocks until they
   * read clear, as locked track and no marker (ADR-0069).
   */
  private names(): Map<string, string> {
    const held = new Map<string, string[]>();
    for (const [resource, train] of this.locks) {
      if (!(resource in this.layout.blocks) || !this.reads.has(resource)) continue;
      held.set(train, [...(held.get(train) ?? []), resource]);
    }
    const names = new Map<string, string>();
    for (const [train, last] of this.stood) {
      for (const block of held.get(train) ?? [last]) {
        if (!names.has(block)) names.set(block, train);
      }
    }
    return names;
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
   * What each block end's detector reads, exactly as its `device/sensor` row
   * said (#898): the readings `layout` folds into `block_occupied` and
   * `block_vacated`, shown for a person debugging the layout. An end no row
   * has named is absent.
   */
  detected(): ReadonlyMap<EndRef, Reading> {
    return this.readings;
  }

  /**
   * Where each point lies, by the address its motor answers to
   * ([ADR-0022](../../../docs/adr/0022-a-symbol-carries-its-hardware-address.md)).
   *
   * `layout` writes a retained `wanted/point` row for each point every
   * `align` names, a route's or a person's throw
   * ([ADR-0068](../../../docs/adr/0068-a-person-throws-a-point-and-the-dispatcher-drops-it-on-a-lit-road.md)),
   * so this is a ledger of those rows rather than anything derived: the panel
   * neither knows which points a transit traverses nor works out how each
   * must lie. An address stays where its row last left it, and a page opened
   * mid-session is handed every row since the broker came up.
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
    const state = new Map<string, Claim>();
    const wires = new Map<string, Claim>();
    const light = (resource: string, claim: Claim) => {
      const way = this.ways.get(resource);
      if (way === undefined) return; // a block, or a transit off this drawing
      for (const [symbol, leg] of way.legs) {
        const taken = legs.get(symbol) ?? new Set<string>();
        taken.add(leg === "" ? WHOLE : leg);
        legs.set(symbol, taken);
        if (claim === "locked" || !state.has(symbol)) state.set(symbol, claim);
      }
      for (const wire of way.wires) {
        if (claim === "locked" || !wires.has(wire)) wires.set(wire, claim);
      }
    };
    for (const resource of this.locks.keys()) light(resource, "locked");
    for (const request of this.requests.values()) {
      if (request.phase !== "committed") continue;
      for (const resource of request.route ?? []) light(resource, "committed");
    }
    return { legs, state, wires };
  }

  /**
   * Every train the run has placed, with the block it stands in, ordered by
   * name so the pane that lists them does not reshuffle as the railroad
   * moves (#169).
   *
   * The roster pane draws a row each. The freeze rule does not count them:
   * track power on or draining freezes the drawing, whatever trains stand
   * (ADR-0071). A crossing train is placed and stands in no block: it is
   * holding a transit, which is as on the layout as a train gets.
   *
   * A train whose head is in the next block while its tail has not cleared
   * the last is named against both, and is one train: the newer block wins,
   * `standing` being written in the order the sensors reported.
   */
  placed(): Placed[] {
    const where = new Map<string, string | null>();
    for (const [block, train] of this.standing) where.set(train, block);
    for (const train of this.crossing.keys()) where.set(train, null);
    return [...where.keys()]
      .sort()
      .map((train) => ({ train, block: where.get(train)! }));
  }

  /**
   * Which throttle holds each train, by the id its page minted, as `layout`
   * last said on `state/taken`. A train the map does not name, no throttle
   * holds.
   *
   * Read and never derived, and never written from a gesture: the topic is
   * the truth about who is driving, and a view that marked a train taken on
   * its own press would show a person holding a train `layout` never handed
   * them (ADR-0035, ui/THROTTLE.md).
   */
  taken(): ReadonlyMap<string, string> {
    return this.holders;
  }

  /**
   * Which of each train's functions are on, by name, as `layout` last said
   * on `state/functions`: train → name → on. A train or a name the map does
   * not give is off, and so is every function before the row is heard.
   *
   * Read and never written from a press, for the reason `taken()` is: the
   * button says what `layout` wrote, not what a person asked for.
   */
  functions(): ReadonlyMap<string, ReadonlyMap<string, boolean>> {
    return this.switched;
  }

  /**
   * The trains with a move outstanding: granted and not yet arrived at the
   * sensor of the block it enters. `layout` applies a throttle's speed only
   * then (BUS.md, `throttle_wanted`), so it is what makes the throttle's
   * lever live.
   *
   * Read off the retained picture, so a page opened mid-move sees the move
   * as `layout` holds it: a train is crossing from its grant to its arrival
   * sensor (the dispatcher's own outstanding set), and a request of its
   * carrying a route is the move behind it. The crossing the dispatcher
   * restores after a restart has no request behind it, and no move `layout`
   * is known to hold, so it grants nothing.
   */
  granted(): ReadonlySet<string> {
    const running = new Set<string>();
    for (const request of this.requests.values()) {
      if (request.route !== undefined) running.add(request.train);
    }
    return new Set([...this.crossing.keys()].filter((train) => running.has(train)));
  }

  /**
   * The end of its block each placed train points at, `<block>.<end>`: where
   * its facing runs to, which is the end it would depart through nose-first
   * and the end whose signal it is reading (GLOSSARY.md, **Facing**).
   *
   * The scheduler's answer with nothing added — the same value the run
   * view's direction arrow is drawn from — put in the form the aspects are
   * keyed by, so a throttle can ask what the train it is driving faces.
   */
  noses(): ReadonlyMap<string, EndRef> {
    return new Map(
      [...this.heading].map(([train, { block, toward }]) => [
        train,
        `${block}.${toward}`,
      ]),
    );
  }

  /**
   * The blocks each train has ahead of it on the route it is committed to,
   * in the order it would run them, with how strong a claim the dispatcher
   * has on each: `locked` where it holds the lock and the train may move,
   * `committed` where the route is chosen and the claim is not made yet.
   *
   * The same two words and the same ledger the picture lights a route with
   * (ui/PANEL.md), read a train at a time because a person driving by hand
   * is reading one train's road. The train's own block is not in it — what
   * is ahead begins past where it stands — and a train with no committed
   * route has nothing ahead, a route being the only thing that says which
   * way it is going.
   */
  ahead(): Map<string, Ahead[]> {
    const where = new Map<string, string | null>();
    for (const { train, block } of this.placed()) where.set(train, block);
    const found = new Map<string, Ahead[]>();
    for (const request of this.requests.values()) {
      if (request.phase !== "committed") continue;
      const route = request.route ?? [];
      const standing = where.get(request.train) ?? null;
      const at = standing === null ? -1 : route.indexOf(standing);
      found.set(
        request.train,
        route
          .slice(at + 1)
          .filter((resource) => resource in this.layout.blocks)
          .map((block) => ({
            block,
            claim:
              this.locks.get(block) === request.train
                ? ("locked" as const)
                : ("committed" as const),
          })),
      );
    }
    return found;
  }

  /**
   * Whether `train` may be put in `block` by hand: no train stands there, no
   * other train holds its lock, and it is on no other train's remaining
   * route — the dispatcher's `DispatchState.free()`, read off
   * `state/allocation` (BUS.md, `placement_wanted`). Power is not asked: a
   * placement is accepted at any power (ADR-0080).
   *
   * The train's own claims are left out, because the dispatcher cancels its
   * request before it asks, and a lock it holds where it does not stand is
   * either that request's or residue of its own removal, free to it
   * (ADR-0069). The dispatcher stays the authority: this only keeps a drop
   * it would drop from being sent.
   */
  free(block: string, train: string): boolean {
    if (this.standing.has(block)) return false;
    const holder = this.locks.get(block);
    if (holder !== undefined && holder !== train) return false;
    const where = new Map<string, string | null>();
    for (const one of this.placed()) where.set(one.train, one.block);
    return ![...this.requests.values()].some((request) => {
      if (request.phase !== "committed" || request.train === train) return false;
      const route = request.route ?? [];
      const standing = where.get(request.train) ?? null;
      const at = standing === null ? 0 : Math.max(route.indexOf(standing), 0);
      return route.slice(at).includes(block);
    });
  }

  /** Whether that block still carries that train's name. The right-click
   *  menu is about one train in one block, and a menu left open outlives
   *  both: a train that has moved on is turned around somewhere else
   *  entirely (ui/PANEL.md). */
  shows(train: string, block: string): boolean {
    return this.names().get(block) === train;
  }

  /**
   * Whether the train has a request in flight: submitted, admitted or
   * committed, but not one already answered with a rejection.
   *
   * The panel pre-judges one gesture on this and no other (ui/PANEL.md).
   * Turning a train around while a request of its own is queued would flip
   * the arrow under it: the request still departs the end the facing named
   * when it was composed, so the train would leave the other way round from
   * the way the arrow now points (#295). A rejected request
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

  /** The id a Cancel request on this train names: its first request in
   *  flight, in the order the dispatcher serves them, or `null` where it has
   *  none. Cancelling that one ends the requests chained after it as well
   *  ([ADR-0080](../../../docs/adr/0080-the-waiting-requests-are-a-list-a-person-orders.md)),
   *  so the gesture still ends whatever the train has. */
  firstRequest(train: string): string | null {
    for (const request of this.requests.values()) {
      if (request.train === train && request.phase !== "rejected") return request.id;
    }
    return null;
  }

  /** The request list, one row per request the dispatcher holds, in the
   *  order it serves them (`state/allocation`'s `requests`,
   *  [ADR-0080](../../../docs/adr/0080-the-waiting-requests-are-a-list-a-person-orders.md)).
   *  A request only submitted is not listed yet, and a rejected one never is:
   *  the dispatcher holds neither. */
  requestList(): RequestRow[] {
    return requestRows(
      [...this.requests.values()].filter(
        (request) => request.phase === "admitted" || request.phase === "committed",
      ),
    );
  }

  /** The endpoints worth marking: pending requests as endpoints only — never
   *  a predicted path — and rejections with their reason in words. */
  markers(): Marker[] {
    const found: Marker[] = [];
    for (const request of this.requests.values()) {
      const { id, train } = request;
      if (request.phase === "requested" || request.phase === "admitted") {
        if (request.depart !== null) {
          found.push({ id, train, at: request.depart, role: "depart" });
        }
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
        const note = spell(REJECTED, request.reason ?? "");
        // A chained request has no departure end of its own, so its arrival
        // ends carry the reason instead.
        if (request.depart !== null) {
          found.push({ id, train, at: request.depart, role: "rejected", note });
        }
        for (const end of request.dest) {
          found.push({
            id,
            train,
            at: end,
            role: "rejected",
            ...(request.depart === null ? { note } : {}),
          });
        }
      }
    }
    return found;
  }
}
