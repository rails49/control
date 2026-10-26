// @vitest-environment happy-dom

/**
 * Choosing a railroad in the settings dialog, end to end through the app
 * ([ADR-0060](../../docs/adr/0060-the-railroad-is-chosen-while-the-apps-run-not-at-startup.md),
 * [ADR-0072](../../docs/adr/0072-the-railroad-is-loaded-from-a-settings-dialog-and-the-store-records-which.md)):
 * the press goes out on the client the session holds, on
 * `tc49/layout/railroad_wanted`, which whichever binding of the layout
 * interface is running is what answers.
 *
 * **It asks and does not load.** The app opens a railroad on one thing and
 * one thing only — `tc49/layout/state/railroad`, the row the answering app
 * publishes (#371) — so a press that is refused, because the store has no
 * such railroad, leaves the page on the
 * railroad that is still running. The dialog is the gesture and the row is
 * the answer, which is the same shape as the band's power presses
 * (ADR-0035).
 *
 * **Making a railroad is the dialog's too** (#737, ADR-0072 decision 3): New
 * writes an empty drawing and Copy loaded as… has the store copy every
 * document of the loaded one, and each then asks for what it wrote the same
 * way a press on the list does. A name or a write refused shows its words in
 * the dialog and asks for nothing.
 *
 * A DOM test because it crosses the band, the dialog, the app and the run
 * view's client.
 * The session itself is `support/session.ts`, shared with the other suites.
 */

import type { LookView } from "@rails49/look";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ANSWER_MS } from "../src/model/settings.js";
import "../src/ui/tc-app.js";
import type { TcApp } from "../src/ui/tc-app.js";
import type { TcSettings } from "../src/ui/tc-settings.js";
import {
  type Answers,
  band,
  edited,
  CLEAN,
  mounted,
  power,
  rail,
  serving,
  session,
  settingsOpened,
  settled,
} from "./support/shell.js";
import {
  brokering,
  joined,
  loads,
  said,
  stored,
  STOCK,
  DERIVES,
  unbrokered,
  written,
} from "./support/session.js";

const RAILROAD_WANTED = "tc49/layout/railroad_wanted";
const POWER = "tc49/layout/state/power";
const POWER_WANTED = "tc49/layout/power_wanted";
const ALLOCATION = "tc49/dispatch/state/allocation";

/** The dispatcher's picture of a railroad it has just built: nothing on it. */
const EMPTY = { trains: {}, locks: {}, requests: [] };

/** The railroads this store has, the toy one among them: a list with one
 *  entry could not tell a choice from a tick. */
const HAS = ["toy", "otira", "reversing-loops"];

/** The store behind the suite, for what it was given to write. */
let store: Answers;

beforeEach(() => {
  brokering();
  store = serving({
    drawings: HAS,
    rosterOf: () => STOCK,
    read: stored,
    review: () => Promise.resolve(DERIVES),
  });
});

afterEach(unbrokered);

/** An app joined to the broker, on the toy railroad, with the rails dead —
 *  which is the whole of the precondition on picking another (ADR-0060). */
async function dark(): Promise<TcApp> {
  const shell = await joined();
  await said(shell, POWER, { power: "off" });
  return shell;
}

/** The dialog's railroads, each as its name and its tick. */
function listed(dialog: TcSettings): string[][] {
  return [
    ...dialog.renderRoot.querySelectorAll(
      "ul.railroads li button:not(.delete)",
    ),
  ].map((one) => [
    one.querySelector(".label")!.textContent!.trim(),
    one.querySelector(".tick")!.textContent!.trim(),
  ]);
}

/** Why the dialog's railroad part is refused, `null` where it is not. */
function refused(dialog: TcSettings): string | null {
  return (
    dialog.renderRoot.querySelector(".hint.refused")?.textContent?.trim() ??
    null
  );
}

/** Choose a railroad the way an operator does: the gear, and a click on the
 *  railroad in the dialog it opens. */
async function pick(shell: TcApp, name: string): Promise<TcSettings> {
  const dialog = await settingsOpened(shell);
  const entries = [
    ...dialog.renderRoot.querySelectorAll(
      "ul.railroads li button:not(.delete)",
    ),
  ];
  const entry = entries.find(
    (one) => one.querySelector(".label")!.textContent!.trim() === name,
  ) as HTMLElement | undefined;
  entry?.click();
  await settled(shell);
  return dialog;
}

