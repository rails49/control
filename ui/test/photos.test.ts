// @vitest-environment happy-dom

/**
 * A model's photo, through the screen that shows it (ui/STOCK.md, #631).
 *
 * A DOM test because it crosses the rows, two routes and a camera that is not
 * this repository's: what is under test is that a row says where the picture
 * is, that a press takes one and the next press keeps it, that a box with no
 * camera is answered in words rather than with a dead control, and that a
 * product written with a picture reaches the store as two writes in the order
 * the store takes them (#629, #630).
 *
 * The client's own side of the photo routes — the URL a photo is at, and the
 * `image/jpeg` a `PUT` carries it under — is `test/catalogue.test.ts`'s, and
 * the words a call that came back with no document gets are
 * `test/asking.test.ts`'s; nothing is asserted twice.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../src/ui/tc-app.js";
import type { ModelDoc, RosterDoc } from "../src/model/store.js";
import type { TcApp } from "../src/ui/tc-app.js";
import type { TcStock } from "../src/ui/tc-stock.js";
import {
  mounted,
  serving,
  settled,
  stocking,
  type Answers,
  type Take,
} from "./support/shell.js";
import { brokering, DERIVES, loads, stored, unbrokered } from "./support/session.js";

const RE460: ModelDoc = { model: "sbb-re460", kind: "locomotive", length: 220 };

/** The railroad owns one item of that product, so a car row and a model row
 *  are both on the screen and both are about the same photo (ADR-0061). Made
 *  fresh for each read: the screen holds the document it was given and edits
 *  it. */
function roster(): RosterDoc {
  return {
    roster: "toy",
    cars: { "krokodil-a": { model: "sbb-re460", addr: "3" } },
    trains: {},
  };
}

/** A picture, as a camera hands one over: a JPEG's magic number and two bytes
 *  after it, which is as much of a photo as anything here reads. */
const TOOK = new Uint8Array([0xff, 0xd8, 0xff, 0x2a, 0x2b]);

/** A camera that takes that picture, which is a box with one plugged in. */
const WORKING = (): Take => ({ status: 200, statusText: "OK", jpeg: TOOK });

let store: Answers;

