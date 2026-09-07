// @vitest-environment happy-dom

/**
 * The rail down the left: the views, what each view's groups carry, what a
 * dead button does, and the run view's own press (ADR-0064).
 *
 * A DOM test, the whole of the behaviour being what the component renders, as
 * `tc-menu`'s and `tc-header`'s are. What is dead and what is alive is
 * `commands.test.ts`; this asks only that the rail draws it.
 */

import { describe, expect, it } from "vitest";

import { NOTHING, type CommandId, type Standing } from "../src/model/commands.js";
import { VIEWS, type ViewId } from "../src/model/views.js";
import "../src/ui/tc-rail.js";
import type { TcRail } from "../src/ui/tc-rail.js";

/** A drawing open with edits in it, one symbol selected that has properties,
 *  a snapshot either way, and nothing standing on the layout to freeze it:
 *  everything alive at once. */
const LIVE: Standing = {
  opened: "reversing-loops",
  saved: false,
  selection: 1,
  editable: true,
  undo: true,
  redo: true,
  backup: "quiet",
  placed: 0,
};

async function rail(
  standing: Standing = LIVE,
  view: ViewId = "edit",
): Promise<TcRail> {
  const element = document.createElement("tc-rail");
  element.view = view;
  element.standing = standing;
  document.body.append(element);
  await element.updateComplete;
  return element;
}

/** The selector's buttons, one per view, in the order they are drawn. */
function views(element: TcRail): HTMLButtonElement[] {
  return [...element.renderRoot.querySelectorAll<HTMLButtonElement>("button.view")];
}

/** The command buttons, top to bottom, whatever group they sit in. */
function commands(element: TcRail): HTMLButtonElement[] {
  return [
    ...element.renderRoot.querySelectorAll<HTMLButtonElement>("button[data-command]"),
  ];
}

/** One command's button, by the command it sends. */
function button(element: TcRail, id: CommandId): HTMLButtonElement | null {
  return element.renderRoot.querySelector<HTMLButtonElement>(
    `button[data-command="${id}"]`,
  );
}

/** The names the groups are drawn under, top to bottom. */
function groups(element: TcRail): string[] {
  return [...element.renderRoot.querySelectorAll(".group")].map(
    (one) => one.getAttribute("aria-label")!,
  );
}

/** The commands the rail dispatched while `act` ran. */
async function asked(element: TcRail, act: () => void): Promise<CommandId[]> {
  const heard: CommandId[] = [];
  element.addEventListener("command", (event) => {
    heard.push((event as CustomEvent<CommandId>).detail);
  });
  act();
  await element.updateComplete;
  return heard;
}

/** Views are a list with one current entry, drawn as one icon-button each with
 *  the current one marked — the selector ADR-0038 said a third view would make
 *  of the toggle two of them were, on the rail since ADR-0064. */
describe("the view selector", () => {
  it("is the group at the top of every view's rail", async () => {
    for (const view of VIEWS) {
      expect(groups(await rail(LIVE, view.id))[0]).toBe("views");
    }
  });

  /** The list is what the views are, so every one of them has a button and
   *  the current one is marked rather than missing. */
  it("offers every view the app has, in the order the list has them", async () => {
    const buttons = views(await rail(LIVE, "run"));
    expect(buttons.map((one) => one.getAttribute("aria-label"))).toEqual(
      VIEWS.map((view) => view.label),
    );
  });

  it("marks the one that is current and no other", async () => {
    for (const view of VIEWS) {
      const marked = views(await rail(LIVE, view.id))
        .filter((one) => one.classList.contains("current"))
        .map((one) => one.dataset["view"]);
      expect(marked).toEqual([view.id]);
    }
  });

  it("asks for the view whose button was pressed", async () => {
    const element = await rail(LIVE, "run");
    const heard: string[] = [];
    element.addEventListener("view-wanted", (event) => {
      heard.push((event as CustomEvent<string>).detail);
    });
    for (const one of views(element)) one.click();
    expect(heard).toEqual(VIEWS.map((view) => view.id));
  });
});

describe("what each view's rail carries", () => {
  /** Every verb, with its label and its key in the title a pointer resting
   *  there reads: a glyph on its own says nothing about the key that does the
   *  same thing, which is what the menu row printed. */
  it("names the editor's commands and the keys that do the same thing", async () => {
    const element = await rail();
    expect(commands(element).map((one) => one.getAttribute("aria-label"))).toEqual([
      "Zoom out  −",
      "Zoom in  +",
      "Fit  0",
      "Netlist  N",
      "New…",
      "Save  ⌘S",
      "Save As…  ⇧⌘S",
      "Export SVG…",
      "Backup…",
      "Undo  ⌘Z",
      "Redo  ⇧⌘Z",
    ]);
  });

  it("groups them under the names the menus carried", async () => {
    expect(groups(await rail())).toEqual(["views", "View", "File", "Edit"]);
  });

  /** The run view's document is a railroad somebody else is running: no File
   *  and no Edit, and what it presses instead is HOLD and GO. */
  it("gives the run view the three view commands and nothing else", async () => {
    const element = await rail(LIVE, "run");
    expect(commands(element).map((one) => one.dataset["command"])).toEqual([
      "zoom-out",
      "zoom-in",
      "fit",
    ]);
  });

  /** Neither draws a document with a viewport, so neither has a command at
   *  all — the views are the whole of their rail (ui/THROTTLE.md, ui/STOCK.md). */
  it.each(["throttle", "stock"] as const)(
    "gives the %s view no commands",
    async (view) => {
      expect(commands(await rail(LIVE, view))).toEqual([]);
    },
  );

  /** The four selection verbs read in the right-click menu instead
   *  (ADR-0064, menu.test.ts). */
  it("leaves the selection verbs off every view's rail", async () => {
    for (const view of VIEWS) {
      const element = await rail(LIVE, view.id);
      for (const id of ["rotate", "flip", "delete", "properties"] as const) {
        expect(button(element, id)).toBeNull();
      }
    }
  });

  it("asks for the command the button carries", async () => {
    const element = await rail(LIVE, "run");
    const heard = await asked(element, () => {
      for (const one of commands(element)) one.click();
    });
    expect(heard).toEqual(["zoom-out", "zoom-in", "fit"]);
  });
});