/** What the band names as the loaded railroad. */
function loaded(shell: TcApp): string {
  return band(shell).querySelector("look-about")!.name;
}

/** Type a name into the dialog's name field, the way a person does. */
async function named(
  shell: TcApp,
  dialog: TcSettings,
  name: string,
): Promise<void> {
  const input =
    dialog.renderRoot.querySelector<HTMLInputElement>("sl-input.name")!;
  input.value = name;
  input.dispatchEvent(new Event("sl-input", { bubbles: true }));
  await settled(shell);
}

/** One of the two presses beside the name field. */
function making(dialog: TcSettings, which: "new" | "copy"): HTMLButtonElement {
  return dialog.renderRoot.querySelector<HTMLButtonElement>(
    `sl-button.${which}`,
  )!;
}

/** Type `name` and press New, or Copy loaded as…, the way a person does. */
async function made(
  shell: TcApp,
  which: "new" | "copy",
  name: string,
): Promise<TcSettings> {
  const dialog = await settingsOpened(shell);
  await named(shell, dialog, name);
  making(dialog, which).click();
  await settled(shell);
  return dialog;
}

/** What the dialog says a name or a write was refused with, `null` where
 *  nothing was. */
function wrong(dialog: TcSettings): string | null {
  return (
    dialog.renderRoot.querySelector(".hint.wrong")?.textContent?.trim() ?? null
  );
}

describe("the dialog asks on the bus", () => {
  it("publishes the railroad that was chosen and nothing else", async () => {
    const shell = await dark();

    await pick(shell, "otira");

    expect(written()).toEqual([
      { topic: RAILROAD_WANTED, payload: { railroad: "otira" } },
    ]);
  });

  /** The one thing that loads a railroad is the row the answering app
   *  publishes. A press is not an answer: the store's documents are not read
   *  and the band goes on naming what is running, so a gesture nothing
   *  answered costs nothing. */
  it("loads nothing until the row says so", async () => {
    const shell = await dark();

    await pick(shell, "otira");

    expect(loaded(shell)).toBe("toy");
  });

  it("opens the railroad when the row moves to it", async () => {
    const shell = await dark();
    await pick(shell, "otira");

    await loads(shell, "otira");

    expect(loaded(shell)).toBe("otira");
  });
});

/**
 * The band names the railroad the apps run, which is the row's (#732), and a
 * row naming `""` is none.
 */
describe("what the band names as loaded", () => {
  /** A row naming `""` is a broker with no railroad loaded (#727): nothing is
   *  read for it, neither a roster nor a drawing called `""`. */
  it("says no railroad is loaded where the row names none, and reads nothing for it", async () => {
    const shell = await joined();
    const asked: string[] = [];
    const store = globalThis.fetch;
    globalThis.fetch = ((path: string, init?: RequestInit) => {
      asked.push(path);
      return store(path, init);
    }) as typeof fetch;

    await loads(shell, "");

    expect(loaded(shell)).toBe("no railroad loaded");
    expect(asked.filter((path) => path.startsWith("/rosters/"))).toEqual([]);
    expect(asked.filter((path) => path.startsWith("/drawings/"))).toEqual([]);
  });

  it("names the railroad again once the row does", async () => {
    const shell = await joined();
    await loads(shell, "");

    await loads(shell, "otira");

    expect(loaded(shell)).toBe("otira");
  });
});

/** What the dialog says while a press waits for the track to go dead, `null`
 *  where nothing waits. */
function stopping(dialog: TcSettings): string | null {
  return (
    dialog.renderRoot.querySelector(".stopping .hint")?.textContent?.trim() ??
    null
  );
}

/**
 * Track power off is the precondition (ADR-0060), and a pick takes the power
 * off itself: it drains, and asks for the railroad once the row reads off
 * (ADR-0085, decision 5). A drain and not a cut, so a train already under a
 * committed route comes to rest rather than stopping across a turnout.
 */