beforeEach(() => {
  brokering();
  store = serving({
    drawings: ["toy"],
    read: stored,
    review: () => Promise.resolve(DERIVES),
    rosterOf: () => ({}),
    documentOf: roster,
    catalogue: { "sbb-re460": RE460 },
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  unbrokered();
});

/** The app with the toy railroad loaded, showing the stock screen. The
 *  broker's retained row is the only thing that loads a railroad (ADR-0060). */
async function opened(): Promise<TcApp> {
  const shell = await mounted("stock");
  await loads(shell, "toy");
  return shell;
}

function screen(shell: TcApp): TcStock {
  return stocking(shell);
}

function part(shell: TcApp, selector: string): HTMLElement | null {
  return screen(shell).renderRoot.querySelector<HTMLElement>(selector);
}

/** What one of the screen's parts says, `null` where there is no such part. */
function text(shell: TcApp, selector: string): string | null {
  return part(shell, selector)?.textContent?.trim() ?? null;
}

/** Where a row's thumbnail is pointed. */
function thumbnail(shell: TcApp, row: string): string | null {
  return part(shell, `${row} button.thumb img`)?.getAttribute("src") ?? null;
}

/** Where every model row's thumbnail is pointed, whichever row is first. */
function thumbnails(shell: TcApp): string[] {
  return [
    ...screen(shell).renderRoot.querySelectorAll("li.product button.thumb img"),
  ].map((img) => img.getAttribute("src") ?? "");
}

/** Whether a control in the New model dialog is dead. */
function dead(shell: TcApp, selector: string): boolean {
  return (part(shell, `sl-dialog ${selector}`) as HTMLInputElement).disabled;
}

async function pressed(shell: TcApp, selector: string): Promise<void> {
  part(shell, selector)!.click();
  await settled(shell);
}

/** The photo dialog opened on the product's row, with nothing taken yet. */
async function dialog(shell: TcApp): Promise<void> {
  await pressed(shell, "li.product button.thumb");
}

/** A picture taken, whatever the camera answers with. */
async function takes(shell: TcApp, where = "sl-dialog.photo"): Promise<void> {
  await pressed(shell, `${where} button.take`);
}

/** What was typed into one of the dialog's fields. */
async function typed(shell: TcApp, selector: string, value: string): Promise<void> {
  const field = part(shell, selector) as HTMLInputElement;
  field.value = value;
  field.dispatchEvent(new Event("change"));
  await settled(shell);
}

/** Write a product in the New model dialog and press Create, the photo in it
 *  left as it stands. */
async function created(shell: TcApp, model: string): Promise<void> {
  await typed(shell, "sl-dialog #model", model);
  await typed(shell, "sl-dialog #length", "120");
  await pressed(shell, "sl-dialog .create");
}

describe("the thumbnail on a row", () => {
  it("is an image on the model's photo route, on a model row and a car row", async () => {
    const shell = await opened();

    expect(thumbnail(shell, "li.product")).toBe("/catalogue/sbb-re460/photo");
    expect(thumbnail(shell, "li.car")).toBe("/catalogue/sbb-re460/photo");
  });

  /** A car's photo is its model's: the picture says what the product looks
   *  like, and ten identical hoppers have one between them (ADR-0061). So the
   *  dialog a car's thumbnail opens is the model's, and says so. */
  it("opens a dialog titled for the model, pressed on a car", async () => {
    const shell = await opened();

    await pressed(shell, "li.car button.thumb");

    expect(part(shell, "sl-dialog.photo")!.getAttribute("label")).toBe(
      "Photo — sbb-re460",
    );
  });
});

describe("taking a picture", () => {
  it("says so while the camera is being waited on, with the press dead", async () => {
    let answer: (took: Take) => void = () => {};
    store.camera = () => new Promise<Take>((resolve) => (answer = resolve));
    const shell = await opened();
    await dialog(shell);

    await takes(shell);

    expect(text(shell, "sl-dialog.photo .picture")).toBe("taking a picture…");
    expect(part(shell, "sl-dialog.photo button.take")).toHaveProperty(
      "disabled",
      true,
    );
    answer(WORKING());
    await settled(shell);
    expect(text(shell, "sl-dialog.photo button.take")).toBe("Retake");
  });

  it("offers to save the picture the camera answered with", async () => {
    store.camera = WORKING;
    const shell = await opened();
    await dialog(shell);

    await takes(shell);

    expect(text(shell, "sl-dialog.photo button.keep")).toBe("Save");
    expect(text(shell, "sl-dialog.photo p.unkept")).toBe("not saved yet");
    expect(store.saved).toEqual([]);
  });

  it("sends the camera's own bytes to the model's photo route", async () => {
    store.camera = WORKING;
    const shell = await opened();
    await dialog(shell);
    await takes(shell);

    await pressed(shell, "sl-dialog.photo button.keep");

    expect(store.saved).toEqual([
      { path: "/catalogue/sbb-re460/photo", body: TOOK },
    ]);
  });

  /** The bytes at that URL have changed and the browser is holding the ones
   *  from before, so the thumbnail asks for them again. The store drops a
   *  query string, so it is the same route (#630). */
  it("points the thumbnail at a URL the browser has no answer for", async () => {
    store.camera = WORKING;
    const shell = await opened();
    await dialog(shell);
    await takes(shell);

    await pressed(shell, "sl-dialog.photo button.keep");

    expect(thumbnail(shell, "li.product")).toBe("/catalogue/sbb-re460/photo?v=1");
  });

  /** Any answer but 200 means no picture and there is nothing else to read out
   *  of it (docs/SYSTEM.md), and the press is never dead for want of a camera:
   *  one plugged in a minute later is a picture a minute later (#629). */
  it("says what the camera answered where it answered no picture", async () => {
    store.camera = () => ({ status: 502, statusText: "Bad Gateway" });
    const shell = await opened();
    await dialog(shell);

    await takes(shell);

    const said = text(shell, "sl-dialog.photo p.no-picture")!;
    expect(said.startsWith("no picture:")).toBe(true);
    expect(said).toContain("502");
    expect(text(shell, "sl-dialog.photo button.take")).toBe("Try again");
  });
});

describe("a product written with a picture", () => {
  /** Two writes and in that order: the store refuses a photo for a model it
   *  has not got, a file beside a document that is not there being a photo of
   *  nothing (#630). */
  it("writes the model's document before its photo", async () => {
    store.camera = WORKING;
    const shell = await opened();
    await pressed(shell, "button.new-model");
    await takes(shell, "sl-dialog");

    await created(shell, "hopper");

    expect(store.saved.map((one) => one.path)).toEqual([
      "/catalogue/hopper",
      "/catalogue/hopper/photo",
    ]);
    expect(store.saved[1]!.body).toEqual(TOOK);
  });

  /** The model is written and the photo is not, so the dialog stays open and
   *  says which of the two is missing: the product is in the catalogue either
   *  way, and the picture is still there to save again (#638). */
  it("leaves the model written where its photo does not land", async () => {
    store.camera = WORKING;
    store.intercepted = (path) =>
      path.endsWith("/photo") ? { status: 404, statusText: "" } : null;
    const shell = await opened();
    await pressed(shell, "button.new-model");
    await takes(shell, "sl-dialog");

    await created(shell, "hopper");

    expect(store.saved.map((one) => one.path)).toEqual(["/catalogue/hopper"]);
    const said = text(shell, "sl-dialog p.trouble")!;
    expect(said).toContain("'hopper' is written, but its photo was not saved");
    expect(said).toContain("PUT /catalogue/hopper/photo answered 404");
  });

  /** Create has written the product, so the dialog's frame is drawn for it and
   *  the picture nothing kept has the photo dialog's own Save — the same bytes
   *  to the same route, and no second Save written for this dialog (#638). */
  it("offers Save for the picture its failed photo left unsaved", async () => {
    store.camera = WORKING;
    // The `PUT` Create makes is refused and the one Save makes is taken, which
    // is the camera's bytes reaching the route on the second press.
    let refuse = true;
    store.intercepted = (path) => {
      if (!path.endsWith("/photo") || !refuse) return null;
      refuse = false;
      return { status: 404, statusText: "" };
    };
    const shell = await opened();
    await pressed(shell, "button.new-model");
    await takes(shell, "sl-dialog");
    await created(shell, "hopper");

    expect(text(shell, "sl-dialog button.keep")).toBe("Save");

    await pressed(shell, "sl-dialog button.keep");

    expect(store.saved.map((one) => one.path)).toEqual([
      "/catalogue/hopper",
      "/catalogue/hopper/photo",
    ]);
    expect(store.saved[1]!.body).toEqual(TOOK);
    // The photo is saved, so both of the dialog's writes are done: it is put
    // away, and the line that said the photo was not saved goes with it (#644).
    expect(text(shell, "sl-dialog p.trouble")).toBeNull();
  });

  /** One product is written per New model dialog. Pressing Create again
   *  reached the duplicate-name check and replaced the refusal with *there is
   *  already a model 'hopper'* — a sentence about this dialog's own write
   *  (#638). */
  it("leaves Create dead once the model is written", async () => {
    store.camera = WORKING;
    store.intercepted = (path) =>
      path.endsWith("/photo") ? { status: 404, statusText: "" } : null;
    const shell = await opened();
    await pressed(shell, "button.new-model");
    await takes(shell, "sl-dialog");
    await created(shell, "hopper");

    expect(
      (part(shell, "sl-dialog .create") as HTMLElement & { disabled: boolean })
        .disabled,
    ).toBe(true);

    await pressed(shell, "sl-dialog .create");

    expect(store.saved.map((one) => one.path)).toEqual(["/catalogue/hopper"]);
    expect(text(shell, "sl-dialog p.trouble")).toContain(
      "'hopper' is written, but its photo was not saved",
    );
  });
});

/** The dialog Create has written a model in: a second state of the same dialog,
 *  where one of its two writes is done and the other is not
 *  ([#644](https://github.com/rails49/control/issues/644)). */
describe("the New model dialog about the model it wrote", () => {
  /** A Create whose photo did not land, a function row filled in so that there
   *  is one to be dead. */
  async function wrote(shell: TcApp): Promise<void> {
    await pressed(shell, "button.new-model");
    await takes(shell, "sl-dialog");
    await pressed(shell, "sl-dialog button.add-function");
    await typed(shell, "sl-dialog li.function input.number", "0");
    await typed(shell, "sl-dialog li.function input.name", "headlights");
    await created(shell, "hopper");
  }

  /** Every control the dialog edits the draft with. */
  const FIELDS = [
    "#model",
    "#kind",
    "#length",
    "li.function input.number",
    "li.function input.name",
    "li.function button.remove",
    "button.add-function",
  ];

  /** Create is dead from the write on and nothing else reads the draft, so an
   *  edit typed into one of these cannot be saved — and a different name typed
   *  there while Save still sends the picture to the written model says nothing
   *  about which model it goes to. */
  it("leaves every control that edits the model dead, and the photo's Save live", async () => {
    store.camera = WORKING;
    store.intercepted = (path) =>
      path.endsWith("/photo") ? { status: 404, statusText: "" } : null;
    const shell = await opened();

    await wrote(shell);

    expect(FIELDS.filter((one) => !dead(shell, one))).toEqual([]);
    expect(dead(shell, "button.keep")).toBe(false);
  });

  /** Both writes are done, so there is nothing left for the dialog to say and
   *  it goes the way a Create whose photo landed first time takes it: the
   *  catalogue row is drawn with the photo it now has. */
  it("is put away when the photo Save lands", async () => {
    store.camera = WORKING;
    // The `PUT` Create makes is refused and the one Save makes is taken.
    let refuse = true;
    store.intercepted = (path) => {
      if (!path.endsWith("/photo") || !refuse) return null;
      refuse = false;
      return { status: 404, statusText: "" };
    };
    const shell = await opened();
    await wrote(shell);

    await pressed(shell, "sl-dialog button.keep");

    expect(part(shell, "sl-dialog")).toBeNull();
    expect(thumbnails(shell)).toContain("/catalogue/hopper/photo?v=1");
  });

  /** A Save the store will not take is a write that did not happen, so the
   *  dialog stays where it was with the picture still on it to save again, and
   *  the store's wording beside the picture. */
  it("stays open where the photo Save is refused, and says what the store said", async () => {
    store.camera = WORKING;
    store.intercepted = (path) =>
      path.endsWith("/photo") ? { status: 404, statusText: "" } : null;
    const shell = await opened();
    await wrote(shell);

    await pressed(shell, "sl-dialog button.keep");

    expect(part(shell, "sl-dialog")).not.toBeNull();
    const said = text(shell, "sl-dialog p.no-picture")!;
    expect(said).toContain("PUT /catalogue/hopper/photo answered 404");
    expect(text(shell, "sl-dialog button.keep")).toBe("Save");
  });
});
