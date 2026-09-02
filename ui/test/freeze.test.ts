// @vitest-environment happy-dom

/**
 * Trains on the layout freeze the drawing
 * ([ADR-0038](../../docs/adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md),
 * #169): you do not rewire track with locomotives standing on it.
 *
 * The rule itself is `commands.test.ts`, where it lives without a DOM. What is
 * here is the path it travels — a picture off the bus, up to the shell as the
 * run's count, and back down to a view whose verbs are dead, whose canvas
 * means nothing by a press, and whose palette has nothing to give. It crosses
 * every one of those, which is why it is a DOM suite.
 *
 * Putting every train away thaws it. There is no gesture that does so from the
 * browser until #170, so what stands in for one here is the picture the
 * dispatcher publishes with nothing placed.
 */

import type { LitElement } from "lit";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-app.js";
import type { Drawing } from "../src/model/drawing.js";
import { centreOf } from "../src/model/geometry.js";
import type { TcApp } from "../src/ui/tc-app.js";
import type { TcCanvas } from "../src/ui/tc-canvas.js";
import type { TcProperties } from "../src/ui/tc-properties.js";
import { band, editing, inside, session, settled, shows } from "./support/shell.js";
import {
  bridging,
  joined,
  loads,
  said,
  stored,
  unbridged,
} from "./support/session.js";

const ALLOCATION = "tc49/dispatch/state/allocation";

/** The run's picture with one train standing in block `a`. */
const STANDING = {
  trains: { goods: "a" },
  locks: { a: "goods" },
  requests: [],
};

/** The same picture with the layout empty: every train off it, which is
 *  absence and not a sentinel (ADR-0039). */
const EMPTY = { trains: {}, locks: {}, requests: [] };

beforeEach(bridging);

afterEach(unbridged);

/** An app joined to a session, showing the editing view: the band's selector
 *  is how an operator gets there, and it is the view that has anything to
 *  freeze. */
async function editor(): Promise<TcApp> {
  const shell = await joined();
  await shows(shell, "edit");
  return shell;
}

/** The editing view with a train standing on the railroad it is showing. */
async function frozen(): Promise<TcApp> {
  const shell = await editor();
  await said(shell, ALLOCATION, STANDING);
  return shell;
}

/** A key pressed with nothing focused, as the shell hears one. */
async function typed(shell: TcApp, key: string): Promise<void> {
  window.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
  await settled(shell);
}

/** A press on the canvas where a grid point is. happy-dom's `getScreenCTM` is
 *  the identity, so a client pixel reads as a square. */
async function pressed(shell: TcApp, at: { x: number; y: number }): Promise<void> {
  (inside(shell, "tc-canvas") as TcCanvas).renderRoot
    .querySelector("svg")!
    .dispatchEvent(
      new PointerEvent("pointerdown", { bubbles: true, clientX: at.x, clientY: at.y }),
    );
  await settled(shell);
}

/** A right-click on the canvas, where the press helper clicks. */
async function clicked(shell: TcApp, at: { x: number; y: number }): Promise<void> {
  (inside(shell, "tc-canvas") as TcCanvas).renderRoot
    .querySelector("svg")!
    .dispatchEvent(
      new MouseEvent("contextmenu", { bubbles: true, clientX: at.x, clientY: at.y }),
    );
  await settled(shell);
}

/** What the editing view's right-click menu is offering. */
function items(shell: TcApp): string[] {
  const menu = inside(shell, "tc-menu") as LitElement;
  return [...menu.renderRoot.querySelectorAll("li button span")].map((one) =>
    one.textContent!.trim(),
  );
}

/** The properties dialog, `null` while none is open. */
function dialog(shell: TcApp): Element | null {
  return (inside(shell, "tc-properties") as TcProperties).renderRoot.querySelector(
    "sl-dialog",
  );
}

/** What the band says about the freeze, `null` while it says nothing. */
function says(shell: TcApp): string | null {
  const said = band(shell).renderRoot.querySelector(".frozen");
  return said === null ? null : said.textContent!.trim();
}

const drawn = (shell: TcApp): Drawing => structuredClone(session(shell).drawing);

