// @vitest-environment happy-dom

/**
 * The controls in the heading of the list under the roster
 * ([#1357](https://github.com/rails49/control/issues/1357)): a menu with New,
 * Load, Rename, Delete and Repeat
 * ([#1368](https://github.com/rails49/control/issues/1368)), the Record
 * switch, and Start.
 *
 * `tc-timetable-controls` draws them in the run view, in the heading of
 * `tc-requests`. Each test stands up a joined session, presses a control as a
 * person does and reads what the page published and what it asked the store.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-app.js";
import { nameRefused, powered, repeatRefused } from "../src/model/timetable.js";
import type { TcApp } from "../src/ui/tc-app.js";
import type { TcMenu } from "../src/ui/tc-menu.js";
import type { TcTimetableControls } from "../src/ui/tc-timetable-controls.js";
import type { TcTimetableDialog } from "../src/ui/tc-timetable-dialog.js";
import { mounted, running, serving, settled, type Answers } from "./support/shell.js";
import {
  brokering,
  DERIVES,
  joined,
  loads,
  said,
  STOCK,
  stored,
  unbrokered,
  written,
} from "./support/session.js";

const POWER = "tc49/layout/state/power";
const TIMETABLE = "tc49/schedule/state/timetable";

/** The state row of `evening`, running with Record off, with `over` laid
 *  over it. */
function row(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    timetable: "evening",
    phase: "running",
    record: false,
    start: "06:00",
    repeat: "1d00:00",
    trains: {},
    positioning: [],
    entries: [],
    ...over,
  };
}

/** A joined session with power as given and the timetable row said, `null`
 *  for the row that says none is loaded. */
async function standing(
  timetable: Record<string, unknown> | null = row(),
  power = "off",
): Promise<{ shell: TcApp; controls: TcTimetableControls }> {
  const shell = await joined();
  await said(shell, POWER, { power });
  await said(shell, TIMETABLE, timetable ?? { timetable: null });
  return { shell, controls: controlsOf(shell) };
}

function controlsOf(shell: TcApp): TcTimetableControls {
  return running(shell).renderRoot.querySelector("tc-timetable-controls")!;
}

/** One of the controls' own elements. */
function part<Part extends Element = HTMLButtonElement>(
  controls: TcTimetableControls,
  selector: string,
): Part | null {
  return controls.renderRoot.querySelector<Part>(selector);
}

/** The menu's rows as drawn: each label, and whether it can be chosen. */
async function offered(controls: TcTimetableControls): Promise<[string, boolean][]> {
  return (await rows(controls)).map((button) => [
    button.textContent!.trim(),
    !button.disabled && button.getAttribute("aria-disabled") !== "true",
  ]);
}

/** The menu opened from its button, and its rows. */
async function rows(controls: TcTimetableControls): Promise<HTMLButtonElement[]> {
  if (part(controls, "tc-menu menu") === null) part(controls, ".menu")!.click();
  await controls.updateComplete;
  const menu = part<TcMenu>(controls, "tc-menu")!;
  await menu.updateComplete;
  return [...menu.renderRoot.querySelectorAll("button")];
}

/** One row of the menu pressed, and the store's answers to what that reads
 *  drawn. */
async function chosen(shell: TcApp, label: string): Promise<void> {
  const row = (await rows(controlsOf(shell))).find(
    (button) => button.textContent!.trim() === label,
  )!;
  row.click();
  await settled(shell);
}

/** The open dialog's own elements, `null` with none open. */
function dialog(shell: TcApp): ParentNode | null {
  return (
    part<TcTimetableDialog>(controlsOf(shell), "tc-timetable-dialog")?.renderRoot ?? null
  );
}

/** A name or a length typed into the dialog that asks for one. */
async function typed(shell: TcApp, name: string): Promise<void> {
  const input = dialog(shell)!.querySelector<HTMLInputElement>("sl-input")!;
  input.value = name;
  input.dispatchEvent(new CustomEvent("sl-input"));
  await settled(shell);
}

/** A button of the open dialog pressed, and the store's answer drawn. */
async function pressed(shell: TcApp, selector: string): Promise<void> {
  dialog(shell)!.querySelector<HTMLElement>(selector)!.click();
  await settled(shell);
}

/** What the open dialog says is wrong, `null` for nothing. */
function trouble(shell: TcApp): string | null {
  return dialog(shell)!.querySelector(".trouble")?.textContent!.trim() ?? null;
}

/** Whether a dialog is open. */
function asking(shell: TcApp): boolean {
  return dialog(shell) !== null;
}

