// @vitest-environment happy-dom

/**
 * Starting a railroad over edits the store has not been given (#101, #415).
 *
 * A DOM test of the shell: what is thrown away is the shell's own state — the
 * drawing, the flag the band's dot reads, the snapshots undo walks — and the
 * question is a dialog the operator answers. It mounts the shell the way
 * `refusals.test.ts` does.
 *
 * **`File ▸ New` is the one gesture that asks.** The railroad itself arrives
 * on the bus — the broker says which one it runs and the app reads it off the
 * store (#371, ADR-0059 decision 2) — and nobody is at the keyboard to have
 * meant that, so it is loaded rather than asked about. The picker that used to
 * ask went with the bridge.
 *
 * The roster is here for the same reason the drawing is: it is the second
 * document the loaded railroad carries, the stock view holds it, and starting
 * another throws it away. The question is the app's either way, so it is asked
 * about here rather than in the stock view's own suites (#415).
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-app.js";
import type { Drawing } from "../src/model/drawing.js";
import type { ModelDoc, RosterDoc } from "../src/model/store.js";
import type { TcApp } from "../src/ui/tc-app.js";
import {
  edited,
  mounted,
  serving,
  session,
  settled,
  shows,
  stocking,
} from "./support/shell.js";
import { loads } from "./support/session.js";

/** A drawing a red pin short of nothing, one per name the store has. */
function stored(name: string): Drawing {
  return {
    drawing: name,
    symbols: { e1: { kind: "terminal", at: [0, 0] } },
    wires: [],
  };
}

/** What the operator types when `File ▸ New…` asks for a name. */
const NAMED = "arth-goldau";

beforeEach(() => {
  window.prompt = () => NAMED;
  serving({ drawings: ["reversing-loops", "otira"], read: stored });
});

// A shell listens on the window for as long as it is in the page, so one left
// behind would answer the next test's keystrokes too.
afterEach(() => {
  document.body.replaceChildren();
});

/** A mounted editor with `reversing-loops` open and saved, which is where every
 *  test here starts. */
async function opened(): Promise<TcApp> {
  const shell = await mounted();
  await loads(shell, "reversing-loops");
  return shell;
}

/** Ask for a new drawing, which is the other way the open one is thrown
 *  away. */
async function fresh(shell: TcApp): Promise<void> {
  shell.renderRoot
    .querySelector("tc-menubar")!
    .dispatchEvent(new CustomEvent<string>("command", { detail: "new" }));
  await settled(shell);
}

/** Draw something, which is what leaves the drawing unsaved. */
async function drawn(shell: TcApp): Promise<void> {
  session(shell).place("block", [4, 0]);
  edited(shell);
  await settled(shell);
}

/** The question, `null` while none is up. */
function asked(shell: TcApp): Element | null {
  return shell.renderRoot.querySelector("sl-dialog");
}

/** Answer it, the way the two buttons in its footer read. */
async function answer(shell: TcApp, said: string): Promise<void> {
  const buttons = [...shell.renderRoot.querySelectorAll("sl-dialog sl-button")];
  const button = buttons.find((one) => one.textContent!.trim() === said);
  (button as HTMLElement).click();
  await settled(shell);
}

/** The drawing the band names as open. */
function open(shell: TcApp): string {
  const band = shell.renderRoot.querySelector("tc-header")!;
  return band.renderRoot.querySelector(".drawing")!.textContent!.trim();
}

/** Whether the band shows the dot that says there are edits to lose. */
function unsaved(shell: TcApp): boolean {
  const band = shell.renderRoot.querySelector("tc-header")!;
  return band.renderRoot.querySelector(".unsaved") !== null;
}

