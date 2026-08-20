// @vitest-environment happy-dom

/**
 * Opening another drawing, and starting one, over edits the store has not been
 * given (#101).
 *
 * A DOM test of the shell: what is thrown away is the shell's own state — the
 * drawing, the flag the band's dot reads, the snapshots undo walks — and the
 * question is a dialog the operator answers. It mounts the shell the way
 * `refusals.test.ts` does.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-editor.js";
import type { Drawing } from "../src/model/drawing.js";
import type { TcEditor } from "../src/ui/tc-editor.js";
import { mounted, serving, session, settled } from "./support/shell.js";

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
  serving({ drawings: ["gotthard", "otira"], read: stored });
});

// A shell listens on the window for as long as it is in the page, so one left
// behind would answer the next test's keystrokes too.
afterEach(() => {
  document.body.replaceChildren();
});

/** A mounted editor with `gotthard` open and saved, which is where every test
 *  here starts. */
async function opened(): Promise<TcEditor> {
  const shell = await mounted();
  await choose(shell, "gotthard");
  return shell;
}

/** Choose a drawing on the bar, which is the one way one is opened. */
async function choose(shell: TcEditor, name: string): Promise<void> {
  shell.renderRoot
    .querySelector("tc-menubar")!
    .dispatchEvent(new CustomEvent<string>("open-drawing", { detail: name }));
  await settled(shell);
}

/** Choose a drawing the way the operator does: the bar's `File` menu, the
 *  drawings `Open` lists, and a click on the entry. `choose` hands the shell
 *  the event the bar would have sent, which is past the bar's own guard on the
 *  ticked entry; this goes through it. */
async function picked(shell: TcEditor, name: string): Promise<void> {
  const bar = shell.renderRoot.querySelector("tc-menubar")!;
  const titles = [...bar.renderRoot.querySelectorAll("button.title")];
  (titles.find((one) => one.textContent!.trim() === "File") as HTMLElement).click();
  await settled(shell);
  (bar.renderRoot.querySelector("li.submenu button") as HTMLElement).click();
  await settled(shell);
  const entries = [...bar.renderRoot.querySelectorAll("menu.drawings li button")];
  const entry = entries.find(
    (one) => one.querySelector(".label")!.textContent!.trim() === name,
  ) as HTMLElement;
  entry.click();
  await settled(shell);
}

/** Ask for a new drawing, which is the other way the open one is thrown
 *  away. */
async function fresh(shell: TcEditor): Promise<void> {
  shell.renderRoot
    .querySelector("tc-menubar")!
    .dispatchEvent(new CustomEvent<string>("command", { detail: "new" }));
  await settled(shell);
}

/** Draw something, which is what leaves the drawing unsaved. */
async function drawn(shell: TcEditor): Promise<void> {
  session(shell).place("block", [4, 0]);
  shell.renderRoot.querySelector("tc-canvas")!.dispatchEvent(new CustomEvent("edit"));
  await settled(shell);
}

/** The question, `null` while none is up. */
function asked(shell: TcEditor): Element | null {
  return shell.renderRoot.querySelector("sl-dialog");
}

/** Answer it, the way the two buttons in its footer read. */
async function answer(shell: TcEditor, said: string): Promise<void> {
  const buttons = [...shell.renderRoot.querySelectorAll("sl-dialog sl-button")];
  const button = buttons.find((one) => one.textContent!.trim() === said);
  (button as HTMLElement).click();
  await settled(shell);
}

/** The drawing the band names as open. */
function open(shell: TcEditor): string {
  const band = shell.renderRoot.querySelector("tc-header")!;
  return band.renderRoot.querySelector(".drawing")!.textContent!.trim();
}

/** Whether the band shows the dot that says there are edits to lose. */
function unsaved(shell: TcEditor): boolean {
  const band = shell.renderRoot.querySelector("tc-header")!;
  return band.renderRoot.querySelector(".unsaved") !== null;
}

describe("opening a drawing over unsaved edits", () => {
  it("asks before anything is read or reset", async () => {
    const shell = await opened();
    await drawn(shell);

    await choose(shell, "otira");

    expect(asked(shell)).not.toBeNull();
    expect(open(shell)).toBe("gotthard");
  });

  /** Declining costs nothing at all: the same drawing, the same edits, the
   *  same dot, and undo still holding the step that made them. */
  it("leaves everything as it was when the edits are kept", async () => {
    const shell = await opened();
    await drawn(shell);
    await choose(shell, "otira");

    await answer(shell, "Cancel");

    expect(asked(shell)).toBeNull();
    expect(open(shell)).toBe("gotthard");
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

    expect(asked(shell)!.textContent).toContain("'gotthard'");
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
    expect(open(shell)).toBe("gotthard");
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
    expect(open(shell)).toBe("gotthard");
  });

  it("leaves everything as it was when the edits are kept", async () => {
    const shell = await opened();
    await drawn(shell);
    await fresh(shell);

    await answer(shell, "Cancel");

    expect(asked(shell)).toBeNull();
    expect(open(shell)).toBe("gotthard");
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

    await picked(shell, "gotthard");

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
