// @vitest-environment happy-dom

/**
 * A person makes cars and trains, end to end through the app (ui/STOCK.md,
 * #393).
 *
 * A DOM test because it crosses the screen, the two store routes and the run
 * view: what is under test is that a fresh box — no `catalogue/`, no roster —
 * reaches a saved roster with one car entry and three model entries, that the
 * run view sees a train made up here without a reload, and that the length
 * guard is off while the run has the train placed.
 *
 * The rules underneath are `test/composing.test.ts`'s, driven from plain
 * values; nothing is asserted twice.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../src/ui/tc-app.js";
import type { RosterDoc } from "../src/model/store.js";
import type { TcApp } from "../src/ui/tc-app.js";
import type { TcStock } from "../src/ui/tc-stock.js";
import { RETRY_MS } from "../src/model/store.js";
import {
  mounted,
  running,
  serving,
  settled,
  shows,
  stocking,
  type Answers,
} from "./support/shell.js";
import { bridging, DERIVES, said, stored, unbridged } from "./support/session.js";

let store: Answers;

beforeEach(() => {
  bridging();
  // A fresh box: the installation has written no model and the railroad has
  // no roster file, which is what the screen writing the first car draws
  // itself from and not a fault.
  store = serving({
    drawings: ["toy"],
    read: stored,
    review: () => Promise.resolve(DERIVES),
    rosterOf: () => ({}),
    catalogue: {},
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  unbridged();
});

/** The app with the toy railroad loaded, showing the stock screen. The band's
 *  picker is the only thing that loads a railroad (#171). */
async function opened(): Promise<TcApp> {
  const shell = await mounted("stock");
  shell.renderRoot
    .querySelector("tc-header")!
    .dispatchEvent(
      new CustomEvent<string>("railroad-wanted", {
        detail: "toy",
        bubbles: true,
        composed: true,
      }),
    );
  await settled(shell);
  return shell;
}

function screen(shell: TcApp): TcStock {
  return stocking(shell);
}

function parts(shell: TcApp, selector: string): HTMLElement[] {
  return [...screen(shell).renderRoot.querySelectorAll<HTMLElement>(selector)];
}

/** What the screen is saying went wrong, `null` where it is saying nothing.
 *  The one beside the trains, which is where a failed read reads; a failed
 *  write in the dialog says it in the dialog. */
function trouble(shell: TcApp): string | null {
  const line = screen(shell).renderRoot.querySelector("section.trains p.trouble");
  return line === null ? null : line.textContent!.trim();
}

/** A page from something in front of the store on the paths `which` picks
 *  out, as a stale route table puts one in front of a store that is up. */
function between(which: (path: string) => boolean): void {
  store.intercepted = (path) => (which(path) ? { status: 404, statusText: "" } : null);
}

/** Type into a control and leave it, which is when an edit is taken. */
async function typed(shell: TcApp, field: HTMLElement, value: string): Promise<void> {
  (field as HTMLInputElement).value = value;
  field.dispatchEvent(new Event("change"));
  await settled(shell);
}

async function pressed(shell: TcApp, selector: string, at = 0): Promise<void> {
  parts(shell, selector)[at]!.click();
  await settled(shell);
}

/** Write a product in the dialog, which is where one that does not exist yet
 *  is created. */
async function product(
  shell: TcApp,
  model: string,
  kind: string,
  length: string,
): Promise<void> {
  await pressed(shell, "button.new-model");
  const dialog = screen(shell).renderRoot.querySelector("sl-dialog")!;
  await typed(shell, dialog.querySelector("#model")!, model);
  await typed(shell, dialog.querySelector("#kind")!, kind);
  await typed(shell, dialog.querySelector("#length")!, length);
  (dialog.querySelector(".create") as HTMLElement).click();
  await settled(shell);
}

/** Make a train up, which is a one-field prompt like naming a railroad. */
async function train(shell: TcApp, name: string): Promise<void> {
  vi.spyOn(window, "prompt").mockReturnValue(name);
  await pressed(shell, "button.new-train");
}

