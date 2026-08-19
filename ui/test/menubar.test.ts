// @vitest-environment happy-dom

/**
 * The bar under the band: what each menu carries, what a dead item does, and
 * the three commands that stay one click.
 *
 * A DOM test, the whole of the behaviour being what the component renders, as
 * `tc-menu`'s and `tc-header`'s are. What is dead and what is alive is
 * `commands.test.ts`; this asks only that the bar draws it.
 */

import { describe, expect, it } from "vitest";

import "../src/ui/tc-menubar.js";
import type { TcMenubar } from "../src/ui/tc-menubar.js";
import { NOTHING, type CommandId, type Standing } from "../src/model/commands.js";

/** A drawing open with edits in it, one symbol selected that has properties,
 *  and a snapshot either way: everything alive at once. */
const LIVE: Standing = {
  opened: "gotthard",
  saved: false,
  drawings: 3,
  selection: 1,
  editable: true,
  undo: true,
  redo: true,
};

async function bar(standing: Standing = LIVE): Promise<TcMenubar> {
  const menubar = document.createElement("tc-menubar");
  menubar.standing = standing;
  menubar.drawings = ["crossover-yard", "facing-pair", "gotthard"];
  document.body.append(menubar);
  await menubar.updateComplete;
  return menubar;
}

/** Put one of the bar's menus down. */
async function down(menubar: TcMenubar, name: string): Promise<TcMenubar> {
  const titles = [...menubar.renderRoot.querySelectorAll("button.title")];
  const title = titles.find((one) => one.textContent!.trim() === name);
  (title as HTMLElement).click();
  await menubar.updateComplete;
  return menubar;
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
    expect(reads(await down(await bar(), "File"))).toEqual([
      "New…",
      "Open",
      "Save ⌘S",
      "Save As… ⇧⌘S",
      "──",
      "Export SVG…",
    ]);
  });

  it("names the edit commands", async () => {
    expect(reads(await down(await bar(), "Edit"))).toEqual([
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
    expect(reads(await down(await bar(), "View"))).toEqual([
      "Zoom in +",
      "Zoom out −",
      "Fit 0",
    ]);
  });

  /** Chrome keeps ⌘N for a new window and never lets the page have it, and ⌘O
   *  is unreliable for the same reason. A blank is better than a binding the
   *  browser eats. */
  it("shows no key for the two the browser would eat", async () => {
    const menu = (await down(await bar(), "File")).renderRoot.querySelector("menu")!;
    for (const label of ["New…", "Open"]) {
      const item = [...menu.children].find(
        (one) => one.querySelector(".label")?.textContent!.trim() === label,
      )!;
      expect(item.querySelector("kbd")).toBeNull();
    }
  });

  it("puts one menu down at a time", async () => {
    const menubar = await down(await bar(), "File");
    await down(menubar, "Edit");
    expect(reads(menubar)[0]).toBe("Undo ⌘Z");
  });
});

describe("opening a drawing", () => {
  /** A submenu rather than a dialog: layouts are edited rarely, so the list is
   *  short and stays short. */
  it("lists the drawings and marks the one that is open", async () => {
    const menubar = await down(await bar(), "File");
    const open = menubar.renderRoot.querySelector("li.submenu button")!;
    (open as HTMLElement).click();
    await menubar.updateComplete;

    const listed = [
      ...menubar.renderRoot.querySelectorAll("menu.drawings li"),
    ].map((one) => [
      one.querySelector(".label")!.textContent!.trim(),
      one.querySelector(".tick")!.textContent!.trim(),
    ]);
    expect(listed).toEqual([
      ["crossover-yard", ""],
      ["facing-pair", ""],
      ["gotthard", "✓"],
    ]);
  });

  it("says which drawing was chosen, and puts the menu up", async () => {
    const menubar = await down(await bar(), "File");
    (menubar.renderRoot.querySelector("li.submenu button") as HTMLElement).click();
    await menubar.updateComplete;
    const heard: string[] = [];
    menubar.addEventListener("open-drawing", (event) => {
      heard.push((event as CustomEvent<string>).detail);
    });

    const first = menubar.renderRoot.querySelector("menu.drawings li button")!;
    (first as HTMLElement).click();
    await menubar.updateComplete;

    expect(heard).toEqual(["crossover-yard"]);
    expect(menubar.renderRoot.querySelector("menu")).toBeNull();
  });
});

describe("what a dead item does", () => {
  it("draws it disabled", async () => {
    const menubar = await down(await bar(NOTHING), "File");
    const dead = [...menubar.renderRoot.querySelectorAll("menu > li button")]
      .filter((one) => (one as HTMLButtonElement).disabled)
      .map((one) => one.querySelector(".label")!.textContent!.trim());
    expect(dead).toEqual(["Open", "Save", "Save As…", "Export SVG…"]);
  });

  it("asks for nothing when it is clicked", async () => {
    const menubar = await down(await bar(NOTHING), "File");
    const save = [...menubar.renderRoot.querySelectorAll("menu > li button")].find(
      (one) => one.querySelector(".label")!.textContent!.trim() === "Save",
    )!;

    expect(await asked(menubar, () => (save as HTMLElement).click())).toEqual([]);
  });
});

describe("what stays one click", () => {
  /** Zoom and fit are pressed constantly while drawing, and `View ▸ Zoom in`
   *  is three clicks for what is now one. */
  it("pins zoom out, zoom in and fit at the right end", async () => {
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

    await down(menubar, "File");
    await down(menubar, "File");

    expect(heard).toEqual([true, false]);
  });

  it("puts the menu up and says so when an item is chosen", async () => {
    const menubar = await down(await bar(), "Edit");
    const heard = await asked(menubar, () => {
      const undo = menubar.renderRoot.querySelector("menu > li button")!;
      (undo as HTMLElement).click();
    });

    expect(heard).toEqual(["undo"]);
    expect(menubar.renderRoot.querySelector("menu")).toBeNull();
  });
});
