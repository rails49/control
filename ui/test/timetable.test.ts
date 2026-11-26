// @vitest-environment happy-dom

/**
 * The Run view's list while a timetable is loaded
 * ([#1345](https://github.com/rails49/control/issues/1345),
 * [#1356](https://github.com/rails49/control/issues/1356)).
 *
 * Three parts, as `requests.test.ts` has. The row the scheduler publishes,
 * the list's rows and what a drag asks are `model/timetable.ts`'s. Then
 * `tc-requests`, which draws them. Then the run view, which reads the row off
 * `tc49/schedule/state/timetable`.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../src/ui/tc-app.js";
import "../src/ui/tc-requests.js";
import {
  reordering,
  requestRows,
  type Listed,
  type RequestRow,
} from "../src/model/requests.js";
import {
  done,
  listRows,
  moving,
  newest,
  timetableOf,
  type Entry,
  type Scheduled,
  type Timetable,
} from "../src/model/timetable.js";
import type { TcApp } from "../src/ui/tc-app.js";
import type { RequestReorder, TcRequests } from "../src/ui/tc-requests.js";
import { requestsStyles } from "../src/ui/tc-requests.styles.js";
import { running, settled } from "./support/shell.js";
import { brokering, joined, said, unbrokered, written } from "./support/session.js";

const ALLOCATION = "tc49/dispatch/state/allocation";
const TIMETABLE = "tc49/schedule/state/timetable";

/** The row as BUS.md gives it: `goods` went to `b` and turned round, and
 *  goes on to `c` once the clock reads 06:12. */
const SAID = {
  timetable: "evening",
  phase: "running",
  record: false,
  start: "06:00",
  repeat: "1d00:00",
  trains: { goods: { at: "a", facing: "A-to-B" } },
  positioning: ["p1"],
  entries: [
    {
      at: "06:02",
      train: "goods",
      to: ["b.A", "b.B"],
      dwell: 2,
      description: "meets the express",
      state: "ended",
      round: 0,
      request: "g1",
      ended: 21_790,
    },
    { at: "06:10", train: "goods", turn: true, state: "ended", round: 0 },
    { at: "06:12", train: "goods", to: ["c.B"], state: "later", round: 0 },
  ],
  at: 12.5,
};

describe("the timetable row", () => {
  /** The row's `positioning` and an entry's `ended` are shown nowhere, and
   *  are not read. */
  it("is read as what the page shows, each entry's document fields apart from what became of it", () => {
    expect(timetableOf(SAID)).toEqual({
      name: "evening",
      phase: "running",
      record: false,
      start: 6 * 3600,
      repeat: 86_400,
      trains: { goods: { at: "a", facing: "A-to-B" } },
      entries: [
        {
          entry: {
            at: "06:02",
            train: "goods",
            to: ["b.A", "b.B"],
            dwell: 2,
            description: "meets the express",
          },
          state: "ended",
          round: 0,
          request: "g1",
        },
        { entry: { at: "06:10", train: "goods", turn: true }, state: "ended", round: 0 },
        { entry: { at: "06:12", train: "goods", to: ["c.B"] }, state: "later", round: 0 },
      ],
    });
  });

  it("reads the round each entry's state is for", () => {
    const again = { ...SAID.entries[2], round: 2 };
    expect(timetableOf({ ...SAID, entries: [again] })).toMatchObject({
      entries: [{ state: "later", round: 2 }],
    });
  });

  it("reads an entry after midnight in the time form, and a repeat of a day", () => {
    const late = { at: "1d01:00", train: "goods", to: ["c.B"], state: "later", round: 0 };
    expect(timetableOf({ ...SAID, entries: [late] })).toMatchObject({
      start: 6 * 3600,
      repeat: 86_400,
      entries: [{ entry: { at: "1d01:00", train: "goods", to: ["c.B"] }, state: "later" }],
    });
  });

  it("reads null where no timetable is loaded", () => {
    expect(timetableOf({ timetable: null, at: 3 })).toBeNull();
  });

  it.each([
    ["no name", { ...SAID, timetable: 7 }],
    ["a phase outside the two", { ...SAID, phase: "paused" }],
    ["the phase over, which is gone", { ...SAID, phase: "over" }],
    ["no entries", { ...SAID, entries: undefined }],
    ["an entry in no known state", { ...SAID, entries: [{ ...SAID.entries[2], state: "lost" }] }],
    ["an entry with no round", { ...SAID, entries: [{ ...SAID.entries[2], round: undefined }] }],
    ["an entry in a round before 0", { ...SAID, entries: [{ ...SAID.entries[2], round: -1 }] }],
    ["an entry in a round that is no whole number", { ...SAID, entries: [{ ...SAID.entries[2], round: 1.5 }] }],
    ["an entry with neither to nor turn", { ...SAID, entries: [{ at: "06:02", train: "goods", state: "later", round: 0 }] }],
    ["an entry with no train", { ...SAID, entries: [{ at: "06:02", to: ["b.A"], state: "later", round: 0 }] }],
    ["an entry at a time with a one-digit hour", { ...SAID, entries: [{ ...SAID.entries[2], at: "6:12" }] }],
    ["an entry at no time", { ...SAID, entries: [{ ...SAID.entries[2], at: "soon" }] }],
    ["an entry at a time as a number", { ...SAID, entries: [{ ...SAID.entries[2], at: 22_320 }] }],
    ["no start", { ...SAID, start: undefined }],
    ["a start after day 0", { ...SAID, start: "1d06:00" }],
    ["no repeat", { ...SAID, repeat: undefined }],
    ["a repeat of 0", { ...SAID, repeat: "00:00" }],
    ["a repeat that is no length", { ...SAID, repeat: "a day" }],
  ])("is not read with %s", (_, said) => {
    expect(timetableOf(said)).toBeUndefined();
  });
});