describe("the dialog against the rails", () => {
  it("asks for the drain, and for no railroad until the track reads off", async () => {
    const shell = await joined();
    await said(shell, POWER, { power: "on" });

    const dialog = await pick(shell, "otira");

    expect(written()).toEqual([
      { topic: POWER_WANTED, payload: { power: "draining" } },
    ]);
    expect(refused(dialog)).toBeNull();
    expect(stopping(dialog)).toBe("stopping trains…");
    expect(loaded(shell)).toBe("toy");

    await said(shell, POWER, { power: "draining" });
    expect(written()).toHaveLength(1);
    await said(shell, POWER, { power: "off" });
    await settled(shell);

    expect(written()).toEqual([
      { topic: POWER_WANTED, payload: { power: "draining" } },
      { topic: RAILROAD_WANTED, payload: { railroad: "otira" } },
    ]);
    expect(stopping(dialog)).toBeNull();
  });

  it("asks for no second drain while the track is already draining", async () => {
    const shell = await joined();
    await said(shell, POWER, { power: "draining" });

    await pick(shell, "otira");
    await said(shell, POWER, { power: "off" });
    await settled(shell);

    expect(written()).toEqual([
      { topic: RAILROAD_WANTED, payload: { railroad: "otira" } },
    ]);
  });

  /** A drain has no time limit, so the stop sign is beside the wait. */
  it("asks for off at once on the stop sign", async () => {
    const shell = await joined();
    await said(shell, POWER, { power: "on" });
    const dialog = await pick(shell, "otira");

    dialog.renderRoot
      .querySelector<HTMLElement>(".stopping sl-button.stop")!
      .click();
    await settled(shell);

    expect(written()).toEqual([
      { topic: POWER_WANTED, payload: { power: "draining" } },
      { topic: POWER_WANTED, payload: { power: "off" } },
    ]);
  });

  /** Closing the dialog abandons the load; power stays as it is. */
  it("asks for nothing more once the dialog is closed", async () => {
    const shell = await joined();
    await said(shell, POWER, { power: "on" });
    const dialog = await pick(shell, "otira");

    dialog.renderRoot
      .querySelector<HTMLElement>("sl-button[slot=footer]")!
      .click();
    await settled(shell);
    await said(shell, POWER, { power: "off" });
    await settled(shell);

    expect(written()).toEqual([
      { topic: POWER_WANTED, payload: { power: "draining" } },
    ]);
  });

  it("drains before New writes anything", async () => {
    const shell = await joined();
    await said(shell, POWER, { power: "on" });

    await made(shell, "new", "b");
    expect(store.saved).toEqual([]);
    await said(shell, POWER, { power: "off" });
    await settled(shell);

    expect(store.saved.map(({ path }) => path)).toEqual(["/drawings/b"]);
    expect(written()).toEqual([
      { topic: POWER_WANTED, payload: { power: "draining" } },
      { topic: RAILROAD_WANTED, payload: { railroad: "b" } },
    ]);
  });

  it("is refused while the layout has not said whether the track has power", async () => {
    const shell = await joined();

    const dialog = await pick(shell, "otira");

    expect(written()).toEqual([]);
    expect(refused(dialog)).toBe(
      "the layout has not said whether the track has power",
    );
  });
});

describe("what the dialog lists", () => {
  it("lists what the store has and ticks the one that is loaded", async () => {
    const shell = await dark();
    const dialog = await settingsOpened(shell);

    expect(listed(dialog)).toEqual([
      ["toy", "✓"],
      ["otira", ""],
      ["reversing-loops", ""],
    ]);
  });

  /** The list is asked for each time the dialog opens, so a railroad made
   *  since the page loaded is there to load. */
  it("asks the store for the list each time it opens", async () => {
    const shell = await dark();
    serving({
      drawings: [...HAS, "fresh"],
      rosterOf: () => STOCK,
      read: stored,
      review: () => Promise.resolve(DERIVES),
    });

    const dialog = await settingsOpened(shell);

    expect(listed(dialog).map(([name]) => name)).toContain("fresh");
  });

  /** The tick says which railroad is loaded, and that is all it says:
   *  re-reading it would throw away whatever has been drawn since (#101). */
  it("asks for nothing when the loaded railroad is pressed", async () => {
    const shell = await dark();

    await pick(shell, "toy");

    expect(written()).toEqual([]);
  });

  /** The dialog stays up until the pick has landed (#902), so the answer is
   *  seen to come back. */
  it("stays open, and moves the tick when the row names the new railroad", async () => {
    const shell = await dark();
    const dialog = await pick(shell, "otira");
    expect(dialog.open).toBe(true);
    expect(listed(dialog).find(([name]) => name === "otira")![1]).toBe("");

    await loads(shell, "otira");

    expect(dialog.open).toBe(true);
    expect(listed(dialog).find(([name]) => name === "otira")![1]).toBe("✓");
  });

  /** A list of nothing is an empty box that looks broken. */
  it("says so where the store lists no railroad", async () => {
    serving({ drawings: [] });
    const shell = await mounted("run");

    const dialog = await settingsOpened(shell);

    expect(dialog.renderRoot.querySelector("ul.railroads")).toBeNull();
    expect(dialog.renderRoot.textContent).toContain(
      "the store lists no railroad",
    );
  });

  it("shuts when the dialog says it was closed", async () => {
    const shell = await dark();
    const dialog = await settingsOpened(shell);

    dialog.dispatchEvent(
      new CustomEvent("settings-closed", { bubbles: true, composed: true }),
    );
    await settled(shell);

    expect(dialog.open).toBe(false);
  });
});

