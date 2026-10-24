// @vitest-environment happy-dom

/**
 * A model's photo, through the screen that shows it (ui/STOCK.md, #631,
 * #978).
 *
 * A DOM test because it crosses the cards, the model editor, two routes and a
 * camera that is not this repository's: what is under test is that a card
 * says where the picture is, that a file dropped or chosen and a picture the
 * camera took become the model's photo, that a file that is no picture is
 * refused in words, and that Save writes the photo after the model's
 * document, the store refusing a photo of a model it has not got (#630).
 *
 * The browser's decoding is `model/photo.ts`'s `toJpeg`, replaced here: a
 * test's DOM has no canvas to decode with, and what is under test is what the
 * screen does with the answer. The client's own side of the photo routes is
 * `test/catalogue.test.ts`'s; nothing is asserted twice.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../src/ui/tc-app.js";
import { fitted, toJpeg, UNREADABLE } from "../src/model/photo.js";
import type { ModelDoc, Picture, RosterDoc } from "../src/model/store.js";
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

vi.mock("../src/model/photo.js", async (original) => ({
  ...(await original<typeof import("../src/model/photo.js")>()),
  toJpeg: vi.fn(),
}));

const RE460: ModelDoc = { model: "sbb-re460", name: "Re 460", kind: "locomotive", length: 220 };

/** The railroad owns one item of that product in one train, so a car card, a
 *  train card and a model card are all about the same photo (ADR-0061).
 *  Made fresh for each read: the screen holds the document it was given and
 *  edits it. */
function roster(): RosterDoc {
  return {
    roster: "toy",
    cars: { "krokodil-a": { model: "sbb-re460", addr: "3" } },
    trains: { ic: { cars: [{ car: "krokodil-a" }] } },
  };
}

/** A picture, as a camera hands one over: a JPEG's magic number and two bytes
 *  after it, which is as much of a photo as anything here reads. */
const TOOK = new Uint8Array([0xff, 0xd8, 0xff, 0x2a, 0x2b]);

/** A camera that takes that picture, which is a box with one plugged in. */
const WORKING = (): Take => ({ status: 200, statusText: "OK", jpeg: TOOK });

/** What the conversion answers for a file: other bytes than the file's, so
 *  that what reaches the store is seen to be the conversion's output. */
const CONVERTED: Picture = {
  jpeg: new Uint8Array([0xff, 0xd8, 0xff, 0x01]),
  shown: "data:image/jpeg;base64,/9j/AQ==",
};

let store: Answers;