describe("starting a new drawing over unsaved edits", () => {
  /** The name is asked for after the edits are, not before: a prompt answered
   *  and then a discard declined would have asked for nothing. */
  it("asks before anything is reset, and asks for no name yet", async () => {
    const shell = await opened();
    await drawn(shell);
    let asks = 0;
    window.prompt = () => {
      asks++;
      return NAMED;
    };

    await fresh(shell);

    expect(asked(shell)).not.toBeNull();
    expect(asks).toBe(0);
    expect(open(shell)).toBe("reversing-loops");
  });

  it("leaves everything as it was when the edits are kept", async () => {
    const shell = await opened();
    await drawn(shell);
    await fresh(shell);

    await answer(shell, "Cancel");

    expect(asked(shell)).toBeNull();
    expect(open(shell)).toBe("reversing-loops");
    expect(unsaved(shell)).toBe(true);
    expect(session(shell).canUndo).toBe(true);
  });

  it("empties the canvas under the new name once they are given up", async () => {
    const shell = await opened();
    await drawn(shell);
    await fresh(shell);

    await answer(shell, "Discard");

    expect(open(shell)).toBe(NAMED);
    expect(session(shell).drawing.symbols).toEqual({});
  });

  it("starts one straight away when there is nothing to lose", async () => {
    const shell = await opened();

    await fresh(shell);

    expect(asked(shell)).toBeNull();
    expect(open(shell)).toBe(NAMED);
  });

  /** Nothing is loaded until the broker names a railroad, and what is drawn
   *  before that is worth the same question — under a name the band has
   *  not got. */
  it("asks about a canvas drawn on before anything was loaded", async () => {
    const shell = await mounted();
    await drawn(shell);

    await fresh(shell);

    expect(asked(shell)!.textContent).toContain("The canvas has edits");
  });

  /** The question is modal, so Escape is its: it declines, and the selection
   *  behind it is not the canvas's to clear on the way. */
  it("takes Escape as a refusal, and the canvas hears nothing", async () => {
    const shell = await opened();
    await drawn(shell);
    await fresh(shell);

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await settled(shell);

    expect(asked(shell)).toBeNull();
    expect(open(shell)).toBe("reversing-loops");
    expect([...session(shell).selection]).toEqual(["b1"]);
  });
});

/**
 * A canvas just started has no file — the dot is up, honestly — but nothing
 * has been drawn on it, so there is nothing an operator would recognise as
 * lost and nothing to ask about (#136).
 */
describe("a new drawing nothing has been drawn on", () => {
  it("shows as unsaved, the file not existing yet", async () => {
    const shell = await mounted();

    await fresh(shell);

    expect(open(shell)).toBe(NAMED);
    expect(unsaved(shell)).toBe(true);
  });

  it("is thrown away for another new one without a question", async () => {
    const shell = await mounted();
    await fresh(shell);

    await fresh(shell);

    expect(asked(shell)).toBeNull();
    expect(open(shell)).toBe(NAMED);
  });

  it("is thrown away for the railroad the broker names, without a question", async () => {
    const shell = await mounted();
    await fresh(shell);

    await loads(shell, "otira");

    expect(asked(shell)).toBeNull();
    expect(open(shell)).toBe("otira");
  });

  it("asks once anything has been drawn on it", async () => {
    const shell = await mounted();
    await fresh(shell);
    await drawn(shell);

    await fresh(shell);

    expect(asked(shell)).not.toBeNull();
    expect(open(shell)).toBe(NAMED);
  });
});

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
});

/**
 * The roster is the railroad's other document, and the stock view holds it
 * unsaved the same way the editor holds the drawing (#415).
 *
 * What the store answers is a train to compose into and a model to compose
 * from, so one press of `+` beside the model is an edit nobody has saved.
 */
