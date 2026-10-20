// @vitest-environment happy-dom

/**
 * The rail down the left, as the app draws it out of look's elements
 * (ADR-0073): the views, what each view's groups carry, and what a dead
 * command does. What is dead and what is alive is `commands.test.ts`; the
 * driving control, on the band, is `run.test.ts`; this asks that the rail
 * draws what those say.
 */

import type { LookCommand, LookView } from "@rails49/look";
import { press } from "@rails49/look/testing";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { VIEWS } from "../src/model/views.js";
import "../src/ui/tc-app.js";
import type { TcApp } from "../src/ui/tc-app.js";
import {
  editing,
  mounted,
  pressed,
  rail,
  railButton,
  serving,
  settled,
} from "./support/shell.js";
import { brokering, joined } from "./support/session.js";

beforeEach(() => {
  serving();
});

afterEach(() => {
  document.body.replaceChildren();
});

/** The commands, top to bottom, whatever group they sit in. */
function commands(shell: TcApp): LookCommand[] {
  return [...rail(shell).querySelectorAll<LookCommand>("look-command[data-command]")];
}

/** The names the command groups are drawn under, top to bottom. */
function groups(shell: TcApp): string[] {
  return [...rail(shell).querySelectorAll("look-group")].map((one) => one.label);
}

/** Views are a list with one current entry (ADR-0038), the rail's first group. */
describe("the views", () => {
  it("offers every view the app has, in the order the list has them", async () => {
    const shell = await mounted("run");
    const views = [...rail(shell).querySelectorAll("look-view")];
    expect(views.map((one) => [one.name, one.label, one.icon])).toEqual(
      VIEWS.map((view) => [view.id, view.label, view.icon]),
    );
  });

  it("marks the one that is current and no other", async () => {
    for (const view of VIEWS) {
      const shell = await mounted(view.id);
      const marked = [...rail(shell).querySelectorAll("look-view")]
        .filter((one) => one.current)
        .map((one) => one.name);
      expect(marked).toEqual([view.id]);
      document.body.replaceChildren();
    }
  });

  it("switches to the view pressed, and says so in the hash", async () => {
    const shell = await mounted("run");
    press(rail(shell).querySelector<LookView>('look-view[name="stock"]')!);
    await settled(shell);
    expect(location.hash).toBe("#stock");
    expect(rail(shell).querySelector<LookView>('look-view[name="stock"]')!.current).toBe(true);
  });
});

describe("what each view's rail carries", () => {
  /** Every verb, with its label and its key as the tooltip a pointer resting
   *  there reads; look shows the key per platform. */
  it("names the editor's commands and the keys that do the same thing", async () => {
    const shell = await mounted("edit");
    expect(commands(shell).map((one) => [one.label, one.key])).toEqual([
      ["Zoom out", "−"],
      ["Zoom in", "+"],
      ["Fit", "0"],
      ["Netlist", "N"],
      ["Save", "Mod+S"],
      ["Export SVG…", ""],
      ["Undo", "Mod+Z"],
      ["Redo", "Shift+Mod+Z"],
    ]);
  });

  it("groups them under the names the menus carried", async () => {
    expect(groups(await mounted("edit"))).toEqual(["View", "File", "Edit"]);
  });

  /** The run view's document is a railroad somebody else is running: no File
   *  and no Edit. The driving control is the whole railroad's, so it is on
   *  the band rather than here (#871). */
  it("gives the run view the three view commands and nothing else", async () => {
    const shell = await mounted("run");
    expect(commands(shell).map((one) => one.dataset["command"])).toEqual([
      "zoom-out",
      "zoom-in",
      "fit",
    ]);
    expect(rail(shell).querySelectorAll("look-command")).toHaveLength(3);
    expect(rail(shell).querySelector("look-group[end]")).toBeNull();
  });

  /** Neither draws a document with a viewport, so the views are the whole of
   *  their rail (ui/THROTTLE.md, ui/STOCK.md). */
  it.each(["throttle", "stock"] as const)("gives the %s view no commands", async (view) => {
    const shell = await mounted(view);
    expect(rail(shell).querySelectorAll("look-command")).toHaveLength(0);
  });

  /** The four selection verbs read in the right-click menu instead (menu.test.ts). */
  it("leaves the selection verbs off the editor's rail", async () => {
    const shell = await mounted("edit");
    for (const id of ["rotate", "flip", "delete", "properties"]) {
      expect(railButton(shell, id)).toBeNull();
    }
  });

  it("does what the command pressed says", async () => {
    brokering();
    const shell = await joined("edit");
    await pressed(shell, "netlist");
    expect(editing(shell).netlist).toBe(true);
  });
});

describe("what a dead command does", () => {
  /** Nothing open: nothing to save, export, undo or inspect. */
  it("draws it disabled", async () => {
    const shell = await mounted("edit");
    const dead = commands(shell)
      .filter((one) => one.disabled)
      .map((one) => one.dataset["command"]);
    expect(dead).toEqual(["netlist", "save", "export-svg", "undo", "redo"]);
  });

  it("does nothing when it is pressed", async () => {
    const shell = await mounted("edit");
    await pressed(shell, "netlist");
    expect(editing(shell).netlist).toBe(false);
  });
});
