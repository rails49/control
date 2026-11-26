// @vitest-environment happy-dom

/**
 * The request list: one row per request the dispatcher holds, in the order it
 * serves them, a cancel on each and a drag to reorder the waiting ones
 * ([ADR-0080](../../docs/adr/0080-the-waiting-requests-are-a-list-a-person-orders.md),
 * [#829](https://github.com/rails49/control/issues/829)).
 *
 * Three parts. The rows and what a drag asks are `model/requests.ts`'s, a
 * seam of their own. Then `tc-requests`, which draws the rows it is handed and
 * raises an event only where the model says a drag is a move. Then the run
 * view, which reads the rows off `state/allocation` and writes the one frame
 * each gesture means.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-app.js";
import "../src/ui/tc-requests.js";
import { reordering, requestRows, type Listed, type RequestRow } from "../src/model/requests.js";
import type { TcApp } from "../src/ui/tc-app.js";
import type { RequestReorder, TcRequests } from "../src/ui/tc-requests.js";
import { requestsStyles } from "../src/ui/tc-requests.styles.js";
import { running, settled } from "./support/shell.js";
import { brokering, joined, said, unbrokered, written } from "./support/session.js";

const ALLOCATION = "tc49/dispatch/state/allocation";

/** `express` underway, then `goods` waiting, then `goods` chained after its
 *  first request, then `local` waiting. */
const LISTED: Listed[] = [
  { id: "e1", train: "express", depart: "c.A", dest: ["a.B"], route: ["c", "sw.side", "a"] },
  { id: "g1", train: "goods", depart: "a.B", dest: ["b.A"] },
  { id: "g2", train: "goods", depart: null, dest: ["c.B"], after: "g1" },
  { id: "l1", train: "local", depart: "d.A", dest: ["b.B", "c.B"] },
];

const ROWS = requestRows(LISTED);

describe("the rows", () => {
  it("are one per request in list order: train, from, to, waiting or underway", () => {
    expect(ROWS).toEqual([
      { id: "e1", train: "express", from: ["c.A"], to: ["a.B"], state: "underway" },
      { id: "g1", train: "goods", from: ["a.B"], to: ["b.A"], state: "waiting" },
      { id: "g2", train: "goods", from: ["b.A"], to: ["c.B"], state: "waiting", after: "g1" },
      { id: "l1", train: "local", from: ["d.A"], to: ["b.B", "c.B"], state: "waiting" },
    ]);
  });

  /** A chained request starts where the one it follows ends, and that one
   *  is in the list for as long as it has not. */
  it("gives a chained request whose earlier one is gone no start", () => {
    const [row] = requestRows([
      { id: "g2", train: "goods", depart: null, dest: ["c.B"], after: "g1" },
    ]);
    expect(row!.from).toEqual([]);
  });
});

describe("a reorder", () => {
  it("names the row it lands in front of", () => {
    expect(reordering(ROWS, "l1", 1)).toEqual({ before: "g1" });
  });

  it("names null for the end of the list", () => {
    expect(reordering(ROWS, "g2", ROWS.length)).toEqual({ before: null });
  });

  /** The dispatcher drops a move in front of a request that has started, and
   *  among the waiting ones in front of the first is the same place. */
  it("lands in front of the first waiting row past an underway one", () => {
    expect(reordering(ROWS, "l1", 0)).toEqual({ before: "g1" });
  });

  it("asks nothing where the row is let go where it was", () => {
    expect(reordering(ROWS, "g1", 1)).toBeNull();
    expect(reordering(ROWS, "g1", 2)).toBeNull();
  });

  it("is refused for an underway row", () => {
    expect(reordering(ROWS, "e1", ROWS.length)).toBeNull();
  });

  it("is refused for a chained row above the one it follows", () => {
    expect(reordering(ROWS, "g2", 0)).toBeNull();
    expect(reordering(ROWS, "g2", 1)).toBeNull();
    // Nor can the one it follows go below it, which is the same order.
    expect(reordering(ROWS, "g1", ROWS.length)).toBeNull();
  });
});

