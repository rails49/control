// @vitest-environment happy-dom

/**
 * A person makes cars and trains, end to end through the app (ui/STOCK.md,
 * #393).
 *
 * A DOM test because it crosses the screen, the two store routes and the run
 * view: what is under test is that a fresh box — no `catalogue/`, no roster —
 * reaches a saved roster with one car entry and three model entries, that the
 * run view sees a train made up here without a reload, and that the length
 * guard is off while the run has the train placed.
 *
 * The rules underneath are `test/composing.test.ts`'s, driven from plain
 * values; nothing is asserted twice.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../src/ui/tc-app.js";
import type { RosterDoc } from "../src/model/store.js";
import type { TcApp } from "../src/ui/tc-app.js";
import type { TcBackup } from "../src/ui/tc-backup.js";
import type { TcStock } from "../src/ui/tc-stock.js";
import { RETRY_MS } from "../src/model/store.js";
import {
  mounted,
  running,
  serving,
  settled,
  shows,
  stocking,
  type Answers,
} from "./support/shell.js";
import {
  Broker,
  brokering,
  DERIVES,
  loads,
  said,
  stored,
  unbrokered,
  written as published,
} from "./support/session.js";

let store: Answers;

beforeEach(() => {
  brokering();
  // A fresh box: the installation has written no model and the railroad has
  // no roster file, which is what the screen writing the first car draws
  // itself from and not a fault.
  store = serving({
    drawings: ["toy"],
    read: stored,
    review: () => Promise.resolve(DERIVES),
    rosterOf: () => ({}),
    catalogue: {},
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  unbrokered();
});

/** The app with the toy railroad loaded, showing the stock screen. The
 *  broker's retained row is the only thing that loads a railroad
 *  (#371, ADR-0059 decision 2). */
async function opened(): Promise<TcApp> {
  const shell = await mounted("stock");
  await loads(shell, "toy");
  return shell;
}

function screen(shell: TcApp): TcStock {
  return stocking(shell);
}

function parts(shell: TcApp, selector: string): HTMLElement[] {
  return [...screen(shell).renderRoot.querySelectorAll<HTMLElement>(selector)];
}

function part(shell: TcApp, selector: string): HTMLElement {
  return screen(shell).renderRoot.querySelector<HTMLElement>(selector)!;
}

/** What the bar says went wrong, `null` where it is saying nothing wrong. A
 *  failed read, a refused edit and a refused Save are all said there. */
function trouble(shell: TcApp): string | null {
  const line = screen(shell).renderRoot.querySelector(".bar .said.trouble");
  return line === null ? null : line.textContent!.trim();
}

/** Everything the bar says, whatever its tone. */
function bar(shell: TcApp): string {
  return part(shell, ".bar .said").textContent!.trim();
}

/** A page from something in front of the store on the paths `which` picks
 *  out, as a stale route table puts one in front of a store that is up. */
function between(which: (path: string) => boolean): void {
  store.intercepted = (path) => (which(path) ? { status: 404, statusText: "" } : null);
}

/** Type into a control and leave it, which is when an edit is taken. */
async function typed(shell: TcApp, field: HTMLElement, value: string): Promise<void> {
  (field as HTMLInputElement).value = value;
  field.dispatchEvent(new Event("change"));
  await settled(shell);
}

/** Type into a control and leave the edit standing: no `change`, so nothing
 *  is committed and the field is still a person's to finish (#444). */
function typing(field: HTMLElement, value: string): void {
  (field as HTMLInputElement).value = value;
}

async function pressed(shell: TcApp, selector: string, at = 0): Promise<void> {
  parts(shell, selector)[at]!.click();
  await settled(shell);
}

/** One of the three lists shown, by its tab. */
async function tab(shell: TcApp, which: "trains" | "cars" | "models"): Promise<void> {
  await pressed(shell, `button.tab[data-tab="${which}"]`);
}

/** The cards the list shown draws, by name. */
function cards(shell: TcApp): string[] {
  return parts(shell, "button.card .name").map((one) => one.textContent!.trim());
}

/** Make a product in the model editor, which is where one is made: New
 *  model, then its name, kind and length typed over what it starts as. */
async function product(
  shell: TcApp,
  name: string,
  kind: string,
  length: string,
): Promise<void> {
  await tab(shell, "models");
  await pressed(shell, "button.new");
  await typed(shell, part(shell, ".model-editor input.name"), name);
  await pressed(shell, `.model-editor .seg.kind button[data-kind="${kind}"]`);
  await typed(shell, part(shell, ".model-editor input.length"), length);
}

/** One model chosen in the Models list, by the name its card shows. */
async function chosen(shell: TcApp, name: string): Promise<void> {
  await tab(shell, "models");
  await pressed(shell, "button.card.model", cards(shell).indexOf(name));
}

/** A field of the model editor, for the model chosen. */
function model(shell: TcApp, selector: string): HTMLInputElement {
  return part(shell, `.model-editor ${selector}`) as HTMLInputElement;
}

/** Make a train up, which is a one-field prompt like naming a railroad. */
async function train(shell: TcApp, name: string): Promise<void> {
  vi.spyOn(window, "prompt").mockReturnValue(name);
  await tab(shell, "trains");
  await pressed(shell, "button.new");
}

/** Press the + beside a car or a model in the train editor, which puts it at
 *  the tail of the train chosen. */
async function add(shell: TcApp, list: "car" | "product", at: number): Promise<void> {
  await tab(shell, "trains");
  await pressed(shell, `li.addable.${list} button.add`, at);
}

/** A field on one of the chosen train's entries. */
async function entry(shell: TcApp, field: string, at = 0): Promise<HTMLInputElement> {
  await tab(shell, "trains");
  return parts(shell, `li.entry input.${field}`)[at] as HTMLInputElement;
}

/** A field of the car chosen, the first in the list unless `at` says
 *  another. */
async function car(shell: TcApp, field: string, at = 0): Promise<HTMLInputElement> {
  await tab(shell, "cars");
  if (at > 0) await pressed(shell, "button.card.car", at);
  return part(shell, `li.car input.${field}`) as HTMLInputElement;
}

/** The roster the screen last wrote, as the store was given it. */
function written(): RosterDoc | undefined {
  const put = store.saved.filter((one) => one.path.startsWith("/rosters/")).at(-1);
  return put?.body as RosterDoc | undefined;
}

/** Build the ore train of the acceptance: a locomotive with an address, and
 *  three hoppers with nothing of their own. */
async function ore(shell: TcApp): Promise<void> {
  await product(shell, "arnold-ce68", "locomotive", "122");
  await product(shell, "hopper", "freight", "100");
  await train(shell, "ore");
  // arnold-ce68 sorts before hopper, so the rows are in that order.
  await add(shell, "product", 0);
  await typed(shell, await entry(shell, "addr"), "3");
  await add(shell, "product", 1);
  await add(shell, "product", 1);
  await add(shell, "product", 1);
}

