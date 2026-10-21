// @vitest-environment happy-dom

/**
 * The railroad the broker names, and the one it does not (#371, #727).
 *
 * A DOM test of the shell: what is opened and what is closed is the shell's
 * own state — the drawing, the flag the band's dot reads, the snapshots undo
 * walks — and the stock view beside it. It mounts the shell the way
 * `refusals.test.ts` does.
 *
 * **The row is the one thing that opens or closes a railroad.** The broker
 * says which one it runs and the app reads it off the store (ADR-0059
 * decision 2), and nobody is at the keyboard to have meant that, so it is
 * loaded rather than asked about; the settings dialog's press is a gesture on
 * the bus and asks nothing either (ADR-0060, ADR-0072). The editor holds that
 * railroad and no other (ADR-0072, decision 3): New and Save As, which once
 * left it on a drawing nothing runs, went with #734, and the question before
 * edits were thrown away went with them, no gesture of a person's throwing
 * any away now.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../src/ui/tc-app.js";
import { emptyDrawing, type Drawing } from "../src/model/drawing.js";
import { RETRY_MS, type ModelDoc, type RosterDoc } from "../src/model/store.js";
import type { TcApp } from "../src/ui/tc-app.js";
import type { TcCanvas } from "../src/ui/tc-canvas.js";
import {
  band,
  edited,
  mounted,
  named,
  railButton,
  running,
  serving,
  session,
  settled,
  shows,
  stocking,
  type Answers,
} from "./support/shell.js";
import { DERIVES, loads, stored as derived, unbrokered } from "./support/session.js";

/** A drawing a red pin short of nothing, one per name the store has. */
function stored(name: string): Drawing {
  return {
    drawing: name,
    symbols: { e1: { kind: "terminal", at: [0, 0] } },
    wires: [],
  };
}

beforeEach(() => {
  serving({ drawings: ["reversing-loops", "otira"], read: stored });
});

// A shell listens on the window for as long as it is in the page, so one left
// behind would answer the next test's keystrokes too.
afterEach(() => {
  document.body.replaceChildren();
});

/** A mounted editor with `reversing-loops` open and saved, which is where every
 *  test here starts. */
async function opened(view: "edit" | "stock" = "edit"): Promise<TcApp> {
  const shell = await mounted(view);
  await loads(shell, "reversing-loops");
  return shell;
}

/** Draw something, which is what leaves the drawing unsaved. */
async function drawn(shell: TcApp): Promise<void> {
  session(shell).place("block", [4, 0]);
  edited(shell);
  await settled(shell);
}

/** The question a discard once asked, `null` while none is up — which is
 *  always, now, and what the suite says of every row. */
function asked(shell: TcApp): Element | null {
  return shell.renderRoot.querySelector("look-dialog[open]");
}

/** The drawing open in the editor. */
function open(shell: TcApp): string {
  return session(shell).drawing.drawing;
}

/** Whether the band shows the dot that says there are edits to lose. */
function unsaved(shell: TcApp): boolean {
  return band(shell).querySelector("look-about")!.detail === "unsaved";
}

/**
 * The retained row the broker holds is republished whenever a page
 * resubscribes, so the railroad it names arrives again and again. It is the
 * one the app already has, and nothing is thrown away for it (#136, #371).
 */
describe("the railroad the broker names", () => {
  it("leaves the edits, the dot and the undo history untouched where it is the one loaded", async () => {
    const shell = await opened();
    await drawn(shell);

    await loads(shell, "reversing-loops");

    expect(asked(shell)).toBeNull();
    expect(unsaved(shell)).toBe(true);
    expect(session(shell).canUndo).toBe(true);
    expect(Object.keys(session(shell).drawing.symbols).sort()).toEqual(["b1", "e1"]);
  });

  /** Another name does load, so what is asserted above is the app reading the
   *  row and not the row going nowhere. */
  it("loads one that is not the railroad already loaded", async () => {
    const shell = await opened();

    await loads(shell, "otira");

    expect(open(shell)).toBe("otira");
  });

  /** The row is a fact the layout interface reports and not a press anybody
   *  made, so nothing asks: whatever was drawn goes with the railroad. */
  it("loads it over unsaved edits without a question", async () => {
    const shell = await opened();
    await drawn(shell);

    await loads(shell, "otira");

    expect(asked(shell)).toBeNull();
    expect(open(shell)).toBe("otira");
    expect(unsaved(shell)).toBe(false);
  });
});

/**
 * A row naming `""` is a broker with no railroad loaded (#727), and the editor
 * holds the loaded railroad and no other (ADR-0072, decision 3): so it holds
 * nothing, and the stock view beside it holds nothing either.
 */
describe("the row naming no railroad", () => {
  it("closes the drawing, with nothing unsaved", async () => {
    const shell = await opened();
    await drawn(shell);

    await loads(shell, "");

    expect(asked(shell)).toBeNull();
    expect(session(shell).drawing).toEqual(emptyDrawing(""));
    expect(open(shell)).toBe("");
    expect(unsaved(shell)).toBe(false);
  });

  it("leaves the stock view with no railroad", async () => {
    const shell = await opened("stock");
    expect(stocking(shell).railroad!.name).toBe("reversing-loops");

    await loads(shell, "");

    expect(stocking(shell).railroad!.name).toBe("");
    const making = stocking(shell).renderRoot.querySelector<HTMLButtonElement>(
      "button.new-model",
    )!;
    expect(making.disabled).toBe(true);
    expect(making.title).toBe("load a railroad first");
  });

  it("opens the railroad the row names next", async () => {
    const shell = await opened();
    await loads(shell, "");

    await loads(shell, "otira");

    expect(open(shell)).toBe("otira");
    expect(railButton(shell, "export-svg")!.disabled).toBe(false);
  });
});