/** The list, holding the rows it was handed, live. */
async function list(requests: RequestRow[]): Promise<TcRequests> {
  const element = document.createElement("tc-requests");
  element.requests = requests;
  element.live = true;
  document.body.append(element);
  await element.updateComplete;
  return element;
}

/** What the list draws, one row at a time. */
function drawn(element: TcRequests): string[][] {
  return [...element.renderRoot.querySelectorAll("li")].map((row) =>
    [".train", ".way", ".state"].map((part) => row.querySelector(part)!.textContent!.trim()),
  );
}

/** The declarations of the rule for `selector`, at the start of a line. */
function rule(sheet: string, selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`^\\s*${escaped} \\{([^}]*)\\}`, "m").exec(sheet)![1]!;
}

/** The moves the list raised while `act` ran. */
function reorders(element: TcRequests, act: () => void): RequestReorder[] {
  const seen: RequestReorder[] = [];
  const hear = (event: Event) => seen.push((event as CustomEvent<RequestReorder>).detail);
  element.addEventListener("request-reordered", hear);
  act();
  element.removeEventListener("request-reordered", hear);
  return seen;
}

describe("tc-requests", () => {
  afterEach(() => {
    document.body.replaceChildren();
  });

  it("draws a row per request: train, from and to, and its state", async () => {
    const element = await list(ROWS);
    expect(drawn(element)).toEqual([
      ["express", "c.A → a.B", "underway"],
      ["goods", "a.B → b.A", "waiting"],
      ["goods", "b.A → c.B", "waiting"],
      ["local", "d.A → b.B, c.B", "waiting"],
    ]);
  });

  /** The list is a table (#1393): the same columns with a timetable or
   *  without, the action's unlabelled. */
  it("heads its columns Time, Train, To, Dwell, Description and State", async () => {
    const element = await list(ROWS);
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

  it("leaves Time, Dwell and Description empty on a request's row", async () => {
    const element = await list(ROWS);
    const row = element.renderRoot.querySelector("li")!;
    expect(
      [".time", ".dwell", ".description"].map((cell) => row.querySelector(cell)!.textContent!.trim()),
    ).toEqual(["", "", ""]);
  });

  /** The headings stay in view at the top of what scrolls, over the rows
   *  scrolled under them. */
  it("keeps its column headings at the top of what scrolls", async () => {
    const element = await list(ROWS);
    const scrolled = element.renderRoot.querySelector(".table")!;
    expect(scrolled.firstElementChild!.classList.contains("columns")).toBe(true);
    expect(scrolled.querySelectorAll("li")).toHaveLength(ROWS.length);
    const sheet = requestsStyles.cssText;
    expect(rule(sheet, ".table")).toMatch(/overflow-y:\s*auto/);
    const columns = rule(sheet, ".columns");
    expect(columns).toMatch(/position:\s*sticky/);
    expect(columns).toMatch(/top:\s*0/);
    expect(columns).toMatch(/background:\s*var\(--paper\)/);
  });

  /** Every other row takes the stripe shade, and no line divides two rows.
   *  The note line and the open row are inside their row's `li`, so they
   *  share its stripe. A row picked up is marked over its stripe, and a done
   *  row is dimmed with it. */
  it("stripes every other row and rules no line between rows", () => {
    const sheet = requestsStyles.cssText;
    expect(rule(sheet, "li:nth-child(even)")).toMatch(/background:\s*var\(--stripe\)/);
    expect(sheet).not.toContain("li + li");
    expect(sheet).not.toMatch(/border-top/);
    expect(rule(sheet, "li.held")).toMatch(/background:\s*var\(--rule\)/);
    expect(sheet.indexOf("li.held {")).toBeGreaterThan(sheet.indexOf("li:nth-child(even) {"));
  });

  /** Each row lines its cells up with the headings' columns: the rows take
   *  the table's columns. */
  it("lines every row's cells up with the headings", () => {
    const sheet = requestsStyles.cssText;
    for (const part of ["ul", "li", ".columns"]) {
      expect(rule(sheet, part)).toMatch(/grid-template-columns:\s*subgrid/);
    }
    expect(rule(sheet, ".note")).toMatch(/grid-column:\s*train\s*\/\s*-1/);
    expect(rule(sheet, "tc-entry")).toMatch(/grid-column:\s*1\s*\/\s*-1/);
  });

  /** The name's rule wraps it at any character and sets no ellipsis (#1305). */
  it("draws a long train name whole, wrapped and not cut short", async () => {
    const long = "Trans Europ Express Rheingold, second section";
    const element = await list(
      requestRows([{ id: "t1", train: long, depart: "a.B", dest: ["b.A"] }]),
    );
    expect(drawn(element)[0]![0]).toBe(long);

    const train = /^\s*\.train \{([^}]*)\}/m.exec(requestsStyles.cssText)![1]!;
    expect(train).toContain("overflow-wrap: anywhere");
    expect(train).not.toContain("nowrap");
    expect(requestsStyles.cssText).not.toContain("text-overflow");
  });

  /** Safari stops selecting only for the prefixed rule, and a finger resting
   *  on a row would select its text instead of dragging it (#1312). happy-dom
   *  selects nothing either way, so this reads the rule. */
  it("leaves Safari no text to select on a row", () => {
    const row = /^\s*li \{([^}]*)\}/m.exec(requestsStyles.cssText)![1]!;
    expect(row).toMatch(/-webkit-user-select:\s*none/);
    expect(row).toMatch(/-webkit-touch-callout:\s*none/);
  });

  it("raises the cancel with the row's id", async () => {
    const element = await list(ROWS);
    const seen: string[] = [];
    element.addEventListener("request-cancelled", (event) =>
      seen.push((event as CustomEvent<{ id: string }>).detail.id),
    );
    element.renderRoot.querySelectorAll<HTMLButtonElement>(".cancel")[1]!.click();
    expect(seen).toEqual(["g1"]);
  });

  /** Running without sensors a person says the train is in its destination
   *  block (#1323). Only an underway request has a train on its way. */
  describe("arrived", () => {
    async function arrivable(live: boolean, arrivable: boolean): Promise<TcRequests> {
      const element = await list(ROWS);
      element.live = live;
      element.arrivable = arrivable;
      await element.updateComplete;
      return element;
    }

    /** Each row's id where it has the button. */
    function arrivals(element: TcRequests): string[] {
      return [...element.renderRoot.querySelectorAll("li")]
        .filter((row) => row.querySelector(".arrived") !== null)
        .map((row) => row.dataset["id"]!);
    }

    it("is on an underway row and not on a waiting one", async () => {
      const element = await arrivable(true, true);
      expect(arrivals(element)).toEqual(["e1"]);
      const button = element.renderRoot.querySelector<HTMLButtonElement>(".arrived")!;
      expect(button.textContent!.trim()).toBe("arrived");
      expect(button.getAttribute("aria-label")).toBe("Train has arrived");
    });

    it("is on no row without arrivable or without live", async () => {
      expect(arrivals(await arrivable(true, false))).toEqual([]);
      document.body.replaceChildren();
      expect(arrivals(await arrivable(false, true))).toEqual([]);
    });

    it("comes before the cancel", async () => {
      const element = await arrivable(true, true);
      const buttons = [...element.renderRoot.querySelectorAll("li")[0]!.querySelectorAll("button")];
      expect(buttons.map((button) => button.className)).toEqual(["arrived", "cancel"]);
    });

    it("raises request-arrived with the row's id and picks nothing up", async () => {
      const element = await arrivable(true, true);
      const seen: string[] = [];
      element.addEventListener("request-arrived", (event) =>
        seen.push((event as CustomEvent<{ id: string }>).detail.id),
      );
      const button = element.renderRoot.querySelector<HTMLButtonElement>(".arrived")!;
      button.dispatchEvent(
        new PointerEvent("pointerdown", { button: 0, bubbles: true, composed: true }),
      );
      button.click();
      await element.updateComplete;
      expect(seen).toEqual(["e1"]);
      expect(element.renderRoot.querySelectorAll("li.held")).toHaveLength(0);
    });
  });

  it("raises a move with its before", async () => {
    const element = await list(ROWS);
    expect(reorders(element, () => element.move("l1", 1))).toEqual([
      { id: "l1", before: "g1" },
    ]);
  });

  it("raises nothing for the two refused drags", async () => {
    const element = await list(ROWS);
    expect(reorders(element, () => element.move("e1", ROWS.length))).toEqual([]);
    expect(reorders(element, () => element.move("g2", 0))).toEqual([]);
  });

  it("lets a waiting row be picked up and an underway one not", async () => {
    const element = await list(ROWS);
    const rows = [...element.renderRoot.querySelectorAll("li")];
    expect(rows.map((row) => row.classList.contains("still"))).toEqual([
      true,
      false,
      false,
      false,
    ]);
  });
});