describe("what a dead button does", () => {
  it("draws it disabled", async () => {
    const element = await rail(NOTHING);
    const dead = commands(element)
      .filter((one) => one.disabled)
      .map((one) => one.dataset["command"]);
    expect(dead).toEqual([
      "netlist",
      "save",
      "save-as",
      "export-svg",
      "undo",
      "redo",
    ]);
  });

  it("asks for nothing when it is clicked", async () => {
    const element = await rail(NOTHING);
    expect(await asked(element, () => button(element, "save")!.click())).toEqual([]);
  });
});

/** What a command has to say before anybody presses it, which is backup's
 *  alone (#321). It warns and never disables: a railroad that is not being
 *  backed up is a railroad somebody still has to be able to back up. */
describe("the mark on a command that has something to say", () => {
  it("rides on the button and leaves it live", async () => {
    const element = await rail({ ...LIVE, backup: "never" });
    const backup = button(element, "backup")!;
    expect(backup.querySelector(".mark")).not.toBeNull();
    expect(backup.disabled).toBe(false);
    expect(backup.title).toBe("this railroad has never been backed up");
  });

  it("draws none where there is nothing to say", async () => {
    const backup = button(await rail(), "backup")!;
    expect(backup.querySelector(".mark")).toBeNull();
    expect(backup.title).toBe("Backup…");
  });
});

/**
 * HOLD and GO (ADR-0037): the run view's own press, and the one thing on the
 * rail that is not a command. One press, and the word is what the press will
 * do — a clearly labelled button is the explicit GO, so there is no second
 * question to click through.
 */
describe("holding the run and releasing it", () => {
  /** The button, wherever it is on the rail. */
  function press(element: TcRail): HTMLButtonElement | null {
    return element.renderRoot.querySelector<HTMLButtonElement>("button.run");
  }

  it("says HOLD while the run is running and GO while it is held", async () => {
    const running = await rail(LIVE, "run");
    running.run = "running";
    await running.updateComplete;
    expect(press(running)!.textContent!.trim()).toBe("HOLD");

    running.run = "held";
    await running.updateComplete;
    expect(press(running)!.textContent!.trim()).toBe("GO");
  });

  it("asks for the state the word names", async () => {
    const element = await rail(LIVE, "run");
    element.run = "held";
    await element.updateComplete;
    const heard: string[] = [];
    element.addEventListener("run-wanted", (event) => {
      heard.push((event as CustomEvent<string>).detail);
    });

    press(element)!.click();
    element.run = "running";
    await element.updateComplete;
    press(element)!.click();

    expect(heard).toEqual(["running", "held"]);
  });

  /** With no session joined there is no run to hold, and before the
   *  dispatcher has said there is no word to offer the other of. */
  it("is dead until a session says where the run stands", async () => {
    const element = await rail(LIVE, "run");
    expect(press(element)!.disabled).toBe(true);

    element.run = "held";
    await element.updateComplete;
    expect(press(element)!.disabled).toBe(false);
  });

  /**
   * GO is greyed while the rails are dead (ADR-0041). The dispatcher drops
   * such a release, so a live button would be one that does nothing; the
   * reason reads on the band, as the panel's greyed "Turn around" says *this
   * train is busy* by being greyed at all.
   */
  it("greys GO while the layout says a train may not move", async () => {
    const element = await rail(LIVE, "run");
    element.run = "held";
    element.power = "on";
    await element.updateComplete;
    expect(press(element)!.disabled).toBe(false);

    for (const state of ["off", "stopped"] as const) {
      element.power = state;
      await element.updateComplete;
      expect(press(element)!.textContent!.trim()).toBe("GO");
      expect(press(element)!.disabled).toBe(true);
    }

    element.power = "on";
    await element.updateComplete;
    expect(press(element)!.disabled).toBe(false);
  });

  /** It asks for less than the railroad is already doing, so there is no
   *  state of the rails it can be refused in. */
  it("leaves HOLD alone whatever the power is doing", async () => {
    const element = await rail(LIVE, "run");
    element.run = "running";
    element.power = "off";
    await element.updateComplete;

    expect(press(element)!.textContent!.trim()).toBe("HOLD");
    expect(press(element)!.disabled).toBe(false);
  });

  /** A session that has said where the run stands but not what the supply is
   *  doing is one the dispatcher would honour a GO from: it takes `on` until
   *  the layout says otherwise, and the button says what the dispatcher would
   *  do rather than guessing at silence. */
  it("offers GO while the layout has said nothing", async () => {
    const element = await rail(LIVE, "run");
    element.run = "held";
    await element.updateComplete;
    expect(press(element)!.disabled).toBe(false);
  });

  /** The editor's document is a drawing; nothing there runs. */
  it("is not on the editor's rail", async () => {
    const element = await rail(LIVE, "edit");
    element.run = "running";
    await element.updateComplete;
    expect(press(element)).toBeNull();
  });
});