/** The names on the buttons of the dialog's list. */
function listed(shell: TcApp): string[] {
  return [...dialog(shell)!.querySelectorAll(".pick")].map((button) =>
    button.textContent!.trim(),
  );
}

/** The open dialog's title. */
function titled(shell: TcApp): string | null {
  return dialog(shell)!.querySelector("look-dialog")!.getAttribute("label");
}

/** One name of the dialog's list pressed. */
async function picked(shell: TcApp, name: string): Promise<void> {
  [...dialog(shell)!.querySelectorAll<HTMLButtonElement>(".pick")]
    .find((button) => button.textContent!.trim() === name)!
    .click();
  await settled(shell);
}

/** A timetable document, as the store keeps one for the toy railroad. */
function kept(name: string): Record<string, unknown> {
  return { timetable: name, layout: "toy", start: "06:00", trains: {}, entries: [] };
}

/** The store behind the page: the toy railroad, with three timetables. */
let store: Answers;

beforeEach(() => {
  brokering();
  store = serving({
    drawings: ["toy"],
    rosterOf: () => STOCK,
    read: stored,
    review: () => Promise.resolve(DERIVES),
    timetables: () => ({
      night: kept("night"),
      evening: kept("evening"),
      morning: kept("morning"),
    }),
  });
});

afterEach(unbrokered);

describe("what the model says", () => {
  /** The timetable document's own check (#1348). */
  it("takes a name that is not empty, has no / and no leading dot", () => {
    expect(nameRefused("evening")).toBeNull();
    expect(nameRefused("Friday evening, 2nd")).toBeNull();
    expect(nameRefused("a.b")).toBeNull();
    expect(nameRefused("")).toBe("a timetable needs a name");
    expect(nameRefused("a/b")).toBe("'a/b' cannot name a timetable");
    expect(nameRefused(".evening")).toBe("'.evening' cannot name a timetable");
  });

  it("refuses a name that is taken", () => {
    expect(nameRefused("evening", ["evening", "night"])).toBe("'evening' is already a timetable");
    expect(nameRefused("morning", ["evening", "night"])).toBeNull();
  });

  /** Lengths in fast seconds: a start of 06:00 and entries up to 08:59. */
  it("refuses a repeat that leaves the latest entry outside, and one of 00:00", () => {
    const timetable = { start: 6 * 3600, entries: ["06:30", "08:59"].map((at) => ({ entry: { at } })) };
    expect(repeatRefused(timetable, 3 * 3600)).toBeNull();
    expect(repeatRefused(timetable, 3 * 3600 - 60)).toBe(
      "the latest entry is at 08:59, so the shortest repeat is 03:00",
    );
    expect(repeatRefused({ start: 6 * 3600, entries: [] }, 60)).toBeNull();
    expect(repeatRefused({ start: 6 * 3600, entries: [] }, 0)).toBe(
      "a repeat is longer than 00:00",
    );
  });

  it("shuts New and Load while power reads on or draining, and not before it is heard", () => {
    expect(powered("on")).toBe("track power is on");
    expect(powered("draining")).toBe("track power is on");
    expect(powered("off")).toBe("");
    expect(powered(null)).toBe("");
  });
});

describe("the menu", () => {
  it("offers New, Load, Rename and Delete", async () => {
    const { controls } = await standing();
    expect(await offered(controls)).toEqual([
      ["New", true],
      ["Load", true],
      ["Rename", true],
      ["Delete", true],
      ["Repeat", true],
    ]);
  });

  it("has Rename disabled with no timetable loaded", async () => {
    const { controls } = await standing(null);
    expect(await offered(controls)).toEqual([
      ["New", true],
      ["Load", true],
      ["Rename", false],
      ["Delete", true],
      ["Repeat", false],
    ]);
  });

  /** The scheduler drops a new timetable and a load unless power reads
   *  `off`. The reason is shown as the rail shows why a view does not open:
   *  the row's tooltip and its description. */
  for (const power of ["on", "draining"]) {
    it(`has New, Load and Repeat disabled, saying why, while power reads ${power}`, async () => {
      const { controls } = await standing(row(), power);
      expect(await offered(controls)).toEqual([
        ["New", false],
        ["Load", false],
        ["Rename", true],
        ["Delete", true],
        ["Repeat", false],
      ]);
      const [fresh, load, rename, , repeat] = await rows(controls);
      for (const shut of [fresh!, load!, repeat!]) {
        expect(shut.getAttribute("aria-description")).toBe("track power is on");
        expect(shut.closest("sl-tooltip")!.getAttribute("content")).toBe("track power is on");
      }
      expect(rename!.closest("sl-tooltip")).toBeNull();
    });

    it(`publishes nothing for a press on New, Load or Repeat while power reads ${power}`, async () => {
      const { shell } = await standing(row(), power);
      await chosen(shell, "New");
      await chosen(shell, "Load");
      await chosen(shell, "Repeat");
      expect(asking(shell)).toBe(false);
      expect(written()).toEqual([]);
    });
  }

  /** No scheduler to ask and no railroad to name to the store. */
  it("does not open before a session is joined", async () => {
    const shell = await mounted("run");
    expect(part(controlsOf(shell), ".menu")!.disabled).toBe(true);

    await loads(shell, "toy");
    expect(part(controlsOf(shell), ".menu")!.disabled).toBe(false);
  });

  it("closes when a row is chosen", async () => {
    const { shell, controls } = await standing();
    await chosen(shell, "New");
    expect(part(controls, "tc-menu menu")).toBeNull();
  });
});