/** The one Save, in the bar. */
function saving(shell: TcApp): HTMLButtonElement {
  return part(shell, ".bar button.save") as HTMLButtonElement;
}

async function saved(shell: TcApp): Promise<void> {
  await pressed(shell, ".bar button.save");
}

/**
 * Nothing is loaded until the broker names a railroad (ADR-0060), and this
 * screen is one of the app's views of the one that is: with none there is no
 * roster and no catalogue, so the presses that write have nothing to write
 * into (#565).
 */
describe("with no railroad loaded", () => {
  /** The app mounted on this view with nothing loaded: `mounted` alone, the
   *  retained row the other suites replay being what loads a railroad. */
  async function empty(): Promise<TcApp> {
    return await mounted("stock");
  }

  it("leaves New model dead, and says what to do first", async () => {
    const shell = await empty();
    await tab(shell, "models");
    const button = part(shell, "button.new") as HTMLButtonElement;

    expect(button.textContent!.trim()).toBe("New model");
    expect(button.disabled).toBe(true);
    expect(button.title).toBe("load a railroad first");
    expect(trouble(shell)).toBe("load a railroad first");

    await pressed(shell, "button.new");

    expect(cards(shell)).toEqual([]);
    expect(store.saved).toEqual([]);
  });

  it("leaves New train dead, and asks for no name it would drop", async () => {
    const shell = await empty();
    const button = part(shell, "button.new") as HTMLButtonElement;
    const asked = vi.spyOn(window, "prompt").mockReturnValue("ore");

    expect(button.disabled).toBe(true);
    expect(button.title).toBe("load a railroad first");

    await pressed(shell, "button.new");

    expect(asked).not.toHaveBeenCalled();
    expect(cards(shell)).toEqual([]);
  });

  it("says the documents are not read yet where a railroad is loaded and its read failed", async () => {
    between((path) => path === "/catalogue");
    const shell = await opened();

    expect((part(shell, "button.new") as HTMLButtonElement).title).toBe(
      "the roster and the catalogue are not read yet",
    );
    expect(trouble(shell)).toBe("GET /catalogue answered 404");
  });
});

describe("the bar", () => {
  it("names the railroad and says everything is saved", async () => {
    const shell = await opened();
    expect(part(shell, ".bar h1").textContent).toBe("Stock");
    expect(part(shell, ".bar .railroad").textContent).toBe("toy");
    expect(bar(shell)).toBe("Everything is saved");
    expect(saving(shell).disabled).toBe(true);
  });

  it("counts what is unsaved, and says Saved once a Save lands", async () => {
    const shell = await opened();
    await product(shell, "hopper", "freight", "100");
    expect(bar(shell)).toBe("4 unsaved changes");

    await saved(shell);

    expect(bar(shell)).toBe("Saved");
  });
});

describe("a fresh box", () => {
  it("draws nothing to begin with and says what to do first", async () => {
    const shell = await opened();
    await tab(shell, "models");
    expect(cards(shell)).toEqual([]);
    expect(
      parts(shell, "p.hint").map((one) => one.textContent!.trim()),
    ).toContain("no models yet — a train is made of them");
    expect(part(shell, ".editor .empty").textContent!.trim()).toBe(
      "Nothing here yet. Press New model.",
    );
  });

  /** A model is written by Save, ahead of the roster, so the roster never
   *  names a model the store lacks (#978). */
  it("writes a model made here only on Save, before the roster", async () => {
    const shell = await opened();
    await product(shell, "hopper", "freight", "100");
    expect(store.saved).toEqual([]);
    expect(cards(shell)).toEqual(["hopper"]);

    await saved(shell);

    expect(store.saved.map((one) => one.path)).toEqual(["/catalogue/hopper", "/rosters/toy"]);
    expect(store.saved[0]!.body).toEqual({
      model: "hopper",
      name: "hopper",
      kind: "freight",
      scale: "H0",
      length: 100,
      decoder: false,
    });
  });
});