describe("a train standing on the railroad", () => {
  /** The bar and the keyboard are one path through `model/commands.ts`, so a
   *  verb that is dead does nothing however it was reached — and the drawing
   *  is what says it did nothing. */
  it("kills the verbs that would change the drawing", async () => {
    const shell = await frozen();
    session(shell).select(["a"]);
    const was = drawn(shell);

    await typed(shell, "r");
    await typed(shell, "Delete");

    expect(drawn(shell)).toEqual(was);
  });

  /** The canvas goes on converting pixels to squares and asking; the machine
   *  is what answers, and while the drawing is frozen it answers nothing
   *  (model/gesture.ts). A press that does not even select is the whole of it:
   *  selecting is where every gesture on the sheet starts. */
  it("makes a press on the sheet mean nothing", async () => {
    const shell = await frozen();
    await pressed(shell, centreOf(stored("toy").symbols.a!));
    expect(session(shell).selection.size).toBe(0);
  });

  /** A palette drag starts on a tile rather than on the sheet, so it is the
   *  view and not the machine that refuses it. */
  it("leaves the palette with nothing to give", async () => {
    const shell = await frozen();
    expect(editing(shell).hasAttribute("frozen")).toBe(true);

    inside(shell, "tc-palette").dispatchEvent(
      new CustomEvent("take", { detail: "block", bubbles: true, composed: true }),
    );
    await settled(shell);

    expect(session(shell).pending).toBeNull();
  });

  /** The freeze can land under an open dialog, whose Apply is an edit. */
  it("takes down a properties dialog it lands under", async () => {
    const shell = await editor();
    session(shell).select(["a"]);
    editing(shell).editSelected();
    await settled(shell);
    expect(dialog(shell)).not.toBeNull();

    await said(shell, ALLOCATION, STANDING);

    expect(dialog(shell)).toBeNull();
  });

  /** The right-click menu is the one edit path that does not go through
   *  `model/commands.ts`, so a menu the freeze lands under would still act on
   *  the drawing. It goes with the dialog. */
  it("takes down a right-click menu it lands under", async () => {
    const shell = await editor();
    await clicked(shell, centreOf(stored("toy").symbols.a!));
    expect(items(shell)).not.toEqual([]);

    await said(shell, ALLOCATION, STANDING);

    expect(items(shell)).toEqual([]);
  });

  /** A wire in flight is the document's rather than the gesture's, so
   *  abandoning presses does not reach it: it would go on following the
   *  pointer across a drawing nobody may draw on, and land on the first click
   *  after the thaw. */
  it("cancels a wire left in flight", async () => {
    const shell = await editor();
    await pressed(shell, centreOf(stored("toy").symbols.a!)); // selects it
    session(shell).startWire("a.B");

    await said(shell, ALLOCATION, STANDING);

    expect(session(shell).pendingFrom).toBeNull();
  });

  /** Looking is what a frozen drawing is still for. */
  it("leaves the netlist and the viewport alone", async () => {
    const shell = await frozen();
    await typed(shell, "n");
    expect(inside(shell, "tc-netlist")).not.toBeNull();
  });

  it("is what the band says, in the words the rest of it uses", async () => {
    const shell = await frozen();
    expect(says(shell)).toBe("drawing frozen");
  });
});

describe("loading another railroad", () => {
  /** The freeze rests on what a joined session is saying about *this*
   *  railroad. Loading another is how a session ends now that the loaded
   *  railroad is the session (#171), and the new run has said nothing yet — so
   *  the drawing must thaw rather than stay locked on a picture of somewhere
   *  else. */
  it("thaws the drawing, the new run having said nothing yet", async () => {
    const shell = await frozen();
    expect(says(shell)).toBe("drawing frozen");

    await loads(shell, "other");

    expect(says(shell)).toBeNull();
    expect(editing(shell).hasAttribute("frozen")).toBe(false);
  });
});

describe("putting every train away", () => {
  it("thaws the drawing, the band and the palette with it", async () => {
    const shell = await frozen();
    session(shell).select(["a"]);
    const was = drawn(shell);

    await said(shell, ALLOCATION, EMPTY);

    expect(says(shell)).toBeNull();
    expect(editing(shell).hasAttribute("frozen")).toBe(false);
    await typed(shell, "r");
    expect(drawn(shell)).not.toEqual(was);
  });

  /** The rule is read off the count afresh rather than latched, so a press
   *  means something again the moment the layout is empty. */
  it("gives the sheet its gestures back", async () => {
    const shell = await frozen();
    await said(shell, ALLOCATION, EMPTY);

    await pressed(shell, centreOf(stored("toy").symbols.a!));

    expect([...session(shell).selection]).toEqual(["a"]);
  });
});
