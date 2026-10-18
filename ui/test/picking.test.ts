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
 * publishes (#371) — so a press that is refused, because the rails have
 * power or because the store has no such railroad, leaves the page on the
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

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-app.js";
import type { TcApp } from "../src/ui/tc-app.js";
import type { TcSettings } from "../src/ui/tc-settings.js";
import {
  type Answers,
  band,
  edited,
  mounted,
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
  return [...dialog.renderRoot.querySelectorAll("ul.railroads li button")].map((one) => [
    one.querySelector(".label")!.textContent!.trim(),
    one.querySelector(".tick")!.textContent!.trim(),
  ]);
}

/** Why the dialog's railroad part is refused, `null` where it is not. */
function refused(dialog: TcSettings): string | null {
  return dialog.renderRoot.querySelector(".hint.refused")?.textContent?.trim() ?? null;
}

/** Choose a railroad the way an operator does: the gear, and a click on the
 *  railroad in the dialog it opens. */
async function pick(shell: TcApp, name: string): Promise<TcSettings> {
  const dialog = await settingsOpened(shell);
  const entries = [...dialog.renderRoot.querySelectorAll("ul.railroads li button")];
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
async function named(shell: TcApp, dialog: TcSettings, name: string): Promise<void> {
  const input = dialog.renderRoot.querySelector<HTMLInputElement>("sl-input.name")!;
  input.value = name;
  input.dispatchEvent(new Event("sl-input", { bubbles: true }));
  await settled(shell);
}

/** One of the two presses beside the name field. */
function making(dialog: TcSettings, which: "new" | "copy"): HTMLButtonElement {
  return dialog.renderRoot.querySelector<HTMLButtonElement>(`sl-button.${which}`)!;
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
  return dialog.renderRoot.querySelector(".hint.wrong")?.textContent?.trim() ?? null;
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

describe("the dialog against the rails", () => {
  /** Track power off is the precondition, and the band reads the row rather
   *  than turning anything off: a train already under a committed route keeps
   *  rolling whatever the software forgets (ADR-0060, ADR-0051). */
  it("asks for nothing while the track has power", async () => {
    const shell = await joined();
    await said(shell, POWER, { power: "on" });

    const dialog = await pick(shell, "otira");

    expect(written()).toEqual([]);
    expect(refused(dialog)).toBe(
      "the track has power: switch it off to load another railroad",
    );
    expect(loaded(shell)).toBe("toy");
  });

  it("asks again once the rails read dead", async () => {
    const shell = await joined();
    await said(shell, POWER, { power: "on" });
    await pick(shell, "otira");

    await said(shell, POWER, { power: "off" });
    await pick(shell, "otira");

    expect(written()).toEqual([
      { topic: RAILROAD_WANTED, payload: { railroad: "otira" } },
    ]);
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

  /** The dialog stays up, so the answer is seen to come back. */
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
    expect(dialog.renderRoot.textContent).toContain("the store lists no railroad");
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
 *  so it waits for unsaved edits to be saved, as ON does (ADR-0072,
 *  decision 4). */
describe("the dialog against unsaved edits", () => {
  it("asks for nothing, and names the drawing", async () => {
    const shell = await joined("edit");
    await said(shell, POWER, { power: "off" });
    session(shell).place("block", [8, 0]);
    edited(shell);
    await settled(shell);

    const dialog = await pick(shell, "otira");

    expect(written()).toEqual([]);
    expect(refused(dialog)).toBe("the drawing has unsaved edits — save first");
  });
});

/** Before the layout has said which railroad is loaded, nothing is on the
 *  other end of a press. */
describe("the dialog before the layout has said", () => {
  it("is refused, and says why", async () => {
    const shell = await mounted("run");

    const dialog = await settingsOpened(shell);

    expect(refused(dialog)).toBe("the layout has not said which railroad is loaded");
    expect(
      [...dialog.renderRoot.querySelectorAll<HTMLButtonElement>("ul.railroads button")].every(
        (one) => one.disabled,
      ),
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
    store.refuses = () => ({ status: 400, error: "drawing 'b' has no symbols" });

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
    await said(shell, POWER, { power: "on" });

    const dialog = await settingsOpened(shell);
    await named(shell, dialog, "b");

    expect(making(dialog, "new").disabled).toBe(true);
    expect(making(dialog, "copy").disabled).toBe(true);
    expect(refused(dialog)).toBe(
      "the track has power: switch it off to load another railroad",
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

    expect(store.saved).toEqual([{ path: "/railroads/toy/copy", body: { to: "b" } }]);
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
    expect(dialog.renderRoot.textContent).toContain("no railroad is loaded to copy");
  });
});