describe("the run view's request list", () => {
  beforeEach(brokering);

  afterEach(unbrokered);

  /** A joined session whose picture holds `LISTED`. */
  async function serving(): Promise<{ shell: TcApp; element: TcRequests }> {
    const shell = await joined();
    await said(shell, ALLOCATION, {
      trains: { goods: "a", express: "c", local: "d" },
      occupied: { goods: ["a"], express: ["c"], local: ["d"] },
      locks: { a: "goods" },
      requests: LISTED,
    });
    await settled(shell);
    const element = running(shell).renderRoot.querySelector("tc-requests")!;
    return { shell, element };
  }

  it("lists the allocation's requests in order", async () => {
    const { element } = await serving();
    expect(element.requests).toEqual(ROWS);
  });

  it("writes one cancel_wanted naming the row's request", async () => {
    const { element } = await serving();
    element.renderRoot.querySelectorAll<HTMLButtonElement>(".cancel")[2]!.click();
    expect(written()).toEqual([
      { topic: "tc49/dispatch/cancel_wanted", payload: { id: "g2" } },
    ]);
  });

  /** "Arrived" is offered only while the railroad runs without sensors
   *  (#1322, #1323). */
  async function settings(shell: TcApp, without_sensors: boolean): Promise<void> {
    await said(shell, "tc49/layout/state/settings", { at: 1, without_sensors });
    await settled(shell);
  }

  it("writes one arrival_wanted naming the row's request without sensors", async () => {
    const { shell, element } = await serving();
    await settings(shell, true);
    element.renderRoot.querySelector<HTMLButtonElement>(".arrived")!.click();
    expect(written()).toEqual([
      { topic: "tc49/dispatch/arrival_wanted", payload: { id: "e1" } },
    ]);
  });

  it("offers no arrived while the railroad runs by its sensors", async () => {
    const { shell, element } = await serving();
    await settings(shell, true);
    await settings(shell, false);
    expect(element.renderRoot.querySelector(".arrived")).toBeNull();
  });

  it("writes one reorder_wanted for a move, and nothing for a refused one", async () => {
    const { element } = await serving();
    element.move("g2", 0);
    element.move("l1", 1);
    expect(written()).toEqual([
      { topic: "tc49/dispatch/reorder_wanted", payload: { id: "l1", before: "g1" } },
    ]);
  });
});