/** Press the + beside one of the rows on the left, which puts it at the tail
 *  of the current train. */
async function add(shell: TcApp, list: "car" | "product", at: number): Promise<void> {
  await pressed(shell, `li.${list} button.add`, at);
}

/** The roster the screen last wrote, as the store was given it. */
function written(): RosterDoc | undefined {
  const put = store.saved.filter((one) => one.path.startsWith("/rosters/")).at(-1);
  return put?.body as RosterDoc | undefined;
}

/** Build the ore train of the acceptance: a locomotive with an address, and
 *  three hoppers with nothing of their own. */
async function ore(shell: TcApp): Promise<void> {
  await product(shell, "arnold-ce68", "locomotive", "122");
  await product(shell, "hopper", "freight", "100");
  await train(shell, "ore");
  // arnold-ce68 sorts before hopper, so the rows are in that order.
  await add(shell, "product", 0);
  await typed(shell, parts(shell, "li.entry input.addr")[0]!, "3");
  await add(shell, "product", 1);
  await add(shell, "product", 1);
  await add(shell, "product", 1);
}

describe("a fresh box", () => {
  it("draws nothing to begin with and says what to do first", async () => {
    const shell = await opened();
    expect(parts(shell, "li.car")).toHaveLength(0);
    expect(parts(shell, "li.product")).toHaveLength(0);
    expect(
      parts(shell, "p.hint").map((one) => one.textContent!.trim()),
    ).toContain("no models yet — a train is made of them, so write the first one");
  });

  /** A product does not exist yet, so it is created in the same dialog: the
   *  catalogue is a real document with its own route underneath and never a
   *  place a person navigates to for its own sake (#392). */
  it("writes a model to the catalogue the moment it is made", async () => {
    const shell = await opened();
    await product(shell, "hopper", "freight", "100");
    expect(store.saved).toEqual([
      { path: "/catalogue/hopper", body: { model: "hopper", kind: "freight", length: 100 } },
    ]);
    expect(parts(shell, "li.product")).toHaveLength(1);
  });

  it("refuses a length that is not one, where it was typed", async () => {
    const shell = await opened();
    await product(shell, "hopper", "freight", "a hundred");
    expect(store.saved).toEqual([]);
    const dialog = screen(shell).renderRoot.querySelector("sl-dialog")!;
    expect(dialog.querySelector(".trouble")!.textContent).toMatch("positive whole number");
  });
});

