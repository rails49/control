// @vitest-environment happy-dom

/**
 * An entry's row opened in the list under the roster: its time, its arrival
 * ends, its dwell, its description and a Delete
 * ([#1345](https://github.com/rails49/control/issues/1345),
 * [#1358](https://github.com/rails49/control/issues/1358),
 * [#1386](https://github.com/rails49/control/issues/1386)).
 *
 * Four parts. What a typed field makes of an entry, and which row is open,
 * are `model/timetable.ts`'s. Then `tc-entry`, the open row, which draws the
 * fields and raises what a person changed. Then `tc-requests`, which draws
 * the open row and keeps its fields. Then the run view, which writes one
 * `entry_wanted` for each change.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../src/ui/tc-app.js";
import "../src/ui/tc-entry.js";
import "../src/ui/tc-requests.js";
import { requestRows } from "../src/model/requests.js";
import {
  asking,
  edited,
  followed,
  misnamed,
  placeOf,
  same,
  tapped,
  type Entry,
  type Field,
  type ListRow,
  type Opened,
  type Scheduled,
  type Timetable,
} from "../src/model/timetable.js";
import type { TcApp } from "../src/ui/tc-app.js";
import type { EntryChange, TcEntry } from "../src/ui/tc-entry.js";
import type { TcRequests } from "../src/ui/tc-requests.js";
import { requestsStyles } from "../src/ui/tc-requests.styles.js";
import { running } from "./support/shell.js";
import { brokering, joined, said, unbrokered, written } from "./support/session.js";

/** `goods` to `b.A` at 06:02, standing two minutes there. */
const GOODS: Entry = {
  at: "06:02",
  train: "goods",
  to: ["b.A"],
  dwell: 2,
  description: "meets the express",
};

/** An entry with no dwell and no description. */
const BARE: Entry = { at: "06:30", train: "local", to: ["c.B"] };

/** A turn-round. */
const TURN: Entry = { at: "06:10", train: "goods", turn: true };

describe("an entry with a field typed", () => {
  it("has a time typed as HH:MM, day 0 said without its day", () => {
    expect(edited(GOODS, "at", "06:10")).toEqual({ ...GOODS, at: "06:10" });
    expect(edited(GOODS, "at", "0d06:10")).toEqual({ ...GOODS, at: "06:10" });
    expect(edited(GOODS, "at", " 23:59 ")).toEqual({ ...GOODS, at: "23:59" });
  });

  it("keeps the day of a time typed with one", () => {
    expect(edited(GOODS, "at", "1d06:10")).toEqual({ ...GOODS, at: "1d06:10" });
  });

  it.each(["", "soon", "0610", "6:10", "24:00", "06:60"])("is not changed by %j, which is no time", (words) => {
    expect(edited(GOODS, "at", words)).toBeNull();
  });

  it("is not changed by the time it has", () => {
    expect(edited(GOODS, "at", "06:02")).toBeNull();
  });

  it("has a dwell typed as whole minutes", () => {
    expect(edited(GOODS, "dwell", "5")).toEqual({ ...GOODS, dwell: 5 });
    expect(edited(BARE, "dwell", " 3 ")).toEqual({ ...BARE, dwell: 3 });
  });

  /** A dwell of 0 is the key left out (BUS.md). */
  it.each(["0", ""])("has no dwell with %j typed", (words) => {
    expect(edited(GOODS, "dwell", words)).toEqual({
      at: "06:02",
      train: "goods",
      to: ["b.A"],
      description: "meets the express",
    });
  });

  it.each(["-1", "1.5", "two", "1e2"])("is not changed by a dwell of %j", (words) => {
    expect(edited(GOODS, "dwell", words)).toBeNull();
  });

  it("is not changed by the dwell it has, 0 where it has none", () => {
    expect(edited(GOODS, "dwell", "2")).toBeNull();
    expect(edited(BARE, "dwell", "0")).toBeNull();
    expect(edited({ ...BARE, dwell: 0 }, "dwell", "")).toBeNull();
  });

  /** A turn-round has no dwell, and the scheduler drops one that has. */
  it("is given no dwell where it is a turn-round", () => {
    expect(edited(TURN, "dwell", "2")).toBeNull();
  });

  it("has a description typed, the space round it dropped", () => {
    expect(edited(BARE, "description", " via the loop ")).toEqual({
      ...BARE,
      description: "via the loop",
    });
    expect(edited(TURN, "description", "runs round")).toEqual({
      ...TURN,
      description: "runs round",
    });
  });

  it("has no description once it is emptied", () => {
    expect(edited(GOODS, "description", " ")).toEqual({
      at: "06:02",
      train: "goods",
      to: ["b.A"],
      dwell: 2,
    });
  });

  it("is not changed by the description it has, or by none where it has none", () => {
    expect(edited(GOODS, "description", "meets the express")).toBeNull();
    expect(edited(BARE, "description", "")).toBeNull();
  });

  it("has its arrival ends typed: a block, or a block with an end", () => {
    expect(edited(GOODS, "to", "c")).toEqual({ ...GOODS, to: ["c"] });
    expect(edited(GOODS, "to", "c.B")).toEqual({ ...GOODS, to: ["c.B"] });
  });

  it("has several arrival ends in the order typed, the space round each dropped", () => {
    expect(edited(GOODS, "to", " dn_e ,up_e.B,  c.A ")).toEqual({
      ...GOODS,
      to: ["dn_e", "up_e.B", "c.A"],
    });
  });

  it("is not changed by the arrival ends it has", () => {
    expect(edited(GOODS, "to", "b.A")).toBeNull();
    expect(edited({ ...GOODS, to: ["b", "c.A"] }, "to", "b, c.A")).toBeNull();
  });

  /** `misnamed` says why such ends are refused. */
  it.each([
    ["", []],
    [" , ", []],
    ["b.C", ["b.C"]],
    ["b, b.A", ["b", "b.A"]],
  ])("has the arrival ends typed as %j, good or not", (words, to) => {
    expect(edited(GOODS, "to", words)).toEqual({ ...GOODS, to });
  });

  /** A turn-round has no arrival ends to change. */
  it("is given no arrival ends where it is a turn-round", () => {
    expect(edited(TURN, "to", "b")).toBeNull();
  });
});

