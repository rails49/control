/**
 * The loaded timetable, as the Run view lists it
 * ([#1345](https://github.com/rails49/control/issues/1345),
 * [#1356](https://github.com/rails49/control/issues/1356)).
 *
 * No DOM. The scheduler says which timetable is loaded and what became of
 * each entry on `tc49/schedule/state/timetable` (BUS.md), and `timetableOf`
 * reads that row.
 *
 * `listRows` works out the list from that timetable and the dispatcher's
 * request rows (`model/requests.ts`), top to bottom:
 *
 * - each entry in the timetable's order. An entry that is `out` and whose
 *   request the dispatcher lists carries that request's row. The requests
 *   that are out keep the dispatcher's order among themselves;
 * - then each request no entry went out as, in the dispatcher's order.
 *
 * With no timetable loaded the list is the request rows.
 *
 * A waiting request's row is dragged to reorder it, as in the request list,
 * and `moving` says what a drag asks the dispatcher. An entry that is not out
 * is no request and is not dragged. `opening` is the row the list is scrolled
 * to when a timetable is first drawn.
 *
 * An entry's row opens to its time, dwell and description
 * ([#1358](https://github.com/rails49/control/issues/1358)). `edited` is the
 * entry with what a person typed in one of them, and `same` is whether two
 * entries are equal as the scheduler compares them, which is how the open row
 * is found again when its entry moves.
 */

import { hhmm, timeOf } from "./clock.js";
import { reordering, type RequestRow } from "./requests.js";

/** The three phases of a loaded timetable (BUS.md). */
export type Phase = "loaded" | "running" | "over";

/** What became of an entry (BUS.md): `later`, its time has not come; `held`,
 *  due and waiting on its train; `out`, gone to the dispatcher as a request;
 *  and the four it ends in. */
export type EntryState =
  | "later"
  | "held"
  | "out"
  | "ended"
  | "rejected"
  | "cancelled"
  | "skipped";

const PHASES: ReadonlySet<string> = new Set(["loaded", "running", "over"]);

const STATES: ReadonlySet<string> = new Set([
  "later",
  "held",
  "out",
  "ended",
  "rejected",
  "cancelled",
  "skipped",
]);

/** An entry as the timetable document lists it (docs/store/LAYOUT.md): its
 *  time as `"HH:MM"`, its train, and `to`, the arrival ends, or `turn` on a
 *  turn-round. `dwell`, whole fast-clock minutes, and `description` are left
 *  out where the document leaves them out. */
export interface Entry {
  at: string;
  train: string;
  to?: string[];
  turn?: true;
  dwell?: number;
  description?: string;
}

/** An entry as the state row lists it: the document's fields, and what became
 *  of it. */
export interface Scheduled {
  entry: Entry;
  state: EntryState;
  /** The id of the request it went out as, kept after that request ends. */
  request?: string;
  /** Timetable time in seconds when it ended by arrival. */
  ended?: number;
}

/** Where a train stands at a timetable's start: its block and its facing. */
export interface TrainStart {
  at: string;
  facing: string;
}

/** The loaded timetable, as `tc49/schedule/state/timetable` says it. */
export interface Timetable {
  name: string;
  phase: Phase;
  /** Whether a drag or a turn-round adds an entry. */
  record: boolean;
  /** `"HH:MM"`. */
  start: string;
  trains: Record<string, TrainStart>;
  /** The ids of the requests to start blocks not yet ended. */
  positioning: string[];
  /** In timetable order. */
  entries: Scheduled[];
}

/** A `state/timetable` payload read: the loaded timetable, `null` where the
 *  row says none is loaded, and `undefined` where the row cannot be read. */
export function timetableOf(said: Record<string, unknown>): Timetable | null | undefined {
  const { timetable, phase, record, start, trains, positioning, entries } = said;
  if (timetable === null) return null;
  if (
    typeof timetable !== "string" ||
    typeof phase !== "string" ||
    !PHASES.has(phase) ||
    typeof record !== "boolean" ||
    typeof start !== "string" ||
    !Array.isArray(entries)
  ) {
    return undefined;
  }
  const starts = startsOf(trains);
  const read = (entries as unknown[]).map(scheduledOf);
  if (starts === null || !strings(positioning) || read.includes(null)) return undefined;
  return {
    name: timetable,
    phase: phase as Phase,
    record,
    start,
    trains: starts,
    positioning,
    entries: read as Scheduled[],
  };
}

/** One row of the list: an entry, a request, or an entry that is out with
 *  the request it went out as. */
export interface ListRow {
  /** The entry's document fields, on an entry's row. */
  entry?: Entry;
  /** What became of the entry, on an entry's row. */
  state?: EntryState;
  /** The request's row, on a request no entry went out as and on an entry
   *  that is `out` while the dispatcher lists its request. */
  request?: RequestRow;
}

/** The list's rows, top to bottom. `requests` is the dispatcher's list in
 *  the order it serves them (`requestRows`). */
export function listRows(
  timetable: Timetable | null,
  requests: readonly RequestRow[],
): ListRow[] {
  const entries = timetable?.entries ?? [];
  const named = new Set(entries.map(({ request }) => request));
  const out = new Set(
    entries.filter(({ state }) => state === "out").map(({ request }) => request),
  );
  // The requests that are out, in the dispatcher's order, with the entry each
  // went out as. They fill the places the out entries have in the timetable.
  const joined = requests
    .filter(({ id }) => out.has(id))
    .map((request) => ({
      entry: entries.find((entry) => entry.request === request.id)!.entry,
      state: "out" as const,
      request,
    }));
  const listed = new Set(joined.map(({ request }) => request.id));
  return [
    ...entries.map(({ entry, state, request }) =>
      state === "out" && request !== undefined && listed.has(request)
        ? joined.shift()!
        : { entry, state },
    ),
    ...requests.filter(({ id }) => !named.has(id)).map((request) => ({ request })),
  ];
}