describe("making up a train", () => {
  /** The acceptance: one car entry and three model entries, the address
   *  written once (ADR-0061). */
  it("saves a document with one car entry and three model entries", async () => {
    const shell = await opened();
    await ore(shell);
    await pressed(shell, "sl-button.save");

    expect(written()).toEqual({
      roster: "toy",
      cars: { "arnold-ce68-1": { model: "arnold-ce68", addr: "3" } },
      trains: {
        ore: {
          cars: [
            { car: "arnold-ce68-1" },
            { model: "hopper" },
            { model: "hopper" },
            { model: "hopper" },
          ],
        },
      },
    });
  });

  it("shows the train's length as the sum of all four", async () => {
    const shell = await opened();
    await ore(shell);
    expect(parts(shell, ".derived")[0]!.textContent).toMatch("422 mm");
    expect(parts(shell, ".derived")[0]!.textContent).toMatch("freight");
  });

  /** Filling in an address promotes an anonymous item to a car in the list
   *  above, named from the model until a person calls it something else. */
  it("promotes an item to a car when an address is filled in", async () => {
    const shell = await opened();
    await ore(shell);
    const [row] = parts(shell, "li.car");
    expect((row!.querySelector("input.name") as HTMLInputElement).value).toBe(
      "arnold-ce68-1",
    );
    await typed(shell, row!.querySelector("input.name")!, "krokodil-a");
    expect(parts(shell, "li.entry .what")[0]!.textContent).toMatch("krokodil-a");
  });

  /** Two locomotives of one product keep their two addresses, written once,
   *  and neither is restated when a rake is made up (ADR-0061). */
  it("keeps two addresses for two locomotives of one model", async () => {
    const shell = await opened();
    await product(shell, "arnold-ce68", "locomotive", "122");
    await train(shell, "shed");
    await add(shell, "product", 0);
    await add(shell, "product", 0);
    await typed(shell, parts(shell, "li.entry input.addr")[0]!, "3");
    await typed(shell, parts(shell, "li.entry input.addr")[1]!, "4");
    await pressed(shell, "sl-button.save");

    expect(written()!.cars).toEqual({
      "arnold-ce68-1": { model: "arnold-ce68", addr: "3" },
      "arnold-ce68-2": { model: "arnold-ce68", addr: "4" },
    });
    expect(written()!.trains.shed!.cars).toEqual([
      { car: "arnold-ce68-1" },
      { car: "arnold-ce68-2" },
    ]);
  });

  /** The screen invites this order of work — make a train up, then fill it —
   *  so an empty train is easy to save. The store refuses one, and the
   *  refusal it answers is about a document; this one is about the row
   *  (#412). */
  it("refuses the save while a train has nothing in it, and sends no PUT", async () => {
    const shell = await opened();
    await product(shell, "hopper", "freight", "100");
    await train(shell, "ore");
    await pressed(shell, "sl-button.save");

    expect(written()).toBeUndefined();
    expect(trouble(shell)).toBe(
      "train 'ore' has nothing in it — press + beside a car or a model, or remove it",
    );
    // Still there to be filled, and the press is still there to make again.
    expect(parts(shell, "li.train")).toHaveLength(1);
    expect(
      (screen(shell).renderRoot.querySelector("sl-button.save") as HTMLElement & {
        disabled: boolean;
      }).disabled,
    ).toBe(false);

    await add(shell, "product", 0);
    await pressed(shell, "sl-button.save");
    expect(written()!.trains.ore!.cars).toEqual([{ model: "hopper" }]);
    expect(trouble(shell)).toBeNull();
  });

  it("says what holds a car somebody asked to remove, and keeps it", async () => {
    const shell = await opened();
    await ore(shell);
    await pressed(shell, "li.car button.remove");
    expect(screen(shell).renderRoot.querySelector(".trouble")!.textContent!.trim()).toBe(
      "car 'arnold-ce68-1' is held by train 'ore'",
    );
    expect(parts(shell, "li.car")).toHaveLength(1);
  });
});

describe("the length guard", () => {
  /** A UI guard in one browser: `tc-app` holds the run state and passes it
   *  down. A second browser editing stock during a run is not covered, which
   *  is the same hole as #390. */
  it("kills length editing while the run shows the train placed, and says why", async () => {
    const shell = await opened();
    await ore(shell);
    await pressed(shell, "sl-button.save");
    store.rosterOf = () => ({ ore: { length: 422 } });

    await said(shell, "tc49/dispatch/state/allocation", {
      trains: { ore: "a" },
      locks: { a: "ore" },
      requests: [],
    });
    await shows(shell, "stock");

    const car = parts(shell, "li.car input.length")[0] as HTMLInputElement;
    expect(car.disabled).toBe(true);
    expect(car.title).toMatch("'ore' is on the layout");
    for (const model of parts(shell, "li.product input.length")) {
      expect((model as HTMLInputElement).disabled).toBe(true);
    }
    expect(parts(shell, ".why")[0]!.textContent).toMatch("take it off to correct a length");
  });

  it("leaves length editing alone with nothing placed", async () => {
    const shell = await opened();
    await ore(shell);
    expect((parts(shell, "li.car input.length")[0] as HTMLInputElement).disabled).toBe(
      false,
    );
    expect(parts(shell, ".why")).toHaveLength(0);
  });
});

