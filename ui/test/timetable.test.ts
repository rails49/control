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

import { describe, expect, it } from "vitest";

import { reordering, requestRows, type Listed } from "../src/model/requests.js";
import {
  done,
  listRows,
  moving,
  opening,
  timetableOf,
  type Entry,
  type Scheduled,
  type Timetable,
} from "../src/model/timetable.js";

/** The row as BUS.md gives it: `goods` went to `b` and turned round, and
 *  goes on to `c` once the clock reads 06:12. */
const SAID = {
  timetable: "evening",
  phase: "running",
  record: false,
  start: "06:00",
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
      request: "g1",
      ended: 190,
    },
    { at: "06:10", train: "goods", turn: true, state: "ended" },
    { at: "06:12", train: "goods", to: ["c.B"], state: "later" },
  ],
  at: 12.5,
};

describe("the timetable row", () => {
  it("is read whole, each entry's document fields apart from what became of it", () => {
    expect(timetableOf(SAID)).toEqual({
      name: "evening",
      phase: "running",
      record: false,
      start: "06:00",
      trains: { goods: { at: "a", facing: "A-to-B" } },
      positioning: ["p1"],
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
          request: "g1",
          ended: 190,
        },
        { entry: { at: "06:10", train: "goods", turn: true }, state: "ended" },
        { entry: { at: "06:12", train: "goods", to: ["c.B"] }, state: "later" },
      ],
    });
  });

  it("reads null where no timetable is loaded", () => {
    expect(timetableOf({ timetable: null, at: 3 })).toBeNull();
  });

  it.each([
    ["no name", { ...SAID, timetable: 7 }],
    ["a phase outside the three", { ...SAID, phase: "paused" }],
    ["no entries", { ...SAID, entries: undefined }],
    ["an entry in no known state", { ...SAID, entries: [{ ...SAID.entries[2], state: "lost" }] }],
    ["an entry with neither to nor turn", { ...SAID, entries: [{ at: "06:02", train: "goods", state: "later" }] }],
    ["an entry with no train", { ...SAID, entries: [{ at: "06:02", to: ["b.A"], state: "later" }] }],
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
    start: "06:00",
    trains: {},
    positioning: [],
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
      { entry: to("06:01", "express", "a.B"), state: "ended", request: "e0", ended: 60 },
      { entry: to("06:02", "local", "b.B"), state: "rejected", request: "l0" },
      { entry: to("06:03", "goods", "b.A"), state: "cancelled", request: "g0" },
      { entry: to("06:04", "shunter", "c.A"), state: "skipped" },
      { entry: to("06:05", "goods", "b.A"), state: "out", request: "g1" },
      { entry: to("06:06", "express", "d.A"), state: "held" },
      { entry: to("06:30", "local", "c.B"), state: "later" },
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
    expect(listRows(loaded({ entry, state: "out", request: "g1" }), [])).toEqual([
      { entry, state: "out" },
    ]);
  });

  it("put a request no entry went out as after the entries, in the dispatcher's order", () => {
    const out = to("06:05", "goods", "b.A");
    const later = to("06:30", "goods", "c.B");
    const rows = listRows(
      loaded({ entry: out, state: "out", request: "g1" }, { entry: later, state: "later" }),
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
    expect(listRows(loaded({ entry, state: "ended", request: "g1" }), [GOODS!])).toEqual([
      { entry, state: "ended" },
    ]);
  });

  it("keep a turn-round as the document has it", () => {
    const turn: Entry = { at: "06:10", train: "goods", turn: true };
    expect(listRows(loaded({ entry: turn, state: "held" }), [])).toEqual([
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
        { entry: goods, state: "out", request: "g1" },
        { entry: held, state: "held" },
        { entry: express, state: "out", request: "e1" },
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

describe("where the list opens", () => {
  const entry = to("06:05", "goods", "b.A");

  it("is the first row that is not done", () => {
    expect(
      opening([
        { entry, state: "ended" },
        { entry, state: "skipped" },
        { entry, state: "held" },
        { entry, state: "cancelled" },
        { entry, state: "later" },
      ]),
    ).toBe(2);
  });

  it("is a request no entry went out as where every entry is done", () => {
    expect(opening([{ entry, state: "ended" }, { request: GOODS! }])).toBe(1);
  });

  it("is nowhere where every row is done, or there is none", () => {
    expect(opening([{ entry, state: "ended" }])).toBeNull();
    expect(opening([])).toBeNull();
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
const MIXED = listRows(
  loaded(
    { entry: to("06:01", "local", "d.A"), state: "ended", request: "l0" },
    { entry: to("06:02", "express", "a.B"), state: "out", request: "e1" },
    { entry: to("06:03", "shunter", "c.A"), state: "later" },
    { entry: to("06:05", "goods", "b.A"), state: "out", request: "g1" },
    { entry: to("06:06", "goods", "c.B"), state: "out", request: "g2" },
    { entry: to("06:30", "local", "c.B"), state: "later" },
  ),
  SERVED,
);

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
