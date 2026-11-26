// @vitest-environment happy-dom

/**
 * A row of the timetable list (`ui/list-row.ts`, #1393): its cells, Time,
 * Train, To, Dwell, Description, State and the action, and the "waits for"
 * line under a refused request. Each test draws one row into a table row of
 * its own and reads what a person sees.
 */

import { render } from "lit";
import { afterEach, describe, expect, it } from "vitest";

import type { RequestRow } from "../src/model/requests.js";
import type { Entry, ListRow } from "../src/model/timetable.js";
import { cells, note, type RowActions } from "../src/ui/list-row.js";

const LIVE: RowActions = { live: true, arrivable: false, arrived: () => {}, cancel: () => {} };

const GOODS: RequestRow = { id: "g1", train: "goods", from: ["a.B"], to: ["b.A"], state: "waiting" };

const EXPRESS: RequestRow = {
  id: "e1",
  train: "express",
  from: ["c.A"],
  to: ["a.B"],
  state: "underway",
};

const MEETS: Entry = {
  at: "06:05",
  train: "goods",
  to: ["b.A", "c.B"],
  dwell: 2,
  description: "meets the express",
};

/** The row's cells drawn into an element of their own. */
function drawn(row: ListRow, actions: RowActions = LIVE): HTMLElement {
  const element = document.createElement("li");
  render(cells(row, actions), element);
  document.body.append(element);
  return element;
}

/** Each cell's words, left to right. */
function words(element: HTMLElement): string[] {
  return [...element.children].map((cell) => cell.textContent!.trim());
}

/** The words of the one cell with `name`. */
function cell(element: HTMLElement, name: string): string {
  return element.querySelector(`.${name}`)!.textContent!.trim();
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("a row's cells", () => {
  it("are Time, Train, To, Dwell, Description, State and the action, in that order", () => {
    const element = drawn({ entry: MEETS, state: "later" });
    expect([...element.children].map((part) => part.className)).toEqual([
      "time",
      "train",
      "way",
      "dwell",
      "description",
      "state",
      "action",
    ]);
    expect(words(element)).toEqual([
      "06:05",
      "goods",
      "→ b.A, c.B",
      "2 min",
      "meets the express",
      "later",
      "",
    ]);
  });

  it("leave Dwell and Description empty for an entry with neither", () => {
    const element = drawn({ entry: { at: "06:30", train: "local", to: ["c.B"] }, state: "held" });
    expect([cell(element, "dwell"), cell(element, "description")]).toEqual(["", ""]);
  });

  it("read turn in To for a turn-round", () => {
    const element = drawn({ entry: { at: "06:10", train: "goods", turn: true }, state: "held" });
    expect(cell(element, "way")).toBe("turn");
  });

  it("read from → to for a request, with Time, Dwell and Description empty", () => {
    const element = drawn({ request: GOODS });
    expect(words(element).slice(0, 6)).toEqual(["", "goods", "a.B → b.A", "", "", "waiting"]);
  });

  it("join several ends with a comma", () => {
    const element = drawn({ request: { ...GOODS, from: ["d.A"], to: ["b.B", "c.B"] } });
    expect(cell(element, "way")).toBe("d.A → b.B, c.B");
  });

  /** A chained request whose earlier one is no longer listed has no start. */
  it("read → to for a chained request with no from", () => {
    const element = drawn({ request: { ...GOODS, id: "g2", from: [], to: ["c.B"], after: "g1" } });
    expect(cell(element, "way")).toBe("→ c.B");
  });

  it("give an out entry's request the entry's time, dwell and description", () => {
    const element = drawn({ entry: MEETS, state: "out", request: GOODS });
    expect(words(element).slice(0, 6)).toEqual([
      "06:05",
      "goods",
      "a.B → b.A",
      "2 min",
      "meets the express",
      "waiting",
    ]);
  });

  it("read where the train stops in State while a cancel is held", () => {
    const element = drawn({ request: { ...EXPRESS, cancelling: "B7" } });
    expect(cell(element, "state")).toBe("cancelling — stops in B7");
  });
});

describe("a row's action", () => {
  /** Each button's class and words. */
  function buttons(element: HTMLElement): string[][] {
    return [...element.querySelectorAll<HTMLButtonElement>(".action button")].map((button) => [
      button.className,
      button.textContent!.trim(),
    ]);
  }

  it("is a cancel on a request, and nothing on an entry that is not out", () => {
    expect(buttons(drawn({ request: GOODS }))).toEqual([["cancel", "×"]]);
    expect(buttons(drawn({ entry: MEETS, state: "later" }))).toEqual([]);
  });

  it("is nothing where a press means nothing", () => {
    expect(buttons(drawn({ request: GOODS }, { ...LIVE, live: false }))).toEqual([]);
  });

  /** Running without sensors a person says the train is in its destination
   *  block (#1323). */
  it("is arrived, then cancel, on an underway row where the list is arrivable", () => {
    const arrivable = { ...LIVE, arrivable: true };
    expect(buttons(drawn({ request: EXPRESS }, arrivable))).toEqual([
      ["arrived", "arrived"],
      ["cancel", "×"],
    ]);
    expect(buttons(drawn({ request: GOODS }, arrivable))).toEqual([["cancel", "×"]]);
  });

  it("has its cancel disabled while a cancel is held", () => {
    const element = drawn({ request: { ...EXPRESS, cancelling: "B7" } });
    const button = element.querySelector<HTMLButtonElement>(".cancel")!;
    expect(button.disabled).toBe(true);
    expect(button.getAttribute("aria-label")).toBe("already cancelling");
  });

  it("says the request's id to the press, and lets no press through to the row", () => {
    const pressed: string[] = [];
    const element = drawn(
      { request: EXPRESS },
      {
        live: true,
        arrivable: true,
        arrived: (id) => pressed.push(`arrived ${id}`),
        cancel: (id) => pressed.push(`cancel ${id}`),
      },
    );
    let reached = 0;
    element.addEventListener("pointerdown", () => (reached += 1));
    for (const button of element.querySelectorAll<HTMLButtonElement>("button")) {
      button.dispatchEvent(new PointerEvent("pointerdown", { button: 0, bubbles: true }));
      button.click();
    }
    expect(pressed).toEqual(["arrived e1", "cancel e1"]);
    expect(reached).toBe(0);
  });
});

/** Which train a refused request waits for (#1114): a line under the row,
 *  a sentence per line. */
describe("a row's note", () => {
  function lines(row: ListRow): string[] {
    const element = document.createElement("div");
    render(note(row), element);
    return [...element.querySelectorAll(".note")].map((line) => line.textContent!.trim());
  }

  it("is the refused request's sentences", () => {
    const refused = {
      ...GOODS,
      note: ["waits for express to pass", "waits for parked to leave b — give parked a request"],
    };
    expect(lines({ request: refused })).toEqual(refused.note);
  });

  it("is nothing on a request not refused, or on an entry", () => {
    expect(lines({ request: GOODS })).toEqual([]);
    expect(lines({ entry: MEETS, state: "later" })).toEqual([]);
  });
});