/** The model editor, as the mockup draws it (#978). */
describe("the model editor", () => {
  /** A catalogue with one model nothing uses, beside the toy railroad's
   *  empty roster. */
  function catalogued(): void {
    store.catalogue = {
      coach: { model: "coach", name: "EW IV B", kind: "passenger", length: 280 },
    };
  }

  it("makes New model, then New model (2), chosen with its name selected", async () => {
    const shell = await opened();
    await tab(shell, "models");
    await pressed(shell, "button.new");
    await pressed(shell, "button.new");

    expect(cards(shell)).toEqual(["New model", "New model (2)"]);
    expect(part(shell, "button.card.model[aria-current='true'] .name").textContent).toBe(
      "New model (2)",
    );
    expect(model(shell, "input.name").value).toBe("New model (2)");
    expect(part(shell, "button.tab[data-tab='models'] .count").textContent).toBe("2");
  });

  it("saves a model named Ae 6/6 under the key ae-6-6", async () => {
    const shell = await opened();
    await product(shell, "Ae 6/6", "locomotive", "230");

    await saved(shell);

    expect(store.saved[0]).toEqual({
      path: "/catalogue/ae-6-6",
      body: {
        model: "ae-6-6",
        name: "Ae 6/6",
        kind: "locomotive",
        scale: "H0",
        length: 230,
        decoder: false,
      },
    });
    expect(part(shell, ".ed-head h2").textContent).toBe("Ae 6/6");
  });

  it("refuses a name another model has, and puts the field back", async () => {
    const shell = await opened();
    await product(shell, "Ae 6/6", "locomotive", "230");
    await product(shell, "Re 460", "locomotive", "220");

    await typed(shell, model(shell, "input.name"), "Ae 6/6");

    expect(trouble(shell)).toBe("There is already a model 'Ae 6/6'.");
    expect(model(shell, "input.name").value).toBe("Re 460");
  });

  it("refuses an empty name, and puts the field back", async () => {
    const shell = await opened();
    await product(shell, "Ae 6/6", "locomotive", "230");

    await typed(shell, model(shell, "input.name"), "  ");

    expect(trouble(shell)).toBe("A model needs a name.");
    expect(model(shell, "input.name").value).toBe("Ae 6/6");
  });

  it("writes the scale, the notes and the kind", async () => {
    catalogued();
    const shell = await opened();
    await tab(shell, "models");
    await typed(shell, model(shell, "select.scale"), "N");
    await typed(shell, part(shell, ".model-editor textarea.notes"), "Second class, green.");
    await pressed(shell, `.model-editor .seg.kind button[data-kind="special"]`);

    await saved(shell);

    expect(store.saved[0]!.body).toEqual({
      model: "coach",
      name: "EW IV B",
      kind: "special",
      scale: "N",
      length: 280,
      notes: "Second class, green.",
    });
  });

  it("refuses a length that is not one, and puts the field back", async () => {
    const shell = await opened();
    await product(shell, "hopper", "freight", "100");

    await typed(shell, model(shell, "input.length"), "a hundred");

    expect(trouble(shell)).toMatch("positive whole number");
    expect(model(shell, "input.length").value).toBe("100");
  });

  describe("its decoder and functions", () => {
    async function decoded(shell: TcApp): Promise<void> {
      await product(shell, "Ae 6/6", "locomotive", "230");
      await pressed(shell, ".model-editor button.switch");
    }

    function rows(shell: TcApp): HTMLElement[] {
      return parts(shell, ".model-editor li.function");
    }

    it("adds F0 Headlights when the decoder is turned on", async () => {
      const shell = await opened();
      await decoded(shell);

      expect(part(shell, "button.switch").getAttribute("aria-checked")).toBe("true");
      expect(rows(shell)).toHaveLength(1);
      expect((rows(shell)[0]!.querySelector("input.number") as HTMLInputElement).value).toBe("0");
      expect((rows(shell)[0]!.querySelector("input.fn-name") as HTMLInputElement).value).toBe(
        "Headlights",
      );
      expect(part(shell, "button.card.model .pill").textContent).toBe("decoder");
    });

    it("reaches the document with each function's mode", async () => {
      const shell = await opened();
      await decoded(shell);
      await pressed(shell, ".model-editor button.add-function");
      await typed(shell, rows(shell)[1]!.querySelector("input.fn-name")!, "Horn");
      await pressed(shell, `.model-editor li.function button[data-mode="momentary"]`, 1);

      await saved(shell);

      expect(store.saved[0]!.body).toMatchObject({
        decoder: true,
        functions: {
          "0": { name: "Headlights" },
          "1": { name: "Horn", mode: "momentary" },
        },
      });
    });

    it("drops the functions when the decoder is turned off", async () => {
      const shell = await opened();
      await decoded(shell);
      await pressed(shell, ".model-editor button.switch");

      expect(rows(shell)).toHaveLength(0);
      await saved(shell);
      expect(store.saved[0]!.body).toMatchObject({ decoder: false });
      expect(store.saved[0]!.body).not.toHaveProperty("functions");
    });

    it("refuses Save while a number is listed twice, and says so", async () => {
      const shell = await opened();
      await decoded(shell);
      await pressed(shell, ".model-editor button.add-function");
      await typed(shell, rows(shell)[1]!.querySelector("input.fn-name")!, "Horn");
      await typed(shell, rows(shell)[1]!.querySelector("input.number")!, "0");

      const twice = "F0 is listed twice. One number names one function.";
      expect(part(shell, ".model-editor p.twice").textContent).toBe(twice);
      await saved(shell);

      expect(store.saved).toEqual([]);
      expect(trouble(shell)).toBe(twice);
    });
  });

  describe("its Delete", () => {
    it("is dead while anything on the railroad uses the model, and says what", async () => {
      const shell = await opened();
      await ore(shell);
      await chosen(shell, "hopper");

      expect((part(shell, ".model-editor button.delete") as HTMLButtonElement).disabled).toBe(
        true,
      );
      expect(parts(shell, ".model-editor ul.uses li").map((one) => one.textContent)).toEqual([
        "train 'ore'",
      ]);
    });

    it("asks first, then sends DELETE and takes the model off the list", async () => {
      catalogued();
      const shell = await opened();
      await tab(shell, "models");
      await pressed(shell, ".model-editor button.delete");

      const asked = part(shell, "look-dialog.delete");
      expect(asked.getAttribute("label")).toBe("Delete EW IV B?");
      expect(asked.querySelector("p")!.textContent).toBe(
        "Its photo goes with it. A backup can bring it back.",
      );
      expect(store.deleted).toEqual([]);

      await pressed(shell, "look-dialog.delete .confirm");

      expect(store.deleted).toEqual(["/catalogue/coach"]);
      expect(cards(shell)).toEqual([]);
      expect(screen(shell).renderRoot.querySelector("look-dialog.delete")).toBeNull();
    });

    it("says the store's refusal under the button, and keeps the model", async () => {
      catalogued();
      const words = "model 'EW IV B' is used by railroad 'otira': car 'ew-1'";
      store.refuses = (path) => (path === "/catalogue/coach" ? { status: 400, error: words } : null);
      const shell = await opened();
      await tab(shell, "models");
      await pressed(shell, ".model-editor button.delete");

      await pressed(shell, "look-dialog.delete .confirm");

      expect(part(shell, ".model-editor .delete-trouble").textContent).toBe(words);
      expect(cards(shell)).toEqual(["EW IV B"]);
    });

    it("drops a model made here without asking the store", async () => {
      const shell = await opened();
      await product(shell, "Ae 6/6", "locomotive", "230");
      await pressed(shell, ".model-editor button.delete");
      await pressed(shell, "look-dialog.delete .confirm");

      expect(store.deleted).toEqual([]);
      expect(cards(shell)).toEqual([]);
    });
  });

  it("makes a car of the model with New car, and shows it in the Cars list", async () => {
    catalogued();
    const shell = await opened();
    await tab(shell, "models");

    await pressed(shell, ".ed-head button.new-car");

    expect(part(shell, "button.tab[aria-selected='true']").dataset.tab).toBe("cars");
    expect(cards(shell)).toEqual(["EW IV B"]);
    await saved(shell);
    expect(written()!.cars).toEqual({ "EW IV B": { model: "coach" } });
  });
});

/** Car and train names take any character, as model names do: no topic level
 *  or path carries one unencoded (#978). */
describe("a name of any characters", () => {
  it("saves a car named Re 4/4 II and a train named S 1/S 2", async () => {
    const shell = await opened();
    await ore(shell);
    await typed(shell, await car(shell, "name"), "Re 4/4 II");
    await tab(shell, "trains");
    await typed(shell, part(shell, "li.train input.name"), "S 1/S 2");

    await saved(shell);

    expect(Object.keys(written()!.cars!)).toEqual(["Re 4/4 II"]);
    expect(Object.keys(written()!.trains)).toEqual(["S 1/S 2"]);
    expect(written()!.trains["S 1/S 2"]!.cars![0]).toEqual({ car: "Re 4/4 II" });
  });
});

describe("the list", () => {
  it("counts each list on its tab, and draws a card's facts", async () => {
    const shell = await opened();
    await ore(shell);

    expect(parts(shell, "button.tab .count").map((one) => one.textContent)).toEqual([
      "1",
      "1",
      "2",
    ]);
    await tab(shell, "trains");
    expect(part(shell, "button.card.train .facts").textContent!.replace(/\s+/g, " ")).toMatch(
      "4 cars422 mmfreight",
    );
    await tab(shell, "cars");
    expect(parts(shell, "button.card.car .facts span").map((one) => one.textContent)).toEqual([
      "arnold-ce68",
      "3",
    ]);
  });

  /** One column where the view is narrower than 760 px: a card pressed
   *  stands the editor in place of the list, and its back button puts the
   *  list back. */
  it("stands the editor in place of the list where a card is pressed, until Back", async () => {
    const shell = await opened();
    await ore(shell);
    await tab(shell, "trains");
    expect(part(shell, ".cols").classList.contains("editing")).toBe(true);
    await pressed(shell, "button.back");
    expect(part(shell, ".cols").classList.contains("editing")).toBe(false);
    await pressed(shell, "button.card.train");
    expect(part(shell, ".cols").classList.contains("editing")).toBe(true);
  });
});

