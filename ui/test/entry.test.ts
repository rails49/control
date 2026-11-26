// @vitest-environment happy-dom

/**
 * An entry's row opened in the list under the roster: its time, its dwell,
 * its description and a Delete
 * ([#1345](https://github.com/rails49/control/issues/1345),
 * [#1358](https://github.com/rails49/control/issues/1358)).
 *
 * Four parts. What a typed field makes of an entry is `model/timetable.ts`'s.
 * Then `tc-entry`, the open row, which draws the fields and raises what a
 * person changed. Then `tc-requests`, which opens one row at a time. Then the
 * run view, which writes one `entry_wanted` for each change.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../src/ui/tc-app.js";
import "../src/ui/tc-entry.js";
import "../src/ui/tc-requests.js";
import { requestRows } from "../src/model/requests.js";
import {
  edited,
  same,
  type Entry,
  type Field,
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
  it("has a time typed as H:MM or HH:MM, said as HH:MM", () => {
    expect(edited(GOODS, "at", "6:10")).toEqual({ ...GOODS, at: "06:10" });
    expect(edited(GOODS, "at", " 23:59 ")).toEqual({ ...GOODS, at: "23:59" });
  });

  it.each(["", "soon", "0610", "24:00", "06:60"])("is not changed by %j, which is no time", (words) => {
    expect(edited(GOODS, "at", words)).toBeNull();
  });

  it("is not changed by the time it has", () => {
    expect(edited(GOODS, "at", "6:02")).toBeNull();
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

/** The open row of `entry`. */
async function opened(entry: Entry): Promise<TcEntry> {
  const element = document.createElement("tc-entry");
  element.entry = entry;
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

/** `words` typed in a field and the field left, or Enter pressed: the
 *  browser says either with `change`. */
async function typed(element: TcEntry, name: Field, words: string): Promise<void> {
  const input = field(element, name)!;
  input.value = words;
  input.dispatchEvent(new Event("change", { bubbles: true }));
  await element.updateComplete;
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
    ["at", "6:10", { ...GOODS, at: "06:10" }],
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
    await typed(element, "at", "6:10");
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
    start: "06:00",
    trains: {},
    positioning: [],
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
  { entry: { at: "06:01", train: "local", to: ["d.A"] }, state: "ended", request: "l0", ended: 55 },
  { entry: { at: "06:02", train: "express", to: ["a.B"] }, state: "out", request: "e1" },
  { entry: GOODS, state: "out", request: "g1" },
  { entry: TURN, state: "held" },
  { entry: LATER, state: "later" },
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

  it("closes the open row at a second tap", async () => {
    const element = await list();
    await tap(element, 4);
    await tap(element, 4);
    expect(open(element)).toEqual([]);
  });

  it("moves the opening at a tap on another row", async () => {
    const element = await list();
    await tap(element, 4);
    await tap(element, 1);
    expect(open(element)).toEqual([1]);
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
    element.timetable = loaded(...ENTRIES.slice(0, 4), { entry: LATER, state: "held" });
    await element.updateComplete;
    expect(open(element)).toEqual([4]);
  });

  /** A changed time moves the entry in the scheduler's row, and entries carry
   *  no id: the row is found by what the change asked the entry to read. */
  it("has the row open at the entry's new place when a changed time moves it", async () => {
    const element = await list();
    await tap(element, 4);
    await typed(parts(element)[4]!, "at", "6:00");
    // Nothing has moved: the scheduler has not said so.
    expect(open(element)).toEqual([4]);
    expect(shown(parts(element)[4]!)).toEqual(["06:30", "0", ""]);

    const moved = { ...LATER, at: "06:00" };
    element.timetable = loaded({ entry: moved, state: "held" }, ...ENTRIES.slice(0, 4));
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

      await typed(parts(element)[4]!, "at", "6:00");
      element.timetable = loaded(
        { entry: { ...LATER, at: "06:00" }, state: "held" },
        ...ENTRIES.slice(0, 4),
      );
      await element.updateComplete;
      expect(asked).toEqual([rows(element)[4], rows(element)[0]]);
    });

    it("is not scrolled while the open row stays where it is", async () => {
      const element = await list();
      await tap(element, 4);
      asked.length = 0;
      element.timetable = loaded(...ENTRIES.slice(0, 4), { entry: LATER, state: "held" });
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
    [2, "at", "6:10", GOODS, { ...GOODS, at: "06:10" }],
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
    await typed(await part(element, 4), "at", "6:00");
    expect(open(element)).toEqual([4]);
    const [ended, express, goods, turn, later] = RUNNING.entries;
    await said(shell, "tc49/schedule/state/timetable", {
      ...RUNNING,
      entries: [{ ...later, at: "06:00", state: "held" }, ended, express, goods, turn],
    });
    expect(open(element)).toEqual([0]);
  });
});