/** Loading a railroad throws away what the page holds of the one it leaves,
 *  so the drawing's edits are saved first and the load follows (ADR-0085,
 *  decision 1). A save that does not land loads nothing. */
describe("the dialog against unsaved edits", () => {
  async function drawnOn(): Promise<TcApp> {
    const shell = await joined("edit");
    await said(shell, POWER, { power: "off" });
    session(shell).place("block", [8, 0]);
    edited(shell);
    await settled(shell);
    return shell;
  }

  it("saves the drawing, then asks for the railroad picked", async () => {
    const shell = await drawnOn();

    const dialog = await pick(shell, "otira");

    expect(refused(dialog)).toBeNull();
    expect(store.saved.map(({ path }) => path)).toEqual(["/drawings/toy"]);
    expect(written()).toEqual([
      { topic: RAILROAD_WANTED, payload: { railroad: "toy" } },
      { topic: RAILROAD_WANTED, payload: { railroad: "otira" } },
    ]);
  });

  it("asks for nothing where the save failed, and says so", async () => {
    store.refuses = (path) =>
      path === "/drawings/toy"
        ? { status: 507, error: "the disk is full" }
        : null;
    const shell = await drawnOn();

    const dialog = await pick(shell, "otira");

    expect(written()).toEqual([]);
    expect(wrong(dialog)).toBe(
      "the drawing could not be saved, so nothing was loaded",
    );
  });

  it("saves the drawing before Copy loaded as… copies it", async () => {
    const shell = await drawnOn();

    await made(shell, "copy", "b");

    expect(store.saved.map(({ path }) => path)).toEqual([
      "/drawings/toy",
      "/railroads/toy/copy",
    ]);
  });
});

/** Before the layout has said which railroad is loaded, nothing is on the
 *  other end of a press. */
describe("the dialog before the layout has said", () => {
  it("is refused, and says why", async () => {
    const shell = await mounted("run");

    const dialog = await settingsOpened(shell);

    expect(refused(dialog)).toBe(
      "the layout has not said which railroad is loaded",
    );
    expect(
      [
        ...dialog.renderRoot.querySelectorAll<HTMLButtonElement>(
          "ul.railroads button",
        ),
      ].every((one) => one.disabled),
    ).toBe(true);
  });
});

/** With no railroad loaded the binding reads no supply, and the first
 *  railroad on a new box is loaded from here (ADR-0072, decision 6). */
describe("the dialog with no railroad loaded", () => {
  it("asks for the railroad pressed, with nothing said about the supply", async () => {
    const shell = await joined();
    await loads(shell, "");

    const dialog = await pick(shell, "otira");

    expect(refused(dialog)).toBeNull();
    expect(written()).toEqual([
      { topic: RAILROAD_WANTED, payload: { railroad: "otira" } },
    ]);
  });
});

/**
 * New writes an empty drawing under the name and asks for it: the railroad
 * exists in the store before anything is asked to load it, and the binding
 * answers the ask as it answers any other (ADR-0072, decision 3). No roster
 * and no script are written: a railroad with none is an ordinary one.
 */
