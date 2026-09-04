// @vitest-environment happy-dom

/**
 * Opening another drawing, and starting one, over edits the store has not been
 * given (#101, #415).
 *
 * A DOM test of the shell: what is thrown away is the shell's own state — the
 * drawing, the flag the band's dot reads, the snapshots undo walks — and the
 * question is a dialog the operator answers. It mounts the shell the way
 * `refusals.test.ts` does.
 *
 * The roster is here for the same reason the drawing is: it is the second
 * document the loaded railroad carries, the stock view holds it, and changing
 * the railroad throws it away. The question is the app's either way, so it is
 * asked about here rather than in the stock view's own suites (#415).
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

/** A mounted editor with `reversing-loops` open and saved, which is where every test
 *  here starts. */
async function opened(): Promise<TcApp> {
  const shell = await mounted();
  await choose(shell, "reversing-loops");
  return shell;
}

/** Choose a railroad in the band, which is the one way one is loaded. */
async function choose(shell: TcApp, name: string): Promise<void> {
  shell.renderRoot
    .querySelector("tc-header")!
    .dispatchEvent(new CustomEvent<string>("railroad-wanted", { detail: name }));
  await settled(shell);
}

/** Choose a railroad the way the operator does: the band's picker, and a
 *  click on the entry. `choose` hands the shell the event the band would have
 *  sent, which is past the band's own guard on the ticked entry; this goes
 *  through it. */
async function picked(shell: TcApp, name: string): Promise<void> {
  const band = shell.renderRoot.querySelector("tc-header")!;
  (band.renderRoot.querySelector("button.chosen") as HTMLElement).click();
  await settled(shell);
  const entries = [...band.renderRoot.querySelectorAll("menu.drawings li button")];
  const entry = entries.find(
    (one) => one.querySelector(".label")!.textContent!.trim() === name,
  ) as HTMLElement;
  entry.click();
  await settled(shell);
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

describe("opening a drawing over unsaved edits", () => {
  it("asks before anything is read or reset", async () => {
    const shell = await opened();
    await drawn(shell);

    await choose(shell, "otira");

    expect(asked(shell)).not.toBeNull();
    expect(open(shell)).toBe("reversing-loops");
  });

  /** Declining costs nothing at all: the same drawing, the same edits, the
   *  same dot, and undo still holding the step that made them. */
  it("leaves everything as it was when the edits are kept", async () => {
    const shell = await opened();
    await drawn(shell);
    await choose(shell, "otira");

    await answer(shell, "Cancel");

    expect(asked(shell)).toBeNull();
    expect(open(shell)).toBe("reversing-loops");
    expect(unsaved(shell)).toBe(true);
    expect(Object.keys(session(shell).drawing.symbols).sort()).toEqual(["b1", "e1"]);
    expect(session(shell).canUndo).toBe(true);
  });

  it("opens the drawing chosen once the edits are given up", async () => {
    const shell = await opened();
    await drawn(shell);
    await choose(shell, "otira");

    await answer(shell, "Discard");

    expect(asked(shell)).toBeNull();
    expect(open(shell)).toBe("otira");
    expect(unsaved(shell)).toBe(false);
    expect(session(shell).canUndo).toBe(false);
  });

  /** The question names both drawings: the one about to be thrown away and
   *  the one asked for. */
  it("names what is at stake and what was asked for", async () => {
    const shell = await opened();
    await drawn(shell);

    await choose(shell, "otira");

    expect(asked(shell)!.textContent).toContain("'reversing-loops'");
    expect(asked(shell)!.textContent).toContain("'otira'");
  });

  /** Nothing is open until a drawing is chosen, and what is drawn before that
   *  is worth the same question — under a name the band does not have. */
  it("asks about a canvas drawn on before anything was opened", async () => {
    const shell = await mounted();
    await drawn(shell);

    await choose(shell, "otira");

    expect(asked(shell)!.textContent).toContain("The canvas has edits");
  });

  /** The question is modal, so Escape is its: it declines, and the selection
   *  behind it is not the canvas's to clear on the way. */
  it("takes Escape as a refusal, and the canvas hears nothing", async () => {
    const shell = await opened();
    await drawn(shell);
    await choose(shell, "otira");

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await settled(shell);

    expect(asked(shell)).toBeNull();
    expect(open(shell)).toBe("reversing-loops");
    expect([...session(shell).selection]).toEqual(["b1"]);
  });

  it("opens straight away when there is nothing to lose", async () => {
    const shell = await opened();

    await choose(shell, "otira");

    expect(asked(shell)).toBeNull();
    expect(open(shell)).toBe("otira");
  });
});

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

  it("is thrown away for a drawing opened without a question", async () => {
    const shell = await mounted();
    await fresh(shell);

    await choose(shell, "otira");

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
 * The tick says which drawing is open and nothing more. The bar asks for
 * nothing when it is clicked (`menubar.test.ts`), and this is what that buys
 * at the editor: the assertion that survives the guard moving (#136).
 */
describe("choosing the drawing already open", () => {
  it("leaves the edits, the dot and the undo history untouched", async () => {
    const shell = await opened();
    await drawn(shell);

    await picked(shell, "reversing-loops");

    expect(asked(shell)).toBeNull();
    expect(unsaved(shell)).toBe(true);
    expect(session(shell).canUndo).toBe(true);
    expect(Object.keys(session(shell).drawing.symbols).sort()).toEqual(["b1", "e1"]);
  });

  /** The same click on the entry beside it does open, so what is asserted
   *  above is the tick's doing and not the click going nowhere. */
  it("opens one that is not the drawing already open", async () => {
    const shell = await opened();

    await picked(shell, "otira");

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
describe("opening a railroad over unsaved roster edits", () => {
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
    await choose(shell, "reversing-loops");
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

  it("asks before the picker changes anything, and names the roster", async () => {
    const shell = await stocked();
    await composed(shell);
    expect(entries(shell)).toBe(2);

    await choose(shell, "otira");

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
    await choose(shell, "otira");

    await answer(shell, "Cancel");

    expect(asked(shell)).toBeNull();
    expect(open(shell)).toBe("reversing-loops");
    expect(entries(shell)).toBe(2);
  });

  it("opens the railroad chosen once they are given up, and reads its roster", async () => {
    const shell = await stocked();
    await composed(shell);
    await choose(shell, "otira");

    await answer(shell, "Discard");

    expect(asked(shell)).toBeNull();
    expect(open(shell)).toBe("otira");
    expect(entries(shell)).toBe(1);
  });

  /** One question, and it says which of the two documents is at stake — a
   *  person who has drawn and composed loses both. */
  it("names both documents where both have edits", async () => {
    const shell = await stocked();
    await drawn(shell);
    await composed(shell);

    await choose(shell, "otira");

    expect(asked(shell)!.textContent).toContain("the drawing and the roster");
  });

  /** The drawing alone reads as it always did, the roster having nothing to
   *  lose. */
  it("names the drawing alone where the roster is clean", async () => {
    const shell = await stocked();
    await drawn(shell);

    await choose(shell, "otira");

    expect(asked(shell)!.textContent).toContain("the drawing");
    expect(asked(shell)!.textContent).not.toContain("the roster");
  });

  it("asks nothing once the roster has been saved", async () => {
    const shell = await stocked();
    await composed(shell);
    await kept(shell);

    await choose(shell, "otira");

    expect(asked(shell)).toBeNull();
    expect(open(shell)).toBe("otira");
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