/** A note under a row that waits or stands: which train it waits for, as the
 *  latest `grant_refused` the picture carries on the request named it
 *  ([#1114](https://github.com/rails49/control/issues/1114)). */
describe("a refused request's note", () => {
  beforeEach(brokering);

  afterEach(unbrokered);

  /** `express` underway through `c`, `goods` waiting at `a`, `parked`
   *  standing in `b` with no request, and `crosser` in the transit `sw.side`
   *  having left `d`. */
  const TRAINS = { express: "c", goods: "a", parked: "b", crosser: "d" };

  /** A joined session whose picture lists `requests`. */
  async function serving(requests: Listed[]): Promise<{ shell: TcApp; element: TcRequests }> {
    const shell = await joined();
    await picture(shell, requests);
    const element = running(shell).renderRoot.querySelector("tc-requests")!;
    return { shell, element };
  }

  async function picture(shell: TcApp, requests: Listed[]): Promise<void> {
    await said(shell, ALLOCATION, {
      trains: TRAINS,
      crossing: { crosser: "sw.side" },
      occupied: { express: ["c"], goods: ["a"], parked: ["b"], crosser: ["d", "sw.side"] },
      locks: { a: "goods", b: "parked", c: "express", "sw.side": "crosser" },
      requests,
    });
    await settled(shell);
  }

  /** The note drawn under each row, a line per sentence, `null` where a row
   *  has none. */
  function notes(element: TcRequests): (string | null)[] {
    return [...element.renderRoot.querySelectorAll("li")].map((row) => {
      const lines = [...row.querySelectorAll(".note")].map((line) => line.textContent!.trim());
      return lines.length === 0 ? null : lines.join(" / ");
    });
  }

  const EXPRESS: Listed = {
    id: "e1",
    train: "express",
    depart: "c.A",
    dest: ["a.B"],
    route: ["c", "sw.side", "a"],
  };

  function goods(obstacles: { resource: string; holder: string }[]): Listed {
    return {
      id: "g1",
      train: "goods",
      depart: "a.B",
      dest: ["b.A"],
      refused: { reason: "unsafe", obstacles },
    };
  }

  it("says a holder with a request of its own is to pass", async () => {
    const { element } = await serving([EXPRESS, goods([{ resource: "c", holder: "express" }])]);
    expect(notes(element)).toEqual([null, "waits for express to pass"]);
  });

  it("tells a person to give a holder with no request one", async () => {
    const { element } = await serving([goods([{ resource: "b", holder: "parked" }])]);
    expect(notes(element)).toEqual(["waits for parked to leave b — give parked a request"]);
  });

  /** A train is left standing in a block, not in a transit. */
  it("names the block a holder in a transit stands in", async () => {
    const { element } = await serving([goods([{ resource: "sw.side", holder: "crosser" }])]);
    expect(notes(element)).toEqual(["waits for crosser to leave d — give crosser a request"]);
  });

  it("says a block held by no train is to read clear", async () => {
    const { element } = await serving([goods([{ resource: "b", holder: "" }])]);
    expect(notes(element)).toEqual(["waits for a sensor of b to read clear"]);
  });

  /** `goods` stands in `a`, whose sensor has not reported: the dispatcher
   *  names no holder, and the note asks for the sensor and not for `goods`
   *  (#1254). */
  it("says a block out of use is to report", async () => {
    const { shell, element } = await serving([goods([{ resource: "a", holder: "" }])]);
    await said(shell, "tc49/layout/state/unknown_sensors", {
      sensors: [{ sensor: "a.A", reason: "no report since start", reported: false }],
    });
    await settled(shell);
    expect(notes(element)).toEqual(["waits for a sensor of a to report"]);
  });

  /** Any one of them moving may free a route. */
  it("joins distinct holders of one kind with or", async () => {
    const local: Listed = { id: "l1", train: "local", depart: "d.A", dest: ["b.B"] };
    const { element } = await serving([
      EXPRESS,
      local,
      goods([
        { resource: "c", holder: "express" },
        { resource: "d", holder: "local" },
        { resource: "sw.side", holder: "express" },
      ]),
    ]);
    expect(notes(element)).toEqual([null, null, "waits for express or local to pass"]);
  });

  it("gives holders of mixed kinds a sentence each", async () => {
    const { element } = await serving([
      EXPRESS,
      goods([
        { resource: "c", holder: "express" },
        { resource: "b", holder: "parked" },
      ]),
    ]);
    expect(notes(element)).toEqual([
      null,
      "waits for express to pass / waits for parked to leave b — give parked a request",
    ]);
  });

  it("shows on an underway row, and goes with the next picture without it", async () => {
    const standing: Listed = {
      ...EXPRESS,
      refused: { reason: "held", obstacles: [{ resource: "b", holder: "parked" }] },
    };
    const { shell, element } = await serving([standing]);
    expect(notes(element)).toEqual(["waits for parked to leave b — give parked a request"]);
    await picture(shell, [EXPRESS]);
    expect(notes(element)).toEqual([null]);
  });

  it("goes with the row when the request completes", async () => {
    const { shell, element } = await serving([goods([{ resource: "b", holder: "parked" }])]);
    await said(shell, "tc49/dispatch/request_completed", { id: "g1" });
    await settled(shell);
    expect(notes(element)).toEqual([]);
  });

  it("goes with the row when the request is cancelled", async () => {
    const { shell, element } = await serving([goods([{ resource: "b", holder: "parked" }])]);
    await picture(shell, []);
    expect(notes(element)).toEqual([]);
  });

  /** The note is in the retained picture, so a page opened after the refusal
   *  shows it: the first picture this page has is the one that carries it. */
  it("shows on the first picture a page has", async () => {
    const { element } = await serving([goods([{ resource: "b", holder: "parked" }])]);
    expect(element.requests.map((row) => row.note)).toEqual([
      ["waits for parked to leave b — give parked a request"],
    ]);
  });
});