describe("the run view and the screen beside it", () => {
  /** The store is not on the bus, so nothing publishes a roster change: a
   *  person who makes a train up here must see it in Run without a reload. */
  it("shows a train made up here when the run view becomes current", async () => {
    const shell = await opened();
    await ore(shell);
    await pressed(shell, "sl-button.save");
    store.rosterOf = () => ({ ore: { length: 422 } });

    await shows(shell, "run");

    const rows = [
      ...running(shell)
        .renderRoot.querySelector("tc-roster")!
        .renderRoot.querySelectorAll("li"),
    ];
    expect(rows.map((row) => row.querySelector(".name")!.textContent!.trim())).toEqual([
      "ore",
    ]);
    expect(rows[0]!.querySelector(".length")!.textContent!.trim()).toBe("422");
  });

  it("keeps the roster it joined with until the view becomes current", async () => {
    const shell = await opened();
    store.rosterOf = () => ({ ore: { length: 422 } });
    const rows = () =>
      running(shell).renderRoot.querySelector("tc-roster")!.renderRoot.querySelectorAll("li");
    expect(rows()).toHaveLength(0);

    await shows(shell, "run");
    expect(rows()).toHaveLength(1);
  });
});

/**
 * A read or a write that does not come back with a document (#411).
 *
 * Three ways to fail and three sets of words, decided in the store helper
 * (`test/asking.test.ts`); what is under test here is that the screen shows
 * them rather than a fixed string, and that it reads again after the two a
 * person can only wait out.
 */
describe("a store that does not answer with a document", () => {
  /** What #405 was: the proxy's route table was stale, so `GET /catalogue`
   *  came back as its own 404 page while the store was up and answering the
   *  roster beside it. The screen said `run \`tc49 serve\`` — for a server
   *  that was running. */
  it("says what was asked and what came back, and reads again", async () => {
    vi.useFakeTimers();
    try {
      between((path) => path === "/catalogue");
      store.catalogue = { hopper: { model: "hopper", kind: "freight", length: 100 } };
      const shell = await opened();

      expect(trouble(shell)).toBe("GET /catalogue answered 404");
      expect(parts(shell, "li.product")).toHaveLength(0);

      store.intercepted = () => null;
      await vi.advanceTimersByTimeAsync(RETRY_MS);
      await settled(shell);

      expect(trouble(shell)).toBeNull();
      expect(parts(shell, "li.product")).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });

  /** Nothing answered at all keeps the words it had: the store is what is
   *  missing, and starting it is the fix. The store goes away under the
   *  roster read alone here, the drawing having arrived from it a moment
   *  earlier — which is what `fetch` rejecting looks like from this screen. */
  it("names `tc49 serve` where nothing answered, and reads again", async () => {
    vi.useFakeTimers();
    try {
      store.documentOf = () => {
        throw new TypeError("Failed to fetch");
      };
      const shell = await opened();

      expect(trouble(shell)).toBe("the store is not answering — run `tc49 serve`");

      store.documentOf = (railroad) => ({ roster: railroad, trains: {} });
      store.catalogue = { hopper: { model: "hopper", kind: "freight", length: 100 } };
      await vi.advanceTimersByTimeAsync(RETRY_MS);
      await settled(shell);

      expect(trouble(shell)).toBeNull();
      expect(parts(shell, "li.product")).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });

  /** The same 404 met by the Create press. The dialog stays open with the
   *  message beside the button, so the product is still there to write again
   *  once the route is back. */
  it("leaves the dialog open and names the write that did not land", async () => {
    const shell = await opened();
    between((path) => path.startsWith("/catalogue/"));

    await product(shell, "hopper", "freight", "100");

    const dialog = screen(shell).renderRoot.querySelector("sl-dialog")!;
    expect(dialog).not.toBeNull();
    expect(dialog.querySelector(".trouble")!.textContent!.trim()).toBe(
      "PUT /catalogue/hopper answered 404",
    );
    expect(store.saved).toEqual([]);
    expect(parts(shell, "li.product")).toHaveLength(0);
  });
});