describe("New", () => {
  it("asks for a name and publishes timetable_wanted with it and new", async () => {
    const { shell } = await standing();
    await chosen(shell, "New");
    await typed(shell, "morning");
    await pressed(shell, ".confirm");
    expect(written()).toEqual([
      { topic: "tc49/schedule/timetable_wanted", payload: { timetable: "morning", new: true } },
    ]);
    expect(asking(shell)).toBe(false);
  });

  it("publishes nothing where the dialog is cancelled", async () => {
    const { shell } = await standing();
    await chosen(shell, "New");
    await typed(shell, "morning");
    await pressed(shell, ".cancel");
    expect(written()).toEqual([]);
    expect(asking(shell)).toBe(false);
  });

  /** The document takes no such name (#1348), so the scheduler would drop
   *  the gesture. */
  for (const [name, why] of [
    ["", null],
    ["  ", null],
    ["a/b", "'a/b' cannot name a timetable"],
    [".hidden", "'.hidden' cannot name a timetable"],
  ] as const) {
    it(`refuses the name '${name}' and publishes nothing`, async () => {
      const { shell } = await standing();
      await chosen(shell, "New");
      await typed(shell, name);
      expect(trouble(shell)).toBe(why);
      await pressed(shell, ".confirm");
      expect(written()).toEqual([]);
      expect(asking(shell)).toBe(true);
    });
  }
});

describe("Load", () => {
  it("lists the names the store has for the railroad", async () => {
    const { shell } = await standing();
    await chosen(shell, "Load");
    expect(listed(shell)).toEqual(["evening", "morning", "night"]);
  });

  it("publishes timetable_wanted with the name pressed", async () => {
    const { shell } = await standing();
    await chosen(shell, "Load");
    await picked(shell, "morning");
    expect(written()).toEqual([
      { topic: "tc49/schedule/timetable_wanted", payload: { timetable: "morning" } },
    ]);
    expect(asking(shell)).toBe(false);
  });

  /** The scheduler drops a load of a document that does not read and says
   *  nothing, so the page reads the document first. */
  it("shows what the store says of a document it refuses, and publishes nothing", async () => {
    const { shell } = await standing();
    store.refuses = (path) =>
      path === "/timetables/toy/morning"
        ? { status: 400, error: "timetable 'toy/morning': 'entries' must be a list, got str" }
        : null;
    await chosen(shell, "Load");
    await picked(shell, "morning");
    expect(trouble(shell)).toBe("timetable 'toy/morning': 'entries' must be a list, got str");
    expect(written()).toEqual([]);
    expect(asking(shell)).toBe(true);

    await picked(shell, "night");
    expect(written()).toEqual([
      { topic: "tc49/schedule/timetable_wanted", payload: { timetable: "night" } },
    ]);
  });

  it("shows what the store says where the list does not read", async () => {
    const { shell } = await standing();
    store.intercepted = (path) =>
      path === "/timetables/toy" ? { status: 502, statusText: "Bad Gateway" } : null;
    await chosen(shell, "Load");
    expect(listed(shell)).toEqual([]);
    expect(trouble(shell)).toBe("GET /timetables/toy answered 502 Bad Gateway");
  });

  it("says so where the railroad has no timetables", async () => {
    const { shell } = await standing(null);
    store.timetables = () => ({});
    await chosen(shell, "Load");
    expect(dialog(shell)!.querySelector(".hint")!.textContent!.trim()).toBe("no timetables");
  });

  /** Power came on with the dialog open. */
  it("publishes nothing once power is on, and says why", async () => {
    const { shell } = await standing();
    await chosen(shell, "Load");
    await said(shell, POWER, { power: "on" });
    await picked(shell, "morning");
    expect(trouble(shell)).toBe("track power is on");
    expect(written()).toEqual([]);
  });
});