/** `express` underway, then `goods` waiting, then `local` waiting: the
 *  dispatcher's list, in the order it serves them. */
const LISTED: Listed[] = [
  { id: "e1", train: "express", depart: "c.A", dest: ["a.B"], route: ["c", "sw.side", "a"] },
  { id: "g1", train: "goods", depart: "a.B", dest: ["b.A"] },
  { id: "l1", train: "local", depart: "d.A", dest: ["b.B", "c.B"] },
];

const [EXPRESS, GOODS, LOCAL] = requestRows(LISTED);

/** A timetable named `evening` with these entries. */
function loaded(...entries: Scheduled[]): Timetable {
  return {
    name: "evening",
    phase: "running",
    record: false,
    start: 6 * 3600,
    repeat: 86_400,
    trains: {},
    entries,
  };
}

function to(at: string, train: string, ...ends: string[]): Entry {
  return { at, train, to: ends };
}

describe("the list's rows", () => {
  it("are the request rows where no timetable is loaded", () => {
    expect(listRows(null, [EXPRESS!, GOODS!, LOCAL!])).toEqual([
      { request: EXPRESS },
      { request: GOODS },
      { request: LOCAL },
    ]);
  });

  it("are one per entry in the row's order, in each of the seven states", () => {
    const entries: Scheduled[] = [
      { entry: to("06:01", "express", "a.B"), state: "ended", round: 0, request: "e0" },
      { entry: to("06:02", "local", "b.B"), state: "rejected", round: 0, request: "l0" },
      { entry: to("06:03", "goods", "b.A"), state: "cancelled", round: 0, request: "g0" },
      { entry: to("06:04", "shunter", "c.A"), state: "skipped", round: 0 },
      { entry: to("06:05", "goods", "b.A"), state: "out", round: 0, request: "g1" },
      { entry: to("06:06", "express", "d.A"), state: "held", round: 0 },
      { entry: to("06:30", "local", "c.B"), state: "later", round: 0 },
    ];
    expect(listRows(loaded(...entries), [GOODS!])).toEqual([
      { entry: entries[0]!.entry, state: "ended" },
      { entry: entries[1]!.entry, state: "rejected" },
      { entry: entries[2]!.entry, state: "cancelled" },
      { entry: entries[3]!.entry, state: "skipped" },
      { entry: entries[4]!.entry, state: "out", request: GOODS },
      { entry: entries[5]!.entry, state: "held" },
      { entry: entries[6]!.entry, state: "later" },
    ]);
  });

  /** Between a request leaving the dispatcher's list and the scheduler's next
   *  row, and before the dispatcher has listed a request just submitted. */
  it("give an out entry whose request is not listed no request row", () => {
    const entry = to("06:05", "goods", "b.A");
    expect(listRows(loaded({ entry, state: "out", round: 0, request: "g1" }), [])).toEqual([
      { entry, state: "out" },
    ]);
  });

  it("put a request no entry went out as after the entries, in the dispatcher's order", () => {
    const out = to("06:05", "goods", "b.A");
    const later = to("06:30", "goods", "c.B");
    const rows = listRows(
      loaded({ entry: out, state: "out", round: 0, request: "g1" }, { entry: later, state: "later", round: 0 }),
      [EXPRESS!, GOODS!, LOCAL!],
    );
    expect(rows).toEqual([
      { entry: out, state: "out", request: GOODS },
      { entry: later, state: "later" },
      { request: EXPRESS },
      { request: LOCAL },
    ]);
  });

  /** The scheduler's row says the entry ended before the page has the
   *  dispatcher's next picture: the request went out as that entry, and is
   *  not listed a second time under the entries. */
  it("list a request an ended entry went out as once, as the entry", () => {
    const entry = to("06:05", "goods", "b.A");
    expect(listRows(loaded({ entry, state: "ended", round: 0, request: "g1" }), [GOODS!])).toEqual([
      { entry, state: "ended" },
    ]);
  });

  it("keep a turn-round as the document has it", () => {
    const turn: Entry = { at: "06:10", train: "goods", turn: true };
    expect(listRows(loaded({ entry: turn, state: "held", round: 0 }), [])).toEqual([
      { entry: turn, state: "held" },
    ]);
  });

  /** The dispatcher serves `express` before `goods`, whatever their entries'
   *  times: the two rows that are out change places and the rest stay. */
  it("keep the requests that are out in the dispatcher's order among themselves", () => {
    const goods = to("06:05", "goods", "b.A");
    const held = to("06:06", "local", "a.A");
    const express = to("06:07", "express", "a.B");
    const rows = listRows(
      loaded(
        { entry: goods, state: "out", round: 0, request: "g1" },
        { entry: held, state: "held", round: 0 },
        { entry: express, state: "out", round: 0, request: "e1" },
      ),
      [EXPRESS!, GOODS!],
    );
    expect(rows).toEqual([
      { entry: express, state: "out", request: EXPRESS },
      { entry: held, state: "held" },
      { entry: goods, state: "out", request: GOODS },
    ]);
  });

  it("are done once ended, rejected, cancelled or skipped", () => {
    const entry = to("06:05", "goods", "b.A");
    const states = ["later", "held", "out", "ended", "rejected", "cancelled", "skipped"] as const;
    expect(states.filter((state) => done({ entry, state }))).toEqual([
      "ended",
      "rejected",
      "cancelled",
      "skipped",
    ]);
    expect(done({ request: GOODS! })).toBe(false);
  });
});