describe("New railroad", () => {
  it("writes an empty drawing under the name, then asks for it", async () => {
    const shell = await dark();

    await made(shell, "new", "b");

    expect(store.saved).toEqual([
      { path: "/drawings/b", body: { drawing: "b", symbols: {}, wires: [] } },
    ]);
    expect(written()).toEqual([
      { topic: RAILROAD_WANTED, payload: { railroad: "b" } },
    ]);
  });

  it("refuses a taken name, writes nothing, and asks for nothing", async () => {
    const shell = await dark();

    const dialog = await made(shell, "new", "otira");

    expect(store.saved).toEqual([]);
    expect(written()).toEqual([]);
    expect(wrong(dialog)).toBe("'otira' is already a railroad");
  });

  it("shows the store's words where the write is refused, and asks for nothing", async () => {
    const shell = await dark();
    store.refuses = () => ({
      status: 400,
      error: "drawing 'b' has no symbols",
    });

    const dialog = await made(shell, "new", "b");

    expect(written()).toEqual([]);
    expect(wrong(dialog)).toBe("drawing 'b' has no symbols");
  });

  it("is dead with no name typed", async () => {
    const shell = await dark();

    const dialog = await settingsOpened(shell);

    expect(making(dialog, "new").disabled).toBe(true);
    expect(making(dialog, "copy").disabled).toBe(true);
  });

  /** The same reasons the list is dead for, in the same words beneath it. */
  it("is dead for the list's reason, which reads once beneath the list", async () => {
    const shell = await joined();

    const dialog = await settingsOpened(shell);
    await named(shell, dialog, "b");

    expect(making(dialog, "new").disabled).toBe(true);
    expect(making(dialog, "copy").disabled).toBe(true);
    expect(refused(dialog)).toBe(
      "the layout has not said whether the track has power",
    );
  });

  /** The dialog stays up, so the new railroad is seen to arrive: the list is
   *  asked for again once the write is through, and the tick lands on the
   *  new name when the row names it. */
  it("lists the new railroad, and ticks it when the row names it", async () => {
    const shell = await dark();
    const dialog = await settingsOpened(shell);
    await named(shell, dialog, "b");
    // The store lists what it holds, so the list has `b` once it is written.
    store.drawings = [...HAS, "b"];

    making(dialog, "new").click();
    await settled(shell);
    expect(store.saved.map(({ path }) => path)).toEqual(["/drawings/b"]);
    expect(listed(dialog).map(([name]) => name)).toContain("b");
    await loads(shell, "b");

    expect(listed(dialog).find(([name]) => name === "b")![1]).toBe("✓");
  });

  /** With no railroad loaded New is how the first one is made (ADR-0072,
   *  decision 6). */
  it("makes the first railroad on a box with none loaded", async () => {
    const shell = await joined();
    await loads(shell, "");

    await made(shell, "new", "b");

    expect(store.saved.map(({ path }) => path)).toEqual(["/drawings/b"]);
    expect(written()).toEqual([
      { topic: RAILROAD_WANTED, payload: { railroad: "b" } },
    ]);
  });
});

/**
 * Copy loaded as… has the store copy every document of the loaded railroad
 * under the name, and asks for it. The loaded railroad is the row's, so the
 * copy is of what the apps run and not of the drawing the editor holds.
 */
describe("Copy loaded railroad as…", () => {
  it("has the store copy the loaded railroad under the name, then asks for it", async () => {
    const shell = await dark();

    await made(shell, "copy", "b");

    expect(store.saved).toEqual([
      { path: "/railroads/toy/copy", body: { to: "b" } },
    ]);
    expect(written()).toEqual([
      { topic: RAILROAD_WANTED, payload: { railroad: "b" } },
    ]);
  });

  it("refuses a taken name before the store sees it", async () => {
    const shell = await dark();

    const dialog = await made(shell, "copy", "otira");

    expect(store.saved).toEqual([]);
    expect(written()).toEqual([]);
    expect(wrong(dialog)).toBe("'otira' is already a railroad");
  });

  /** A name the page's list did not have but the store does — made on
   *  another page since the dialog opened — is the store's to refuse. */
  it("shows the store's words on a 409, and asks for nothing", async () => {
    const shell = await dark();
    store.refuses = () => ({ status: 409, error: "'b' is already a railroad" });

    const dialog = await made(shell, "copy", "b");

    expect(written()).toEqual([]);
    expect(wrong(dialog)).toBe("'b' is already a railroad");
  });

  it("is dead with no railroad loaded, and says so", async () => {
    const shell = await joined();
    await loads(shell, "");

    const dialog = await settingsOpened(shell);
    await named(shell, dialog, "b");

    expect(making(dialog, "copy").disabled).toBe(true);
    expect(making(dialog, "new").disabled).toBe(false);
    expect(dialog.renderRoot.textContent).toContain(
      "no railroad is loaded to copy",
    );
  });
});

/** The railroad on the row named `name`'s Delete press, `undefined` where the
 *  row has none. */
function deleting(
  dialog: TcSettings,
  name: string,
): HTMLButtonElement | undefined {
  const row = [...dialog.renderRoot.querySelectorAll("ul.railroads li")].find(
    (one) => one.querySelector(".label")?.textContent?.trim() === name,
  );
  return row?.querySelector<HTMLButtonElement>("button.delete") ?? undefined;
}