describe("Rename", () => {
  it("asks for a name and publishes timetable_rename_wanted with it", async () => {
    const { shell } = await standing();
    await chosen(shell, "Rename");
    expect(titled(shell)).toBe("Rename evening");
    await typed(shell, "friday");
    await pressed(shell, ".confirm");
    expect(written()).toEqual([
      { topic: "tc49/schedule/timetable_rename_wanted", payload: { to: "friday" } },
    ]);
    expect(asking(shell)).toBe(false);
  });

  it("is taken with power on", async () => {
    const { shell } = await standing(row(), "on");
    await chosen(shell, "Rename");
    await typed(shell, "friday");
    await pressed(shell, ".confirm");
    expect(written()).toEqual([
      { topic: "tc49/schedule/timetable_rename_wanted", payload: { to: "friday" } },
    ]);
  });

  /** The scheduler drops a rename to a name the store has, and says nothing. */
  it("refuses a name the store lists and publishes nothing", async () => {
    const { shell } = await standing();
    await chosen(shell, "Rename");
    await typed(shell, "morning");
    expect(trouble(shell)).toBe("'morning' is already a timetable");
    await pressed(shell, ".confirm");
    expect(written()).toEqual([]);
  });

  it("refuses a name with a / and publishes nothing", async () => {
    const { shell } = await standing();
    await chosen(shell, "Rename");
    await typed(shell, "fri/day");
    expect(trouble(shell)).toBe("'fri/day' cannot name a timetable");
    await pressed(shell, ".confirm");
    expect(written()).toEqual([]);
  });
});

describe("Delete", () => {
  it("lists the store's names without the loaded one", async () => {
    const { shell } = await standing();
    await chosen(shell, "Delete");
    expect(listed(shell)).toEqual(["morning", "night"]);
  });

  it("lists every name with no timetable loaded", async () => {
    const { shell } = await standing(null);
    await chosen(shell, "Delete");
    expect(listed(shell)).toEqual(["evening", "morning", "night"]);
  });

  it("asks before deleting, and sends nothing where that is cancelled", async () => {
    const { shell } = await standing();
    await chosen(shell, "Delete");
    await picked(shell, "morning");
    expect(titled(shell)).toBe("Delete morning?");
    expect(store.deleted).toEqual([]);

    await pressed(shell, ".cancel");
    expect(store.deleted).toEqual([]);
    expect(asking(shell)).toBe(false);
  });

  it("sends the DELETE once confirmed, and publishes nothing", async () => {
    const { shell } = await standing();
    await chosen(shell, "Delete");
    await picked(shell, "morning");
    await pressed(shell, ".confirm");
    expect(store.deleted).toEqual(["/timetables/toy/morning"]);
    expect(written()).toEqual([]);
    expect(asking(shell)).toBe(false);
  });

  it("shows what the store says where it refuses", async () => {
    const { shell } = await standing();
    store.refuses = () => ({ status: 404, error: "no timetable 'toy/morning'" });
    await chosen(shell, "Delete");
    await picked(shell, "morning");
    await pressed(shell, ".confirm");
    expect(trouble(shell)).toBe("no timetable 'toy/morning'");
    expect(store.deleted).toEqual([]);
    expect(asking(shell)).toBe(true);
  });
});

/** An entry of the state row at `at`, not yet out in round 0. */
function listedAt(at: string): Record<string, unknown> {
  return { at, train: "freight_1", to: ["dn_e"], state: "later", round: 0 };
}

