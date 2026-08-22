// @vitest-environment happy-dom

/**
 * The bar under the band: what each view's menus carry, what a dead item does,
 * and the three commands that stay one click.
 *
 * A DOM test, the whole of the behaviour being what the component renders, as
 * `tc-menu`'s and `tc-header`'s are. What is dead and what is alive is
 * `commands.test.ts`; this asks only that the bar draws it.
 */

import { describe, expect, it } from "vitest";

import "../src/ui/tc-menubar.js";
import type { TcMenubar } from "../src/ui/tc-menubar.js";
import { NOTHING, type CommandId, type Standing } from "../src/model/commands.js";
import type { ViewId } from "../src/model/views.js";

/** A drawing open with edits in it, one symbol selected that has properties,
 *  and a snapshot either way: everything alive at once. */
const LIVE: Standing = {
  opened: "gotthard",
  saved: false,
  selection: 1,
  editable: true,
  undo: true,
  redo: true,
  zoomable: true,
};

async function bar(
  standing: Standing = LIVE,
  view: ViewId = "edit",
): Promise<TcMenubar> {
  const menubar = document.createElement("tc-menubar");
  menubar.view = view;
  menubar.standing = standing;
  document.body.append(menubar);
  await menubar.updateComplete;
  return menubar;
}

/** The title on the bar that reads `name`. */
function title(menubar: TcMenubar, name: string): HTMLElement {
  const titles = [...menubar.renderRoot.querySelectorAll("button.title")];
  return titles.find((one) => one.textContent!.trim() === name) as HTMLElement;
}

/** Click one of the bar's titles, which puts its menu down where the title was
 *  closed and takes it up again where it was down. */
async function click(menubar: TcMenubar, name: string): Promise<TcMenubar> {
  title(menubar, name).click();
  await menubar.updateComplete;
  return menubar;
}

/** Slide the pointer onto one of the bar's titles. */
async function onto(menubar: TcMenubar, name: string): Promise<TcMenubar> {
  title(menubar, name).dispatchEvent(new Event("pointerenter"));
  await menubar.updateComplete;
  return menubar;
}

/** The title whose menu is down, `null` while none is. */
function showing(menubar: TcMenubar): string | null {
  const titles = [...menubar.renderRoot.querySelectorAll("button.title")];
  const down = titles.find((one) => one.getAttribute("aria-expanded") === "true");
  return down === undefined ? null : down.textContent!.trim();
}

/** What the menu that is down reads, top to bottom. A divider is a rule. */
function reads(menubar: TcMenubar): string[] {
  const menu = menubar.renderRoot.querySelector("menu")!;
  return [...menu.children].map((item) => {
    if (item.classList.contains("divider")) return "──";
    const label = item.querySelector(".label")!.textContent!.trim();
    const key = item.querySelector("kbd");
    return key === null ? label : `${label} ${key.textContent!.trim()}`;
  });
}

/** The commands the bar dispatched while `act` ran. */
async function asked(
  menubar: TcMenubar,
  act: () => void,
): Promise<CommandId[]> {
  const heard: CommandId[] = [];
  menubar.addEventListener("command", (event) => {
    heard.push((event as CustomEvent<CommandId>).detail);
  });
  act();
  await menubar.updateComplete;
  return heard;
}

describe("what each menu carries", () => {
  /** Every verb with its key beside it: a menu is where a shortcut is
   *  conventionally learnt, which is what makes a menu bar the thing
   *  EDITOR.md#editing endorses rather than the button it refuses. */
  it("names the file commands and the keys that do the same thing", async () => {
    expect(reads(await click(await bar(), "File"))).toEqual([
      "New…",
      "Save ⌘S",
      "Save As… ⇧⌘S",
      "──",
      "Export SVG…",
    ]);
  });

  it("names the edit commands", async () => {
    expect(reads(await click(await bar(), "Edit"))).toEqual([
      "Undo ⌘Z",
      "Redo ⇧⌘Z",
      "──",
      "Rotate R",
      "Flip F",
      "Delete ⌫",
      "──",
      "Properties…",
    ]);
  });

  it("names the view commands", async () => {
    expect(reads(await click(await bar(), "View"))).toEqual([
      "Zoom in +",
      "Zoom out −",
      "Fit 0",
      "──",
      "Netlist N",
    ]);
  });

  /** Chrome keeps ⌘N for a new window and never lets the page have it. A
   *  blank is better than a binding the browser eats. */
  it("shows no key for the one the browser would eat", async () => {
    const menu = (await click(await bar(), "File")).renderRoot.querySelector("menu")!;
    const item = [...menu.children].find(
      (one) => one.querySelector(".label")?.textContent!.trim() === "New…",
    )!;
    expect(item.querySelector("kbd")).toBeNull();
  });

  it("puts one menu down at a time", async () => {
    const menubar = await click(await bar(), "File");
    await click(menubar, "Edit");
    expect(reads(menubar)[0]).toBe("Undo ⌘Z");
  });
});