/** The rows that have a Delete press, by name. */
function deletable(dialog: TcSettings): string[] {
  return listed(dialog)
    .map(([name]) => name!)
    .filter((name) => deleting(dialog, name) !== undefined);
}

/** The question a row asks once its Delete is pressed: its words, and the
 *  press of the two beneath them that `which` names. */
function asked(dialog: TcSettings, which: "confirm" | "cancel"): HTMLElement {
  return dialog.renderRoot.querySelector<HTMLElement>(
    `ul.railroads li sl-button.${which}`,
  )!;
}

/**
 * Delete asks the store to delete a railroad whole (#1074,
 * `DELETE /railroads/<name>`, #1073), once more in the row before anything
 * is sent. The loaded railroad has no Delete — the steel runs it, and another
 * is loaded first — and nor has the drawing the page holds; neither depends on
 * track power, Delete touching nothing the layout runs.
 */
describe("Delete railroad", () => {
  it("is on every row but the loaded one", async () => {
    const shell = await dark();

    const dialog = await settingsOpened(shell);

    expect(deletable(dialog)).toEqual(["otira", "reversing-loops"]);
  });

  /** The page holds the drawing the row names once it has been read, so the
   *  two differ only between the row moving and the read landing; the dialog
   *  is handed another `opened` here to stand for that moment. */
  it("is not on the row of the drawing the page holds", async () => {
    const shell = await dark();
    const dialog = await settingsOpened(shell);

    dialog.opened = "otira";
    await settled(shell);

    expect(deletable(dialog)).toEqual(["reversing-loops"]);
  });

  it("is live with the track powered", async () => {
    const shell = await joined();
    await said(shell, POWER, { power: "on" });

    const dialog = await settingsOpened(shell);

    expect(deleting(dialog, "otira")!.disabled).toBe(false);
  });

  it("is dead while the layout has not said what is loaded", async () => {
    const shell = await mounted("run");

    const dialog = await settingsOpened(shell);

    expect(deletable(dialog)).toEqual(HAS);
    for (const name of deletable(dialog)) {
      expect(deleting(dialog, name)!.disabled).toBe(true);
    }
  });

  it("is dead while a pick is out", async () => {
    const shell = await dark();

    const dialog = await pick(shell, "otira");

    expect(deleting(dialog, "reversing-loops")!.disabled).toBe(true);
  });

  it("asks in the row, and Cancel sends nothing", async () => {
    const shell = await dark();
    const dialog = await settingsOpened(shell);

    deleting(dialog, "otira")!.click();
    await settled(shell);
    expect(dialog.renderRoot.textContent).toContain(
      "Delete otira? Its drawing, roster, script and clock go.",
    );
    asked(dialog, "cancel").click();
    await settled(shell);

    expect(store.deleted).toEqual([]);
    expect(deleting(dialog, "otira")).toBeDefined();
  });

  /** The dialog stays in the page while it is closed, so a question left
   *  asking would greet the next opening one press from deleting (#1081). */
  it("asks nothing once the dialog is closed and opened again", async () => {
    const shell = await dark();
    const first = await settingsOpened(shell);
    deleting(first, "otira")!.click();
    await settled(shell);
    first.dispatchEvent(
      new CustomEvent("settings-closed", { bubbles: true, composed: true }),
    );
    await settled(shell);
    expect(first.open).toBe(false);

    const dialog = await settingsOpened(shell);

    expect(dialog.open).toBe(true);
    expect(dialog.renderRoot.querySelector("ul.railroads li.deleting")).toBeNull();
    expect(dialog.renderRoot.textContent).not.toContain("Delete otira?");
    expect(deleting(dialog, "otira")).toBeDefined();
    expect(store.deleted).toEqual([]);
  });

  it("asks in one row at a time", async () => {
    const shell = await dark();
    const dialog = await settingsOpened(shell);

    deleting(dialog, "otira")!.click();
    await settled(shell);
    deleting(dialog, "reversing-loops")!.click();
    await settled(shell);

    expect(
      dialog.renderRoot.querySelectorAll("ul.railroads li sl-button.confirm"),
    ).toHaveLength(1);
    expect(deleting(dialog, "otira")).toBeDefined();
  });

  it("deletes the railroad, and the list drops it", async () => {
    store.drawings = [...HAS, "b"];
    const shell = await dark();
    const dialog = await settingsOpened(shell);
    const changed = vi.fn();
    shell.addEventListener("railroads-changed", changed);

    deleting(dialog, "b")!.click();
    await settled(shell);
    // The store lists what it holds, so the list loses `b` once it is gone.
    store.drawings = HAS;
    asked(dialog, "confirm").click();
    await settled(shell);

    expect(store.deleted).toEqual(["/railroads/b"]);
    expect(changed).toHaveBeenCalledOnce();
    expect(listed(dialog).map(([name]) => name)).toEqual(HAS);
    expect(written()).toEqual([]);
  });

  it("shows the store's words on a 409, and leaves the row", async () => {
    const shell = await dark();
    store.refuses = () => ({
      status: 409,
      error: "'otira' is loaded; load another railroad first",
    });
    const dialog = await settingsOpened(shell);

    deleting(dialog, "otira")!.click();
    await settled(shell);
    asked(dialog, "confirm").click();
    await settled(shell);

    expect(store.deleted).toEqual([]);
    expect(wrong(dialog)).toBe(
      "'otira' is loaded; load another railroad first",
    );
    expect(listed(dialog).map(([name]) => name)).toContain("otira");
    expect(deleting(dialog, "otira")).toBeDefined();
  });
});

