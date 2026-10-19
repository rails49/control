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
import { running, settled } from "./support/shell.js";
import { brokering, joined, said, unbrokered, written } from "./support/session.js";

const ALLOCATION = "tc49/dispatch/state/allocation";

/** `goods` underway, then `express` waiting, then `goods` chained after its
 *  first request, then `local` waiting. */
const LISTED: Listed[] = [
  { id: "g1", train: "goods", depart: "a.B", dest: ["b.A"], route: ["a", "sw.main", "b"] },
  { id: "e1", train: "express", depart: "c.A", dest: ["a.B"] },
  { id: "g2", train: "goods", depart: null, dest: ["c.B"], after: "g1" },
  { id: "l1", train: "local", depart: "d.A", dest: ["b.B", "c.B"] },
];

const ROWS = requestRows(LISTED);

describe("the rows", () => {
  it("are one per request in list order: train, from, to, waiting or underway", () => {
    expect(ROWS).toEqual([
      { id: "g1", train: "goods", from: ["a.B"], to: ["b.A"], state: "underway" },
      { id: "e1", train: "express", from: ["c.A"], to: ["a.B"], state: "waiting" },
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
    expect(reordering(ROWS, "l1", 1)).toEqual({ before: "e1" });
  });

  it("names null for the end of the list", () => {
    expect(reordering(ROWS, "e1", ROWS.length)).toEqual({ before: null });
  });

  /** The dispatcher drops a move in front of a request that has started, and
   *  among the waiting ones in front of the first is the same place. */
  it("lands in front of the first waiting row past an underway one", () => {
    expect(reordering(ROWS, "l1", 0)).toEqual({ before: "e1" });
  });

  it("asks nothing where the row is let go where it was", () => {
    expect(reordering(ROWS, "e1", 1)).toBeNull();
    expect(reordering(ROWS, "e1", 2)).toBeNull();
  });

  it("is refused for an underway row", () => {
    expect(reordering(ROWS, "g1", ROWS.length)).toBeNull();
  });

  it("is refused for a chained row above the one it follows", () => {
    const rows = requestRows([
      { id: "e1", train: "express", depart: "c.A", dest: ["a.B"] },
      { id: "g1", train: "goods", depart: "a.B", dest: ["b.A"] },
      { id: "g2", train: "goods", depart: null, dest: ["c.B"], after: "g1" },
    ]);
    expect(reordering(rows, "g2", 0)).toBeNull();
    expect(reordering(rows, "g2", 1)).toBeNull();
    // Nor can the one it follows go below it, which is the same order.
    expect(reordering(rows, "g1", rows.length)).toBeNull();
    // Above every other request is fine.
    expect(reordering(rows, "g1", 0)).toEqual({ before: "e1" });
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
      ["goods", "a.B → b.A", "underway"],
      ["express", "c.A → a.B", "waiting"],
      ["goods", "b.A → c.B", "waiting"],
      ["local", "d.A → b.B, c.B", "waiting"],
    ]);
  });

  it("raises the cancel with the row's id", async () => {
    const element = await list(ROWS);
    const seen: string[] = [];
    element.addEventListener("request-cancelled", (event) =>
      seen.push((event as CustomEvent<{ id: string }>).detail.id),
    );
    element.renderRoot.querySelectorAll<HTMLButtonElement>(".cancel")[1]!.click();
    expect(seen).toEqual(["e1"]);
  });

  it("raises a move with its before", async () => {
    const element = await list(ROWS);
    expect(reorders(element, () => element.move("l1", 1))).toEqual([
      { id: "l1", before: "e1" },
    ]);
  });

  it("raises nothing for the two refused drags", async () => {
    const element = await list(ROWS);
    expect(reorders(element, () => element.move("g1", ROWS.length))).toEqual([]);
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

  it("writes one reorder_wanted for a move, and nothing for a refused one", async () => {
    const { element } = await serving();
    element.move("g2", 0);
    element.move("l1", 1);
    expect(written()).toEqual([
      { topic: "tc49/dispatch/reorder_wanted", payload: { id: "l1", before: "e1" } },
    ]);
  });
});
