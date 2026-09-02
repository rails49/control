// @vitest-environment happy-dom

/**
 * The app: one railroad and two views of it (#167, ADR-0038).
 *
 * A DOM test, because what is under test is the frame — which view is on
 * screen, what the two rows of chrome say about it, and that the railroad
 * survives the switch. What each view then does with the railroad is that
 * view's own suite.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-app.js";
import type { Drawing } from "../src/model/drawing.js";
import { hashOf, viewOf } from "../src/model/views.js";
import type { TcApp } from "../src/ui/tc-app.js";
import {
  band,
  bar,
  editing,
  mounted,
  serving,
  session,
  settled,
  shows,
} from "./support/shell.js";

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

// An app listens on the window for as long as it is in the page, so one left
// behind would answer the next test's keystrokes and hash changes too.
afterEach(() => {
  document.body.replaceChildren();
});

/** Load a railroad, the way the band's picker does. */
async function load(shell: TcApp, name: string): Promise<void> {
  band(shell).dispatchEvent(
    new CustomEvent<string>("railroad-wanted", { detail: name }),
  );
  await settled(shell);
}

/** Which view is on screen: the one that is not hidden. */
function showing(shell: TcApp): string {
  const on = [...shell.renderRoot.querySelectorAll("tc-editor, tc-panel")].filter(
    (view) => !view.classList.contains("off"),
  );
  expect(on).toHaveLength(1);
  return on[0]!.tagName.toLowerCase();
}

/** What the band names as the loaded railroad. */
function loaded(shell: TcApp): string {
  return band(shell).renderRoot.querySelector(".drawing")!.textContent!.trim();
}

/** The titles the bar carries, which are the current view's. */
function titles(shell: TcApp): string[] {
  return [...bar(shell).renderRoot.querySelectorAll("button.title")].map((one) =>
    one.textContent!.trim(),
  );
}

/** The hash, as a view name and no `#`. */
function named(): string {
  return viewOf(location.hash);
}

describe("which view the app opens in", () => {
  /** It is a control surface; the editor is the setup tool you go to
   *  deliberately. */
  it("opens in the run view with nothing said", async () => {
    location.hash = "";
    const shell = document.createElement("tc-app");
    document.body.append(shell);
    await settled(shell);
    expect(showing(shell)).toBe("tc-panel");
  });

  /** A link that has gone stale opens on the control surface rather than on
   *  nothing. */
  it("opens in the run view on a hash naming no view", async () => {
    location.hash = "#stock";
    const shell = document.createElement("tc-app");
    document.body.append(shell);
    await settled(shell);
    expect(showing(shell)).toBe("tc-panel");
  });

  it("opens in the view the hash names", async () => {
    expect(showing(await mounted("edit"))).toBe("tc-editor");
    document.body.replaceChildren();
    expect(showing(await mounted("run"))).toBe("tc-panel");
  });
});

describe("the hash the view is bookmarked by", () => {
  it("round trips a view", () => {
    for (const view of ["run", "edit"] as const) {
      expect(viewOf(hashOf(view))).toBe(view);
    }
  });

  it("says which view the selector chose, so a reload keeps it", async () => {
    const shell = await mounted("run");

    await shows(shell, "edit");

    expect(showing(shell)).toBe("tc-editor");
    expect(named()).toBe("edit");
  });

  /** A bookmark opened and a back button pressed are the same choice by
   *  another route. */
  it("switches the view when the hash moves under the app", async () => {
    const shell = await mounted("run");

    location.hash = hashOf("edit");
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    await settled(shell);

    expect(showing(shell)).toBe("tc-editor");
  });
});

describe("switching view", () => {
  /** The app holds the railroad and the views are of it, which is the whole
   *  of ADR-0038: a toggle is not a reload. */
  it("keeps the loaded railroad, and the editor's document with it", async () => {
    const shell = await mounted("edit");
    await load(shell, "reversing-loops");
    expect(loaded(shell)).toBe("reversing-loops");

    await shows(shell, "run");
    await shows(shell, "edit");

    expect(loaded(shell)).toBe("reversing-loops");
    expect(session(shell).drawing.drawing).toBe("reversing-loops");
    expect(editing(shell).editor).toBe(session(shell));
  });

  /** The views are hidden rather than taken away: an operator toggling to
   *  look at the netlist must not lose the session, and a canvas fitted while
   *  hidden has to fit to the shape it will be seen at. */
  it("keeps both views on the page, and shows one", async () => {
    const shell = await mounted("edit");
    expect(shell.renderRoot.querySelector("tc-panel")).not.toBeNull();
    expect(showing(shell)).toBe("tc-editor");

    await shows(shell, "run");

    expect(shell.renderRoot.querySelector("tc-editor")).not.toBeNull();
    expect(showing(shell)).toBe("tc-panel");
  });

  /** The bar is the current view's document's, so its menus follow the
   *  switch. */
  it("hands the bar the menus of the view it switched to", async () => {
    const shell = await mounted("edit");
    expect(titles(shell)).toEqual(["File", "Edit", "View"]);

    await shows(shell, "run");

    expect(titles(shell)).toEqual(["View"]);
  });

  /** A menu is the view's too: one left down would be drawing the titles of a
   *  view that is no longer on screen. */
  it("takes a menu that is down up with the view", async () => {
    const shell = await mounted("edit");
    const titled = bar(shell).renderRoot.querySelectorAll("button.title")[0]!;
    (titled as HTMLElement).click();
    await settled(shell);
    expect(bar(shell).renderRoot.querySelector("menu")).not.toBeNull();

    await shows(shell, "run");

    expect(bar(shell).renderRoot.querySelector("menu")).toBeNull();
  });
});

describe("the band's picker against the bar's menus", () => {
  /** The band sits above the bar, so a press on the picker lands on it rather
   *  than on the overlay the open menu is waiting for. The menu would be left
   *  down with the keyboard still its, so the picker takes it up. */
  it("takes a menu on the bar up when the picker goes down", async () => {
    const shell = await mounted("edit");
    (bar(shell).renderRoot.querySelector("button.title") as HTMLElement).click();
    await settled(shell);
    expect(bar(shell).renderRoot.querySelector("menu")).not.toBeNull();

    (band(shell).renderRoot.querySelector("button.chosen") as HTMLElement).click();
    await settled(shell);

    expect(bar(shell).renderRoot.querySelector("menu")).toBeNull();
    expect(band(shell).renderRoot.querySelector("menu.drawings")).not.toBeNull();
  });
});

describe("the picker over unsaved edits", () => {
  /** The question is the app's, because what it guards is the app's: the
   *  railroad, not one view's document (#101). */
  it("asks before the band's picker changes anything", async () => {
    const shell = await mounted("edit");
    await load(shell, "reversing-loops");
    session(shell).place("block", [4, 0]);
    editing(shell).dispatchEvent(
      new CustomEvent("edit", { bubbles: true, composed: true }),
    );
    await settled(shell);

    await load(shell, "otira");

    expect(shell.renderRoot.querySelector("sl-dialog")).not.toBeNull();
    expect(loaded(shell)).toBe("reversing-loops");
  });
});