describe("making up a train", () => {
  /** The acceptance: one car entry and three model entries, the address
   *  written once (ADR-0061). */
  it("saves a document with one car entry and three model entries", async () => {
    const shell = await opened();
    await ore(shell);
    await saved(shell);

    expect(written()).toEqual({
      roster: "toy",
      cars: { "arnold-ce68-1": { model: "arnold-ce68", addr: "3" } },
      trains: {
        ore: {
          cars: [
            { car: "arnold-ce68-1" },
            { model: "hopper" },
            { model: "hopper" },
            { model: "hopper" },
          ],
        },
      },
    });
  });

  it("shows the train's length as the sum of all four", async () => {
    const shell = await opened();
    await ore(shell);
    expect(part(shell, ".derived").textContent).toMatch("422 mm");
    expect(part(shell, ".derived").textContent).toMatch("freight");
  });

  /** Filling in an address promotes an anonymous item to a car, named from
   *  the model until a person calls it something else. */
  it("promotes an item to a car when an address is filled in", async () => {
    const shell = await opened();
    await ore(shell);
    const name = await car(shell, "name");
    expect(name.value).toBe("arnold-ce68-1");
    await typed(shell, name, "krokodil-a");
    await tab(shell, "trains");
    expect(parts(shell, "li.entry .what")[0]!.textContent).toMatch("krokodil-a");
  });

  /** Two locomotives of one product keep their two addresses, written once,
   *  and neither is restated when a rake is made up (ADR-0061). */
  it("keeps two addresses for two locomotives of one model", async () => {
    const shell = await opened();
    await product(shell, "arnold-ce68", "locomotive", "122");
    await train(shell, "shed");
    await add(shell, "product", 0);
    await add(shell, "product", 0);
    await typed(shell, await entry(shell, "addr", 0), "3");
    await typed(shell, await entry(shell, "addr", 1), "4");
    await saved(shell);

    expect(written()!.cars).toEqual({
      "arnold-ce68-1": { model: "arnold-ce68", addr: "3" },
      "arnold-ce68-2": { model: "arnold-ce68", addr: "4" },
    });
    expect(written()!.trains.shed!.cars).toEqual([
      { car: "arnold-ce68-1" },
      { car: "arnold-ce68-2" },
    ]);
  });

  /** The screen invites this order of work — make a train up, then fill it —
   *  so an empty train is easy to save. The store refuses one, and the
   *  refusal it answers is about a document; this one is about the row
   *  (#412). */
  it("refuses the save while a train has nothing in it, and sends no PUT", async () => {
    const shell = await opened();
    await product(shell, "hopper", "freight", "100");
    await train(shell, "ore");
    await saved(shell);

    expect(store.saved).toEqual([]);
    expect(trouble(shell)).toBe(
      "train 'ore' has nothing in it — press + beside a car or a model, or remove it",
    );
    // Still there to be filled, and the press is still there to make again.
    expect(cards(shell)).toEqual(["ore"]);
    expect(saving(shell).disabled).toBe(false);

    await add(shell, "product", 0);
    await saved(shell);
    expect(written()!.trains.ore!.cars).toEqual([{ model: "hopper" }]);
    expect(trouble(shell)).toBeNull();
  });

  it("says what holds a car somebody asked to remove, and keeps it", async () => {
    const shell = await opened();
    await ore(shell);
    await tab(shell, "cars");
    await pressed(shell, "li.car button.remove");
    expect(trouble(shell)).toBe("car 'arnold-ce68-1' is held by train 'ore'");
    expect(cards(shell)).toEqual(["arnold-ce68-1"]);
  });
});

/** A camera is the item's own as an address is, and Save carries it in the
 *  whole roster like any other edit (ADR-0082, ui/STOCK.md). */
describe("a car's camera", () => {
  it("promotes a model entry to a car with the camera and no address", async () => {
    const shell = await opened();
    await product(shell, "van", "freight", "90");
    await train(shell, "ore");
    await add(shell, "product", 0);
    await typed(shell, await entry(shell, "camera"), "192.168.178.58");
    await saved(shell);

    expect(written()!.cars).toEqual({ "van-1": { model: "van", camera: "192.168.178.58" } });
    expect(written()!.trains.ore!.cars).toEqual([{ car: "van-1" }]);
    expect((await car(shell, "camera")).value).toBe("192.168.178.58");
  });

  it("is taken off a car cleared on its row, and the car stays", async () => {
    const shell = await opened();
    await ore(shell);
    await typed(shell, await car(shell, "camera"), "cam-1");
    await saved(shell);
    expect(written()!.cars).toEqual({
      "arnold-ce68-1": { model: "arnold-ce68", addr: "3", camera: "cam-1" },
    });

    await typed(shell, await car(shell, "camera"), "");
    await saved(shell);
    expect(written()!.cars).toEqual({ "arnold-ce68-1": { model: "arnold-ce68", addr: "3" } });
  });

  it("puts a malformed camera back to the roster's, says why, and saves none", async () => {
    const shell = await opened();
    await ore(shell);
    await typed(shell, await car(shell, "camera"), "cam-1");

    await typed(shell, await car(shell, "camera"), "http://cam-1:8080/");

    expect(trouble(shell)).toBe(
      "'http://cam-1:8080/' is not a camera address — write the camera's host name or IP address",
    );
    expect((await car(shell, "camera")).value).toBe("cam-1");
    await saved(shell);
    expect(written()!.cars!["arnold-ce68-1"]!.camera).toBe("cam-1");
  });
});

const POWER = "tc49/layout/state/power";
const RAILROAD_WANTED = "tc49/layout/railroad_wanted";
const HELD = "track power is on — turn it off to correct a length";
const WAITS = "a length has changed — turn track power off to save";
const UNHEARD =
  "the layout has not said whether the track has power, so a length cannot be corrected";
const UNHEARD_WAITS =
  "a length has changed — the layout has not said whether the track has power";

/** What the page has asked for on `railroad_wanted`. */
function wants(): unknown[] {
  return published().filter((one) => (one as { topic: string }).topic === RAILROAD_WANTED);
}

/** The length field of one model, chosen in the Models list by name. */
async function length(shell: TcApp, name: string): Promise<HTMLInputElement> {
  await chosen(shell, name);
  return model(shell, "input.length");
}

/** Whether each model's length field is dead and what it says, each model
 *  chosen in turn. */
async function lengths(shell: TcApp): Promise<{ disabled: boolean; title: string }[]> {
  const said = [];
  for (const name of ["arnold-ce68", "hopper"]) {
    const field = await length(shell, name);
    said.push({ disabled: field.disabled, title: field.title });
  }
  return said;
}