/** An underway row whose cancel the dispatcher holds: the train runs on into
 *  the block its move enters and stops there, and only then does the row go
 *  ([#1115](https://github.com/rails49/control/issues/1115)). */
describe("a held cancel", () => {
  beforeEach(brokering);

  afterEach(unbrokered);

  const EXPRESS: Listed = {
    id: "e1",
    train: "express",
    depart: "c.A",
    dest: ["a.B"],
    route: ["c", "sw.side", "a"],
  };

  const CANCELLING: Listed = { ...EXPRESS, cancelling: "B7" };

  async function picture(shell: TcApp, requests: Listed[]): Promise<void> {
    await said(shell, ALLOCATION, {
      trains: { express: "c" },
      occupied: { express: ["c"] },
      locks: { c: "express", "sw.side": "express", a: "express" },
      requests,
    });
    await settled(shell);
  }

  async function serving(requests: Listed[]): Promise<{ shell: TcApp; element: TcRequests }> {
    const shell = await joined();
    await picture(shell, requests);
    const element = running(shell).renderRoot.querySelector("tc-requests")!;
    return { shell, element };
  }

  function states(element: TcRequests): string[] {
    return [...element.renderRoot.querySelectorAll("li .state")].map(
      (state) => state.textContent!.trim(),
    );
  }

  function cancels(element: TcRequests): { disabled: boolean; label: string | null }[] {
    return [...element.renderRoot.querySelectorAll<HTMLButtonElement>("li .cancel")].map(
      (button) => ({ disabled: button.disabled, label: button.getAttribute("aria-label") }),
    );
  }

  it("says where the train stops in place of underway, and its × is disabled", async () => {
    const { element } = await serving([CANCELLING]);
    expect(states(element)).toEqual(["cancelling — stops in B7"]);
    expect(cancels(element)).toEqual([{ disabled: true, label: "already cancelling" }]);
  });

  it("leaves an underway row with no held cancel as it was", async () => {
    const { element } = await serving([EXPRESS]);
    expect(states(element)).toEqual(["underway"]);
    expect(cancels(element)).toEqual([{ disabled: false, label: "Cancel request" }]);
  });

  /** Whether by `move_withdrawn` or by the move ending at its sensor, the
   *  request leaves the list, and the mark with it. */
  it("goes with the row when the request leaves the list", async () => {
    const { shell, element } = await serving([CANCELLING]);
    await picture(shell, []);
    expect(states(element)).toEqual([]);
    expect(element.requests).toEqual([]);
  });

  /** The allocation is retained, so a page that connects after the × shows
   *  what one open at the time did. */
  it("shows on the first picture a page has", async () => {
    const { element } = await serving([CANCELLING]);
    expect(element.requests.map((row) => row.cancelling)).toEqual(["B7"]);
  });

  it("is not read where `cancelling` is not a block id", async () => {
    const { element } = await serving([{ ...EXPRESS, cancelling: 7 } as unknown as Listed]);
    expect(states(element)).toEqual(["underway"]);
  });
});