describe("starting a railroad over unsaved roster edits", () => {
  const HOPPER: ModelDoc = { model: "hopper", kind: "freight", length: 100 };

  /** A railroad that owns one rake of one hopper, whichever name is asked
   *  for: the count of entries is what says which railroad the screen is
   *  showing. */
  function owned(railroad: string): RosterDoc {
    return {
      roster: railroad,
      cars: {},
      trains: { ore: { cars: [{ model: "hopper" }] } },
    };
  }

  /** The app in the stock view with `reversing-loops` loaded and its roster
   *  read. The drawing is what the store answered, so it is clean. */
  async function stocked(): Promise<TcApp> {
    serving({
      drawings: ["reversing-loops", "otira"],
      read: stored,
      catalogue: { hopper: HOPPER },
      documentOf: owned,
    });
    const shell = await mounted("stock");
    await loads(shell, "reversing-loops");
    return shell;
  }

  /** Compose: the `+` beside a model, which appends it to the current train
   *  and is the whole of composing right from left. */
  async function composed(shell: TcApp): Promise<void> {
    stocking(shell)
      .renderRoot.querySelector<HTMLElement>("li.product button.add")!
      .click();
    await settled(shell);
  }

  /** Press Save beside the trains, which gives the roster to the store. */
  async function kept(shell: TcApp): Promise<void> {
    stocking(shell).renderRoot.querySelector<HTMLElement>("sl-button.save")!.click();
    await settled(shell);
  }

  /** How many places the current train has, which is what an appended entry
   *  moves and what a reloaded roster puts back. */
  function entries(shell: TcApp): number {
    return stocking(shell).renderRoot.querySelectorAll("li.entry").length;
  }

  it("asks before `File ▸ New` changes anything, and names the roster", async () => {
    const shell = await stocked();
    await composed(shell);
    expect(entries(shell)).toBe(2);

    await fresh(shell);

    expect(asked(shell)!.textContent).toContain("has edits that have not been saved");
    expect(asked(shell)!.textContent).toContain("the roster");
    expect(asked(shell)!.textContent).not.toContain("the drawing");
    expect(open(shell)).toBe("reversing-loops");
  });

  /** Declining costs nothing: the same railroad, and the rake still being
   *  composed. */
  it("leaves the rake being composed in place when the edits are kept", async () => {
    const shell = await stocked();
    await composed(shell);
    await fresh(shell);

    await answer(shell, "Cancel");

    expect(asked(shell)).toBeNull();
    expect(open(shell)).toBe("reversing-loops");
    expect(entries(shell)).toBe(2);
  });

  it("starts the railroad once they are given up, and reads its roster", async () => {
    const shell = await stocked();
    await composed(shell);
    await fresh(shell);

    await answer(shell, "Discard");

    expect(asked(shell)).toBeNull();
    expect(open(shell)).toBe(NAMED);
    expect(entries(shell)).toBe(1);
  });

  /** One question, and it says which of the two documents is at stake — a
   *  person who has drawn and composed loses both. */
  it("names both documents where both have edits", async () => {
    const shell = await stocked();
    await drawn(shell);
    await composed(shell);

    await fresh(shell);

    expect(asked(shell)!.textContent).toContain("the drawing and the roster");
  });

  /** The drawing alone reads as it always did, the roster having nothing to
   *  lose. */
  it("names the drawing alone where the roster is clean", async () => {
    const shell = await stocked();
    await drawn(shell);

    await fresh(shell);

    expect(asked(shell)!.textContent).toContain("the drawing");
    expect(asked(shell)!.textContent).not.toContain("the roster");
  });

  it("asks nothing once the roster has been saved", async () => {
    const shell = await stocked();
    await composed(shell);
    await kept(shell);

    await fresh(shell);

    expect(asked(shell)).toBeNull();
    expect(open(shell)).toBe(NAMED);
  });

  /** Switching view changes no railroad, so nothing is read again and the
   *  rake comes back as it was left. */
  it("keeps the rake across a look at another view", async () => {
    const shell = await stocked();
    await composed(shell);

    await shows(shell, "run");
    await shows(shell, "stock");

    expect(asked(shell)).toBeNull();
    expect(entries(shell)).toBe(2);
  });
});