/** The ore train saved and standing in block `a`, with track power as given. */
async function placed(shell: TcApp, power: "on" | "draining" | "off"): Promise<void> {
  await ore(shell);
  await saved(shell);
  store.rosterOf = () => ({ ore: { length: 422 } });
  await said(shell, "tc49/dispatch/state/allocation", {
    trains: { ore: "a" },
    locks: { a: "ore" },
    requests: [],
  });
  await said(shell, POWER, { power });
  await shows(shell, "stock");
}

describe("the length guard", () => {
  /** A UI guard in one browser: `tc-app` holds the run's power and passes it
   *  down (ADR-0071). A second browser editing stock during a run is not
   *  covered. */
  it.each(["on", "draining"] as const)(
    "kills length editing while power is %s, and says why",
    async (power) => {
      const shell = await opened();
      await placed(shell, power);

      const field = await car(shell, "length");
      expect(field.disabled).toBe(true);
      expect(field.title).toBe(HELD);
      expect(part(shell, ".why").textContent).toBe(HELD);
      for (const model of await lengths(shell)) {
        expect(model.disabled).toBe(true);
        expect(model.title).toBe(HELD);
      }
    },
  );

  /** Placed trains hold nothing with power off: the save names the railroad
   *  again and the rebuild keeps them where they still fit. */
  it("leaves length editing alone with power off and the train placed", async () => {
    const shell = await opened();
    await placed(shell, "off");
    expect((await car(shell, "length")).disabled).toBe(
      false,
    );
    expect(parts(shell, ".why")).toHaveLength(0);
    for (const model of await lengths(shell)) {
      expect(model.disabled).toBe(false);
    }
  });

  it("writes a correction to the store only on Save", async () => {
    const shell = await opened();
    await placed(shell, "off");
    store.saved.length = 0;

    await typed(shell, await car(shell, "length"), "150");
    expect(store.saved).toEqual([]);

    await saved(shell);
    expect(written()!.cars!["arnold-ce68-1"]!.length).toBe(150);
  });

  it("leaves length editing alone with nothing placed", async () => {
    const shell = await opened();
    await ore(shell);
    expect((await car(shell, "length")).disabled).toBe(
      false,
    );
    expect(parts(shell, ".why")).toHaveLength(0);
  });

  /** A page that has lost the broker still holds the roster, and cannot know
   *  whether the track has power: the broker, `layout` and the dispatcher may
   *  be running without it (#804). The hold lifts once the row is heard again
   *  with power off; nothing is latched. */
  describe("with the broker gone", () => {
    async function every(shell: TcApp): Promise<{ disabled: boolean; title: string }[]> {
      const field = await car(shell, "length");
      return [{ disabled: field.disabled, title: field.title }, ...(await lengths(shell))];
    }

    it("holds every length, refuses one typed, and saves no length edit", async () => {
      const shell = await opened();
      await placed(shell, "off");
      await typed(shell, await car(shell, "length"), "150");
      store.saved.length = 0;
      Broker.last!.closes();
      await settled(shell);

      for (const field of await every(shell)) {
        expect(field.disabled).toBe(true);
        expect(field.title).toBe(UNHEARD);
      }
      await typed(shell, await length(shell, "hopper"), "110");
      expect(trouble(shell)).toBe(UNHEARD);

      expect(saving(shell).disabled).toBe(true);
      expect(saving(shell).title).toBe(UNHEARD_WAITS);
      await saved(shell);
      expect(store.saved).toEqual([]);
    });

    it("lifts once the row is heard again with power off, and Save writes", async () => {
      const shell = await opened();
      await placed(shell, "off");
      await typed(shell, await car(shell, "length"), "150");
      store.saved.length = 0;
      Broker.last!.closes();
      await settled(shell);
      Broker.last!.opens();
      await settled(shell);

      for (const field of await every(shell)) {
        expect(field.disabled).toBe(false);
      }
      expect(saving(shell).disabled).toBe(false);
      await saved(shell);
      expect(written()!.cars!["arnold-ce68-1"]!.length).toBe(150);
    });

    it("says power is on once the row is heard again with power on", async () => {
      const shell = await opened();
      await placed(shell, "off");
      Broker.last!.closes();
      await settled(shell);
      Broker.last!.says(POWER, { power: "on" });
      Broker.last!.opens();
      await settled(shell);

      for (const field of await every(shell)) {
        expect(field.disabled).toBe(true);
        expect(field.title).toBe(HELD);
      }
    });
  });
});

/**
 * A length correction is saved with the roster (ADR-0071, decision 6). The
 * layout builds only with power off, so while power is on or draining the Save
 * waits if its edits change a length; a save that changed one names the loaded
 * railroad again, so the dispatcher fits trains with the new length.
 */
