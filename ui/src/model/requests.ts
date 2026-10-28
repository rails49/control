/**
 * The request list: the requests the dispatcher holds, in the order it serves
 * them, as the run view lists them
 * ([ADR-0080](../../../docs/adr/0080-the-waiting-requests-are-a-list-a-person-orders.md),
 * [#829](https://github.com/rails49/control/issues/829)).
 *
 * No DOM. The rows are `state/allocation`'s `requests`, and what a drag of one
 * of them asks the dispatcher is worked out here, so `tc-requests` only draws
 * rows and reports where a row was let go.
 *
 * The panel refuses the drags the dispatcher would drop (BUS.md,
 * `reorder_wanted`): a request that has started cannot move, and a train's
 * chained request cannot come before the one it follows. Refused here, the
 * row goes back where it was rather than being sent and silently dropped.
 *
 * A request the dispatcher last refused a launch or a move carries a note:
 * which train it waits for, and, where that train has no request of its own
 * and so will never move, that a person has to give it one
 * ([#1114](https://github.com/rails49/control/issues/1114)).
 */

import type { EndRef } from "./panel.js";

/** A request as the dispatcher's picture lists it. */
export interface Listed {
  id: string;
  train: string;
  /** `null` on a request chained `after` an earlier one. */
  depart: EndRef | null;
  dest: EndRef[];
  after?: string;
  /** Present once the request has started. */
  route?: string[];
  /** The latest `grant_refused` since its last grant, where there is one. */
  refused?: Refused;
}

/** Why a request waits, as `grant_refused` said it (BUS.md): the reason, and
 *  each block or transit in the way with the train holding it, `""` for a
 *  block that reads occupied with no train in it. */
export interface Refused {
  reason: string;
  obstacles: { resource: string; holder: string }[];
}

/** One row of the request list. */
export interface RequestRow {
  id: string;
  train: string;
  /** Where the request starts: its departure end, or, on a chained request,
   *  the arrival ends of the one it follows, which is where that one leaves
   *  the train. Empty where the one it follows is no longer listed. */
  from: EndRef[];
  to: EndRef[];
  state: "waiting" | "underway";
  /** The id of the request this one follows, on a chained request. */
  after?: string;
  /** Which train the request waits for, a sentence per kind of holder, on
   *  a request the dispatcher last refused. */
  note?: string[];
}

/** The rows, one per request in list order. `standsIn` is the block a train
 *  holding `resource` is to leave: the resource itself where it is a block,
 *  and where it is a transit the block the train stands in. */
export function requestRows(
  requests: readonly Listed[],
  standsIn: (holder: string, resource: string) => string = (_, resource) => resource,
): RequestRow[] {
  const byId = new Map(requests.map((request) => [request.id, request]));
  const listed = new Set(requests.map((request) => request.train));
  return requests.map(({ id, train, depart, dest, after, route, refused }) => ({
    id,
    train,
    from:
      depart !== null
        ? [depart]
        : after === undefined
          ? []
          : (byId.get(after)?.dest ?? []),
    to: dest,
    state: route === undefined ? "waiting" : "underway",
    ...(after === undefined ? {} : { after }),
    ...(refused === undefined || refused.obstacles.length === 0
      ? {}
      : { note: waitsFor(refused, listed, standsIn) }),
  }));
}

/**
 * What a refused request waits for, a sentence per kind of holder, each
 * distinct holder once and several of one kind joined with "or", since any
 * one of them moving may free a route:
 *
 * - a train with a request of its own will pass by itself;
 * - a train with none never moves, so a person has to give it a request;
 * - a block held by no train waits for its detector to read clear.
 */
function waitsFor(
  refused: Refused,
  listed: ReadonlySet<string>,
  standsIn: (holder: string, resource: string) => string,
): string[] {
  const passing = new Set<string>();
  const parked = new Map<string, string>();
  const clearing = new Set<string>();
  for (const { resource, holder } of refused.obstacles) {
    if (holder === "") clearing.add(resource);
    else if (listed.has(holder)) passing.add(holder);
    else if (!parked.has(holder)) parked.set(holder, standsIn(holder, resource));
  }
  const sentences: string[] = [];
  if (passing.size > 0) sentences.push(`waits for ${or([...passing])} to pass`);
  if (parked.size > 0) {
    const leaving = [...parked].map(([holder, block]) => `${holder} to leave ${block}`);
    sentences.push(`waits for ${or(leaving)} — give ${or([...parked.keys()])} a request`);
  }
  if (clearing.size > 0) sentences.push(`waits for ${or([...clearing])} to read clear`);
  return sentences;
}

function or(words: readonly string[]): string {
  return words.join(" or ");
}

/**
 * What letting row `id` go at position `at` asks for — `reorder_wanted`'s
 * `before` — or `null` where the drag is refused or moves nothing.
 *
 * `at` counts rows from the top: `0` is in front of the first row and
 * `rows.length` is the end of the list. The row lands in front of the first
 * **waiting** row from there on, `null` for the end: the dispatcher drops a
 * move in front of a request that has started, and among the waiting ones
 * that is the same place in the order it serves them.
 *
 * Refused: a request that has started, and a move that would put a train's
 * chained request in front of the one it follows, either by moving the
 * chained one up or the one it follows down.
 */
export function reordering(
  rows: readonly RequestRow[],
  id: string,
  at: number,
): { before: string | null } | null {
  const row = rows.find((candidate) => candidate.id === id);
  if (row === undefined || row.state === "underway") return null;
  const others = rows.filter((candidate) => candidate.id !== id);
  // Where `at` falls once the row is lifted out of the list.
  const from = rows.indexOf(row);
  const slot = Math.max(0, Math.min(at > from ? at - 1 : at, others.length));
  const next = others.slice(slot).find((candidate) => candidate.state === "waiting");
  const before = next?.id ?? null;
  const order = [...others];
  order.splice(before === null ? order.length : order.indexOf(next!), 0, row);
  if (order.every((candidate, index) => candidate === rows[index])) return null;
  const place = new Map(order.map((candidate, index) => [candidate.id, index]));
  for (const candidate of order) {
    if (candidate.after === undefined) continue;
    const earlier = place.get(candidate.after);
    if (earlier !== undefined && earlier > place.get(candidate.id)!) return null;
  }
  return { before };
}
