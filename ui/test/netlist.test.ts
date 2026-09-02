// @vitest-environment happy-dom

/**
 * The netlist folding behind `View ▸ Netlist` (#90).
 *
 * The pane itself is unchanged; what is under test is the shell around it —
 * whether the column is there at all, and what puts it there. A DOM test
 * because that is the whole of it: `commands.test.ts` holds the rule saying
 * when the item is dead, and this asks that both ways of reaching it obey the
 * one rule and leave the same page behind.
 *
 * Shut is the state the editor loads in and returns to whenever a drawing is
 * opened, because the netlist is a debugging view now rather than what the
 * editor is for (ADR-0024).
 */

import { beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-app.js";
import type { Drawing } from "../src/model/drawing.js";
import type { TcCanvas } from "../src/ui/tc-canvas.js";
import type { TcApp } from "../src/ui/tc-app.js";
import { editing, inside, mounted, serving, settled } from "./support/shell.js";

const DRAWING: Drawing = {
  drawing: "reversing-loops",
  symbols: { sw1: { kind: "turnout", at: [0, 0] } },
  wires: [],
};

beforeEach(() => {
  document.body.replaceChildren();
  serving({ drawings: ["reversing-loops"], read: () => DRAWING });
});

/** The shell with `reversing-loops` open, which is what the netlist item needs to be
 *  alive at all. */
async function open(): Promise<TcApp> {
  const shell = await mounted();
  shell.renderRoot
    .querySelector("tc-header")!
    .dispatchEvent(new CustomEvent("railroad-wanted", { detail: "reversing-loops" }));
  await settled(shell);
  return shell;
}

/** A command asked for on the menu bar, the way an item's click asks it. */
async function asked(shell: TcApp, command: string): Promise<void> {
  shell.renderRoot
    .querySelector("tc-menubar")!
    .dispatchEvent(new CustomEvent("command", { detail: command }));
  await settled(shell);
}

/** The same command reached by the key the menu prints beside it. */
async function pressed(shell: TcApp, name: string): Promise<void> {
  window.dispatchEvent(
    new KeyboardEvent("keydown", { key: name, bubbles: true, composed: true }),
  );
  await settled(shell);
}

/** Whether the pane is on the page at all. Shut, it is not rendered, which is
 *  what leaves its grid column with nothing in it. */
function showing(shell: TcApp): boolean {
  return editing(shell).renderRoot.querySelector("tc-netlist") !== null;
}

describe("the column the netlist sits in", () => {
  it("is not there when the editor loads", async () => {
    expect(showing(await mounted())).toBe(false);
  });

  it("is not there when a drawing is opened either", async () => {
    expect(showing(await open())).toBe(false);
  });

  /** The stylesheet drops the third column with the pane, so the canvas has
   *  the width rather than a 22rem gap beside it. */
  it("is what the host attribute the grid reads says it is", async () => {
    const shell = await open();
    expect(editing(shell).hasAttribute("netlist")).toBe(false);

    await asked(shell, "netlist");

    expect(editing(shell).hasAttribute("netlist")).toBe(true);
    expect(showing(shell)).toBe(true);
  });

  it("goes away again on the second ask", async () => {
    const shell = await open();
    await asked(shell, "netlist");
    await asked(shell, "netlist");
    expect(showing(shell)).toBe(false);
  });

  /** Opening a drawing is where the netlist is closed, so a debugging view
   *  left open over one railroad is not inherited by the next. */
  it("is shut again by opening a drawing", async () => {
    const shell = await open();
    await asked(shell, "netlist");

    shell.renderRoot
      .querySelector("tc-header")!
      .dispatchEvent(new CustomEvent("railroad-wanted", { detail: "reversing-loops" }));
    await settled(shell);

    expect(showing(shell)).toBe(false);
  });
});

describe("the key and the item", () => {
  it("opens and shuts it on the key the menu prints", async () => {
    const shell = await open();

    await pressed(shell, "n");
    expect(showing(shell)).toBe(true);

    await pressed(shell, "N");
    expect(showing(shell)).toBe(false);
  });

  /** Both ways through ask `model/commands.ts`, so the item being dead with
   *  nothing open is the key being dead too — otherwise the two would come to
   *  mean different things. */
  it("does nothing either way while no drawing is open", async () => {
    const shell = await mounted();

    await pressed(shell, "n");
    expect(showing(shell)).toBe(false);

    await asked(shell, "netlist");
    expect(showing(shell)).toBe(false);
  });

  /** A bare key is the menu's while a menu is down, as `r` and `0` are
   *  (keys.test.ts). */
  it("leaves the key to the menu while one is down", async () => {
    const shell = await open();
    const bar = shell.renderRoot.querySelector("tc-menubar")!;
    bar.dispatchEvent(new CustomEvent("menu-open", { detail: true }));
    await settled(shell);

    await pressed(shell, "n");

    expect(showing(shell)).toBe(false);
  });
});

/** The pane's own reason to be a panel and not a popup: a transit chosen in it
 *  lights its way on the drawing beside it (ADR-0024). Folding the column away
 *  must not cost that, and shutting it takes the lit way with it — nothing
 *  left on screen could unlight it otherwise. */
describe("a transit chosen in it", () => {
  async function choose(shell: TcApp): Promise<void> {
    editing(shell).renderRoot.querySelector("tc-netlist")!.dispatchEvent(
      new CustomEvent("transit-chosen", {
        detail: { connection: "butterfly", transit: "A3_B__CW_A" },
      }),
    );
    await settled(shell);
  }

  it("is handed to the canvas while the pane is open", async () => {
    const shell = await open();
    await asked(shell, "netlist");

    await choose(shell);

    expect((inside(shell, "tc-canvas") as TcCanvas).chosen).toEqual({
      connection: "butterfly",
      transit: "A3_B__CW_A",
    });
  });

  it("is unlit when the pane is shut", async () => {
    const shell = await open();
    await asked(shell, "netlist");
    await choose(shell);

    await asked(shell, "netlist");

    expect((inside(shell, "tc-canvas") as TcCanvas).chosen).toBeNull();
  });
});
