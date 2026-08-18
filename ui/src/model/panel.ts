/**
 * The panel model: bus payloads in, render state out (ui/PANEL.md, #70).
 *
 * No DOM anywhere. The component paints what this class answers — block
 * states, direction arrows, signal aspects, request markers, lit route legs —
 * and a trace replay or the live bridge feed the same `apply`, which is what
 * lets the live panel consume this model unchanged.
 *
 * Everything is derived the way the dispatcher derives it: occupancy events
 * are anonymous, so an occupied block's train is the holder of its lock, and
 * direction is the entry end of the last granted move. Nothing here computes
 * topology — which ends a transit joins and which legs its way takes come
 * from the store's `/review`, handed in at construction.
 */

import { WHOLE } from "./inspect.js";
import type { Explained, Layout } from "./store.js";
import type { Submission, TraceEvent } from "./trace.js";

/** A block end, written `<block>.<end>` as the bus writes it. */
export type EndRef = string;

export interface BlockView {
  state: "free" | "occupied" | "reserved" | "planned";
  /** The train standing, holding or heading here, where one is. */
  train?: string;
  /** The end the occupying train faces, once a granted move has said. */
  toward?: string;
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

/** A rejection reason spelled out, as the spec words them (#67). */
const REJECTED: Record<string, string> = {
  no_fit: "the train doesn't fit",
  no_entry: "no arrival end is enterable",
  unreachable: "no path exists",
};

/** A pruned arrival end's reason, short enough to sit at the end it marks. */
const PRUNED: Record<string, string> = {
  no_fit: "doesn't fit",
  no_entry: "not enterable",
  unreachable: "unreachable",
};

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
  /** block → the train standing in it. */
  private standing = new Map<string, string>();
  /** train → the block it last entered and the end it now faces. */
  private heading = new Map<string, { block: string; toward: string }>();
  /** train → the facing its granted move will give it, held until the train
   *  is actually in that block. A grant names the next block a tick ahead of
   *  the sensor, and until the sensor speaks the train is still standing
   *  where it was, facing the end it is leaving through. */
  private granted = new Map<string, { block: string; toward: string }>();
  private requests = new Map<string, Request>();
  /** train → the highest id number it has been given, which is what numbers
   *  the next one the way the file scheduler numbers its own (`<train>-1`,
   *  `<train>-2`, …). Not cleared by `reset`: rejoining a session does not
   *  make the ids it already handed out available again. */
  private minted = new Map<string, number>();
  /** Whether the first tick has passed: a lock on a block before it is the
   *  trace's opening placement, there being no occupancy event for a train
   *  that never moved. */
  private started = false;

  /** end → the transit resources attached there. */
  private readonly attached = new Map<EndRef, string[]>();
  /** transit resource → the two block ends it joins. */
  private readonly joins = new Map<string, [EndRef, EndRef]>();
  /** transit resource → the symbols and legs its way takes. */
  private readonly ways = new Map<string, [string, string][]>();

  constructor(
    private readonly layout: Layout,
    explain: Explained,
  ) {
    for (const [connection, { transits }] of Object.entries(layout.connections)) {
      for (const [transit, ends] of Object.entries(transits)) {
        const resource = `${connection}.${transit}`;
        this.joins.set(resource, ends);
        for (const end of ends) {
          this.attached.set(end, [...(this.attached.get(end) ?? []), resource]);
        }
        const way = explain.connections[connection]?.transits[transit]?.way;
        if (way !== undefined) this.ways.set(resource, way);
      }
    }
  }

  reset(): void {
    this.locks.clear();
    this.standing.clear();
    this.heading.clear();
    this.requests.clear();
    this.granted.clear();
    this.started = false;
  }

  /**
   * The scenario's stock, placement and facing (#72): where a live session's
   * trains stand before the first event arrives, and which way they face.
   *
   * A trace replay reads placement off the opening locks, but a browser joins
   * a session that was already assembled, so those locks are long gone. The
   * scenario is where facing is written down at all (ADR-0019), and it is the
   * one thing no event carries. A live panel therefore starts here, and
   * everything after it is derived from the bus exactly as a replay derives
   * it.
   *
   * It seeds only the trains this model knows nothing about. The scenario
   * says where a railroad *started*, and rejoining does not rewind it: a
   * train the bus has already shown somewhere keeps that place. Putting it
   * back would make the next drag state a departure block the dispatcher
   * knows is wrong.
   */
  place(trains: Record<string, { at: string; facing: string }>): void {
    for (const [train, { at, facing }] of Object.entries(trains)) {
      if (this.heading.has(train)) continue;
      this.standing.set(at, train);
      this.heading.set(train, { block: at, toward: facing });
    }
    this.started = true;
  }