describe("arrival ends typed", () => {
  const BLOCKS = ["a", "b", "dn_e", "up_e"];

  it.each(["a", "b.A", "dn_e, up_e.B", " a.B ,b ", "a, b,"])("are good as %j", (words) => {
    expect(misnamed(BLOCKS, words)).toBeNull();
  });

  it.each(["", "  ", " , "])("are refused as none for %j", (words) => {
    expect(misnamed(BLOCKS, words)).toBe("no arrival end");
  });

  it.each([
    ["b.C", "b.C: the end is A or B"],
    ["a, b.", "b.: the end is A or B"],
    ["a.a", "a.a: the end is A or B"],
  ])("are refused for an end other than A or B in %j", (words, why) => {
    expect(misnamed(BLOCKS, words)).toBe(why);
  });

  it("are refused for a block the railroad does not have, named", () => {
    expect(misnamed(BLOCKS, "a, dn_w.A")).toBe("the railroad has no block dn_w");
    expect(misnamed([], "a")).toBe("the railroad has no block a");
  });

  it.each([
    ["dn_e, dn_e", "dn_e"],
    ["dn_e, dn_e.A", "dn_e"],
    ["up_e.A, a, up_e.B", "up_e"],
    ["b.B, b", "b"],
  ])("are refused for a block named twice in %j, named", (words, block) => {
    expect(misnamed(BLOCKS, words)).toBe(`${block} is named twice`);
  });
});

describe("two entries", () => {
  it("are the same with every field of the document equal", () => {
    expect(same(GOODS, { ...GOODS, to: ["b.A"] })).toBe(true);
    expect(same(TURN, { ...TURN })).toBe(true);
  });

  it("are the same where one leaves out a dwell of 0 or an empty description", () => {
    expect(same(BARE, { ...BARE, dwell: 0, description: "" })).toBe(true);
  });

  it.each([
    ["time", { at: "06:03" }],
    ["train", { train: "local" }],
    ["arrival ends", { to: ["b.A", "c.B"] }],
    ["dwell", { dwell: 3 }],
    ["description", { description: "" }],
  ])("are not the same with another %s", (_, other) => {
    expect(same(GOODS, { ...GOODS, ...other })).toBe(false);
  });

  it("are not the same where one is a turn-round", () => {
    expect(same(TURN, { at: "06:10", train: "goods", to: ["b.A"] })).toBe(false);
  });
});

describe("the open row", () => {
  const later: Entry = { at: "06:30", train: "local", to: ["c.B"] };

  /** `GOODS`, a turn-round and `later`, in that order. */
  const rows: ListRow[] = [
    { entry: GOODS, state: "ended" },
    { entry: TURN, state: "held" },
    { entry: later, state: "later" },
  ];

  const open = (entry: Entry, sent: Entry | null = null): Opened => ({ entry, sent });

  it("is the row tapped", () => {
    expect(tapped(null, TURN)).toEqual(open(TURN));
  });

  it("is none after a second tap on it", () => {
    expect(tapped(open(TURN), { ...TURN })).toBeNull();
  });

  it("is another row after a tap on that one", () => {
    expect(tapped(open(TURN, { ...TURN, at: "06:11" }), later)).toEqual(open(later));
  });

  it("is none once it asked for its entry to be deleted", () => {
    expect(asking(open(later), null)).toBeNull();
  });

  it("keeps what it asked its entry to read", () => {
    const moved = { ...later, at: "06:00" };
    expect(asking(open(later), moved)).toEqual(open(later, moved));
    expect(asking(null, moved)).toBeNull();
  });

  it("stays where new rows list its entry as it read", () => {
    expect(followed(open(later), rows)).toEqual(open(later));
    // The scheduler has not taken the change yet.
    const asked = open(later, { ...later, at: "06:00" });
    expect(followed(asked, rows)).toEqual(asked);
  });

  /** A changed time moves the entry in the scheduler's row, and entries
   *  carry no id. */
  it("is the row that reads as the change asked, once new rows list one", () => {
    const moved = { ...later, at: "06:00" };
    const said: ListRow[] = [
      { entry: moved, state: "held" },
      { entry: GOODS, state: "ended" },
      { entry: TURN, state: "held" },
    ];
    expect(followed(open(later, moved), said)).toEqual(open(moved));
    expect(placeOf(said, moved)).toBe(0);
  });

  it("is none once no row lists its entry", () => {
    expect(followed(open(BARE, null), rows.slice(0, 2))).toBeNull();
    expect(followed(null, rows)).toBeNull();
  });

  /** The scheduler changes the first of two entries that read the same. */
  it("is at the first of two rows whose entries read the same", () => {
    const twice: ListRow[] = [...rows, { entry: { ...TURN }, state: "later" }];
    expect(placeOf(twice, TURN)).toBe(1);
    expect(placeOf(rows, { ...TURN, at: "07:00" })).toBe(-1);
  });
});