describe("Repeat", () => {
  it("asks for a length filled in with the loaded repeat", async () => {
    const { shell } = await standing(row({ repeat: "1d00:00" }));
    await chosen(shell, "Repeat");
    expect(titled(shell)).toBe("Repeat evening");
    expect(dialog(shell)!.querySelector<HTMLInputElement>("sl-input")!.value).toBe("1d00:00");
    expect(trouble(shell)).toBeNull();
  });

  it("publishes timetable_repeat_wanted with the length typed", async () => {
    const { shell } = await standing();
    await chosen(shell, "Repeat");
    await typed(shell, "0d03:00");
    await pressed(shell, ".confirm");
    expect(written()).toEqual([
      { topic: "tc49/schedule/timetable_repeat_wanted", payload: { repeat: "03:00" } },
    ]);
    expect(asking(shell)).toBe(false);
  });

  /** The scheduler drops a repeat that puts an entry at or after the start
   *  plus the repeat. */
  it("refuses a length too short, naming the latest entry and the shortest that fits", async () => {
    const { shell } = await standing(
      row({ entries: [listedAt("06:30"), listedAt("08:59")] }),
    );
    await chosen(shell, "Repeat");
    await typed(shell, "02:00");
    expect(trouble(shell)).toBe("the latest entry is at 08:59, so the shortest repeat is 03:00");
    await pressed(shell, ".confirm");
    expect(written()).toEqual([]);
    expect(asking(shell)).toBe(true);

    await typed(shell, "03:00");
    expect(trouble(shell)).toBeNull();
    await pressed(shell, ".confirm");
    expect(written()).toEqual([
      { topic: "tc49/schedule/timetable_repeat_wanted", payload: { repeat: "03:00" } },
    ]);
  });

  for (const [length, why] of [
    ["00:00", "a repeat is longer than 00:00"],
    ["3:00", "'3:00' is no length: write [<day>d]HH:MM"],
    ["", "'' is no length: write [<day>d]HH:MM"],
  ] as const) {
    it(`refuses the length '${length}' and publishes nothing`, async () => {
      const { shell } = await standing();
      await chosen(shell, "Repeat");
      await typed(shell, length);
      expect(trouble(shell)).toBe(why);
      await pressed(shell, ".confirm");
      expect(written()).toEqual([]);
    });
  }

  /** Power came on with the dialog open. */
  it("publishes nothing once power is on, and says why", async () => {
    const { shell } = await standing();
    await chosen(shell, "Repeat");
    await said(shell, POWER, { power: "on" });
    await typed(shell, "03:00");
    expect(trouble(shell)).toBe("track power is on");
    await pressed(shell, ".confirm");
    expect(written()).toEqual([]);
  });
});

describe("Start", () => {
  it("is drawn only while the phase is loaded", async () => {
    const { shell, controls } = await standing(row({ phase: "loaded" }));
    expect(part(controls, ".start")!.textContent!.trim()).toBe("Start");

    await said(shell, TIMETABLE, row({ phase: "running" }));
    expect(part(controls, ".start")).toBeNull();

    await said(shell, TIMETABLE, { timetable: null });
    expect(part(controls, ".start")).toBeNull();
  });

  it("publishes timetable_start_wanted with no fields", async () => {
    const { controls } = await standing(row({ phase: "loaded" }));
    part(controls, ".start")!.click();
    expect(written()).toEqual([
      { topic: "tc49/schedule/timetable_start_wanted", payload: {} },
    ]);
  });
});

describe("the Record switch", () => {
  it("shows the row's record", async () => {
    const { shell, controls } = await standing(row({ record: false }));
    expect(part(controls, ".record")!.getAttribute("aria-checked")).toBe("false");

    await said(shell, TIMETABLE, row({ record: true }));
    expect(part(controls, ".record")!.getAttribute("aria-checked")).toBe("true");
  });

  it("publishes timetable_record_wanted with record true where the row reads off", async () => {
    const { controls } = await standing(row({ record: false }));
    part(controls, ".record")!.click();
    expect(written()).toEqual([
      { topic: "tc49/schedule/timetable_record_wanted", payload: { record: true } },
    ]);
  });

  it("publishes timetable_record_wanted with record false where the row reads on", async () => {
    const { controls } = await standing(row({ record: true }));
    part(controls, ".record")!.click();
    expect(written()).toEqual([
      { topic: "tc49/schedule/timetable_record_wanted", payload: { record: false } },
    ]);
  });

  /** What the switch shows is the row's answer, not the press. */
  it("stays as the row reads until the row changes", async () => {
    const { shell, controls } = await standing(row({ record: false }));
    part(controls, ".record")!.click();
    await settled(shell);
    expect(part(controls, ".record")!.getAttribute("aria-checked")).toBe("false");
  });

  /** A running timetable repeats and never ends, so Record stays open. */
  it("is disabled only with no timetable loaded", async () => {
    const { shell, controls } = await standing(null);
    expect(part(controls, ".record")!.disabled).toBe(true);

    await said(shell, TIMETABLE, row({ phase: "loaded" }));
    expect(part(controls, ".record")!.disabled).toBe(false);

    await said(shell, TIMETABLE, row({ phase: "running" }));
    expect(part(controls, ".record")!.disabled).toBe(false);
  });
});