  /**
   * The `request_submitted` payload a drag composes, or `null` where the train
   * stands nowhere this model knows.
   *
   * The panel is the scheduler (ADR-0016), so it mints the ids and supplies
   * the departure end from facing: the drag names the destination only, and
   * the dispatcher sees a request no different from a file scheduler's.
   */
  request(train: string, dest: EndRef[]): Submission | null {
    const facing = this.heading.get(train);
    if (facing === undefined || this.standing.get(facing.block) !== train) {
      return null;
    }
    const nth = (this.minted.get(train) ?? 0) + 1;
    this.minted.set(train, nth);
    return {
      id: `${train}-${nth}`,
      train,
      depart: `${facing.block}.${facing.toward}`,
      dest,
    };
  }

  apply(event: TraceEvent): void {
    switch (event.event) {
      case "tick":
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
        const arriving = this.granted.get(holder);
        if (arriving?.block === block) {
          this.heading.set(holder, arriving);
          this.granted.delete(holder);
        }
        return;
      }
      case "block_vacated": {
        const { block } = event as unknown as { block: string };
        this.standing.delete(block);
        return;
      }
      case "move_granted": {
        const { train, transit, into } = event as unknown as {
          train: string;
          transit: string;
          into: string;
        };
        const ends = this.joins.get(transit);
        const entry = ends?.find((end) => blockOf(end) === into);
        if (entry === undefined) return;
        this.granted.set(train, {
          block: into,
          toward: endOf(entry) === "A" ? "B" : "A",
        });
        return;
      }
      case "request_submitted": {
        const { id, train, depart, dest } = event as unknown as Submission;
        this.counted(id, train);
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
        // Direction comes from the chosen route or the entry end of the last
        // granted transit (ui/PANEL.md): the train will leave nose-first
        // through the request's departure end, so it faces that end now.
        const from = blockOf(request.depart);
        if (this.standing.get(from) === request.train) {
          this.heading.set(request.train, {
            block: from,
            toward: endOf(request.depart),
          });
        }
        return;
      }
      case "request_completed": {
        const { id } = event as unknown as { id: string };
        this.requests.delete(id);
        return;
      }
      default:
        return; // ticks aside, the panel reads a subset of the bus
    }
  }

  /** Take an id's number into account, whoever minted it. The relay echoes
   *  the panel's own requests back, so this covers a second panel and a
   *  rejoined one alike. */
  private counted(id: string, train: string): void {
    const nth = Number(id.slice(id.lastIndexOf("-") + 1));
    if (!Number.isInteger(nth)) return;
    this.minted.set(train, Math.max(this.minted.get(train) ?? 0, nth));
  }

  /** Every block of the layout, at the strongest state that holds for it:
   *  a train standing there, a lock holding it, a committed route heading
   *  through it, or nothing. */
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
      if (train !== undefined) {
        const heading = this.heading.get(train);
        views.set(block, {
          state: "occupied",
          train,
          ...(heading?.block === block ? { toward: heading.toward } : {}),
        });
        continue;
      }
      const holder = this.locks.get(block);
      if (holder !== undefined) {
        views.set(block, { state: "reserved", train: holder });
        continue;
      }
      const expecting = planned.get(block);
      if (expecting !== undefined) {
        views.set(block, { state: "planned", train: expecting });
        continue;
      }
      views.set(block, { state: "free" });
    }
    return views;
  }

  /**
   * The block ends showing green: the resource beyond the end is locked to
   * the train standing there — the locked-ahead rule (ui/PANEL.md).
   *
   * A known facing gates the aspect. The transit a train came in through
   * stays locked a tick behind it, and a signal can only mean "may the train
   * leave via this end" (ui/PANEL.md) — green over the entry end would
   * promise a departure no grant allows.
   */
  greenEnds(): Set<EndRef> {
    const green = new Set<EndRef>();
    for (const [block, train] of this.standing) {
      const facing = this.heading.get(train);
      for (const end of ["A", "B"]) {
        if (facing?.block === block && facing.toward !== end) continue;
        const beyond = this.attached.get(`${block}.${end}`) ?? [];
        if (beyond.some((resource) => this.locks.get(resource) === train)) {
          green.add(`${block}.${end}`);
        }
      }
    }
    return green;
  }

  /** The legs of every committed route's way, symbol by symbol, in the shape
   *  `inspect.lit` gives the canvas: `""` from the store means the symbol has
   *  no legs of its own and lights whole. */
  litLegs(): Map<string, Set<string>> {
    const lit = new Map<string, Set<string>>();
    for (const request of this.requests.values()) {
      if (request.phase !== "committed") continue;
      for (const resource of request.route ?? []) {
        for (const [symbol, leg] of this.ways.get(resource) ?? []) {
          const legs = lit.get(symbol) ?? new Set<string>();
          legs.add(leg === "" ? WHOLE : leg);
          lit.set(symbol, legs);
        }
      }
    }
    return lit;
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
            note: PRUNED[reason] ?? reason,
          });
        }
      } else if (request.phase === "rejected") {
        found.push({
          id,
          train,
          at: request.depart,
          role: "rejected",
          note: REJECTED[request.reason ?? ""] ?? request.reason,
        });
        for (const end of request.dest) {
          found.push({ id, train, at: end, role: "rejected" });
        }
      }
    }
    return found;
  }
}