/**
 * A railroad whose drawing is not a valid drawing is picked like any other
 * (#900, [ADR-0085](../../docs/adr/0085-the-editor-saves-when-it-is-left-and-a-railroad-can-be-named-without-being-built.md),
 * decision 4): the list carries no mark for it and refuses it nothing, and
 * the layout's row names it with `built: false`, so the page opens its
 * drawing in the Edit view to be fixed and ON waits, as after a restart.
 */
describe("a railroad whose drawing is invalid", () => {
  beforeEach(() => {
    serving({
      drawings: HAS,
      rosterOf: () => STOCK,
      read: stored,
      review: () =>
        Promise.resolve({ ...CLEAN, refused: "pin 'b1.a' is not wired" }),
    });
  });

  /** The view that is current, by the rail's mark. */
  function current(shell: TcApp): string {
    return rail(shell).querySelector<LookView>("look-view[current]")!.name;
  }

  it("is listed unmarked, and its press is live", async () => {
    const shell = await dark();
    const dialog = await settingsOpened(shell);

    expect(listed(dialog)).toEqual([
      ["toy", "✓"],
      ["otira", ""],
      ["reversing-loops", ""],
    ]);
    const buttons = [
      ...dialog.renderRoot.querySelectorAll<HTMLButtonElement>(
        "ul.railroads li button:not(.delete)",
      ),
    ];
    expect(buttons.map((one) => one.disabled)).toEqual([false, false, false]);
    expect(refused(dialog)).toBeNull();
  });

  it("is asked for on the bus like any other", async () => {
    const shell = await dark();

    await pick(shell, "otira");

    expect(written()).toEqual([
      { topic: RAILROAD_WANTED, payload: { railroad: "otira" } },
    ]);
  });

  it("ends with its drawing open in the Edit view, and ON refused", async () => {
    const shell = await dark();
    await pick(shell, "otira");

    await said(shell, "tc49/layout/state/railroad", {
      name: "otira",
      at: 7,
      built: false,
    });
    // The layout clears its rows on a load and says the supply again.
    await said(shell, POWER, { power: "off" });

    expect(loaded(shell)).toBe("otira");
    expect(session(shell).drawing.drawing).toBe("otira");
    expect(current(shell)).toBe("edit");
    expect(power(shell).toggleReason).toBe("Fix the drawing first");
  });
});

/** The view that is current, by the rail's mark. */
function viewed(shell: TcApp): string {
  return rail(shell).querySelector<LookView>("look-view[current]")!.name;
}

/** The railroads whose rows wear the spinner. */
function busy(dialog: TcSettings): string[] {
  return [...dialog.renderRoot.querySelectorAll("ul.railroads li button")]
    .filter((one) => one.querySelector("sl-spinner") !== null)
    .map((one) => one.querySelector(".label")!.textContent!.trim());
}

/** What a row says beside its name where the layout did not answer. */
function unanswered(dialog: TcSettings, name: string): string | null {
  const row = [
    ...dialog.renderRoot.querySelectorAll("ul.railroads li button"),
  ].find((one) => one.querySelector(".label")!.textContent!.trim() === name);
  return row?.querySelector(".unanswered")?.textContent?.trim() ?? null;
}