describe("where the list scrolls", () => {
  const goods = to("06:05", "goods", "b.A");
  const local = to("06:30", "local", "c.B");
  const turn: Entry = { at: "06:10", train: "goods", turn: true };

  it("is an entry a drag recorded, out at once", () => {
    const was = loaded({ entry: local, state: "later", round: 0 });
    const now = loaded(
      { entry: goods, state: "out", round: 0, request: "g1" },
      { entry: local, state: "later", round: 0 },
    );
    expect(newest(was, now)).toBe(0);
  });

  it("is a turn-round recorded, ended at once", () => {
    const was = loaded({ entry: goods, state: "ended", round: 0, request: "g1" });
    const now = loaded(
      { entry: goods, state: "ended", round: 0, request: "g1" },
      { entry: turn, state: "ended", round: 0 },
    );
    expect(newest(was, now)).toBe(1);
  });

  it.each(["later", "held"] as const)("is an entry that was %s and went out", (state) => {
    const was = loaded({ entry: goods, state, round: 0 }, { entry: turn, state, round: 0 });
    expect(
      newest(was, loaded({ entry: goods, state: "out", round: 0, request: "g1" }, { entry: turn, state, round: 0 })),
    ).toBe(0);
    expect(
      newest(was, loaded({ entry: goods, state, round: 0 }, { entry: turn, state: "ended", round: 0 })),
    ).toBe(1);
  });

  it("is an entry that went out in a later round", () => {
    const ended = loaded({ entry: goods, state: "ended", round: 0, request: "g1" });
    const again = loaded({ entry: goods, state: "later", round: 1, request: "g1" });
    const out = loaded({ entry: goods, state: "out", round: 1, request: "g2" });
    expect(newest(ended, again)).toBeNull();
    expect(newest(again, out)).toBe(0);
    // The round began and the entry went out between two of the scheduler's rows.
    expect(newest(ended, out)).toBe(0);
  });

  it("is the later in the list of two entries that went out in one row", () => {
    const was = loaded({ entry: goods, state: "held", round: 0 }, { entry: local, state: "later", round: 0 });
    const now = loaded(
      { entry: goods, state: "out", round: 0, request: "g1" },
      { entry: local, state: "out", round: 0, request: "l1" },
    );
    expect(newest(was, now)).toBe(1);
  });

  it.each(["ended", "rejected", "cancelled"] as const)("is none for an entry that is %s", (state) => {
    const was = loaded({ entry: goods, state: "out", round: 0, request: "g1" });
    expect(newest(was, loaded({ entry: goods, state, round: 0, request: "g1" }))).toBeNull();
  });

  /** A drag with Record off is a request no entry went out as: the row the
   *  scheduler says next lists the same entries. */
  it("is none for a request no entry went out as", () => {
    const was = loaded({ entry: goods, state: "ended", round: 0, request: "g1" });
    expect(newest(was, loaded({ entry: goods, state: "ended", round: 0, request: "g1" }))).toBeNull();
  });

  it("is none for an entry changed or deleted", () => {
    const was = loaded(
      { entry: goods, state: "out", round: 0, request: "g1" },
      { entry: turn, state: "ended", round: 0 },
      { entry: local, state: "later", round: 0 },
    );
    const moved = { ...goods, at: "06:20", description: "meets the express" };
    expect(
      newest(
        was,
        loaded(
          { entry: turn, state: "ended", round: 0 },
          { entry: moved, state: "out", round: 0, request: "g1" },
          { entry: { ...local, dwell: 2 }, state: "later", round: 0 },
        ),
      ),
    ).toBeNull();
    expect(newest(was, loaded({ entry: turn, state: "ended", round: 0 }))).toBeNull();
  });

  /** An entry out since the round before is passed over for the entries of
   *  this round that went out before it in the list. */
  it("is the last entry gone out in the highest round when the list is first drawn", () => {
    const now = loaded(
      { entry: to("06:01", "local", "d.A"), state: "ended", round: 1, request: "l1" },
      { entry: goods, state: "out", round: 1, request: "g1" },
      { entry: to("06:20", "express", "a.B"), state: "out", round: 0, request: "e0" },
      { entry: local, state: "later", round: 1 },
    );
    expect(newest(null, now)).toBe(1);
  });

  it("is none when the list is first drawn with no entry gone out", () => {
    const now = loaded(
      { entry: goods, state: "skipped", round: 0 },
      { entry: turn, state: "held", round: 0 },
      { entry: local, state: "later", round: 0 },
    );
    expect(newest(null, now)).toBeNull();
    expect(newest(null, loaded())).toBeNull();
    expect(newest(loaded(), null)).toBeNull();
  });

  /** The two may list the same entries: what the other timetable's row says
   *  is not compared with this one's. */
  it("is as when first drawn for another timetable loaded", () => {
    const entries: Scheduled[] = [
      { entry: goods, state: "ended", round: 0, request: "g1" },
      { entry: local, state: "ended", round: 0, request: "l1" },
    ];
    expect(newest(loaded(...entries), { ...loaded(...entries), name: "morning" })).toBe(1);
  });
});