/** The blocks of the railroad an open row is on. */
const RAILROAD = ["a", "b", "c"];

/** The open row of `entry`, in a timetable that starts at 06:00 and repeats
 *  each day, or as `repeating` says, on a railroad of `RAILROAD`'s blocks. */
async function opened(
  entry: Entry,
  repeating: { start: number; repeat: number } = { start: 6 * 3600, repeat: 86_400 },
): Promise<TcEntry> {
  const element = document.createElement("tc-entry");
  element.entry = entry;
  element.timetable = repeating;
  element.blocks = RAILROAD;
  document.body.append(element);
  await element.updateComplete;
  return element;
}

/** The field of an open row, `null` where the row has none. */
function field(element: TcEntry, name: Field): HTMLInputElement | null {
  return element.renderRoot.querySelector<HTMLInputElement>(`input.${name}`);
}

/** What each field of an open row shows, `null` for a field it has not. */
function shown(element: TcEntry): (string | null)[] {
  return (["at", "dwell", "description"] as const).map(
    (name) => field(element, name)?.value ?? null,
  );
}

/** `words` typed in a field that is not left: the field has the focus and
 *  the browser says `input` at each key. */
function typing(element: TcEntry, name: Field, words: string): HTMLInputElement {
  const input = field(element, name)!;
  input.focus();
  input.value = words;
  input.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
  return input;
}

/** `words` typed in a field and the field left, or Enter pressed: the
 *  browser says either with `change`. */
async function typed(element: TcEntry, name: Field, words: string): Promise<void> {
  typing(element, name, words).dispatchEvent(new Event("change", { bubbles: true }));
  await element.updateComplete;
}

/** Why the open row refused what was typed, `null` where it says nothing. */
function refusal(element: TcEntry): string | null {
  return element.renderRoot.querySelector(".refused")?.textContent?.trim() ?? null;
}

/** What an open row, or the list round it, has asked since this was called. */
function asked(element: Element): EntryChange[] {
  const seen: EntryChange[] = [];
  element.addEventListener("entry-changed", (event) =>
    seen.push((event as CustomEvent<EntryChange>).detail),
  );
  return seen;
}