describe("whose menus the bar carries", () => {
  /** The bar is the document's and the document is the current view's
   *  (ADR-0038), so which titles are on it is the view's answer. */
  it("gives the editor File, Edit and View", async () => {
    const titles = [
      ...(await bar()).renderRoot.querySelectorAll("button.title"),
    ].map((one) => one.textContent!.trim());
    expect(titles).toEqual(["File", "Edit", "View"]);
  });

  it("gives the run view View alone", async () => {
    const titles = [
      ...(await bar(LIVE, "run")).renderRoot.querySelectorAll("button.title"),
    ].map((one) => one.textContent!.trim());
    expect(titles).toEqual(["View"]);
  });

  /** Which railroad is loaded is the whole system's and the band picks it, so
   *  there is no way to one from here (#167). */
  it("offers no way to another railroad", async () => {
    const menubar = await click(await bar(), "File");
    expect(reads(menubar)).not.toContain("Open");
    expect(menubar.renderRoot.querySelector("menu.drawings")).toBeNull();
  });
});

describe("what a dead item does", () => {
  it("draws it disabled", async () => {
    const menubar = await click(await bar(NOTHING), "File");
    const dead = [...menubar.renderRoot.querySelectorAll("menu > li button")]
      .filter((one) => (one as HTMLButtonElement).disabled)
      .map((one) => one.querySelector(".label")!.textContent!.trim());
    expect(dead).toEqual(["Save", "Save As…", "Export SVG…"]);
  });

  /** The zoom commands are the surface's own and stay alive on an empty page;
   *  the netlist is of a drawing, and there is none. */
  it("draws the netlist dead while the zoom commands stay alive", async () => {
    const menubar = await click(await bar({ ...NOTHING, zoomable: true }), "View");
    const items = [...menubar.renderRoot.querySelectorAll("menu > li button")];
    const dead = items
      .filter((one) => (one as HTMLButtonElement).disabled)
      .map((one) => one.querySelector(".label")!.textContent!.trim());
    expect(dead).toEqual(["Netlist"]);
  });

  it("asks for nothing when it is clicked", async () => {
    const menubar = await click(await bar(NOTHING), "File");
    const save = [...menubar.renderRoot.querySelectorAll("menu > li button")].find(
      (one) => one.querySelector(".label")!.textContent!.trim() === "Save",
    )!;

    expect(await asked(menubar, () => (save as HTMLElement).click())).toEqual([]);
  });
});

describe("what stays one click", () => {
  /** Zoom and fit are pressed constantly while drawing, and `View ▸ Zoom in`
   *  is three clicks for what is now one. */
  it("pins zoom out, zoom in and fit at the editor's right end", async () => {
    const menubar = await bar();
    const tools = [...menubar.renderRoot.querySelectorAll("button.tool")];
    expect(tools.map((one) => one.getAttribute("aria-label"))).toEqual([
      "Zoom out  −",
      "Zoom in  +",
      "Fit  0",
    ]);
  });

  it("asks for the command the button carries", async () => {
    const menubar = await bar();
    const tools = [...menubar.renderRoot.querySelectorAll("button.tool")];
    const heard = await asked(menubar, () => {
      for (const tool of tools) (tool as HTMLElement).click();
    });
    expect(heard).toEqual(["zoom-out", "zoom-in", "fit"]);
  });
});

describe("what the editor is told", () => {
  /** With a menu down the keyboard is the menu's, so the editor has to know
   *  (keys.test.ts). */
  it("says when a menu goes down and comes back up", async () => {
    const menubar = await bar();
    const heard: boolean[] = [];
    menubar.addEventListener("menu-open", (event) => {
      heard.push((event as CustomEvent<boolean>).detail);
    });

    await click(menubar, "File");
    await click(menubar, "File");

    expect(heard).toEqual([true, false]);
  });

  it("puts the menu up and says so when an item is chosen", async () => {
    const menubar = await click(await bar(), "Edit");
    const heard = await asked(menubar, () => {
      const undo = menubar.renderRoot.querySelector("menu > li button")!;
      (undo as HTMLElement).click();
    });

    expect(heard).toEqual(["undo"]);
    expect(menubar.renderRoot.querySelector("menu")).toBeNull();
  });
});

describe("sliding along the bar", () => {
  /** Every menu bar reads the next title as the pointer crosses it, and the
   *  click that catches up with the hand must not undo what the hand did
   *  (#100). */
  it("opens the neighbour hovered onto, and the click that follows leaves it", async () => {
    const menubar = await click(await bar(), "File");

    await onto(menubar, "Edit");
    expect(showing(menubar)).toBe("Edit");

    await click(menubar, "Edit");
    expect(showing(menubar)).toBe("Edit");
  });

  /** A bar whose menus opened under a pointer merely crossing it would open
   *  them by accident, so the hover only reads on while one is already down. */
  it("opens nothing while no menu is down", async () => {
    const menubar = await bar();

    await onto(menubar, "File");
    await onto(menubar, "Edit");

    expect(showing(menubar)).toBeNull();
  });

  /** A click away from the bar takes the menu up however it went down: the
   *  absorbed click is the one on the title, not the next one anywhere. */
  it("puts the menu up when the click lands outside it", async () => {
    const menubar = await click(await bar(), "File");
    await onto(menubar, "Edit");

    const overlay = menubar.renderRoot.querySelector(".dismiss")!;
    overlay.dispatchEvent(new Event("pointerdown"));
    await menubar.updateComplete;

    expect(showing(menubar)).toBeNull();
  });

  it("closes on the second click after a hover", async () => {
    const menubar = await click(await bar(), "File");
    await onto(menubar, "Edit");

    await click(menubar, "Edit");
    await click(menubar, "Edit");

    expect(showing(menubar)).toBeNull();
  });
});