/** The dispatcher's list of `requests.test.ts`: `express` underway, `goods`
 *  waiting, `goods` chained after it, `local` waiting. */
const SERVED = requestRows([
  LISTED[0]!,
  LISTED[1]!,
  { id: "g2", train: "goods", depart: null, dest: ["c.B"], after: "g1" },
  LISTED[2]!,
]);

/** Those four in a timetable's list. `local`'s request went out as no entry,
 *  and three entries that are not out stand between the others:
 *
 *      0  06:01  local    ended
 *      1  06:02  express  e1, underway
 *      2  06:03  shunter  later
 *      3  06:05  goods    g1, waiting
 *      4  06:06  goods    g2, waiting, after g1
 *      5  06:30  local    later
 *      6         local    l1, waiting
 */
const EVENING = loaded(
  { entry: to("06:01", "local", "d.A"), state: "ended", round: 0, request: "l0" },
  { entry: to("06:02", "express", "a.B"), state: "out", round: 0, request: "e1" },
  { entry: to("06:03", "shunter", "c.A"), state: "later", round: 0 },
  { entry: to("06:05", "goods", "b.A"), state: "out", round: 0, request: "g1" },
  { entry: to("06:06", "goods", "c.B"), state: "out", round: 0, request: "g2" },
  { entry: to("06:30", "local", "c.B"), state: "later", round: 0 },
);

const MIXED = listRows(EVENING, SERVED);

describe("a drag in a timetable's list", () => {
  it("names the first waiting request from where the row is let go", () => {
    expect(moving(MIXED, SERVED, "l1", 3)).toEqual({ before: "g1" });
    // Above the entries too: the first waiting request below is `g1`.
    expect(moving(MIXED, SERVED, "l1", 0)).toEqual({ before: "g1" });
    expect(moving(MIXED, SERVED, "l1", 2)).toEqual({ before: "g1" });
  });

  it("names null where no waiting request is below", () => {
    expect(moving(MIXED, SERVED, "g2", MIXED.length)).toEqual({ before: null });
  });

  it("asks nothing where the row is let go where it was, or among the entries round it", () => {
    expect(moving(MIXED, SERVED, "g1", 2)).toBeNull();
    expect(moving(MIXED, SERVED, "g1", 3)).toBeNull();
    expect(moving(MIXED, SERVED, "g1", 4)).toBeNull();
    expect(moving(MIXED, SERVED, "l1", 5)).toBeNull();
  });

  it("keeps the rule of the request list: no underway row, no chained row above its own", () => {
    expect(moving(MIXED, SERVED, "e1", MIXED.length)).toBeNull();
    expect(moving(MIXED, SERVED, "g2", 0)).toBeNull();
    expect(moving(MIXED, SERVED, "g1", MIXED.length)).toBeNull();
  });

  /** An entry that is not out has no request, so there is nothing to name. */
  it("asks nothing for a row that is no request", () => {
    expect(moving(MIXED, SERVED, "l0", 6)).toBeNull();
  });

  it("asks what the request list asks where no timetable is loaded", () => {
    const rows = listRows(null, SERVED);
    for (const { id } of SERVED) {
      for (let at = 0; at <= SERVED.length; at += 1) {
        expect(moving(rows, SERVED, id, at)).toEqual(reordering(SERVED, id, at));
      }
    }
  });
});

/** The list, holding the timetable and the requests it was handed, live. */
async function list(
  timetable: Timetable | null,
  requests: readonly RequestRow[] = [],
): Promise<TcRequests> {
  const element = document.createElement("tc-requests");
  element.timetable = timetable;
  element.requests = requests;
  element.live = true;
  document.body.append(element);
  await element.updateComplete;
  return element;
}