describe("tc-entry", () => {
  afterEach(() => {
    document.body.replaceChildren();
  });

  it("shows the entry's time, dwell and description", async () => {
    expect(shown(await opened(GOODS))).toEqual(["06:02", "2", "meets the express"]);
  });

  it("shows a dwell of 0 and no description where the entry has neither", async () => {
    expect(shown(await opened(BARE))).toEqual(["06:30", "0", ""]);
  });

  it("has no dwell field on a turn-round", async () => {
    expect(shown(await opened(TURN))).toEqual(["06:10", null, ""]);
  });

  it.each([
    ["at", "06:10", { ...GOODS, at: "06:10" }],
    ["dwell", "5", { ...GOODS, dwell: 5 }],
    ["description", "meets the local", { ...GOODS, description: "meets the local" }],
  ] as const)("asks for the entry with `%s` changed", async (name, words, now) => {
    const element = await opened(GOODS);
    const seen = asked(element);
    await typed(element, name, words);
    expect(seen).toEqual([{ was: GOODS, now }]);
  });

  it.each([
    ["at", "soon"],
    ["at", ""],
    ["dwell", "-1"],
    ["dwell", "1.5"],
  ] as const)("asks nothing for `%s` typed as %j, and shows what the entry has", async (name, words) => {
    const element = await opened(GOODS);
    const seen = asked(element);
    await typed(element, name, words);
    expect(seen).toEqual([]);
    expect(shown(element)).toEqual(["06:02", "2", "meets the express"]);
  });

  it("asks for a time after midnight within the repeat", async () => {
    const element = await opened(GOODS);
    const seen = asked(element);
    await typed(element, "at", "1d01:00");
    expect(seen).toEqual([{ was: GOODS, now: { ...GOODS, at: "1d01:00" } }]);
    expect(refusal(element)).toBeNull();
  });

  /** The scheduler drops an entry outside the repeat (BUS.md). */
  it.each([
    ["05:00", "before the start 06:00"],
    ["1d06:00", "after the last minute, 1d05:59"],
    ["2d07:00", "after the last minute, 1d05:59"],
  ])("asks nothing for %s, outside the repeat, and says %j", async (words, why) => {
    const element = await opened(GOODS);
    const seen = asked(element);
    await typed(element, "at", words);
    expect(seen).toEqual([]);
    expect(refusal(element)).toBe(why);
    expect(shown(element)).toEqual(["06:02", "2", "meets the express"]);
  });

  it("asks for the first and the last minute of the repeat", async () => {
    const element = await opened(GOODS);
    const seen = asked(element);
    await typed(element, "at", "06:00");
    await typed(element, "at", "1d05:59");
    expect(seen.map(({ now }) => now?.at)).toEqual(["06:00", "1d05:59"]);
  });

  it("names the start and the last minute of the timetable it is in", async () => {
    const element = await opened({ ...GOODS, at: "08:00" }, { start: 7.5 * 3600, repeat: 3 * 3600 });
    await typed(element, "at", "07:00");
    expect(refusal(element)).toBe("before the start 07:30");
    await typed(element, "at", "10:30");
    expect(refusal(element)).toBe("after the last minute, 10:29");
  });

  it("says nothing once a change is asked after a refusal", async () => {
    const element = await opened(GOODS);
    await typed(element, "at", "05:00");
    await typed(element, "at", "06:10");
    expect(refusal(element)).toBeNull();
  });

  it("says nothing for words that are no time", async () => {
    const element = await opened(GOODS);
    await typed(element, "at", "soon");
    expect(refusal(element)).toBeNull();
  });

  it("asks nothing for a field left as it was", async () => {
    const element = await opened(GOODS);
    const seen = asked(element);
    await typed(element, "at", "06:02");
    await typed(element, "dwell", "2");
    await typed(element, "description", "meets the express");
    expect(seen).toEqual([]);
  });

  /** The page changes nothing by itself: the scheduler's row says what the
   *  entry reads (ADR-0035). */
  it("shows what the entry has after a change, until the entry is another", async () => {
    const element = await opened(GOODS);
    await typed(element, "at", "06:10");
    expect(shown(element)).toEqual(["06:02", "2", "meets the express"]);
    element.entry = { ...GOODS, at: "06:10" };
    await element.updateComplete;
    expect(shown(element)).toEqual(["06:10", "2", "meets the express"]);
  });

  /** The scheduler says its row at each change of any entry, and each row
   *  hands this the entry again. */
  it("keeps the words in a field in use when it is handed the entry again", async () => {
    const element = await opened(GOODS);
    const seen = asked(element);
    const input = typing(element, "description", "meets the loc");
    element.entry = { ...GOODS };
    await element.updateComplete;
    expect(input.value).toBe("meets the loc");
    expect(seen).toEqual([]);
  });

  it("shows a change to another field while one is in use, and asks with it", async () => {
    const element = await opened(GOODS);
    const seen = asked(element);
    const input = typing(element, "description", "meets the local");
    const moved = { ...GOODS, at: "06:10" };
    element.entry = moved;
    await element.updateComplete;
    expect(shown(element)).toEqual(["06:10", "2", "meets the local"]);
    input.dispatchEvent(new Event("change", { bubbles: true }));
    expect(seen).toEqual([{ was: moved, now: { ...moved, description: "meets the local" } }]);
  });

  /** The browser says no `change` for words typed and taken out again. */
  it("shows what the entry has in a field left with nothing to ask", async () => {
    const element = await opened(GOODS);
    const input = typing(element, "at", "6:1");
    input.blur();
    await element.updateComplete;
    expect(shown(element)).toEqual(["06:02", "2", "meets the express"]);
    element.entry = { ...GOODS, at: "06:10" };
    await element.updateComplete;
    expect(shown(element)).toEqual(["06:10", "2", "meets the express"]);
  });

  it("asks for the entry to be deleted, without asking the person first", async () => {
    const element = await opened(GOODS);
    const seen = asked(element);
    element.renderRoot.querySelector<HTMLButtonElement>("button.delete")!.click();
    expect(seen).toEqual([{ was: GOODS, now: null }]);
  });

  describe("its To field", () => {
    it("shows the entry's arrival ends, joined by a comma and a space", async () => {
      expect(field(await opened(GOODS), "to")!.value).toBe("b.A");
      expect(field(await opened({ ...GOODS, to: ["b", "c.A"] }), "to")!.value).toBe("b, c.A");
    });

    it("is drawn after the time and before the dwell", async () => {
      const inputs = (await opened(GOODS)).renderRoot.querySelectorAll("input");
      expect([...inputs].map((input) => input.className)).toEqual([
        "at",
        "to",
        "dwell",
        "description",
      ]);
    });

    it("is not drawn on a turn-round", async () => {
      expect(field(await opened(TURN), "to")).toBeNull();
    });

    /** The browser says `change` for a field left and for Enter in it. */
    it("asks for the entry with the arrival ends in the order typed", async () => {
      const element = await opened(GOODS);
      const seen = asked(element);
      await typed(element, "to", " c.B, a ,b");
      expect(seen).toEqual([{ was: GOODS, now: { ...GOODS, to: ["c.B", "a", "b"] } }]);
      expect(refusal(element)).toBeNull();
    });

    it.each(["b.A", " b.A "])("asks nothing for %j, the ends the entry has", async (words) => {
      const element = await opened(GOODS);
      const seen = asked(element);
      await typed(element, "to", words);
      expect(seen).toEqual([]);
      expect(refusal(element)).toBeNull();
    });

    /** The railroad may no longer have a block the entry names. */
    it("asks nothing and refuses nothing for the ends the entry has, spaced otherwise", async () => {
      const entry = { ...GOODS, to: ["z", "b.A"] };
      const element = await opened(entry);
      const seen = asked(element);
      await typed(element, "to", "z,b.A ");
      expect(seen).toEqual([]);
      expect(refusal(element)).toBeNull();
    });

    it.each([
      ["", "no arrival end"],
      ["b.C", "b.C: the end is A or B"],
      ["a, z.A", "the railroad has no block z"],
      ["c, c.A", "c is named twice"],
    ])("asks nothing for %j, says %j under the field, and shows the ends", async (words, why) => {
      const element = await opened(GOODS);
      const seen = asked(element);
      await typed(element, "to", words);
      expect(seen).toEqual([]);
      expect(refusal(element)).toBe(why);
      const line = element.renderRoot.querySelector(".refused")!;
      expect(line.previousElementSibling!.querySelector("input")).toBe(field(element, "to"));
      expect(field(element, "to")!.value).toBe("b.A");
    });

    it("says nothing once the next field is changed", async () => {
      const element = await opened(GOODS);
      await typed(element, "to", "z");
      await typed(element, "description", "meets the local");
      expect(refusal(element)).toBeNull();
    });

    it("keeps the words typed in it when it is handed another entry", async () => {
      const element = await opened(GOODS);
      const seen = asked(element);
      const input = typing(element, "to", "c, a");
      element.entry = { ...GOODS, at: "06:10" };
      await element.updateComplete;
      expect(input.value).toBe("c, a");
      expect(seen).toEqual([]);
    });
  });
});