const DONE: ReadonlySet<EntryState | undefined> = new Set([
  "ended",
  "rejected",
  "cancelled",
  "skipped",
]);

/** Whether a row's entry is over for this run: ended, rejected, cancelled or
 *  skipped. A request no entry went out as never is. */
export function done(row: ListRow): boolean {
  return DONE.has(row.state);
}

/** The position of the row the list opens at, the first that is not done,
 *  `null` where every row is. */
export function opening(rows: readonly ListRow[]): number | null {
  const first = rows.findIndex((row) => !done(row));
  return first === -1 ? null : first;
}

/**
 * What letting the row of request `id` go at position `at` of the list asks
 * for, `reorder_wanted`'s `before`, or `null` where the drag is refused or
 * moves nothing.
 *
 * `at` counts `rows` from the top, as `reordering` counts the request list.
 * The row lands in front of the first waiting request from there on, `null`
 * for the end, and `reordering` judges that move in `requests`, the
 * dispatcher's order. Entries that are not out are passed over: they are no
 * requests and the dispatcher orders none of them.
 */
export function moving(
  rows: readonly ListRow[],
  requests: readonly RequestRow[],
  id: string,
  at: number,
): { before: string | null } | null {
  const next = rows
    .slice(Math.max(0, at))
    .find(({ request }) => request?.state === "waiting" && request.id !== id)?.request;
  const place = requests.findIndex((request) => request.id === next?.id);
  return reordering(requests, id, place === -1 ? requests.length : place);
}

/** The fields of an entry a person types in its open row. */
export type Field = "at" | "dwell" | "description";

/**
 * `entry` with `words` typed in one field of its open row, `entry_wanted`'s
 * `now`, or `null` where nothing is to be sent: the words are no value for
 * that field, or the entry reads the same with them.
 *
 * - A time is `H:MM` or `HH:MM` and is said as `HH:MM`.
 * - A dwell is whole minutes in digits, 0 or more, and only an entry with
 *   `to` has one. Emptied it is 0, and 0 is the key left out.
 * - A description is the words with the space round them dropped. Emptied,
 *   the key is left out.
 */
export function edited(entry: Entry, field: Field, words: string): Entry | null {
  const typed = words.trim();
  const { dwell, description, ...rest } = entry;
  let now: Entry;
  if (field === "at") {
    const time = timeOf(typed);
    if (time === null) return null;
    now = { ...entry, at: hhmm(time) };
  } else if (field === "dwell") {
    if (entry.to === undefined || !/^\d*$/.test(typed)) return null;
    const minutes = Number(typed);
    now = {
      ...rest,
      ...(minutes === 0 ? {} : { dwell: minutes }),
      ...(description === undefined ? {} : { description }),
    };
  } else {
    now = {
      ...rest,
      ...(dwell === undefined ? {} : { dwell }),
      ...(typed === "" ? {} : { description: typed }),
    };
  }
  return same(entry, now) ? null : now;
}

/** Whether two entries are equal in every field of the document, a dwell
 *  left out being 0 and a description left out being empty: the scheduler's
 *  rule for the entry `entry_wanted` names (BUS.md). */
export function same(a: Entry, b: Entry): boolean {
  return (
    a.at === b.at &&
    a.train === b.train &&
    JSON.stringify(a.to) === JSON.stringify(b.to) &&
    (a.dwell ?? 0) === (b.dwell ?? 0) &&
    (a.description ?? "") === (b.description ?? "")
  );
}

function startsOf(trains: unknown): Record<string, TrainStart> | null {
  if (!mapping(trains)) return null;
  const starts: Record<string, TrainStart> = {};
  for (const [train, stands] of Object.entries(trains)) {
    if (!mapping(stands)) return null;
    const { at, facing } = stands;
    if (typeof at !== "string" || typeof facing !== "string") return null;
    starts[train] = { at, facing };
  }
  return starts;
}

function scheduledOf(listed: unknown): Scheduled | null {
  if (!mapping(listed)) return null;
  const { at, train, to, turn, dwell, description, state, request, ended } = listed;
  if (typeof at !== "string" || typeof train !== "string") return null;
  if (typeof state !== "string" || !STATES.has(state)) return null;
  // A turn-round has no arrival ends.
  const ends = to === undefined ? null : strings(to) && to.length > 0 ? to : undefined;
  if (ends === undefined || (ends === null && turn !== true)) return null;
  if (dwell !== undefined && typeof dwell !== "number") return null;
  if (description !== undefined && typeof description !== "string") return null;
  if (request !== undefined && typeof request !== "string") return null;
  if (ended !== undefined && typeof ended !== "number") return null;
  return {
    entry: {
      at,
      train,
      ...(ends === null ? { turn: true as const } : { to: ends }),
      ...(dwell === undefined ? {} : { dwell }),
      ...(description === undefined ? {} : { description }),
    },
    state: state as EntryState,
    ...(request === undefined ? {} : { request }),
    ...(ended === undefined ? {} : { ended }),
  };
}

function mapping(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}