/** The heading's words: the title, and the name beside it where one is. */
function heading(element: TcRequests): (string | null)[] {
  const header = element.renderRoot.querySelector("header")!;
  return ["h2", ".name"].map((part) => header.querySelector(part)?.textContent!.trim() ?? null);
}

describe("tc-requests with a timetable", () => {
  afterEach(() => {
    document.body.replaceChildren();
  });

  it("is headed Timetable and the loaded timetable's name", async () => {
    expect(heading(await list(loaded()))).toEqual(["Timetable", "evening"]);
  });

  it("is headed Timetable alone where none is loaded", async () => {
    expect(heading(await list(null, SERVED))).toEqual(["Timetable", null]);
  });

  it("heads its columns as the request list does (#1393)", async () => {
    const element = await list(EVENING, SERVED);
    const headings = [...element.renderRoot.querySelectorAll(".columns > *")];
    expect(headings.map((cell) => cell.textContent!.trim())).toEqual([
      "Time",
      "Train",
      "To",
      "Dwell",
      "Description",
      "State",
      "",
    ]);
  });

  it("draws each entry's time, train, destination and state, an out one as its request", async () => {
    const element = await list(EVENING, SERVED);
    expect(drawn(element)).toEqual([
      ["06:01", "local", "→ d.A", "ended"],
      ["06:02", "express", "c.A → a.B", "underway"],
      ["06:03", "shunter", "→ c.A", "later"],
      ["06:05", "goods", "a.B → b.A", "waiting"],
      ["06:06", "goods", "b.A → c.B", "waiting"],
      ["06:30", "local", "→ c.B", "later"],
      ["", "local", "d.A → b.B, c.B", "waiting"],
    ]);
  });

  it("draws turn for a turn-round's destination", async () => {
    const turn: Entry = { at: "06:10", train: "goods", turn: true };
    const element = await list(loaded({ entry: turn, state: "held", round: 0 }));
    expect(drawn(element)).toEqual([["06:10", "goods", "turn", "held"]]);
  });

  it("says no entries for a timetable with none, and no requests", async () => {
    const element = await list(loaded());
    expect(element.renderRoot.querySelector(".table > .hint")!.textContent!.trim()).toBe(
      "no entries",
    );
    expect(element.renderRoot.querySelectorAll(".columns > *")).toHaveLength(7);
  });

  it.each(["ended", "rejected", "cancelled", "skipped"] as const)(
    "dims a row that is %s",
    async (state) => {
      const element = await list(
        loaded(
          { entry: to("06:01", "local", "d.A"), state, round: 0 },
          { entry: to("06:02", "local", "c.B"), state: "held", round: 0 },
        ),
      );
      const rows = [...element.renderRoot.querySelectorAll("li")];
      expect(rows.map((row) => row.classList.contains("done"))).toEqual([true, false]);
      expect(rows[0]!.querySelector(".state")!.textContent!.trim()).toBe(state);
    },
  );

  it("dims no row that is later, held or out, and no request", async () => {
    const element = await list(EVENING, SERVED);
    const rows = [...element.renderRoot.querySelectorAll("li")];
    expect(rows.map((row) => row.classList.contains("done"))).toEqual([
      true,
      false,
      false,
      false,
      false,
      false,
      false,
    ]);
    expect(rule(requestsStyles.cssText, "li.done")).toMatch(/opacity:\s*0\.\d+/);
  });

  /** What the row of a request has today (`requests.test.ts`). */
  describe("an out entry's row", () => {
    it("has the cancel, and raises it with the request's id", async () => {
      const element = await list(EVENING, SERVED);
      const seen: string[] = [];
      element.addEventListener("request-cancelled", (event) =>
        seen.push((event as CustomEvent<{ id: string }>).detail.id),
      );
      const rows = [...element.renderRoot.querySelectorAll("li")];
      expect(rows.map((row) => row.querySelector(".cancel") !== null)).toEqual([
        false,
        true,
        false,
        true,
        true,
        false,
        true,
      ]);
      rows[3]!.querySelector<HTMLButtonElement>(".cancel")!.click();
      expect(seen).toEqual(["g1"]);
    });

    it("has the line that says which train it waits for", async () => {
      const waits = { ...SERVED[1]!, note: ["waits for express to pass"] };
      const element = await list(EVENING, [SERVED[0]!, waits, SERVED[2]!, SERVED[3]!]);
      const rows = [...element.renderRoot.querySelectorAll("li")];
      expect(rows.map((row) => row.querySelector(".note")?.textContent!.trim() ?? null)).toEqual([
        null,
        null,
        null,
        "waits for express to pass",
        null,
        null,
        null,
      ]);
    });

    it("has arrived while it is underway and the railroad runs without sensors", async () => {
      const element = await list(EVENING, SERVED);
      element.arrivable = true;
      await element.updateComplete;
      const seen: string[] = [];
      element.addEventListener("request-arrived", (event) =>
        seen.push((event as CustomEvent<{ id: string }>).detail.id),
      );
      const buttons = element.renderRoot.querySelectorAll<HTMLButtonElement>(".arrived");
      expect(buttons).toHaveLength(1);
      buttons[0]!.click();
      expect(seen).toEqual(["e1"]);
    });
  });

  describe("a drag", () => {
    /** A press on the row at `at`, and the rows then picked up. */
    async function pressed(element: TcRequests, at: number): Promise<number> {
      element.renderRoot
        .querySelectorAll("li")
        [at]!.dispatchEvent(new PointerEvent("pointerdown", { button: 0, bubbles: true }));
      await element.updateComplete;
      return element.renderRoot.querySelectorAll("li.held").length;
    }

    it("picks up a waiting request, with an entry or without", async () => {
      const element = await list(EVENING, SERVED);
      const rows = [...element.renderRoot.querySelectorAll("li")];
      expect(rows.map((row) => row.classList.contains("still"))).toEqual([
        true,
        true,
        true,
        false,
        false,
        true,
        false,
      ]);
      expect(await pressed(element, 3)).toBe(1);
    });

    it("does not pick up an entry that is not out", async () => {
      const element = await list(EVENING, SERVED);
      expect(await pressed(element, 2)).toBe(0);
      expect(await pressed(element, 0)).toBe(0);
    });

    /** `held` is an entry's state and also the mark of a row picked up. */
    it("does not draw an entry that is held as picked up", async () => {
      const element = await list(loaded({ entry: to("06:05", "goods", "b.A"), state: "held", round: 0 }));
      expect(element.renderRoot.querySelectorAll("li.held")).toHaveLength(0);
    });

    it("raises a move by the place in the list, and nothing for a refused one", async () => {
      const element = await list(EVENING, SERVED);
      const seen: RequestReorder[] = [];
      element.addEventListener("request-reordered", (event) =>
        seen.push((event as CustomEvent<RequestReorder>).detail),
      );
      element.move("l1", 3);
      element.move("g2", 0);
      element.move("e1", 7);
      expect(seen).toEqual([{ id: "l1", before: "g1" }]);
    });
  });

  /** happy-dom lays nothing out, so these watch which row is asked to scroll
   *  into view. */
  describe("where it scrolls", () => {
    let asked: Element[];

    beforeEach(() => {
      asked = [];
      vi.spyOn(Element.prototype, "scrollIntoView").mockImplementation(function (
        this: Element,
      ) {
        asked.push(this);
      });
    });

    afterEach(() => {
      vi.restoreAllMocks();
    });

    const gone = to("06:01", "local", "d.A");
    const next = to("06:05", "goods", "b.A");
    const last = to("06:30", "local", "c.B");

    /** The time drawn on each row asked to scroll into view. */
    function times(): (string | null)[] {
      return asked.map((row) => row.querySelector(".time")?.textContent ?? null);
    }

    it("is scrolled to the entry that went out last when it is first drawn", async () => {
      await list(
        loaded(
          { entry: gone, state: "ended", round: 0, request: "l0" },
          { entry: next, state: "out", round: 0, request: "g1" },
          { entry: last, state: "later", round: 0 },
        ),
      );
      expect(times()).toEqual(["06:05"]);
    });

    it("is not scrolled when it is first drawn with no entry gone out", async () => {
      await list(loaded({ entry: next, state: "held", round: 0 }, { entry: last, state: "later", round: 0 }));
      expect(asked).toEqual([]);
    });

    it("is scrolled to each entry that goes out, and not for one that ends", async () => {
      const element = await list(
        loaded({ entry: gone, state: "ended", round: 0, request: "l0" }, { entry: next, state: "held", round: 0 }),
      );
      element.timetable = loaded(
        { entry: gone, state: "ended", round: 0, request: "l0" },
        { entry: next, state: "out", round: 0, request: "g1" },
      );
      await element.updateComplete;
      element.timetable = loaded(
        { entry: gone, state: "ended", round: 0, request: "l0" },
        { entry: next, state: "ended", round: 0, request: "g1" },
      );
      await element.updateComplete;
      element.requests = SERVED;
      await element.updateComplete;
      expect(times()).toEqual(["06:01", "06:05"]);
    });

    it("is scrolled to an entry a drag recorded", async () => {
      const element = await list(loaded({ entry: next, state: "later", round: 0 }));
      element.timetable = loaded(
        { entry: next, state: "later", round: 0 },
        { entry: last, state: "out", round: 0, request: "l1" },
      );
      await element.updateComplete;
      expect(times()).toEqual(["06:30"]);
    });

    it("is scrolled for a timetable that arrives after the list was drawn", async () => {
      const element = await list(null, SERVED);
      expect(asked).toEqual([]);
      element.timetable = loaded({ entry: gone, state: "ended", round: 0 }, { entry: last, state: "ended", round: 0 });
      await element.updateComplete;
      expect(times()).toEqual(["06:30"]);
    });

    it("is scrolled again for another timetable", async () => {
      const element = await list(loaded({ entry: gone, state: "ended", round: 0 }, { entry: next, state: "held", round: 0 }));
      expect(times()).toEqual(["06:01"]);
      asked.length = 0;
      element.timetable = { ...loaded({ entry: last, state: "ended", round: 0 }), name: "morning" };
      await element.updateComplete;
      expect(times()).toEqual(["06:30"]);
    });

    it("is not scrolled to an entry that goes out while a row is open", async () => {
      const element = await list(loaded({ entry: next, state: "held", round: 0 }, { entry: last, state: "later", round: 0 }));
      element.renderRoot.querySelectorAll("li")[1]!.click();
      await element.updateComplete;
      asked.length = 0;
      element.timetable = loaded(
        { entry: next, state: "out", round: 0, request: "g1" },
        { entry: last, state: "later", round: 0 },
      );
      await element.updateComplete;
      expect(asked).toEqual([]);
      // Nor once it closes: the entry went out while it was open.
      element.renderRoot.querySelectorAll("li")[1]!.click();
      await element.updateComplete;
      element.timetable = loaded(
        { entry: next, state: "out", round: 0, request: "g1" },
        { entry: last, state: "later", round: 0 },
      );
      await element.updateComplete;
      expect(asked).toEqual([]);
    });

    /** The heading has Start, the Record switch and the menu, and a row
     *  scrolled to the top of what scrolls took it out of view. The rows are
     *  what scrolls: the list is a column, the heading keeps its height and
     *  the rows take what is left. */
    it("scrolls its rows under the heading, which stays in view", async () => {
      const element = await list(loaded({ entry: gone, state: "ended", round: 0 }, { entry: next, state: "held", round: 0 }));
      const scrolled = element.renderRoot.querySelector(".table")!;
      expect(scrolled.querySelector("header")).toBeNull();
      expect(asked.every((row) => scrolled.contains(row))).toBe(true);

      const sheet = requestsStyles.cssText;
      const host = /:host \{([^}]*)\}/.exec(sheet)![1]!;
      expect(host).toMatch(/display:\s*flex/);
      expect(host).toMatch(/flex-direction:\s*column/);
      const rows = rule(sheet, ".table");
      expect(rows).toMatch(/overflow-y:\s*auto/);
      expect(rows).toMatch(/min-height:\s*0/);
      expect(/^\s*header \{([^}]*)\}/m.exec(sheet)![1]!).toMatch(/flex:\s*none/);
    });
  });

  describe("an entry's dwell and description", () => {
    const meets: Entry = { ...to("06:05", "goods", "b.A"), dwell: 2, description: "meets the express" };

    /** Each row's dwell and description as its markup has them. */
    function more(element: TcRequests): (string | null)[][] {
      return [...element.renderRoot.querySelectorAll("li")].map((row) =>
        [".dwell", ".description"].map(
          (part) => row.querySelector(part)?.textContent!.trim() ?? null,
        ),
      );
    }

    it("are in the row's markup, out as a request or not", async () => {
      const element = await list(
        loaded(
          { entry: { ...meets, at: "06:01" }, state: "ended", round: 0 },
          { entry: meets, state: "out", round: 0, request: "g1" },
          { entry: to("06:30", "local", "c.B"), state: "later", round: 0 },
        ),
        SERVED,
      );
      expect(more(element).slice(0, 3)).toEqual([
        ["2 min", "meets the express"],
        ["2 min", "meets the express"],
        ["", ""],
      ]);
    });

    /** Their headings with them, and the table has their columns only
     *  there (#1393). */
    it("are shown where the list is 34rem wide or more, and not below that", () => {
      const sheet = requestsStyles.cssText;
      expect(rule(sheet, ":host")).toMatch(/container-type:\s*inline-size/);
      expect(sheet).not.toContain("24rem");
      const [narrow, wide] = sheet.split("@container (min-width: 34rem)");
      expect(narrow).toMatch(/\.dwell,\s*\.description \{[^}]*display:\s*none/);
      expect(rule(narrow!, ".table")).not.toMatch(/\[dwell\]|\[description\]/);
      expect(wide).toMatch(/\.dwell,\s*\.description \{[^}]*display:\s*block/);
      expect(rule(wide!, ".table")).toMatch(/\[dwell\][^;]*\[description\]/);
    });
  });
});