/** The dispatcher's list: `express` underway, `goods` waiting, and `local`
 *  waiting on a request no entry went out as. */
const SERVED = requestRows([
  { id: "e1", train: "express", depart: "c.A", dest: ["a.B"], route: ["c", "sw.side", "a"] },
  { id: "g1", train: "goods", depart: "a.B", dest: ["b.A"] },
  { id: "l1", train: "local", depart: "d.A", dest: ["b.B", "c.B"] },
]);

const LATER: Entry = BARE;

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

/** The list those requests and this timetable make:
 *
 *      0  06:01  local    ended
 *      1  06:02  express  e1, underway
 *      2  06:02  goods    g1, waiting
 *      3  06:10  goods    turn, held
 *      4  06:30  local    later
 *      5         local    l1, waiting, no entry
 */
const ENTRIES: Scheduled[] = [
  { entry: { at: "06:01", train: "local", to: ["d.A"] }, state: "ended", round: 0, request: "l0" },
  { entry: { at: "06:02", train: "express", to: ["a.B"] }, state: "out", round: 0, request: "e1" },
  { entry: GOODS, state: "out", round: 0, request: "g1" },
  { entry: TURN, state: "held", round: 0 },
  { entry: LATER, state: "later", round: 0 },
];

const EVENING = loaded(...ENTRIES);

/** The list, holding that timetable and those requests, live. */
async function list(timetable: Timetable = EVENING): Promise<TcRequests> {
  const element = document.createElement("tc-requests");
  element.timetable = timetable;
  element.requests = SERVED;
  element.live = true;
  document.body.append(element);
  await element.updateComplete;
  return element;
}

function rows(element: TcRequests): HTMLLIElement[] {
  return [...element.renderRoot.querySelectorAll("li")];
}

/** A tap on the row at `at`: the click a browser makes of a press and its
 *  release. The two are left out. happy-dom lays nothing out, so the release
 *  of a waiting row would read as a drop at the end of the list. */
async function tap(element: TcRequests, at: number): Promise<void> {
  rows(element)[at]!.click();
  await element.updateComplete;
}

/** The open row of each row of the list, `null` for a row that is not open. */
function parts(element: TcRequests): (TcEntry | null)[] {
  return rows(element).map((row) => row.querySelector("tc-entry"));
}

/** The places of the rows that are open. */
function open(element: TcRequests): number[] {
  return parts(element).flatMap((part, at) => (part === null ? [] : [at]));
}