describe("the roster's Save with a length corrected", () => {
  it("is dead while power is on, and says why", async () => {
    const shell = await opened();
    await placed(shell, "off");
    await typed(shell, await car(shell, "length"), "150");
    await said(shell, POWER, { power: "on" });

    expect(saving(shell).disabled).toBe(true);
    expect(saving(shell).title).toBe(WAITS);
  });

  it("is live while power is on for any other roster edit", async () => {
    const shell = await opened();
    await placed(shell, "on");
    await typed(shell, await car(shell, "addr"), "7");

    expect(saving(shell).disabled).toBe(false);
    expect(saving(shell).title).toBe("");
  });

  it("writes the roster and then names the loaded railroad again, with power off", async () => {
    const shell = await opened();
    await placed(shell, "off");
    store.saved.length = 0;
    await typed(shell, await car(shell, "length"), "150");
    expect(wants()).toEqual([]);

    await saved(shell);

    expect(written()!.cars!["arnold-ce68-1"]!.length).toBe(150);
    expect(wants()).toEqual([{ topic: RAILROAD_WANTED, payload: { railroad: "toy" } }]);
    expect(saving(shell).disabled).toBe(true);
  });

  /** A save that lands with the broker gone has nobody to name the railroad
   *  to, and the row coming back names the same one, so the press is owed
   *  and sent once the row and power off are replayed (#803). It is pressed
   *  while the broker is up and lands after it went: a length edit is not
   *  saved with the broker gone (#804). */
  it("names the railroad once the broker is back, for a save landing while it was gone", async () => {
    const shell = await opened();
    await placed(shell, "off");
    await typed(shell, await car(shell, "length"), "150");
    let answer: () => void = () => {};
    store.held = (path) =>
      path.startsWith("/rosters/") ? new Promise<void>((resolve) => (answer = resolve)) : null;

    await saved(shell);
    Broker.last!.closes();
    await settled(shell);
    store.held = () => null;
    answer();
    await settled(shell);
    expect(written()!.cars!["arnold-ce68-1"]!.length).toBe(150);
    expect(wants()).toEqual([]);

    Broker.last!.opens();
    await settled(shell);

    expect(wants()).toEqual([{ topic: RAILROAD_WANTED, payload: { railroad: "toy" } }]);
  });

  /** A model's length corrected on its row is written on Save, before the
   *  roster, and names the railroad again like any other length (#718). */
  describe("on a model's row", () => {
    /** Correct the hopper, in the model editor. */
    async function corrected(shell: TcApp, mm: string): Promise<void> {
      await typed(shell, await length(shell, "hopper"), mm);
    }

    function paths(): string[] {
      return store.saved.map((one) => one.path);
    }

    it("writes the model, then the roster, then names the railroad again", async () => {
      const shell = await opened();
      await placed(shell, "off");
      store.saved.length = 0;
      await corrected(shell, "110");
      expect(store.saved).toEqual([]);
      expect(saving(shell).disabled).toBe(false);

      await saved(shell);

      expect(paths()).toEqual(["/catalogue/hopper", "/rosters/toy"]);
      expect(store.saved[0]!.body).toMatchObject({
        model: "hopper",
        kind: "freight",
        length: 110,
      });
      expect(wants()).toEqual([{ topic: RAILROAD_WANTED, payload: { railroad: "toy" } }]);
      expect(saving(shell).disabled).toBe(true);
    });

    it.each(["on", "draining"] as const)(
      "is dead while power is %s, and says why",
      async (power) => {
        const shell = await opened();
        await placed(shell, "off");
        await corrected(shell, "110");
        await said(shell, POWER, { power });

        expect(saving(shell).disabled).toBe(true);
        expect(saving(shell).title).toBe(WAITS);
      },
    );

    /** Power is off, so the railroad can be named again, and the dispatcher
     *  must not go on fitting trains by a length the store no longer holds. */
    it("names the railroad again where the roster is refused after the model", async () => {
      const shell = await opened();
      await placed(shell, "off");
      store.saved.length = 0;
      await corrected(shell, "110");
      between((path) => path.startsWith("/rosters/"));

      await saved(shell);

      expect(paths()).toEqual(["/catalogue/hopper"]);
      expect(trouble(shell)).not.toBeNull();
      expect(wants()).toEqual([{ topic: RAILROAD_WANTED, payload: { railroad: "toy" } }]);
      expect(saving(shell).disabled).toBe(false);

      store.intercepted = () => null;
      store.saved.length = 0;
      await saved(shell);
      expect(paths()).toEqual(["/rosters/toy"]);
      expect(trouble(shell)).toBeNull();
    });

    it("writes nothing else where the model is refused, and keeps it", async () => {
      const shell = await opened();
      await placed(shell, "off");
      store.saved.length = 0;
      await corrected(shell, "110");
      between((path) => path.startsWith("/catalogue/"));

      await saved(shell);

      expect(store.saved).toEqual([]);
      expect(trouble(shell)).not.toBeNull();
      expect(wants()).toEqual([]);
      expect(saving(shell).disabled).toBe(false);

      store.intercepted = () => null;
      await saved(shell);
      expect(paths()).toEqual(["/catalogue/hopper", "/rosters/toy"]);
    });

    it("is an edit a restore asks about", async () => {
      const shell = await opened();
      await placed(shell, "off");
      await corrected(shell, "110");

      const backup = shell.renderRoot.querySelector<TcBackup>("tc-backup")!;
      expect(backup.unsaved).toBe("the roster");
    });
  });

  /** With nothing loaded there is no roster to write into: Save is dead and
   *  nothing is named. */
  it("names nothing with no railroad loaded", async () => {
    const shell = await mounted("stock");
    expect(saving(shell).disabled).toBe(true);
    await saved(shell);
    expect(store.saved).toEqual([]);
    expect(wants()).toEqual([]);
  });
});

/** Save is dead while its own write is in flight and the rest of the screen
 *  is not: an edit made meanwhile is written by the next Save (#723). */
describe("the roster's Save in flight", () => {
  /** The next `PUT` on a path starting with `prefix` held in flight, and the
   *  press that lets it answer, settled. */
  function holding(shell: TcApp, prefix = "/rosters/"): () => Promise<void> {
    let answer: () => void = () => {};
    store.held = (path) =>
      path.startsWith(prefix)
        ? new Promise<void>((resolve) => (answer = resolve))
        : null;
    return async () => {
      store.held = () => null;
      answer();
      await settled(shell);
    };
  }

  function puts(): number {
    return store.saved.filter((one) => one.path.startsWith("/rosters/")).length;
  }

  it("is dead from the press until the write answers, and writes once", async () => {
    const shell = await opened();
    await placed(shell, "off");
    store.saved.length = 0;
    await typed(shell, await car(shell, "addr"), "7");
    const answer = holding(shell);

    await saved(shell);
    expect(saving(shell).disabled).toBe(true);
    // A second press on the dead button writes nothing more. The guard behind
    // it, for a press that reached the handler anyway, is `railroad.test.ts`'s.
    await saved(shell);
    await answer();

    expect(puts()).toBe(1);
    expect(saving(shell).disabled).toBe(true);
  });

  it("is dead while a corrected model is written", async () => {
    const shell = await opened();
    await placed(shell, "off");
    store.saved.length = 0;
    await typed(shell, await length(shell, "hopper"), "110");
    const answer = holding(shell, "/catalogue/");

    await saved(shell);
    expect(saving(shell).disabled).toBe(true);
    // A second press on the dead button writes nothing more. The guard behind
    // it, for a press that reached the handler anyway, is `railroad.test.ts`'s.
    await saved(shell);
    await answer();

    expect(store.saved.map((one) => one.path)).toEqual(["/catalogue/hopper", "/rosters/toy"]);
    expect(saving(shell).disabled).toBe(true);
  });

  it("is live again once the write is refused", async () => {
    const shell = await opened();
    await placed(shell, "off");
    await typed(shell, await car(shell, "addr"), "7");
    const answer = holding(shell);
    between((path) => path.startsWith("/rosters/"));

    await saved(shell);
    expect(saving(shell).disabled).toBe(true);
    await answer();

    expect(trouble(shell)).not.toBeNull();
    expect(saving(shell).disabled).toBe(false);
  });

  it("keeps an edit typed during the write, and is live for it", async () => {
    const shell = await opened();
    await placed(shell, "off");
    await typed(shell, await car(shell, "addr"), "7");
    const answer = holding(shell);

    await saved(shell);
    await typed(shell, await car(shell, "addr"), "8");
    await answer();

    expect(written()!.cars!["arnold-ce68-1"]!.addr).toBe("7");
    expect((await car(shell, "addr")).value).toBe("8");
    expect(saving(shell).disabled).toBe(false);

    await saved(shell);
    expect(written()!.cars!["arnold-ce68-1"]!.addr).toBe("8");
    expect(saving(shell).disabled).toBe(true);
  });

  it("keeps a length typed during the write waiting for power off", async () => {
    const shell = await opened();
    await placed(shell, "off");
    await typed(shell, await car(shell, "addr"), "7");
    const answer = holding(shell);

    await saved(shell);
    await typed(shell, await car(shell, "length"), "150");
    await answer();
    await said(shell, POWER, { power: "on" });

    expect(saving(shell).disabled).toBe(true);
    expect(saving(shell).title).toBe(WAITS);
  });
});