beforeEach(() => {
  brokering();
  vi.mocked(toJpeg).mockReset();
  vi.mocked(toJpeg).mockResolvedValue(CONVERTED);
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

/** The app with the toy railroad loaded, showing the stock screen's Models
 *  list. The broker's retained row is the only thing that loads a railroad
 *  (ADR-0060). */
async function opened(): Promise<TcApp> {
  const shell = await mounted("stock");
  await loads(shell, "toy");
  await tab(shell, "models");
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

async function pressed(shell: TcApp, selector: string): Promise<void> {
  part(shell, selector)!.click();
  await settled(shell);
}

async function tab(shell: TcApp, which: "trains" | "cars" | "models"): Promise<void> {
  await pressed(shell, `button.tab[data-tab="${which}"]`);
}

/** Where a card's photo is pointed. */
function card(shell: TcApp, which: string): string | null {
  return part(shell, `button.card.${which} .frame img`)?.getAttribute("src") ?? null;
}

/** Where the model editor's photo frame is pointed. */
function framed(shell: TcApp): string | null {
  return part(shell, ".model-editor .photo-frame img")?.getAttribute("src") ?? null;
}

/** A file dropped on the model editor's photo frame. */
async function dropped(shell: TcApp, file: File): Promise<void> {
  const drop = new Event("drop", { bubbles: true, cancelable: true });
  Object.defineProperty(drop, "dataTransfer", { value: { files: [file] } });
  part(shell, ".model-editor .photo-frame")!.dispatchEvent(drop);
  await settled(shell);
}

/** A file chosen with Choose file…, which is the browser's own file input. */
async function picked(shell: TcApp, file: File): Promise<void> {
  const input = part(shell, ".model-editor input.file") as HTMLInputElement;
  Object.defineProperty(input, "files", { value: [file], configurable: true });
  input.dispatchEvent(new Event("change"));
  await settled(shell);
}

/** A photo off a phone, which is what a person drops. */
function phone(): File {
  return new File([new Uint8Array([1, 2, 3])], "IMG_0001.jpg", { type: "image/jpeg" });
}

/** The photo writes the store took. */
function photos(): { path: string; body: unknown }[] {
  return store.saved.filter((one) => one.path.endsWith("/photo"));
}

describe("a card's photo", () => {
  it("is the model's photo route, on a model card, a car card and a train card", async () => {
    const shell = await opened();
    expect(card(shell, "model")).toBe("/catalogue/sbb-re460/photo");
    await tab(shell, "cars");
    expect(card(shell, "car")).toBe("/catalogue/sbb-re460/photo");
    await tab(shell, "trains");
    expect(card(shell, "train")).toBe("/catalogue/sbb-re460/photo");
  });

  /** Nothing on a model's document says whether there is a photo, so a route
   *  answering anything but 200 is the whole of how the screen learns (#630). */
  it("says No photo, and the editor's frame asks for one, where the route did not load", async () => {
    const shell = await opened();
    part(shell, "button.card.model .frame img")!.dispatchEvent(new Event("error"));
    await settled(shell);

    expect(text(shell, "button.card.model .frame")).toBe("No photo");
    expect(text(shell, ".model-editor .photo-frame b")).toBe("Drop a picture here");
    expect(text(shell, ".model-editor button.take")).toBe("Take photo");
  });
});

describe("a file dropped or chosen", () => {
  it("reaches PUT /catalogue/<model>/photo as the conversion's output, on Save", async () => {
    const shell = await opened();
    const file = phone();

    await dropped(shell, file);

    expect(vi.mocked(toJpeg)).toHaveBeenCalledWith(file);
    expect(framed(shell)).toBe(CONVERTED.shown);
    expect(photos()).toEqual([]);
    await pressed(shell, ".bar button.save");

    expect(photos()).toEqual([{ path: "/catalogue/sbb-re460/photo", body: CONVERTED.jpeg }]);
    expect(card(shell, "model")).toBe("/catalogue/sbb-re460/photo?v=1");
  });

  it("is the photo the same way where it is chosen with Choose file…", async () => {
    const shell = await opened();
    await picked(shell, phone());
    await pressed(shell, ".bar button.save");

    expect(photos()).toEqual([{ path: "/catalogue/sbb-re460/photo", body: CONVERTED.jpeg }]);
  });

  it("is refused where it is not a picture, and decodes nothing", async () => {
    const shell = await opened();

    await dropped(shell, new File(["hello"], "notes.txt", { type: "text/plain" }));

    expect(text(shell, ".model-editor .photo-trouble")).toBe("That file is not a picture.");
    expect(vi.mocked(toJpeg)).not.toHaveBeenCalled();
    expect(text(shell, ".bar .said")).toBe("Everything is saved");
  });

  it("is refused where the browser cannot read it", async () => {
    vi.mocked(toJpeg).mockRejectedValue(new Error(UNREADABLE));
    const shell = await opened();

    await dropped(shell, new File(["…"], "IMG_0002.heic", { type: "image/heic" }));

    expect(text(shell, ".model-editor .photo-trouble")).toBe(
      "This browser cannot read that picture. Try a JPEG or PNG.",
    );
    expect(text(shell, ".bar .said")).toBe("Everything is saved");
  });
});

describe("a picture the camera took", () => {
  it("says so while the camera is being waited on, with the press dead", async () => {
    let answer: (took: Take) => void = () => {};
    store.camera = () => new Promise<Take>((resolve) => (answer = resolve));
    const shell = await opened();

    await pressed(shell, ".model-editor button.take");

    expect(text(shell, ".model-editor .photo-frame .wait")).toBe("Taking a picture…");
    expect(part(shell, ".model-editor button.take")).toHaveProperty("disabled", true);
    answer(WORKING());
    await settled(shell);
    expect(part(shell, ".model-editor button.take")).toHaveProperty("disabled", false);
    expect(text(shell, ".model-editor button.take")).toBe("Retake photo");
  });

  it("goes to the store as the camera's own bytes, on Save", async () => {
    store.camera = WORKING;
    const shell = await opened();
    await pressed(shell, ".model-editor button.take");

    expect(text(shell, ".bar .said")).toBe("1 unsaved change");
    await pressed(shell, ".bar button.save");

    expect(photos()).toEqual([{ path: "/catalogue/sbb-re460/photo", body: TOOK }]);
    expect(vi.mocked(toJpeg)).not.toHaveBeenCalled();
  });

  /** Any answer but 200 means no picture and there is nothing else to read
   *  out of it (docs/SYSTEM.md), and the press is never dead for want of a
   *  camera: one plugged in a minute later is a picture a minute later (#629). */
  it("says what the camera answered where it answered no picture", async () => {
    store.camera = () => ({ status: 502, statusText: "Bad Gateway" });
    const shell = await opened();

    await pressed(shell, ".model-editor button.take");

    const said = text(shell, ".model-editor .photo-trouble")!;
    expect(said.startsWith("no picture:")).toBe(true);
    expect(said).toContain("502");
    expect(part(shell, ".model-editor button.take")).toHaveProperty("disabled", false);
  });
});

describe("a model made with a photo", () => {
  /** Three writes and in that order: the store refuses a photo for a model
   *  it has not got, and a roster naming one (#630, #978). */
  it("is written as the document, then the photo, then the roster, under the key minted", async () => {
    const shell = await opened();
    await pressed(shell, "button.new");
    expect(text(shell, ".model-editor .photo-frame b")).toBe("Drop a picture here");
    const name = part(shell, ".model-editor input.name") as HTMLInputElement;
    name.value = "Ae 6/6";
    name.dispatchEvent(new Event("change"));
    await settled(shell);
    await dropped(shell, phone());

    await pressed(shell, ".bar button.save");

    expect(store.saved.map((one) => one.path)).toEqual([
      "/catalogue/ae-6-6",
      "/catalogue/ae-6-6/photo",
      "/rosters/toy",
    ]);
    expect(card(shell, "model[aria-current='true']")).toBe("/catalogue/ae-6-6/photo?v=1");
  });

  it("keeps the photo for the next Save where the store refuses it", async () => {
    const shell = await opened();
    await dropped(shell, phone());
    store.refuses = (path) =>
      path.endsWith("/photo") ? { status: 400, error: "not a JPEG" } : null;

    await pressed(shell, ".bar button.save");

    expect(text(shell, ".bar .said")).toBe("not a JPEG");
    expect(framed(shell)).toBe(CONVERTED.shown);
    store.refuses = () => null;
    await pressed(shell, ".bar button.save");
    expect(photos()).toEqual([{ path: "/catalogue/sbb-re460/photo", body: CONVERTED.jpeg }]);
  });
});

describe("the conversion's size", () => {
  it("is the picture's own up to 1600 px wide, and scaled down whole past it", () => {
    expect(fitted(1200, 400)).toEqual({ width: 1200, height: 400 });
    expect(fitted(4000, 1200)).toEqual({ width: 1600, height: 480 });
  });
});