describe("tc-requests with a row tapped", () => {
  afterEach(() => {
    document.body.replaceChildren();
  });

  it("has no row open until one is tapped", async () => {
    expect(open(await list())).toEqual([]);
  });

  it("opens the row with the entry's values", async () => {
    const element = await list();
    await tap(element, 2);
    expect(open(element)).toEqual([2]);
    const part = parts(element)[2]!;
    await part.updateComplete;
    expect(part.entry).toEqual(GOODS);
    expect(shown(part)).toEqual(["06:02", "2", "meets the express"]);
  });

  it.each([
    [0, "ended"],
    [1, "out and underway"],
    [2, "out and waiting"],
    [3, "held"],
    [4, "later"],
  ])("opens row %i, whose entry is %s", async (at) => {
    const element = await list();
    await tap(element, at);
    expect(open(element)).toEqual([at]);
  });

  it("closes the open row at a second tap, and opens another at a tap on it", async () => {
    const element = await list();
    await tap(element, 4);
    await tap(element, 4);
    expect(open(element)).toEqual([]);
    await tap(element, 1);
    await tap(element, 2);
    expect(open(element)).toEqual([2]);
  });

  it("does not open a request no entry went out as", async () => {
    const element = await list();
    await tap(element, 5);
    expect(open(element)).toEqual([]);
  });

  /** The cancel is for the request of this run, and leaves the entry. */
  it.each([
    [1, "e1"],
    [2, "g1"],
  ])("cancels the request of row %i and asks nothing of its entry", async (at, id) => {
    const element = await list();
    const cancelled: string[] = [];
    element.addEventListener("request-cancelled", (event) =>
      cancelled.push((event as CustomEvent<{ id: string }>).detail.id),
    );
    const seen = asked(element);
    rows(element)[at]!.querySelector<HTMLButtonElement>(".cancel")!.click();
    await element.updateComplete;
    expect(cancelled).toEqual([id]);
    expect(seen).toEqual([]);
    expect(open(element)).toEqual([]);
  });

  it("keeps the cancel on an open row", async () => {
    const element = await list();
    await tap(element, 1);
    const cancelled: string[] = [];
    element.addEventListener("request-cancelled", (event) =>
      cancelled.push((event as CustomEvent<{ id: string }>).detail.id),
    );
    rows(element)[1]!.querySelector<HTMLButtonElement>(".cancel")!.click();
    await element.updateComplete;
    expect(cancelled).toEqual(["e1"]);
    expect(open(element)).toEqual([1]);
  });

  /** A row picked up captures the pointer, and a browser may send it the
   *  click that ends the drag. happy-dom lays nothing out: every row's box is
   *  empty at the origin, so a release 40px down is off the row. */
  it("does not open a waiting row that is dragged", async () => {
    const element = await list();
    const row = rows(element)[2]!;
    row.dispatchEvent(new PointerEvent("pointerdown", { button: 0, bubbles: true }));
    row.dispatchEvent(new PointerEvent("pointerup", { clientY: 40, bubbles: true }));
    row.dispatchEvent(new MouseEvent("click", { clientY: 40, bubbles: true }));
    await element.updateComplete;
    expect(open(element)).toEqual([]);
  });

  /** The tap is the click, on every row. Taken from a waiting row's release,
   *  with no click heard on that row, it opened the row above too: under a
   *  finger WebKit sends the click to an element beside it that hears one. */
  it("opens a row at one click, and a waiting row at no release without one", async () => {
    const element = await list();
    const row = rows(element)[2]!;
    row.dispatchEvent(new PointerEvent("pointerdown", { button: 0, bubbles: true }));
    row.dispatchEvent(new PointerEvent("pointerup", { bubbles: true }));
    await element.updateComplete;
    expect(open(element)).toEqual([]);
    row.click();
    await element.updateComplete;
    expect(open(element)).toEqual([2]);
  });

  it("does not pick a waiting row up by a press in its open part", async () => {
    const element = await list();
    await tap(element, 2);
    parts(element)[2]!.dispatchEvent(
      new PointerEvent("pointerdown", { button: 0, bubbles: true, composed: true }),
    );
    await element.updateComplete;
    expect(element.renderRoot.querySelectorAll("li.held")).toHaveLength(0);
  });

  it("does not close the row at a press in its open part", async () => {
    const element = await list();
    for (const at of [2, 4]) {
      await tap(element, at);
      parts(element)[at]!.click();
      await element.updateComplete;
      expect(open(element)).toEqual([at]);
    }
  });

  it("passes on what the open row asks", async () => {
    const element = await list();
    const seen = asked(element);
    await tap(element, 4);
    await typed(parts(element)[4]!, "description", "last train");
    expect(seen).toEqual([{ was: LATER, now: { ...LATER, description: "last train" } }]);
  });

  it("keeps the row open while the scheduler's row changes what became of the entry", async () => {
    const element = await list();
    await tap(element, 4);
    element.timetable = loaded(...ENTRIES.slice(0, 4), { entry: LATER, state: "held", round: 0 });
    await element.updateComplete;
    expect(open(element)).toEqual([4]);
  });

  /** The open part of the row at `at`, drawn, with `words` typed in its
   *  description and the field not left. */
  async function described(
    element: TcRequests,
    at: number,
    words: string,
  ): Promise<{ part: TcEntry; input: HTMLInputElement }> {
    await tap(element, at);
    const part = parts(element)[at]!;
    await part.updateComplete;
    return { part, input: typing(part, "description", words) };
  }

  /** Whether `input` is the field a key would go to. */
  function focused(part: TcEntry, input: HTMLInputElement): boolean {
    return (part.renderRoot as ShadowRoot).activeElement === input;
  }

  /** The scheduler says the row at each change of any entry's state. */
  it("keeps what a person is typing while the scheduler's row changes another entry", async () => {
    const element = await list();
    const seen = asked(element);
    const { part, input } = await described(element, 4, "meets the exp");

    // The express arrives.
    element.timetable = loaded(
      ENTRIES[0]!,
      { ...ENTRIES[1]!, state: "ended" },
      ...ENTRIES.slice(2),
    );
    await element.updateComplete;
    await part.updateComplete;
    expect(open(element)).toEqual([4]);
    expect(parts(element)[4]).toBe(part);
    expect(input.value).toBe("meets the exp");
    expect(focused(part, input)).toBe(true);
    expect(seen).toEqual([]);

    // The field is left: the change asks with the words typed.
    input.dispatchEvent(new Event("change", { bubbles: true }));
    expect(seen).toEqual([{ was: LATER, now: { ...LATER, description: "meets the exp" } }]);
  });

  /** A recorded drag adds an entry, and the open row is one place down. */
  it("keeps the open row's fields and the words in them when an entry is added above it", async () => {
    const element = await list();
    const { part, input } = await described(element, 4, "meets the exp");
    element.timetable = loaded(
      ENTRIES[0]!,
      { entry: { at: "06:01", train: "express", to: ["c.A"] }, state: "ended", round: 0, request: "e0" },
      ...ENTRIES.slice(1),
    );
    await element.updateComplete;
    await part.updateComplete;
    expect(open(element)).toEqual([5]);
    expect(parts(element)[5]).toBe(part);
    expect(input.value).toBe("meets the exp");
    expect(focused(part, input)).toBe(true);
  });

  /** The entry's row becomes its request's row. */
  it("keeps the open row's fields and the words in them when its entry goes out", async () => {
    const element = await list();
    const { part, input } = await described(element, 4, "meets the exp");
    element.timetable = loaded(...ENTRIES.slice(0, 4), {
      entry: LATER,
      state: "out",
      round: 0,
      request: "l1",
    });
    await element.updateComplete;
    await part.updateComplete;
    expect(rows(element)[4]!.dataset.id).toBe("l1");
    expect(open(element)).toEqual([4]);
    expect(parts(element)[4]).toBe(part);
    expect(input.value).toBe("meets the exp");
    expect(focused(part, input)).toBe(true);
  });

  /** A tap that does not take the focus from the field leaves it in use. */
  it("opens another row with its entry's values, whatever is typed in the row before", async () => {
    const element = await list();
    await described(element, 4, "meets the exp");
    await tap(element, 3);
    const part = parts(element)[3]!;
    await part.updateComplete;
    expect(shown(part)).toEqual(["06:10", null, ""]);
  });

  /** Enter in the time field asks for the change and leaves the focus there. */
  it("keeps the open row's fields when a changed time moves its entry", async () => {
    const element = await list();
    await tap(element, 4);
    const part = parts(element)[4]!;
    await part.updateComplete;
    const input = typing(part, "at", "06:00");
    input.dispatchEvent(new Event("change", { bubbles: true }));
    element.timetable = loaded(
      { entry: { ...LATER, at: "06:00" }, state: "held", round: 0 },
      ...ENTRIES.slice(0, 4),
    );
    await element.updateComplete;
    await part.updateComplete;
    expect(open(element)).toEqual([0]);
    expect(parts(element)[0]).toBe(part);
    expect(input.value).toBe("06:00");
    expect(focused(part, input)).toBe(true);
  });

  /** A changed time moves the entry in the scheduler's row, and entries carry
   *  no id: the row is found by what the change asked the entry to read. */
  it("has the row open at the entry's new place when a changed time moves it", async () => {
    const element = await list();
    await tap(element, 4);
    await typed(parts(element)[4]!, "at", "06:00");
    // Nothing has moved: the scheduler has not said so.
    expect(open(element)).toEqual([4]);
    expect(shown(parts(element)[4]!)).toEqual(["06:30", "0", ""]);

    const moved = { ...LATER, at: "06:00" };
    element.timetable = loaded({ entry: moved, state: "held", round: 0 }, ...ENTRIES.slice(0, 4));
    await element.updateComplete;
    expect(open(element)).toEqual([0]);
    const part = parts(element)[0]!;
    await part.updateComplete;
    expect(shown(part)).toEqual(["06:00", "0", ""]);

    // The next change names the entry as the row now lists it.
    const seen = asked(element);
    await typed(part, "dwell", "3");
    expect(seen).toEqual([{ was: moved, now: { ...moved, dwell: 3 } }]);
  });

  it("closes the row at Delete", async () => {
    const element = await list();
    await tap(element, 4);
    parts(element)[4]!.renderRoot.querySelector<HTMLButtonElement>("button.delete")!.click();
    await element.updateComplete;
    expect(open(element)).toEqual([]);
  });

  /** A row that is done is dimmed, and a dimmed field reads as one that
   *  cannot be typed in. */
  it("does not dim a done row while it is open", () => {
    const sheet = requestsStyles.cssText;
    const dimmed = /^\s*li\.done \{([^}]*)\}/m.exec(sheet)![1]!;
    const open = /^\s*li\.done:has\(tc-entry\) \{([^}]*)\}/m.exec(sheet)?.[1] ?? "";
    expect(dimmed).toMatch(/opacity:\s*0\.\d+/);
    expect(open).toMatch(/opacity:\s*1;/);
    expect(sheet.indexOf("li.done:has(tc-entry)")).toBeGreaterThan(sheet.indexOf("li.done {"));
  });

  it("has no row open once the scheduler's row lists the entry no more", async () => {
    const element = await list();
    await tap(element, 4);
    element.timetable = loaded(...ENTRIES.slice(0, 4));
    await element.updateComplete;
    expect(open(element)).toEqual([]);
    // Nor when an entry that reads the same is listed later.
    element.timetable = EVENING;
    await element.updateComplete;
    expect(open(element)).toEqual([]);
  });

  describe("in a list that scrolls", () => {
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

    it("is scrolled to the row that opens, and again where the open row moves", async () => {
      const element = await list();
      asked.length = 0;
      await tap(element, 4);
      expect(asked).toEqual([rows(element)[4]]);

      await typed(parts(element)[4]!, "at", "06:00");
      element.timetable = loaded(
        { entry: { ...LATER, at: "06:00" }, state: "held", round: 0 },
        ...ENTRIES.slice(0, 4),
      );
      await element.updateComplete;
      // The open row is the same element, now the first.
      expect(asked).toHaveLength(2);
      expect(asked[1]).toBe(rows(element)[0]);
    });

    it("is not scrolled while the open row stays where it is", async () => {
      const element = await list();
      await tap(element, 4);
      asked.length = 0;
      element.timetable = loaded(...ENTRIES.slice(0, 4), { entry: LATER, state: "held", round: 0 });
      await element.updateComplete;
      expect(asked).toEqual([]);
    });
  });
});