/** A roster written before #223 states a train's length and names no cars.
 *  The store keeps that shape legal for an older file and answers it as
 *  written, so the screen has to draw one: it used to throw on the first
 *  render and paint nothing, which read as a dead tab (#414). */
describe("a roster written the old way", () => {
  /** The screen over such a roster, with a car of one's own to compose from,
   *  showing the train. */
  async function older(): Promise<TcApp> {
    store.catalogue = {
      "arnold-ce68": { model: "arnold-ce68", kind: "locomotive", length: 122 },
    };
    store.documentOf = () => ({
      roster: "toy",
      cars: { "krokodil-a": { model: "arnold-ce68", addr: "3" } },
      trains: { goods: { length: 400 } },
    });
    const shell = await opened();
    await tab(shell, "trains");
    return shell;
  }

  it("draws the train with its stated length and says what it is", async () => {
    const shell = await older();
    expect(trouble(shell)).toBeNull();
    expect(cards(shell)).toEqual(["goods"]);
    expect(part(shell, ".derived").textContent).toMatch("400 mm");
    expect(part(shell, "li.train p.hint").textContent!.trim()).toBe(
      "states its length and names no cars — press + beside a car or a model" +
        " to fill it in, and the stated 400 mm goes",
    );
  });

  /** The conversion consumes the stated number, and emptying the converted
   *  train writes `cars: []` rather than putting it back — a document the
   *  store refuses and Save stops (#412). So the note names the number and
   *  says it goes, before the press that takes it (#448). */
  it("says what the stated length costs before it is given up", async () => {
    const shell = await older();
    expect(part(shell, "li.train p.hint").textContent).toMatch("the stated 400 mm goes");

    await add(shell, "car", 0);
    await pressed(shell, "li.entry button.remove");

    // The conversion is not undone: the train is the ordinary shape now, so
    // the note is the ordinary one and the stated number is not on the row.
    expect(part(shell, "li.train p.hint").textContent!.trim()).toBe("nothing in it yet");
    expect(part(shell, ".derived").textContent).not.toMatch("400 mm");
    await saved(shell);
    expect(written()).toBeUndefined();
    expect(trouble(shell)).toMatch("train 'goods' has nothing in it");
  });

  /** Composing it converts it: a train says a stated length or cars and never
   *  both, and the store refuses one that says both. */
  it("drops the stated length when the first car is put in it", async () => {
    const shell = await older();
    await add(shell, "car", 0);
    await saved(shell);

    expect(written()!.trains.goods).toEqual({ cars: [{ car: "krokodil-a" }] });
    expect(part(shell, ".derived").textContent).toMatch("122 mm");
  });

  /** The document is spread, so nothing is lost: a roster nobody has edited
   *  has nothing to give the store, and one edited elsewhere keeps the stated
   *  length as it was. */
  it("keeps the stated length through a save of the roster", async () => {
    const shell = await older();
    await saved(shell);
    expect(written()).toBeUndefined();

    await typed(shell, await car(shell, "name"), "krokodil");
    await saved(shell);
    expect(written()!.trains.goods).toEqual({ length: 400 });
    expect(written()!.cars).toEqual({ krokodil: { model: "arnold-ce68", addr: "3" } });
  });
});

describe("the run view and the screen beside it", () => {
  /** The store is not on the bus, so nothing publishes a roster change: a
   *  person who makes a train up here must see it in Run without a reload. */
  it("shows a train made up here when the run view becomes current", async () => {
    const shell = await opened();
    await ore(shell);
    await saved(shell);
    store.rosterOf = () => ({ ore: { length: 422 } });

    await shows(shell, "run");

    const rows = [
      ...running(shell)
        .renderRoot.querySelector("tc-roster")!
        .renderRoot.querySelectorAll("li"),
    ];
    expect(rows.map((row) => row.querySelector(".name")!.textContent!.trim())).toEqual([
      "ore",
    ]);
    expect(rows[0]!.querySelector(".length")!.textContent!.trim()).toBe("422");
  });

  it("keeps the roster it joined with until the view becomes current", async () => {
    const shell = await opened();
    store.rosterOf = () => ({ ore: { length: 422 } });
    const rows = () =>
      running(shell).renderRoot.querySelector("tc-roster")!.renderRoot.querySelectorAll("li");
    expect(rows()).toHaveLength(0);

    await shows(shell, "run");
    expect(rows()).toHaveLength(1);
  });
});

/**
 * A read or a write that does not come back with a document (#411).
 *
 * Three ways to fail and three sets of words, decided in the store helper
 * (`test/asking.test.ts`); what is under test here is that the screen shows
 * them rather than a fixed string, and that it reads again after the two a
 * person can only wait out.
 */
describe("a store that does not answer with a document", () => {
  /** What #405 was: the proxy's route table was stale, so `GET /catalogue`
   *  came back as its own 404 page while the store was up and answering the
   *  roster beside it. The screen said `run \`tc49 serve\`` — for a server
   *  that was running. */
  it("says what was asked and what came back, and reads again", async () => {
    vi.useFakeTimers();
    try {
      between((path) => path === "/catalogue");
      store.catalogue = { hopper: { model: "hopper", kind: "freight", length: 100 } };
      const shell = await opened();
      await tab(shell, "models");

      expect(trouble(shell)).toBe("GET /catalogue answered 404");
      expect(cards(shell)).toEqual([]);

      store.intercepted = () => null;
      await vi.advanceTimersByTimeAsync(RETRY_MS);
      await settled(shell);

      expect(trouble(shell)).toBeNull();
      expect(cards(shell)).toEqual(["hopper"]);
    } finally {
      vi.useRealTimers();
    }
  });

  /** Nothing answered at all keeps the words it had: the store is what is
   *  missing, and starting it is the fix. */
  it("names `tc49 serve` where nothing answered, and reads again", async () => {
    vi.useFakeTimers();
    try {
      store.documentOf = () => {
        throw new TypeError("Failed to fetch");
      };
      const shell = await opened();
      await tab(shell, "models");

      expect(trouble(shell)).toBe("the store is not answering — run `tc49 serve`");

      store.documentOf = (railroad) => ({ roster: railroad, trains: {} });
      store.catalogue = { hopper: { model: "hopper", kind: "freight", length: 100 } };
      await vi.advanceTimersByTimeAsync(RETRY_MS);
      await settled(shell);

      expect(trouble(shell)).toBeNull();
      expect(cards(shell)).toEqual(["hopper"]);
    } finally {
      vi.useRealTimers();
    }
  });

  /** The same 404 met by a Save writing a model made here: the model is
   *  still there to write again once the route is back, and so is the
   *  roster that names it. */
  it("keeps a model made here where its write did not land, and names the write", async () => {
    const shell = await opened();
    between((path) => path.startsWith("/catalogue/"));
    await product(shell, "hopper", "freight", "100");

    await saved(shell);

    expect(trouble(shell)).toBe("PUT /catalogue/hopper answered 404");
    expect(store.saved).toEqual([]);
    expect(cards(shell)).toEqual(["hopper"]);

    store.intercepted = () => null;
    await saved(shell);
    expect(store.saved.map((one) => one.path)).toEqual(["/catalogue/hopper", "/rosters/toy"]);
  });
});