describe("the run view's list", () => {
  beforeEach(brokering);

  afterEach(unbrokered);

  /** `goods` waits for `express`, as the dispatcher last refused it. */
  const REFUSED: Listed[] = [
    LISTED[0]!,
    {
      ...LISTED[1]!,
      refused: { reason: "unsafe", obstacles: [{ resource: "c", holder: "express" }] },
    },
    LISTED[2]!,
  ];

  /** `local` has been and gone, `express` and `goods` are out, and `local`
   *  goes again at 06:30. Its request `l1` went out as no entry. */
  const RUNNING = {
    timetable: "evening",
    phase: "running",
    record: false,
    start: "06:00",
    repeat: "1d00:00",
    trains: { goods: { at: "a", facing: "A-to-B" } },
    positioning: [],
    entries: [
      { at: "06:01", train: "local", to: ["d.A"], state: "ended", round: 0, request: "l0", ended: 21_655 },
      { at: "06:02", train: "express", to: ["a.B"], state: "out", round: 0, request: "e1" },
      { at: "06:05", train: "goods", to: ["b.A"], dwell: 2, state: "out", round: 0, request: "g1" },
      { at: "06:30", train: "local", to: ["c.B"], state: "later", round: 0 },
    ],
  };

  /** A joined session whose picture holds `REFUSED`. */
  async function serving(): Promise<{ shell: TcApp; element: TcRequests }> {
    const shell = await joined();
    await said(shell, ALLOCATION, {
      trains: { goods: "a", express: "c", local: "d" },
      occupied: { goods: ["a"], express: ["c"], local: ["d"] },
      locks: { a: "goods" },
      requests: REFUSED,
    });
    await settled(shell);
    const element = running(shell).renderRoot.querySelector("tc-requests")!;
    return { shell, element };
  }

  const REQUESTS = [
    ["", "express", "c.A → a.B", "underway"],
    ["", "goods", "a.B → b.A", "waiting"],
    ["", "local", "d.A → b.B, c.B", "waiting"],
  ];

  it("is headed Timetable alone and lists the requests before the scheduler has said", async () => {
    const { element } = await serving();
    expect(heading(element)).toEqual(["Timetable", null]);
    expect(drawn(element)).toEqual(REQUESTS);
  });

  it("lists the timetable the scheduler says is loaded, under its name", async () => {
    const { shell, element } = await serving();
    await said(shell, TIMETABLE, RUNNING);
    expect(heading(element)).toEqual(["Timetable", "evening"]);
    expect(drawn(element)).toEqual([
      ["06:01", "local", "→ d.A", "ended"],
      ["06:02", "express", "c.A → a.B", "underway"],
      ["06:05", "goods", "a.B → b.A", "waiting"],
      ["06:30", "local", "→ c.B", "later"],
      ["", "local", "d.A → b.B, c.B", "waiting"],
    ]);
  });

  it("lists an entry after midnight at its time in the time form", async () => {
    const { shell, element } = await serving();
    const late = { at: "1d01:00", train: "local", to: ["c.B"], state: "later", round: 0 };
    await said(shell, TIMETABLE, { ...RUNNING, entries: [...RUNNING.entries, late] });
    expect(drawn(element).slice(3, 5)).toEqual([
      ["06:30", "local", "→ c.B", "later"],
      ["1d01:00", "local", "→ c.B", "later"],
    ]);
  });

  /** The retained rows arrive in no fixed order. */
  it("lists it where the scheduler's row came before the dispatcher's picture", async () => {
    const shell = await joined();
    await said(shell, TIMETABLE, RUNNING);
    const element = running(shell).renderRoot.querySelector("tc-requests")!;
    expect(drawn(element).map(([time, , , state]) => [time, state])).toEqual([
      ["06:01", "ended"],
      ["06:02", "out"],
      ["06:05", "out"],
      ["06:30", "later"],
    ]);
  });

  it("keeps the waits-for line and the cancel on an out entry's row", async () => {
    const { shell, element } = await serving();
    await said(shell, TIMETABLE, RUNNING);
    const goods = element.renderRoot.querySelectorAll("li")[2]!;
    expect(goods.querySelector(".note")!.textContent!.trim()).toBe("waits for express to pass");
    goods.querySelector<HTMLButtonElement>(".cancel")!.click();
    expect(written()).toEqual([
      { topic: "tc49/dispatch/cancel_wanted", payload: { id: "g1" } },
    ]);
  });

  it("writes one reorder_wanted for a waiting row let go above an out entry", async () => {
    const { shell, element } = await serving();
    await said(shell, TIMETABLE, RUNNING);
    element.move("l1", 2);
    expect(written()).toEqual([
      { topic: "tc49/dispatch/reorder_wanted", payload: { id: "l1", before: "g1" } },
    ]);
  });

  it("lists the requests again once the row says no timetable is loaded", async () => {
    const { shell, element } = await serving();
    await said(shell, TIMETABLE, RUNNING);
    await said(shell, TIMETABLE, { timetable: null });
    expect(heading(element)).toEqual(["Timetable", null]);
    expect(drawn(element)).toEqual(REQUESTS);
  });
});

/** What the list draws, a row at a time: its time, where it has one, its
 *  train, where it goes and its state. */
function drawn(element: TcRequests): (string | null)[][] {
  return [...element.renderRoot.querySelectorAll("li")].map((row) =>
    [".time", ".train", ".way", ".state"].map(
      (part) => row.querySelector(part)?.textContent!.trim() ?? null,
    ),
  );
}

/** The declarations of the rule for `selector`, at the start of a line. */
function rule(sheet: string, selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`^\\s*${escaped} \\{([^}]*)\\}`, "m").exec(sheet)![1]!;
}