describe("the run view's open row", () => {
  beforeEach(brokering);

  afterEach(unbrokered);

  const ENTRY_WANTED = "tc49/schedule/entry_wanted";

  /** `EVENING` as the scheduler says it: each entry's document fields with
   *  what became of it beside them. */
  const RUNNING = {
    timetable: "evening",
    phase: "running",
    record: false,
    start: "06:00",
    repeat: "1d00:00",
    trains: {},
    positioning: [],
    entries: ENTRIES.map(({ entry, ...became }) => ({ ...entry, ...became })),
  };

  const ENDED: Entry = { at: "06:01", train: "local", to: ["d.A"] };

  /** A joined session whose picture holds the three requests and whose
   *  scheduler has `evening` loaded. */
  async function serving(): Promise<{ shell: TcApp; element: TcRequests }> {
    const shell = await joined();
    await said(shell, "tc49/dispatch/state/allocation", {
      trains: { goods: "a", express: "c", local: "d" },
      occupied: { goods: ["a"], express: ["c"], local: ["d"] },
      locks: { a: "goods" },
      requests: [
        { id: "e1", train: "express", depart: "c.A", dest: ["a.B"], route: ["c", "sw.side", "a"] },
        { id: "g1", train: "goods", depart: "a.B", dest: ["b.A"] },
        { id: "l1", train: "local", depart: "d.A", dest: ["b.B", "c.B"] },
      ],
    });
    await said(shell, "tc49/schedule/state/timetable", RUNNING);
    const element = running(shell).renderRoot.querySelector("tc-requests")!;
    return { shell, element };
  }

  /** The row at `at` opened, and its open part. */
  async function part(element: TcRequests, at: number): Promise<TcEntry> {
    await tap(element, at);
    const opened = parts(element)[at]!;
    await opened.updateComplete;
    return opened;
  }

  /** `was` is the entry's document fields, with nothing of what became of
   *  it: the scheduler drops a gesture that carries `state`, `request` or
   *  `ended`. */
  it.each([
    [2, "at", "06:10", GOODS, { ...GOODS, at: "06:10" }],
    [2, "dwell", "5", GOODS, { ...GOODS, dwell: 5 }],
    [2, "description", "meets the local", GOODS, { ...GOODS, description: "meets the local" }],
    [0, "at", "06:03", ENDED, { ...ENDED, at: "06:03" }],
    [0, "dwell", "1", ENDED, { ...ENDED, dwell: 1 }],
    [3, "description", "runs round", TURN, { ...TURN, description: "runs round" }],
  ] as const)(
    "writes one entry_wanted for row %i with `%s` changed to %j",
    async (at, name, words, was, now) => {
      const { element } = await serving();
      await typed(await part(element, at), name, words);
      expect(written()).toEqual([{ topic: ENTRY_WANTED, payload: { was, now } }]);
    },
  );

  it.each([
    ["at", "soon"],
    ["at", "25:00"],
    ["dwell", "-1"],
    ["dwell", "1.5"],
  ] as const)("writes nothing for `%s` typed as %j", async (name, words) => {
    const { element } = await serving();
    await typed(await part(element, 2), name, words);
    expect(written()).toEqual([]);
  });

  it("writes entry_wanted for a time after midnight within the repeat", async () => {
    const { element } = await serving();
    await typed(await part(element, 2), "at", "1d01:00");
    expect(written()).toEqual([
      { topic: ENTRY_WANTED, payload: { was: GOODS, now: { ...GOODS, at: "1d01:00" } } },
    ]);
  });

  it.each([
    ["05:00", "before the start 06:00"],
    ["1d06:00", "after the last minute, 1d05:59"],
  ])("writes nothing for %s, outside the repeat, and the row says %j", async (words, why) => {
    const { element } = await serving();
    const opened = await part(element, 2);
    await typed(opened, "at", words);
    expect(written()).toEqual([]);
    expect(refusal(opened)).toBe(why);
  });

  /** `panel.ts` reads each `state/timetable` row into new entries. */
  it("writes nothing for words being typed when the scheduler's row arrives, and the change when the field is left", async () => {
    const { shell, element } = await serving();
    const opened = await part(element, 4);
    const input = typing(opened, "description", "last train");
    const [ended, express, ...rest] = RUNNING.entries;
    await said(shell, "tc49/schedule/state/timetable", {
      ...RUNNING,
      entries: [ended, { ...express, state: "ended", ended: 130 }, ...rest],
    });
    await opened.updateComplete;
    expect(input.value).toBe("last train");
    expect(written()).toEqual([]);
    input.dispatchEvent(new Event("change", { bubbles: true }));
    expect(written()).toEqual([
      { topic: ENTRY_WANTED, payload: { was: LATER, now: { ...LATER, description: "last train" } } },
    ]);
  });

  /** The railroad the session is joined to has the blocks `a` and `b`. */
  it("writes entry_wanted for arrival ends of the railroad's blocks", async () => {
    const { element } = await serving();
    await typed(await part(element, 2), "to", "a, b.B");
    expect(written()).toEqual([
      { topic: ENTRY_WANTED, payload: { was: GOODS, now: { ...GOODS, to: ["a", "b.B"] } } },
    ]);
  });

  it("writes nothing for a block the railroad does not have, and the row names it", async () => {
    const { element } = await serving();
    const opened = await part(element, 2);
    await typed(opened, "to", "a, c.A");
    expect(written()).toEqual([]);
    expect(refusal(opened)).toBe("the railroad has no block c");
  });

  it("writes one entry_wanted with now null for Delete", async () => {
    const { element } = await serving();
    const opened = await part(element, 2);
    opened.renderRoot.querySelector<HTMLButtonElement>("button.delete")!.click();
    expect(written()).toEqual([{ topic: ENTRY_WANTED, payload: { was: GOODS, now: null } }]);
  });

  it("writes cancel_wanted and no entry_wanted for the cancel of an out entry's row", async () => {
    const { element } = await serving();
    await part(element, 2);
    rows(element)[2]!.querySelector<HTMLButtonElement>(".cancel")!.click();
    expect(written()).toEqual([
      { topic: "tc49/dispatch/cancel_wanted", payload: { id: "g1" } },
    ]);
  });

  it("has the row open where the scheduler's row puts the entry", async () => {
    const { shell, element } = await serving();
    await typed(await part(element, 4), "at", "06:00");
    expect(open(element)).toEqual([4]);
    const [ended, express, goods, turn, later] = RUNNING.entries;
    await said(shell, "tc49/schedule/state/timetable", {
      ...RUNNING,
      entries: [{ ...later, at: "06:00", state: "held" }, ended, express, goods, turn],
    });
    expect(open(element)).toEqual([0]);
  });
});