/**
 * The roster is the railroad's other document, and the stock view holds it
 * unsaved the same way the editor holds the drawing (#415). Switching view
 * changes no railroad, so nothing is read again.
 */
describe("the roster across a look at another view", () => {
  const HOPPER: ModelDoc = { model: "hopper", kind: "freight", length: 100 };

  /** A railroad that owns one rake of one hopper, whichever name is asked
   *  for. */
  function owned(railroad: string): RosterDoc {
    return {
      roster: railroad,
      cars: {},
      trains: { ore: { cars: [{ model: "hopper" }] } },
    };
  }

  /** The app in the stock view with `reversing-loops` loaded and its roster
   *  read. */
  async function stocked(): Promise<TcApp> {
    serving({
      drawings: ["reversing-loops", "otira"],
      read: stored,
      catalogue: { hopper: HOPPER },
      documentOf: owned,
    });
    return await opened("stock");
  }

  /** Compose: the `+` beside a model, which appends it to the current train
   *  and is the whole of composing right from left. */
  async function composed(shell: TcApp): Promise<void> {
    stocking(shell)
      .renderRoot.querySelector<HTMLElement>("li.product button.add")!
      .click();
    await settled(shell);
  }

  /** How many places the current train has, which is what an appended entry
   *  moves and what a reloaded roster puts back. */
  function entries(shell: TcApp): number {
    return stocking(shell).renderRoot.querySelectorAll("li.entry").length;
  }

  it("keeps the rake being composed", async () => {
    const shell = await stocked();
    await composed(shell);
    expect(entries(shell)).toBe(2);

    await shows(shell, "run");
    await shows(shell, "stock");

    expect(asked(shell)).toBeNull();
    expect(entries(shell)).toBe(2);
  });
});

/**
 * The store not answering when the row names a railroad (#758). The row is
 * the broker's and arrives whatever the store is doing, so the documents it
 * names are read again until the store answers — and until then no view holds
 * the railroad that was loaded before, whose drawing under another railroad's
 * name is a picture of nothing that runs (ADR-0072, decision 3).
 */
describe("the store not answering for the railroad the row names", () => {
  const HOPPER: ModelDoc = { model: "hopper", kind: "freight", length: 100 };

  /** A store with a deriving drawing, a train and a rake for any railroad
   *  asked for, each named after it. */
  function served(): Answers {
    return serving({
      drawings: ["toy", "otira"],
      read: derived,
      review: () => Promise.resolve(DERIVES),
      rosterOf: (railroad) => ({ [`${railroad}-goods`]: { length: 400 } }),
      documentOf: (railroad) => ({
        roster: railroad,
        trains: { [`${railroad}-ore`]: { cars: [{ model: "hopper" }] } },
      }),
      catalogue: { hopper: HOPPER },
    });
  }

  /** What each view holds of a railroad: the editor's drawing, the run view's
   *  painted drawing and its roster pane, and the stock view's trains. */
  function held(shell: TcApp) {
    const canvas = running(shell).renderRoot.querySelector<TcCanvas>("tc-canvas");
    const pane = running(shell).renderRoot.querySelector("tc-roster")!.renderRoot;
    return {
      editor: session(shell).drawing.drawing,
      run: canvas === null ? null : canvas.drawing.drawing,
      roster: [...pane.querySelectorAll("span.name")].map((one) => one.textContent!.trim()),
      stock: [
        ...stocking(shell).renderRoot.querySelectorAll<HTMLInputElement>("li.train input.name"),
      ].map((one) => one.value),
    };
  }

  /** Everything of one railroad, in every view. */
  function all(railroad: string) {
    return {
      editor: railroad,
      run: railroad,
      roster: [`${railroad}-goods`],
      stock: [`${railroad}-ore`],
    };
  }

  const NOTHING = { editor: "", run: null, roster: [], stock: [] };

  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    unbrokered();
  });

  it("holds the railroad in every view once the store answers, with no reload", async () => {
    const store = served();
    store.broken = new Error("connection refused");
    const shell = await mounted("run");
    await loads(shell, "toy");
    expect(held(shell)).toEqual(NOTHING);

    store.broken = null;
    await vi.advanceTimersByTimeAsync(RETRY_MS);
    await settled(shell);

    expect(held(shell)).toEqual(all("toy"));
  });

  it("holds nothing of the last railroad until the next one is read", async () => {
    const store = served();
    const shell = await mounted("run");
    await loads(shell, "toy");
    expect(held(shell)).toEqual(all("toy"));

    store.broken = new Error("connection refused");
    await loads(shell, "otira");

    expect(named(shell)).toBe("otira");
    expect(held(shell)).toEqual(NOTHING);

    store.broken = null;
    await vi.advanceTimersByTimeAsync(RETRY_MS);
    await settled(shell);

    expect(held(shell)).toEqual(all("otira"));
  });
});