/**
 * The chosen train: the one the `+` buttons put something at the tail of,
 * and the one the train editor shows.
 *
 * Every `+` names one train, and it is always a train there is
 * (ui/STOCK.md). It used to be left naming one that was gone (#416), and
 * renaming it was the other road there, the train being held as a name and
 * the rename writing the roster under a new key (#445).
 */
describe("the chosen train", () => {
  /** Two trains, the second of which is chosen: making one up chooses it.
   *  They sort `ore` then `shunt`. */
  async function pair(): Promise<TcApp> {
    const shell = await opened();
    await product(shell, "hopper", "freight", "100");
    await train(shell, "ore");
    await train(shell, "shunt");
    return shell;
  }

  /** The `+` beside the first model, which is what composing is. */
  function plus(shell: TcApp): HTMLButtonElement {
    return part(shell, "li.addable.product button.add") as HTMLButtonElement;
  }

  /** What the chosen train is called, which is the train every `+` names. */
  function current(shell: TcApp): string | null {
    const row = screen(shell).renderRoot.querySelector("li.train.current input.name");
    return row === null ? null : (row as HTMLInputElement).value;
  }

  it("makes the first train left chosen, and adds to that one", async () => {
    const shell = await pair();
    expect(current(shell)).toBe("shunt");
    await pressed(shell, "li.train button.remove");

    expect(cards(shell)).toEqual(["ore"]);
    expect(current(shell)).toBe("ore");
    expect(plus(shell).title).toBe("add to 'ore'");

    await pressed(shell, "li.addable.product button.add");
    expect(part(shell, "li.entry .what").textContent).toMatch("hopper");
  });

  it("leaves no train to add to where the last train goes", async () => {
    const shell = await pair();
    await pressed(shell, "li.train button.remove");
    await pressed(shell, "li.train button.remove");

    expect(cards(shell)).toEqual([]);
    expect(screen(shell).renderRoot.querySelector("li.addable")).toBeNull();
    expect(part(shell, ".editor .empty").textContent!.trim()).toBe(
      "Nothing here yet. Press New train.",
    );
  });

  /** `shunt` is chosen and sorts second, so a fallback to the first train
   *  the roster has would answer `ore`: the rename has to carry the choice. */
  it("goes on naming the train it named when that train is renamed", async () => {
    const shell = await pair();

    await typed(shell, part(shell, "li.train input.name"), "shunt-2");

    expect(current(shell)).toBe("shunt-2");
    expect(plus(shell).title).toBe("add to 'shunt-2'");
    await pressed(shell, "li.addable.product button.add");
    expect(part(shell, "li.train.current li.entry .what").textContent).toMatch("hopper");
  });

  /** A refusal changes the document by construction not at all, so there is
   *  nothing to carry: the roster still has `shunt` and the `+` still names
   *  it. */
  it("is left as it was where a rename is refused for the name in use", async () => {
    const shell = await pair();

    await typed(shell, part(shell, "li.train input.name"), "ore");

    expect(trouble(shell)).toBe("there is already a train 'ore'");
    expect(current(shell)).toBe("shunt");
    expect(plus(shell).title).toBe("add to 'shunt'");
  });

  it("is left as it was where a rename is refused for the name itself", async () => {
    const shell = await pair();

    await typed(shell, part(shell, "li.train input.name"), " ");

    expect(trouble(shell)).toBe("A train needs a name.");
    expect(current(shell)).toBe("shunt");
    expect(plus(shell).title).toBe("add to 'shunt'");
  });

  it("is the train whose card is pressed", async () => {
    const shell = await pair();

    await pressed(shell, "button.card.train", 0);

    expect(current(shell)).toBe("ore");
    expect(part(shell, "button.card.train[aria-current='true'] .name").textContent).toBe("ore");
  });
});

/**
 * A refusal changes nothing by construction, so the value bound to a field is
 * the one it was last rendered with: Lit skips the write and the field goes on
 * showing what was typed, which is a value the document has not got (#416).
 */
describe("a refused edit", () => {
  it("puts the car's name back to the one the roster holds", async () => {
    const shell = await opened();
    await ore(shell);
    const field = await car(shell, "name");

    await typed(shell, field, "");

    expect(trouble(shell)).toBe("A car needs a name.");
    expect((await car(shell, "name")).value).toBe("arnold-ce68-1");
  });

  it("puts a length refused under power back to the document's", async () => {
    const shell = await opened();
    await ore(shell);
    await typed(shell, await car(shell, "length"), "150");
    await saved(shell);

    await said(shell, POWER, { power: "on" });
    await shows(shell, "stock");
    await typed(shell, await car(shell, "length"), "200");

    expect(trouble(shell)).toBe(HELD);
    expect((await car(shell, "length")).value).toBe("150");
  });
});

/**
 * An edit standing in a field: text typed and the field not left, so no
 * `change` has fired and nothing has been committed. A frame about the
 * railroad is not news about what somebody is typing (#444).
 *
 * The stock view redraws for reasons that have nothing to do with the field
 * being typed in — the app hands it `placed`, and every new status the
 * session answers replaces the run state whole — so power going off is a
 * render, and the person correcting a length is halfway through the number.
 */
describe("an edit standing in a field", () => {
  /** A frame every one of these publishes: power going off is a real change
   *  and hands the app a fresh run state, which redraws this view. */
  async function power(shell: TcApp): Promise<void> {
    await said(shell, "tc49/layout/state/power", { power: "off" });
  }

  it("keeps a half-typed length in the model editor", async () => {
    const shell = await opened();
    await ore(shell);
    await chosen(shell, "arnold-ce68");
    typing(model(shell, "input.length"), "12");

    await power(shell);

    expect(model(shell, "input.length").value).toBe("12");
  });

  it("keeps a car's name and its address", async () => {
    const shell = await opened();
    await ore(shell);
    typing(await car(shell, "name"), "krokodil-");
    typing(await car(shell, "addr"), "37");

    await power(shell);

    expect((await car(shell, "name")).value).toBe("krokodil-");
    expect((await car(shell, "addr")).value).toBe("37");
  });

  it("keeps a train's name", async () => {
    const shell = await opened();
    await ore(shell);
    await tab(shell, "trains");
    typing(part(shell, "li.train input.name"), "ore up");

    await power(shell);

    expect((part(shell, "li.train input.name") as HTMLInputElement).value).toBe("ore up");
  });

  /** A refusal is about the field it was typed in. What stands in another
   *  field was not refused and is nobody's to take back. */
  it("is left alone where another field's edit is refused", async () => {
    const shell = await opened();
    await ore(shell);
    typing(await car(shell, "addr"), "37");

    await typed(shell, await car(shell, "name"), "");

    expect(trouble(shell)).toBe("A car needs a name.");
    expect((await car(shell, "name")).value).toBe("arnold-ce68-1");
    expect((await car(shell, "addr")).value).toBe("37");
  });
});