/**
 * A pick looks busy until it has landed (#902): the row wears a spinner from
 * the press until the page holds the drawing, the row names it and the
 * dispatcher has said its picture since; then the dialog goes and the page
 * shows the Run view, or the Edit view where nothing was built. A pick that
 * has not landed `ANSWER_MS` after it was asked for stops, and its row says
 * the layout did not answer.
 */
describe("a pick on its way", () => {
  it("wears the spinner, and its presses are dead, until it lands", async () => {
    const shell = await dark();

    const dialog = await pick(shell, "otira");

    expect(busy(dialog)).toEqual(["otira"]);
    const buttons = [
      ...dialog.renderRoot.querySelectorAll<HTMLButtonElement>(
        "ul.railroads li button:not(.delete)",
      ),
    ];
    expect(buttons.every((one) => one.disabled)).toBe(true);
  });

  it("is still on its way once the row names it, until the allocation", async () => {
    const shell = await dark();
    const dialog = await pick(shell, "otira");

    await loads(shell, "otira");

    expect(dialog.open).toBe(true);
    expect(busy(dialog)).toEqual(["otira"]);
  });

  it("closes the dialog on the run view once the dispatcher has said", async () => {
    const shell = await joined("throttle");
    await said(shell, POWER, { power: "off" });
    const dialog = await pick(shell, "otira");

    await loads(shell, "otira");
    await said(shell, ALLOCATION, EMPTY);

    expect(dialog.open).toBe(false);
    expect(viewed(shell)).toBe("run");
  });

  /** The allocation of the railroad being left is not the new one's. */
  it("does not take an allocation before the row for the new one", async () => {
    const shell = await dark();
    const dialog = await pick(shell, "otira");

    await said(shell, ALLOCATION, EMPTY);
    await loads(shell, "otira");

    expect(dialog.open).toBe(true);
  });

  it("wears the spinner through the drain", async () => {
    const shell = await joined();
    await said(shell, POWER, { power: "on" });

    const dialog = await pick(shell, "otira");

    expect(busy(dialog)).toEqual(["otira"]);
    await said(shell, POWER, { power: "off" });
    await settled(shell);
    expect(busy(dialog)).toEqual(["otira"]);
  });

  it("stops where the drain was given up", async () => {
    const shell = await joined();
    await said(shell, POWER, { power: "on" });
    const dialog = await pick(shell, "otira");

    await said(shell, POWER, { power: "draining" });
    await said(shell, POWER, { power: "on" });

    expect(busy(dialog)).toEqual([]);
  });

  it("closes the dialog on the edit view where nothing was built", async () => {
    serving({
      drawings: HAS,
      rosterOf: () => STOCK,
      read: stored,
      review: () =>
        Promise.resolve({ ...CLEAN, refused: "pin 'b1.a' is not wired" }),
    });
    const shell = await dark();
    const dialog = await pick(shell, "otira");

    await said(shell, "tc49/layout/state/railroad", {
      name: "otira",
      at: 7,
      built: false,
    });

    expect(dialog.open).toBe(false);
    expect(viewed(shell)).toBe("edit");
  });

  describe("unanswered", () => {
    beforeEach(() => {
      vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    });
    afterEach(() => {
      vi.useRealTimers();
    });

    it("says the layout did not answer once ANSWER_MS has passed", async () => {
      const shell = await dark();
      const dialog = await pick(shell, "otira");

      await vi.advanceTimersByTimeAsync(ANSWER_MS - 1);
      await settled(shell);
      expect(busy(dialog)).toEqual(["otira"]);
      expect(unanswered(dialog, "otira")).toBeNull();

      await vi.advanceTimersByTimeAsync(1);
      await settled(shell);
      expect(busy(dialog)).toEqual([]);
      expect(unanswered(dialog, "otira")).toBe("the layout did not answer");
      expect(dialog.open).toBe(true);
    });

    it("gives the layout ANSWER_MS from the ask, not from a drain", async () => {
      const shell = await joined();
      await said(shell, POWER, { power: "on" });
      const dialog = await pick(shell, "otira");

      await vi.advanceTimersByTimeAsync(ANSWER_MS);
      await settled(shell);
      expect(busy(dialog)).toEqual(["otira"]);
      await said(shell, POWER, { power: "off" });
      await settled(shell);
      await vi.advanceTimersByTimeAsync(ANSWER_MS - 1);
      await settled(shell);

      expect(busy(dialog)).toEqual(["otira"]);
    });
  });
});
