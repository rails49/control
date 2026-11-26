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

import { afterEach, describe, expect, it } from "vitest";

import "../src/ui/tc-entry.js";
import { edited, same, type Entry, type Field } from "../src/model/timetable.js";
import type { EntryChange, TcEntry } from "../src/ui/tc-entry.js";

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
