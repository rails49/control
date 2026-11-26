/**
 * The loaded timetable, as the Run view lists it
 * ([#1345](https://github.com/rails49/control/issues/1345),
 * [#1356](https://github.com/rails49/control/issues/1356)).
 *
 * No DOM. The scheduler says which timetable is loaded and what became of
 * each entry on `tc49/schedule/state/timetable` (BUS.md), and `timetableOf`
 * reads of that row what the page shows. The row's `positioning` and an
 * entry's `ended` are not read. Its `start`, its `repeat` and each entry's
 * `at` are in the time form `model/clock.ts` reads, `[<day>d]HH:MM`
 * ([#1363](https://github.com/rails49/control/issues/1363)).
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
 * is no request and is not dragged. `newest` is the row the list is scrolled
 * to when the scheduler says a new row.
 *
 * An entry's row opens to its time, arrival ends, dwell and description
 * ([#1358](https://github.com/rails49/control/issues/1358),
 * [#1386](https://github.com/rails49/control/issues/1386)). `edited` is the
 * entry with what a person typed in one of them, `outside` why a typed time
 * is not within the timetable's repeat, `misnamed` why typed arrival ends
 * are refused, and `same` is whether two entries are equal as the scheduler
 * compares them. Which row is open is `Opened`: `tapped` is what a tap makes
 * of it, `asking` what a change the row asked for makes of it, and
 * `followed` where it is when the scheduler says new rows. Entries carry no
 * id, so the open row is the first whose entry reads the same (`placeOf`).
 *
 * `starts` is each train's start cell in the roster: the block the loaded
 * timetable starts it in, and whether it is there. `startShown` is whether
 * the roster has those cells at all. `repeatRefused` is why a length is
 * refused as its repeat, and `typedRepeatRefused` why the Repeat dialog
 * sends nothing for what a person typed.
 */

import { DAY_S, timeOf, written } from "./clock.js";
import { reordering, type RequestRow } from "./requests.js";
import { trackLive, type Power } from "./trace.js";

/** The two phases of a loaded timetable (BUS.md). A running timetable
 *  repeats and never ends. */
export type Phase = "loaded" | "running";

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

const PHASES: ReadonlySet<string> = new Set(["loaded", "running"]);

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
 *  time in the time form, `"06:00"` or `"1d01:00"`, its train, and `to`, the arrival ends, or `turn` on a
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
  /** The round `state` is for, from 0
   *  ([#1367](https://github.com/rails49/control/issues/1367)). */
  round: number;
  /** The id of the request it went out as, kept after that request ends. */
  request?: string;
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
  /** Its start, a time on day 0, in fast seconds. */
  start: number;
  /** The time from its start to where it begins again, in fast seconds,
   *  greater than 0. Each entry's time is from `start` to before `start`
   *  plus `repeat`. */
  repeat: number;
  trains: Record<string, TrainStart>;
  /** In timetable order. */
  entries: Scheduled[];
}

/** A `state/timetable` payload read: the loaded timetable, `null` where the
 *  row says none is loaded, and `undefined` where the row cannot be read. */
