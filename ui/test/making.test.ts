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

/** What the screen is saying went wrong, `null` where it is saying nothing.
 *  The one beside the trains, which is where a failed read reads; a failed
 *  write in the dialog says it in the dialog. */
function trouble(shell: TcApp): string | null {
  const line = screen(shell).renderRoot.querySelector("section.trains p.trouble");
  return line === null ? null : line.textContent!.trim();
}

/** The New-model dialog, `null` while it is shut. */
function dialog(shell: TcApp): Element | null {
  return screen(shell).renderRoot.querySelector("look-dialog");
}

/** What the dialog is saying went wrong, beside its Create button, `null`
 *  where it is saying nothing. The dialog's own and not the screen's (#446). */
function beside(shell: TcApp): string | null {
  const line = dialog(shell)?.querySelector("p.trouble") ?? null;
  return line === null ? null : line.textContent!.trim();
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

/** Write a product in the dialog, which is where one that does not exist yet
 *  is created. */
async function product(
  shell: TcApp,
  model: string,
  kind: string,
  length: string,
): Promise<void> {
  await pressed(shell, "button.new-model");
  const dialog = screen(shell).renderRoot.querySelector("look-dialog")!;
  await typed(shell, dialog.querySelector("#model")!, model);
  await typed(shell, dialog.querySelector("#kind")!, kind);
  await typed(shell, dialog.querySelector("#length")!, length);
  (dialog.querySelector(".create") as HTMLElement).click();
  await settled(shell);
}

/** Put the dialog away the way a person does, by the button in its footer. */
async function cancelled(shell: TcApp): Promise<void> {
  const buttons = [...dialog(shell)!.querySelectorAll("sl-button")];
  const cancel = buttons.find((one) => one.textContent!.trim() === "Cancel");
  (cancel as HTMLElement).click();
  await settled(shell);
}

/** Make a train up, which is a one-field prompt like naming a railroad. */
async function train(shell: TcApp, name: string): Promise<void> {
  vi.spyOn(window, "prompt").mockReturnValue(name);
  await pressed(shell, "button.new-train");
}

/** Press the + beside one of the rows on the left, which puts it at the tail
 *  of the current train. */
async function add(shell: TcApp, list: "car" | "product", at: number): Promise<void> {
  await pressed(shell, `li.${list} button.add`, at);
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
  await typed(shell, parts(shell, "li.entry input.addr")[0]!, "3");
  await add(shell, "product", 1);
  await add(shell, "product", 1);
  await add(shell, "product", 1);
}

/**
 * Nothing is loaded until the broker names a railroad (ADR-0060), and this
 * screen is one of the app's views of the one that is: with none there is no
 * roster and no catalogue, so the two presses that write have nothing to write
 * into.
 *
 * New model was live all the same. The dialog opened, every field took input,
 * and Create returned at its guard: no document written, no refusal shown, and
 * no request out of the browser — a dialog that takes a product and drops it
 * ([#565](https://github.com/rails49/control/issues/565)).
 */
describe("with no railroad loaded", () => {
  /** The app mounted on this view with nothing loaded: `mounted` alone, the
   *  retained row the other suites replay being what loads a railroad. */
  async function empty(): Promise<TcApp> {
    return await mounted("stock");
  }

  it("leaves New model… dead, and says what to do first", async () => {
    const shell = await empty();
    const button = parts(shell, "button.new-model")[0] as HTMLButtonElement;

    expect(button.disabled).toBe(true);
    expect(button.title).toBe("load a railroad first");

    await pressed(shell, "button.new-model");

    expect(dialog(shell)).toBeNull();
    expect(store.saved).toEqual([]);
  });

  it("leaves New train… dead, and asks for no name it would drop", async () => {
    const shell = await empty();
    const button = parts(shell, "button.new-train")[0] as HTMLButtonElement;
    const asked = vi.spyOn(window, "prompt").mockReturnValue("ore");

    expect(button.disabled).toBe(true);
    expect(button.title).toBe("load a railroad first");

    await pressed(shell, "button.new-train");

    expect(asked).not.toHaveBeenCalled();
    expect(parts(shell, "li.train")).toHaveLength(0);
  });

  /** The way into the guard now that the button is dead: the broker moves the
   *  railroad while the dialog is open, so the screen forgets the documents
   *  and keeps what somebody is writing. A railroad is loaded here and its
   *  read did not land, which is the other half of the sentence. */
  it("says why Create cannot proceed when the documents go from under it", async () => {
    const shell = await opened();
    await pressed(shell, "button.new-model");
    between((path) => path === "/catalogue");

    await loads(shell, "other");
    (dialog(shell)!.querySelector(".create") as HTMLElement).click();
    await settled(shell);

    expect(beside(shell)).toBe("the roster and the catalogue are not read yet");
    expect(store.saved).toEqual([]);
    // The dialog's refusal is the dialog's; the failed read is the screen's.
    expect(trouble(shell)).toBe("GET /catalogue answered 404");
  });
});

describe("a fresh box", () => {
  it("draws nothing to begin with and says what to do first", async () => {
    const shell = await opened();
    expect(parts(shell, "li.car")).toHaveLength(0);
    expect(parts(shell, "li.product")).toHaveLength(0);
    expect(
      parts(shell, "p.hint").map((one) => one.textContent!.trim()),
    ).toContain("no models yet — a train is made of them, so write the first one");
  });

  /** A product does not exist yet, so it is created in the same dialog: the
   *  catalogue is a real document with its own route underneath and never a
   *  place a person navigates to for its own sake (#392). */
  it("writes a model to the catalogue the moment it is made", async () => {
    const shell = await opened();
    await product(shell, "hopper", "freight", "100");
    expect(store.saved).toEqual([
      { path: "/catalogue/hopper", body: { model: "hopper", kind: "freight", length: 100 } },
    ]);
    expect(parts(shell, "li.product")).toHaveLength(1);
  });

  /** A dialog labelled New model with a Create button touches nothing that
   *  exists: `PUT /catalogue/<name>` replaces the document whole, so Create
   *  under a name in use would rewrite that product for every railroad in the
   *  installation, and say nothing. Correcting one is done on its row (#413). */
  it("refuses a name the catalogue already has, and sends no PUT", async () => {
    const shell = await opened();
    await product(shell, "hopper", "freight", "100");
    store.saved.length = 0;

    await product(shell, "hopper", "freight", "95");

    expect(store.saved).toEqual([]);
    const dialog = screen(shell).renderRoot.querySelector("look-dialog")!;
    expect(dialog.querySelector(".trouble")!.textContent!.trim()).toBe(
      "there is already a model 'hopper'",
    );
    expect(
      (dialog.querySelector("#model") as HTMLInputElement).value,
    ).toBe("hopper");
    expect(parts(shell, "li.product")).toHaveLength(1);
    expect(
      (parts(shell, "li.product input.length")[0] as HTMLInputElement).value,
    ).toBe("100");
  });

  it("refuses a length that is not one, where it was typed", async () => {
    const shell = await opened();
    await product(shell, "hopper", "freight", "a hundred");
    expect(store.saved).toEqual([]);
    const dialog = screen(shell).renderRoot.querySelector("look-dialog")!;
    expect(dialog.querySelector(".trouble")!.textContent).toMatch("positive whole number");
  });
});

/**
 * The dialog's refusal is the dialog's, and the line under the Trains heading
 * is the screen's.
 *
 * They were one state, so one refusal did two things: *there is already a
 * model 'hopper'* was said twice at once — in the dialog a person is looking
 * at and under a list the sentence is not about — and it stood under the
 * trains after the dialog it was about had been dismissed (#446).
 */
describe("a refusal in the dialog", () => {
  it("is said in the dialog and not under the trains", async () => {
    const shell = await opened();
    await product(shell, "hopper", "freight", "100");

    await product(shell, "hopper", "freight", "95");

    expect(beside(shell)).toBe("there is already a model 'hopper'");
    expect(trouble(shell)).toBeNull();
  });

  it("goes when the dialog it is about is dismissed", async () => {
    const shell = await opened();
    await product(shell, "hopper", "freight", "100");
    await product(shell, "hopper", "freight", "95");

    await cancelled(shell);

    expect(dialog(shell)).toBeNull();
    expect(trouble(shell)).toBeNull();
  });

  /** The name is corrected and Create pressed again, which is what a person
   *  does with the refusal in front of them. */
  it("leaves nothing standing when the model is written after it", async () => {
    const shell = await opened();
    await product(shell, "hopper", "freight", "100");
    await product(shell, "hopper", "freight", "95");

    await typed(shell, dialog(shell)!.querySelector("#model")!, "van");
    (dialog(shell)!.querySelector(".create") as HTMLElement).click();
    await settled(shell);

    expect(dialog(shell)).toBeNull();
    expect(screen(shell).renderRoot.querySelector("p.trouble")).toBeNull();
    expect(parts(shell, "li.product")).toHaveLength(2);
  });
});

describe("making up a train", () => {
  /** The acceptance: one car entry and three model entries, the address
   *  written once (ADR-0061). */
  it("saves a document with one car entry and three model entries", async () => {
    const shell = await opened();
    await ore(shell);
    await pressed(shell, "sl-button.save");

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
    expect(parts(shell, ".derived")[0]!.textContent).toMatch("422 mm");
    expect(parts(shell, ".derived")[0]!.textContent).toMatch("freight");
  });

  /** Filling in an address promotes an anonymous item to a car in the list
   *  above, named from the model until a person calls it something else. */
  it("promotes an item to a car when an address is filled in", async () => {
    const shell = await opened();
    await ore(shell);
    const [row] = parts(shell, "li.car");
    expect((row!.querySelector("input.name") as HTMLInputElement).value).toBe(
      "arnold-ce68-1",
    );
    await typed(shell, row!.querySelector("input.name")!, "krokodil-a");
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
    await typed(shell, parts(shell, "li.entry input.addr")[0]!, "3");
    await typed(shell, parts(shell, "li.entry input.addr")[1]!, "4");
    await pressed(shell, "sl-button.save");

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
    await pressed(shell, "sl-button.save");

    expect(written()).toBeUndefined();
    expect(trouble(shell)).toBe(
      "train 'ore' has nothing in it — press + beside a car or a model, or remove it",
    );
    // Still there to be filled, and the press is still there to make again.
    expect(parts(shell, "li.train")).toHaveLength(1);
    expect(
      (screen(shell).renderRoot.querySelector("sl-button.save") as HTMLElement & {
        disabled: boolean;
      }).disabled,
    ).toBe(false);

    await add(shell, "product", 0);
    await pressed(shell, "sl-button.save");
    expect(written()!.trains.ore!.cars).toEqual([{ model: "hopper" }]);
    expect(trouble(shell)).toBeNull();
  });

  it("says what holds a car somebody asked to remove, and keeps it", async () => {
    const shell = await opened();
    await ore(shell);
    await pressed(shell, "li.car button.remove");
    expect(screen(shell).renderRoot.querySelector(".trouble")!.textContent!.trim()).toBe(
      "car 'arnold-ce68-1' is held by train 'ore'",
    );
    expect(parts(shell, "li.car")).toHaveLength(1);
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
    await typed(shell, parts(shell, "li.entry input.camera")[0]!, "192.168.178.58");
    await pressed(shell, "sl-button.save");

    expect(written()!.cars).toEqual({ "van-1": { model: "van", camera: "192.168.178.58" } });
    expect(written()!.trains.ore!.cars).toEqual([{ car: "van-1" }]);
    expect((parts(shell, "li.car input.camera")[0] as HTMLInputElement).value).toBe(
      "192.168.178.58",
    );
  });

  it("is taken off a car cleared on its row, and the car stays", async () => {
    const shell = await opened();
    await ore(shell);
    await typed(shell, parts(shell, "li.car input.camera")[0]!, "cam-1");
    await pressed(shell, "sl-button.save");
    expect(written()!.cars).toEqual({
      "arnold-ce68-1": { model: "arnold-ce68", addr: "3", camera: "cam-1" },
    });

    await typed(shell, parts(shell, "li.car input.camera")[0]!, "");
    await pressed(shell, "sl-button.save");
    expect(written()!.cars).toEqual({ "arnold-ce68-1": { model: "arnold-ce68", addr: "3" } });
  });

  it("puts a malformed camera back to the roster's, says why, and saves none", async () => {
    const shell = await opened();
    await ore(shell);
    const field = () => parts(shell, "li.car input.camera")[0] as HTMLInputElement;
    await typed(shell, field(), "cam-1");

    await typed(shell, field(), "http://cam-1:8080/");

    expect(trouble(shell)).toBe(
      "'http://cam-1:8080/' is not a camera address — write the camera's host name or IP address",
    );
    expect(field().value).toBe("cam-1");
    await pressed(shell, "sl-button.save");
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

/** The roster's Save. */
function saving(shell: TcApp): HTMLElement & { disabled: boolean } {
  return parts(shell, "sl-button.save")[0] as HTMLElement & { disabled: boolean };
}

/** The ore train saved and standing in block `a`, with track power as given. */
async function placed(shell: TcApp, power: "on" | "draining" | "off"): Promise<void> {
  await ore(shell);
  await pressed(shell, "sl-button.save");
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

      const car = parts(shell, "li.car input.length")[0] as HTMLInputElement;
      expect(car.disabled).toBe(true);
      expect(car.title).toBe(HELD);
      for (const model of parts(shell, "li.product input.length")) {
        expect((model as HTMLInputElement).disabled).toBe(true);
        expect(model.title).toBe(HELD);
      }
      expect(parts(shell, ".why")[0]!.textContent).toBe(HELD);
    },
  );

  /** Placed trains hold nothing with power off: the save names the railroad
   *  again and the rebuild keeps them where they still fit. */
  it("leaves length editing alone with power off and the train placed", async () => {
    const shell = await opened();
    await placed(shell, "off");
    expect((parts(shell, "li.car input.length")[0] as HTMLInputElement).disabled).toBe(
      false,
    );
    for (const model of parts(shell, "li.product input.length")) {
      expect((model as HTMLInputElement).disabled).toBe(false);
    }
    expect(parts(shell, ".why")).toHaveLength(0);
  });

  it("writes a correction to the store only on Save", async () => {
    const shell = await opened();
    await placed(shell, "off");
    store.saved.length = 0;

    await typed(shell, parts(shell, "li.car input.length")[0]!, "150");
    expect(store.saved).toEqual([]);

    await pressed(shell, "sl-button.save");
    expect(written()!.cars!["arnold-ce68-1"]!.length).toBe(150);
  });

  /** The dialog stepped around this guard: New model under a name in use
   *  replaced the product whole, moving a placed train's derived length under
   *  the dispatcher with nothing said. Refusing the name closes it (#413). */
  it("refuses a placed train's model in the dialog, and moves no length", async () => {
    const shell = await opened();
    await ore(shell);
    await pressed(shell, "sl-button.save");
    store.rosterOf = () => ({ ore: { length: 422 } });

    await said(shell, "tc49/dispatch/state/allocation", {
      trains: { ore: "a" },
      locks: { a: "ore" },
      requests: [],
    });
    await shows(shell, "stock");
    store.saved.length = 0;

    await product(shell, "hopper", "freight", "95");

    expect(store.saved).toEqual([]);
    const dialog = screen(shell).renderRoot.querySelector("look-dialog")!;
    expect(dialog.querySelector(".trouble")!.textContent!.trim()).toBe(
      "there is already a model 'hopper'",
    );
    expect(
      (parts(shell, "li.product input.length")[1] as HTMLInputElement).value,
    ).toBe("100");
    expect(parts(shell, ".derived")[0]!.textContent).toMatch("422 mm");
  });

  it("leaves length editing alone with nothing placed", async () => {
    const shell = await opened();
    await ore(shell);
    expect((parts(shell, "li.car input.length")[0] as HTMLInputElement).disabled).toBe(
      false,
    );
    expect(parts(shell, ".why")).toHaveLength(0);
  });

  /** A page that has lost the broker still holds the roster, and cannot know
   *  whether the track has power: the broker, `layout` and the dispatcher may
   *  be running without it (#804). The hold lifts once the row is heard again
   *  with power off; nothing is latched. */
  describe("with the broker gone", () => {
    function lengths(shell: TcApp): HTMLInputElement[] {
      return [
        ...parts(shell, "li.car input.length"),
        ...parts(shell, "li.product input.length"),
      ] as HTMLInputElement[];
    }

    it("holds every length, refuses one typed, and saves no length edit", async () => {
      const shell = await opened();
      await placed(shell, "off");
      await typed(shell, parts(shell, "li.car input.length")[0]!, "150");
      store.saved.length = 0;
      Broker.last!.closes();
      await settled(shell);

      for (const field of lengths(shell)) {
        expect(field.disabled).toBe(true);
        expect(field.title).toBe(UNHEARD);
      }
      await typed(shell, parts(shell, "li.product input.length")[1]!, "110");
      expect(trouble(shell)).toBe(UNHEARD);

      expect(saving(shell).disabled).toBe(true);
      expect(saving(shell).title).toBe(UNHEARD_WAITS);
      await pressed(shell, "sl-button.save");
      expect(store.saved).toEqual([]);
    });

    it("lifts once the row is heard again with power off, and Save writes", async () => {
      const shell = await opened();
      await placed(shell, "off");
      await typed(shell, parts(shell, "li.car input.length")[0]!, "150");
      store.saved.length = 0;
      Broker.last!.closes();
      await settled(shell);
      Broker.last!.opens();
      await settled(shell);

      for (const field of lengths(shell)) {
        expect(field.disabled).toBe(false);
      }
      expect(saving(shell).disabled).toBe(false);
      await pressed(shell, "sl-button.save");
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

      for (const field of lengths(shell)) {
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
    await typed(shell, parts(shell, "li.car input.length")[0]!, "150");
    await said(shell, POWER, { power: "on" });

    expect(saving(shell).disabled).toBe(true);
    expect(saving(shell).title).toBe(WAITS);
  });

  it("is live while power is on for any other roster edit", async () => {
    const shell = await opened();
    await placed(shell, "on");
    await typed(shell, parts(shell, "li.car input.addr")[0]!, "7");

    expect(saving(shell).disabled).toBe(false);
    expect(saving(shell).title).toBe("");
  });

  it("writes the roster and then names the loaded railroad again, with power off", async () => {
    const shell = await opened();
    await placed(shell, "off");
    store.saved.length = 0;
    await typed(shell, parts(shell, "li.car input.length")[0]!, "150");
    expect(wants()).toEqual([]);

    await pressed(shell, "sl-button.save");

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
    await typed(shell, parts(shell, "li.car input.length")[0]!, "150");
    let answer: () => void = () => {};
    store.held = (path) =>
      path.startsWith("/rosters/") ? new Promise<void>((resolve) => (answer = resolve)) : null;

    await pressed(shell, "sl-button.save");
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
    /** Correct the hopper, which is the second product row. */
    async function corrected(shell: TcApp, length: string): Promise<void> {
      await typed(shell, parts(shell, "li.product input.length")[1]!, length);
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

      await pressed(shell, "sl-button.save");

      expect(paths()).toEqual(["/catalogue/hopper", "/rosters/toy"]);
      expect(store.saved[0]!.body).toEqual({
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

      await pressed(shell, "sl-button.save");

      expect(paths()).toEqual(["/catalogue/hopper"]);
      expect(trouble(shell)).not.toBeNull();
      expect(wants()).toEqual([{ topic: RAILROAD_WANTED, payload: { railroad: "toy" } }]);
      expect(saving(shell).disabled).toBe(false);

      store.intercepted = () => null;
      store.saved.length = 0;
      await pressed(shell, "sl-button.save");
      expect(paths()).toEqual(["/rosters/toy"]);
      expect(trouble(shell)).toBeNull();
    });

    it("writes nothing else where the model is refused, and keeps it", async () => {
      const shell = await opened();
      await placed(shell, "off");
      store.saved.length = 0;
      await corrected(shell, "110");
      between((path) => path.startsWith("/catalogue/"));

      await pressed(shell, "sl-button.save");

      expect(store.saved).toEqual([]);
      expect(trouble(shell)).not.toBeNull();
      expect(wants()).toEqual([]);
      expect(saving(shell).disabled).toBe(false);

      store.intercepted = () => null;
      await pressed(shell, "sl-button.save");
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
    await pressed(shell, "sl-button.save");
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
    await typed(shell, parts(shell, "li.car input.addr")[0]!, "7");
    const answer = holding(shell);

    await pressed(shell, "sl-button.save");
    expect(saving(shell).disabled).toBe(true);
    // A second press on the dead button writes nothing more. The guard behind
    // it, for a press that reached the handler anyway, is `railroad.test.ts`'s.
    await pressed(shell, "sl-button.save");
    await answer();

    expect(puts()).toBe(1);
    expect(saving(shell).disabled).toBe(true);
  });

  it("is dead while a corrected model is written", async () => {
    const shell = await opened();
    await placed(shell, "off");
    store.saved.length = 0;
    await typed(shell, parts(shell, "li.product input.length")[1]!, "110");
    const answer = holding(shell, "/catalogue/");

    await pressed(shell, "sl-button.save");
    expect(saving(shell).disabled).toBe(true);
    // A second press on the dead button writes nothing more. The guard behind
    // it, for a press that reached the handler anyway, is `railroad.test.ts`'s.
    await pressed(shell, "sl-button.save");
    await answer();

    expect(store.saved.map((one) => one.path)).toEqual(["/catalogue/hopper", "/rosters/toy"]);
    expect(saving(shell).disabled).toBe(true);
  });

  it("is live again once the write is refused", async () => {
    const shell = await opened();
    await placed(shell, "off");
    await typed(shell, parts(shell, "li.car input.addr")[0]!, "7");
    const answer = holding(shell);
    between((path) => path.startsWith("/rosters/"));

    await pressed(shell, "sl-button.save");
    expect(saving(shell).disabled).toBe(true);
    await answer();

    expect(trouble(shell)).not.toBeNull();
    expect(saving(shell).disabled).toBe(false);
  });

  it("keeps an edit typed during the write, and is live for it", async () => {
    const shell = await opened();
    await placed(shell, "off");
    await typed(shell, parts(shell, "li.car input.addr")[0]!, "7");
    const answer = holding(shell);

    await pressed(shell, "sl-button.save");
    await typed(shell, parts(shell, "li.car input.addr")[0]!, "8");
    await answer();

    expect(written()!.cars!["arnold-ce68-1"]!.addr).toBe("7");
    expect((parts(shell, "li.car input.addr")[0] as HTMLInputElement).value).toBe("8");
    expect(saving(shell).disabled).toBe(false);

    await pressed(shell, "sl-button.save");
    expect(written()!.cars!["arnold-ce68-1"]!.addr).toBe("8");
    expect(saving(shell).disabled).toBe(true);
  });

  it("keeps a length typed during the write waiting for power off", async () => {
    const shell = await opened();
    await placed(shell, "off");
    await typed(shell, parts(shell, "li.car input.addr")[0]!, "7");
    const answer = holding(shell);

    await pressed(shell, "sl-button.save");
    await typed(shell, parts(shell, "li.car input.length")[0]!, "150");
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
  /** The screen over such a roster, with a car of one's own to compose from. */
  async function older(): Promise<TcApp> {
    store.catalogue = {
      "arnold-ce68": { model: "arnold-ce68", kind: "locomotive", length: 122 },
    };
    store.documentOf = () => ({
      roster: "toy",
      cars: { "krokodil-a": { model: "arnold-ce68", addr: "3" } },
      trains: { goods: { length: 400 } },
    });
    return await opened();
  }

  it("draws the train with its stated length and says what it is", async () => {
    const shell = await older();
    expect(trouble(shell)).toBeNull();
    expect(parts(shell, "li.train")).toHaveLength(1);
    expect(parts(shell, ".derived")[0]!.textContent).toMatch("400 mm");
    expect(parts(shell, "li.train p.hint")[0]!.textContent!.trim()).toBe(
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
    expect(parts(shell, "li.train p.hint")[0]!.textContent).toMatch(
      "the stated 400 mm goes",
    );

    await add(shell, "car", 0);
    await pressed(shell, "li.entry button.remove");

    // The conversion is not undone: the train is the ordinary shape now, so
    // the note is the ordinary one and the stated number is not on the row.
    expect(parts(shell, "li.train p.hint")[0]!.textContent!.trim()).toBe(
      "nothing in it yet",
    );
    expect(parts(shell, ".derived")[0]!.textContent).not.toMatch("400 mm");
    await pressed(shell, "sl-button.save");
    expect(written()).toBeUndefined();
    expect(trouble(shell)).toMatch("train 'goods' has nothing in it");
  });

  /** Composing it converts it: a train says a stated length or cars and never
   *  both, and the store refuses one that says both. */
  it("drops the stated length when the first car is put in it", async () => {
    const shell = await older();
    await add(shell, "car", 0);
    await pressed(shell, "sl-button.save");

    expect(written()!.trains.goods).toEqual({ cars: [{ car: "krokodil-a" }] });
    expect(parts(shell, ".derived")[0]!.textContent).toMatch("122 mm");
  });

  /** The document is spread, so nothing is lost: a roster nobody has edited
   *  has nothing to give the store, and one edited elsewhere keeps the stated
   *  length as it was. */
  it("keeps the stated length through a save of the roster", async () => {
    const shell = await older();
    await pressed(shell, "sl-button.save");
    expect(written()).toBeUndefined();

    await typed(shell, parts(shell, "li.car input.name")[0]!, "krokodil");
    await pressed(shell, "sl-button.save");
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
    await pressed(shell, "sl-button.save");
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

      expect(trouble(shell)).toBe("GET /catalogue answered 404");
      expect(parts(shell, "li.product")).toHaveLength(0);

      store.intercepted = () => null;
      await vi.advanceTimersByTimeAsync(RETRY_MS);
      await settled(shell);

      expect(trouble(shell)).toBeNull();
      expect(parts(shell, "li.product")).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });

  /** Nothing answered at all keeps the words it had: the store is what is
   *  missing, and starting it is the fix. The store goes away under the
   *  roster read alone here, the drawing having arrived from it a moment
   *  earlier — which is what `fetch` rejecting looks like from this screen. */
  it("names `tc49 serve` where nothing answered, and reads again", async () => {
    vi.useFakeTimers();
    try {
      store.documentOf = () => {
        throw new TypeError("Failed to fetch");
      };
      const shell = await opened();

      expect(trouble(shell)).toBe("the store is not answering — run `tc49 serve`");

      store.documentOf = (railroad) => ({ roster: railroad, trains: {} });
      store.catalogue = { hopper: { model: "hopper", kind: "freight", length: 100 } };
      await vi.advanceTimersByTimeAsync(RETRY_MS);
      await settled(shell);

      expect(trouble(shell)).toBeNull();
      expect(parts(shell, "li.product")).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });

  /** The same 404 met by the Create press. The dialog stays open with the
   *  message beside the button, so the product is still there to write again
   *  once the route is back. */
  it("leaves the dialog open and names the write that did not land", async () => {
    const shell = await opened();
    between((path) => path.startsWith("/catalogue/"));

    await product(shell, "hopper", "freight", "100");

    const dialog = screen(shell).renderRoot.querySelector("look-dialog")!;
    expect(dialog).not.toBeNull();
    expect(dialog.querySelector(".trouble")!.textContent!.trim()).toBe(
      "PUT /catalogue/hopper answered 404",
    );
    expect(store.saved).toEqual([]);
    expect(parts(shell, "li.product")).toHaveLength(0);
  });
});

/**
 * The current train: the one the `+` buttons put something at the tail of,
 * and the row drawn as current.
 *
 * Every `+` names one train, and it is always a train there is
 * (ui/STOCK.md). It used to be left naming one that was gone — every `+`
 * enabled, saying *add to \'ore\'*, doing nothing and saying nothing when
 * pressed, `append` returning silently for a train the roster has not got.
 * Unmaking the current train was one road into that (#416); renaming it was
 * the other, the current train being a name and the rename writing the roster
 * under a new key (#445).
 */
describe("the current train", () => {
  /** Two trains, the second of which is current: making one up makes it the
   *  one the left points at. They sort `ore` then `shunt`. */
  async function pair(): Promise<TcApp> {
    const shell = await opened();
    await product(shell, "hopper", "freight", "100");
    await train(shell, "ore");
    await train(shell, "shunt");
    return shell;
  }

  /** The `+` beside the first model row, which is what a press on the left
   *  is. */
  function plus(shell: TcApp): HTMLButtonElement {
    return parts(shell, "li.product button.add")[0] as HTMLButtonElement;
  }

  it("makes the first train left current, and adds to that one", async () => {
    const shell = await pair();
    await pressed(shell, "li.train button.remove", 1);

    expect(parts(shell, "li.train")).toHaveLength(1);
    expect(
      (parts(shell, "li.train.current input.name")[0] as HTMLInputElement).value,
    ).toBe("ore");
    expect(plus(shell).disabled).toBe(false);
    expect(plus(shell).title).toBe("add to 'ore'");

    await pressed(shell, "li.product button.add");
    expect(parts(shell, "li.entry .what")[0]!.textContent).toMatch("hopper");
  });

  it("leaves the + with no target where the last train goes", async () => {
    const shell = await pair();
    await pressed(shell, "li.train button.remove", 1);
    await pressed(shell, "li.train button.remove");

    expect(parts(shell, "li.train")).toHaveLength(0);
    expect(plus(shell).disabled).toBe(true);
    expect(plus(shell).title).toBe("make a train up first");
  });

  /** The name field on one of the two rows. They sort, so `ore` is the first
   *  and `shunt` — the current one — the second. */
  function named(shell: TcApp, at: number): HTMLInputElement {
    return parts(shell, "li.train input.name")[at] as HTMLInputElement;
  }

  /** What the current row is called, which is the train every `+` names. */
  function current(shell: TcApp): string | null {
    const row = parts(shell, "li.train.current input.name")[0];
    return row === undefined ? null : (row as HTMLInputElement).value;
  }

  /** `shunt` is current and sorts second, so a fallback to the first train
   *  the roster has would answer `ore`: the rename has to carry the current
   *  train rather than pick one again. */
  it("goes on naming the train it named when that train is renamed", async () => {
    const shell = await pair();

    await typed(shell, named(shell, 1), "shunt-2");

    expect(current(shell)).toBe("shunt-2");
    expect(plus(shell).disabled).toBe(false);
    expect(plus(shell).title).toBe("add to 'shunt-2'");

    await pressed(shell, "li.product button.add");
    expect(
      parts(shell, "li.train.current li.entry .what")[0]!.textContent,
    ).toMatch("hopper");
  });

  /** A refusal changes the document by construction not at all, so there is
   *  nothing to carry: the roster still has `shunt` and the `+` still names
   *  it. */
  it("is left as it was where a rename is refused for the name in use", async () => {
    const shell = await pair();

    await typed(shell, named(shell, 1), "ore");

    expect(trouble(shell)).toBe("there is already a train 'ore'");
    expect(current(shell)).toBe("shunt");
    expect(plus(shell).title).toBe("add to 'shunt'");

    await pressed(shell, "li.product button.add");
    expect(
      parts(shell, "li.train.current li.entry .what")[0]!.textContent,
    ).toMatch("hopper");
  });

  it("is left as it was where a rename is refused for the name itself", async () => {
    const shell = await pair();

    await typed(shell, named(shell, 1), " ");

    expect(trouble(shell)).toBe("A train needs a name.");
    expect(current(shell)).toBe("shunt");
    expect(plus(shell).title).toBe("add to 'shunt'");
  });

  it("does not move when another train is renamed", async () => {
    const shell = await pair();

    await typed(shell, named(shell, 0), "ore-2");

    expect(parts(shell, "li.train input.name").map((one) => (one as HTMLInputElement).value)).toEqual(
      ["ore-2", "shunt"],
    );
    expect(current(shell)).toBe("shunt");
    expect(plus(shell).title).toBe("add to 'shunt'");
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
    const field = () => parts(shell, "li.car input.name")[0] as HTMLInputElement;

    await typed(shell, field(), "");

    expect(trouble(shell)).toBe("A car needs a name.");
    expect(field().value).toBe("arnold-ce68-1");
  });

  it("puts a length refused under power back to the document's", async () => {
    const shell = await opened();
    await ore(shell);
    const field = () => parts(shell, "li.car input.length")[0] as HTMLInputElement;
    await typed(shell, field(), "150");
    await pressed(shell, "sl-button.save");

    await said(shell, POWER, { power: "on" });
    await shows(shell, "stock");
    await typed(shell, field(), "200");

    expect(trouble(shell)).toBe(HELD);
    expect(field().value).toBe("150");
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

  it("keeps a half-typed length on a model's row", async () => {
    const shell = await opened();
    await ore(shell);
    const field = () => parts(shell, "li.product input.length")[0] as HTMLInputElement;
    typing(field(), "12");

    await power(shell);

    expect(field().value).toBe("12");
  });

  it("keeps a car's name and its address", async () => {
    const shell = await opened();
    await ore(shell);
    const name = () => parts(shell, "li.car input.name")[0] as HTMLInputElement;
    const addr = () => parts(shell, "li.car input.addr")[0] as HTMLInputElement;
    typing(name(), "krokodil-");
    typing(addr(), "37");

    await power(shell);

    expect(name().value).toBe("krokodil-");
    expect(addr().value).toBe("37");
  });

  it("keeps a train's name", async () => {
    const shell = await opened();
    await ore(shell);
    const field = () => parts(shell, "li.train input.name")[0] as HTMLInputElement;
    typing(field(), "ore up");

    await power(shell);

    expect(field().value).toBe("ore up");
  });

  /** A refusal is about the field it was typed in. What stands in another
   *  field was not refused and is nobody's to take back. */
  it("is left alone where another field's edit is refused", async () => {
    const shell = await opened();
    await ore(shell);
    const name = () => parts(shell, "li.car input.name")[0] as HTMLInputElement;
    const length = () => parts(shell, "li.product input.length")[0] as HTMLInputElement;
    typing(length(), "12");

    await typed(shell, name(), "");

    expect(trouble(shell)).toBe("A car needs a name.");
    expect(name().value).toBe("arnold-ce68-1");
    expect(length().value).toBe("12");
  });
});
