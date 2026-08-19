// @vitest-environment happy-dom

/**
 * Opening another drawing, and starting one, over edits the store has not been
 * given (#101).
 *
 * A DOM test of the shell: what is thrown away is the shell's own state — the
 * drawing, the flag the band's dot reads, the snapshots undo walks — and the
 * question is a dialog the operator answers. It mounts the shell the way
 * `findings.test.ts` does.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-editor.js";
import type { Drawing } from "../src/model/drawing.js";
import type { Editor } from "../src/model/editor.js";
import type { Review } from "../src/model/store.js";
import type { TcEditor } from "../src/ui/tc-editor.js";

/** A drawing a red pin short of nothing, one per name the store has. */
function stored(name: string): Drawing {
  return {
    drawing: name,
    symbols: { e1: { kind: "terminal", at: [0, 0] } },
    wires: [],
  };
}

/** A drawing the store is happy with: nothing to report. */
const CLEAN: Review = {
  red_pins: [],
  unpaired_portals: [],
  junctions: [],
  joints: [],
  layout: null,
  explain: null,
  refused: null,
};

/** What the operator types when `File ▸ New…` asks for a name. */
const NAMED = "arth-goldau";

beforeEach(() => {
  window.prompt = () => NAMED;
  globalThis.fetch = ((path: string) => {
    const body =
      path === "/review"
        ? CLEAN
        : path === "/drawings"
          ? { drawings: ["gotthard", "otira"] }
          : stored(path.slice("/drawings/".length));
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve(body),
    } as unknown as Response);
  }) as unknown as typeof fetch;
});

// A shell listens on the window for as long as it is in the page, so one left
// behind would answer the next test's keystrokes too.
afterEach(() => {
  document.body.replaceChildren();
});

/** Let the reviews and reads in flight settle, then let Lit paint what they
 *  said — the band included, the dot being what it draws. */
async function settled(shell: TcEditor): Promise<void> {
  for (let turn = 0; turn < 10; turn++) await Promise.resolve();
  await shell.updateComplete;
  await shell.renderRoot.querySelector("tc-header")!.updateComplete;
}

/** A mounted editor with `gotthard` open and saved, which is where every test
 *  here starts. */
async function mounted(): Promise<TcEditor> {
  const shell = document.createElement("tc-editor");
  document.body.append(shell);
  await settled(shell);
  await choose(shell, "gotthard");
  return shell;
}

/** The session the shell is editing. */
function session(shell: TcEditor): Editor {
  return (shell as unknown as { editor: Editor }).editor;
}

/** Choose a drawing on the bar, which is the one way one is opened. */
async function choose(shell: TcEditor, name: string): Promise<void> {
  shell.renderRoot
    .querySelector("tc-menubar")!
    .dispatchEvent(new CustomEvent<string>("open-drawing", { detail: name }));
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
    const shell = await mounted();
    await drawn(shell);

    await choose(shell, "otira");

    expect(asked(shell)).not.toBeNull();
    expect(open(shell)).toBe("gotthard");
  });

  /** Declining costs nothing at all: the same drawing, the same edits, the
   *  same dot, and undo still holding the step that made them. */
  it("leaves everything as it was when the edits are kept", async () => {
    const shell = await mounted();
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
    const shell = await mounted();
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
    const shell = await mounted();
    await drawn(shell);

    await choose(shell, "otira");

    expect(asked(shell)!.textContent).toContain("'gotthard'");
    expect(asked(shell)!.textContent).toContain("'otira'");
  });

  /** Nothing is open until a drawing is chosen, and what is drawn before that
   *  is worth the same question — under a name the band does not have. */
  it("asks about a canvas drawn on before anything was opened", async () => {
    const shell = document.createElement("tc-editor");
    document.body.append(shell);
    await settled(shell);
    await drawn(shell);

    await choose(shell, "otira");

    expect(asked(shell)!.textContent).toContain("The canvas has edits");
  });

  /** The question is modal, so Escape is its: it declines, and the selection
   *  behind it is not the canvas's to clear on the way. */
  it("takes Escape as a refusal, and the canvas hears nothing", async () => {
    const shell = await mounted();
    await drawn(shell);
    await choose(shell, "otira");

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await settled(shell);

    expect(asked(shell)).toBeNull();
    expect(open(shell)).toBe("gotthard");
    expect([...session(shell).selection]).toEqual(["b1"]);
  });

  it("opens straight away when there is nothing to lose", async () => {
    const shell = await mounted();

    await choose(shell, "otira");

    expect(asked(shell)).toBeNull();
    expect(open(shell)).toBe("otira");
  });
});

describe("starting a new drawing over unsaved edits", () => {
  /** The name is asked for after the edits are, not before: a prompt answered
   *  and then a discard declined would have asked for nothing. */
  it("asks before anything is reset, and asks for no name yet", async () => {
    const shell = await mounted();
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
    const shell = await mounted();
    await drawn(shell);
    await fresh(shell);

    await answer(shell, "Cancel");

    expect(asked(shell)).toBeNull();
    expect(open(shell)).toBe("gotthard");
    expect(unsaved(shell)).toBe(true);
    expect(session(shell).canUndo).toBe(true);
  });

  it("empties the canvas under the new name once they are given up", async () => {
    const shell = await mounted();
    await drawn(shell);
    await fresh(shell);

    await answer(shell, "Discard");

    expect(open(shell)).toBe(NAMED);
    expect(session(shell).drawing.symbols).toEqual({});
  });

  it("starts one straight away when there is nothing to lose", async () => {
    const shell = await mounted();

    await fresh(shell);

    expect(asked(shell)).toBeNull();
    expect(open(shell)).toBe(NAMED);
  });
});