export function timetableOf(said: Record<string, unknown>): Timetable | null | undefined {
  const { timetable, phase, record, start, repeat, trains, entries } = said;
  if (timetable === null) return null;
  const begins = typeof start === "string" ? timeOf(start) : null;
  const length = typeof repeat === "string" ? timeOf(repeat) : null;
  if (
    typeof timetable !== "string" ||
    typeof phase !== "string" ||
    !PHASES.has(phase) ||
    typeof record !== "boolean" ||
    begins === null ||
    begins >= DAY_S ||
    length === null ||
    length === 0 ||
    !Array.isArray(entries)
  ) {
    return undefined;
  }
  const starts = startsOf(trains);
  const read = (entries as unknown[]).map(scheduledOf);
  if (starts === null || read.includes(null)) return undefined;
  return {
    name: timetable,
    phase: phase as Phase,
    record,
    start: begins,
    repeat: length,
    trains: starts,
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

/** Whether a row's entry is done in its round: ended, rejected, cancelled or
 *  skipped. A request no entry went out as never is. */
export function done(row: ListRow): boolean {
  return DONE.has(row.state);
}

const GONE: ReadonlySet<EntryState> = new Set(["out", "ended", "rejected", "cancelled"]);

/**
 * The position in the list of the newest entry once the scheduler's row
 * `was` is followed by `now`, `null` for none: the row the list is scrolled
 * to ([#1385](https://github.com/rails49/control/issues/1385)). An entry's
 * place among the entries is its row's place in the list (`listRows`).
 *
 * An entry has gone out when it is `out`, `ended`, `rejected` or
 * `cancelled`. A newest entry has gone out and is one `was` does not list,
 * or lists as not gone out, or in an earlier round. `was` lists an entry
 * that reads the same (`same`), or that went out as the same request: a
 * changed entry keeps its request. Where several are newest, the last in the
 * list is the row.
 *
 * With no `was`, or `was` another timetable by its name, the row is the last
 * entry gone out in the highest round any entry has gone out in, and none
 * where no entry has. A request no entry went out as is never the row.
 */
export function newest(was: Timetable | null, now: Timetable | null): number | null {
  if (now === null) return null;
  const gone = now.entries.map(({ state }) => GONE.has(state));
  let at = -1;
  if (was === null || was.name !== now.name) {
    const top = Math.max(...now.entries.filter((_, i) => gone[i]).map(({ round }) => round));
    now.entries.forEach(({ round }, i) => {
      if (gone[i] && round === top) at = i;
    });
  } else {
    now.entries.forEach(({ entry, round, request }, i) => {
      if (!gone[i]) return;
      const listed = was.entries.find(
        (old) => same(old.entry, entry) || (request !== undefined && old.request === request),
      );
      if (listed === undefined || !GONE.has(listed.state) || listed.round < round) at = i;
    });
  }
  return at === -1 ? null : at;
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
export type Field = "at" | "to" | "dwell" | "description";

/**
 * `entry` with `words` typed in one field of its open row, `entry_wanted`'s
 * `now`, or `null` where nothing is to be sent: the words are no value for
 * that field, or the entry reads the same with them.
 *
 * - A time is read and said as `model/clock.ts` reads and writes one:
 *   `0d06:10` is said as `06:10`.
 * - Arrival ends are the words split at commas, in the order typed, the
 *   space round each dropped and an empty part left out. Only an entry with
 *   `to` has them. Any words are read as ends here. `misnamed` says why ends
 *   are refused.
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
    now = { ...entry, at: written(time) };
  } else if (field === "to") {
    if (entry.to === undefined) return null;
    now = { ...entry, to: endsIn(typed) };
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

/** Why `words` typed as an entry's time are refused, `null` where they are
 *  no time (`edited` asks nothing for them) or a time within `timetable`'s
 *  repeat, from its start to before its start plus its repeat. The scheduler
 *  drops an entry outside (BUS.md). The words name the range: "before the
 *  start 06:00", or "after the last minute, 1d05:59", the start plus the
 *  repeat less one minute. */
export function outside(
  { start, repeat }: Pick<Timetable, "start" | "repeat">,
  words: string,
): string | null {
  const time = timeOf(words);
  if (time === null) return null;
  if (time < start) return `before the start ${written(start)}`;
  if (time >= start + repeat) return `after the last minute, ${written(start + repeat - 60)}`;
  return null;
}

/** Why `words` typed as an entry's arrival ends are refused, `null` where
 *  they are good ends of `blocks`, the railroad's block names. The words
 *  name what is wrong with the first end that is: "no arrival end" for
 *  none, "b.C: the end is A or B", "the railroad has no block z", or "b is
 *  named twice", which `b, b.A` is too. A comma with nothing after it adds
 *  no end. */
export function misnamed(blocks: readonly string[], words: string): string | null {
  const ends = endsIn(words);
  if (ends.length === 0) return "no arrival end";
  const named = new Set<string>();
  for (const end of ends) {
    const [block = "", letter] = end.split(/\.(.*)/);
    if (letter !== undefined && letter !== "A" && letter !== "B") {
      return `${end}: the end is A or B`;
    }
    if (!blocks.includes(block)) return `the railroad has no block ${block}`;
    if (named.has(block)) return `${block} is named twice`;
    named.add(block);
  }
  return null;
}

/** The arrival ends in `words`: split at commas, the space round each
 *  dropped, and none for a part that is empty. */
function endsIn(words: string): string[] {
  return words
    .split(",")
    .map((part) => part.trim())
    .filter((part) => part !== "");
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

/** The entry whose row is open in the list
 *  ([#1358](https://github.com/rails49/control/issues/1358)). One row is
 *  open at a time. */
export interface Opened {
  /** The entry as the scheduler's row lists it. */
  entry: Entry;
  /** The entry as the last change asked of it reads, `null` once the
   *  scheduler's row lists it so. */
  sent: Entry | null;
}

/** The place in `rows` of the first row whose entry reads as `entry`, -1 for
 *  none. The scheduler changes the first too (BUS.md). */
export function placeOf(rows: readonly ListRow[], entry: Entry): number {
  return rows.findIndex((row) => row.entry !== undefined && same(row.entry, entry));
}

/** What is open after a tap on `entry`'s row: that row, or none where it was
 *  the open one. */
export function tapped(open: Opened | null, entry: Entry): Opened | null {
  return open !== null && same(open.entry, entry) ? null : { entry, sent: null };
}

/** What is open after the open row asked for its entry to read `now`, `null`
 *  to delete it. A deleted entry's row is closed at once, so a second Delete
 *  is not sent for an entry that reads the same. A changed one is kept as
 *  asked, to find its row again. */
export function asking(open: Opened | null, now: Entry | null): Opened | null {
  return open === null || now === null ? null : { ...open, sent: now };
}

/** What is open in new rows. A change the scheduler took is in them: the
 *  entry reads as the change asked, and may be at another place. An entry no
 *  row lists is open no more. */
export function followed(open: Opened | null, rows: readonly ListRow[]): Opened | null {
  if (open === null) return null;
  if (open.sent !== null && placeOf(rows, open.sent) !== -1) {
    return { entry: open.sent, sent: null };
  }
  return placeOf(rows, open.entry) === -1 ? null : open;
}

/** A train's start cell in the roster: the block the loaded timetable starts
 *  it in, and whether it is there. `met`, it is; `missed`, it is off the
 *  layout, in another block or crossing a transit; `turned`, it is there
 *  facing the other way. */
export interface Start {
  block: string;
  state: "met" | "missed" | "turned";
}

/** Whether the roster shows where the loaded timetable starts its trains:
 *  only while its phase is `loaded`, as a timetable that has started moves
 *  its trains out of their start blocks. */
export function startShown(timetable: Timetable | null): timetable is Timetable {
  return timetable?.phase === "loaded";
}

/**
 * Each train's start cell, by train
 * ([#1357](https://github.com/rails49/control/issues/1357),
 * [#1392](https://github.com/rails49/control/issues/1392)). A train the
 * timetable does not name has none.
 *
 * `placed` is each train on the layout and the block it stands in, `null`
 * while it crosses a transit. `noses` is the block end each train points at,
 * `<block>.<end>`, as `tc49/schedule/state/facing` says it. A train with no
 * facing said is not turned.
 *
 * None unless `startShown`.
 */
export function starts(
  timetable: Timetable | null,
  placed: readonly { train: string; block: string | null }[],
  noses: ReadonlyMap<string, string>,
): Map<string, Start> {
  const cells = new Map<string, Start>();
  if (!startShown(timetable)) return cells;
  const where = new Map(placed.map(({ train, block }) => [train, block]));
  for (const [train, { at, facing }] of Object.entries(timetable.trains)) {
    const nose = noses.get(train);
    const state =
      where.get(train) !== at
        ? "missed"
        : nose !== undefined && nose !== `${at}.${facing.split("-to-")[1]}`
          ? "turned"
          : "met";
    cells.set(train, { block: at, state });
  }
  return cells;
}

/**
 * Why a name cannot name a timetable, `null` for one that can
 * ([#1357](https://github.com/rails49/control/issues/1357)). The timetable
 * document takes a name that is not empty, has no `/` and does not start
 * with `.` (docs/store/LAYOUT.md), and the scheduler drops a gesture with any
 * other. `taken` is the names a rename may not use: the scheduler drops a
 * rename to a name the store has.
 */
export function nameRefused(name: string, taken: readonly string[] = []): string | null {
  if (name === "") return "a timetable needs a name";
  if (name.includes("/") || name.startsWith(".")) return `'${name}' cannot name a timetable`;
  if (taken.includes(name)) return `'${name}' is already a timetable`;
  return null;
}

/** Why `repeat`, a length in fast seconds, is refused as `timetable`'s
 *  repeat, `null` where the scheduler takes it
 *  ([#1368](https://github.com/rails49/control/issues/1368)): it is 0, or the
 *  latest entry falls at or after the start plus `repeat`. The words then
 *  name that entry's time and the shortest repeat that fits, its offset from
 *  the start plus one minute. */
export function repeatRefused(
  timetable: { start: number; entries: readonly { entry: Pick<Entry, "at"> }[] },
  repeat: number,
): string | null {
  if (repeat === 0) return "a repeat is longer than 00:00";
  const latest = Math.max(...timetable.entries.map(({ entry }) => timeOf(entry.at) ?? 0));
  if (latest < timetable.start + repeat) return null;
  return `the latest entry is at ${written(latest)}, so the shortest repeat is ${written(
    latest - timetable.start + 60,
  )}`;
}

/** Why the Repeat dialog sends nothing for `words` typed as `timetable`'s
 *  repeat, `null` where it sends them: they are no length, `repeatRefused`
 *  refuses the length, or track power is on (`powered`). With no timetable
 *  loaded only the words and the power are checked. */
export function typedRepeatRefused(
  timetable: Parameters<typeof repeatRefused>[0] | null,
  words: string,
  power: Power | null,
): string | null {
  const length = timeOf(words);
  if (length === null) return `'${words.trim()}' is no length: write [<day>d]HH:MM`;
  const short = timetable === null ? null : repeatRefused(timetable, length);
  return short ?? (powered(power) || null);
}

/** Why a new timetable and a load are not asked for, `""` where they are:
 *  the scheduler takes either only while track power reads `off` (BUS.md). A
 *  supply not yet heard shuts neither, as it shuts no view (`shut` in
 *  `model/views.ts`). */
export function powered(power: Power | null): string {
  return trackLive(power) ? "track power is on" : "";
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
  const { at, train, to, turn, dwell, description, state, round, request } = listed;
  if (typeof at !== "string" || timeOf(at) === null || typeof train !== "string") return null;
  if (typeof state !== "string" || !STATES.has(state)) return null;
  if (typeof round !== "number" || !Number.isInteger(round) || round < 0) return null;
  // A turn-round has no arrival ends.
  const ends = to === undefined ? null : strings(to) && to.length > 0 ? to : undefined;
  if (ends === undefined || (ends === null && turn !== true)) return null;
  if (dwell !== undefined && typeof dwell !== "number") return null;
  if (description !== undefined && typeof description !== "string") return null;
  if (request !== undefined && typeof request !== "string") return null;
  return {
    entry: {
      at,
      train,
      ...(ends === null ? { turn: true as const } : { to: ends }),
      ...(dwell === undefined ? {} : { dwell }),
      ...(description === undefined ? {} : { description }),
    },
    state: state as EntryState,
    round,
    ...(request === undefined ? {} : { request }),
  };
}

function mapping(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}
