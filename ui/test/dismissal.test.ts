// @vitest-environment happy-dom

/**
 * The right-click that lands on a menu's dismissal overlay
 * ([#180](https://github.com/rails49/control/issues/180)).
 *
 * An open menu covers the page with the overlay a press outside is dismissed
 * by, and that overlay is then the topmost thing over the drawing. A second
 * right-click landed on it: the menu came down, `contextmenu` never reached
 * the canvas, nothing called `preventDefault`, and Chrome put its own menu up
 * over the railroad. Both menu systems wear the one overlay, so the bar's
 * menus did it too.
 *
 * **This suite cannot see the bug, and no vitest suite can.** happy-dom does
 * not render, so it has no hit testing: `document.elementFromPoint` returns
 * null there whatever is on top, and the browser's own hit test is the whole
 * of what put the press on the overlay rather than on the drawing. What the
 * suite does hold is everything the overlay does once the press is on it —
 * dismiss, forward to what is underneath, and answer for the native menu as
 * that forwarding answered — with the one thing it cannot do, the hit test,
 * standing in as a stub. The bug itself is checked in a browser, and #180
 * records the reading.
 */

import type { LitElement } from "lit";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-app.js";
import { centreOf, type Point } from "../src/model/geometry.js";
import type { TcApp } from "../src/ui/tc-app.js";
import { bar, running, settled } from "./support/shell.js";
import {
  bridging,
  joined,
  said,
  stored,
  unbridged,
  written,
} from "./support/session.js";

const ALLOCATION = "tc49/dispatch/state/allocation";

/** happy-dom's own answer, put back after each test: the stub below is what
 *  stands in for the browser's hit test. */
const NOWHERE = document.elementFromPoint;

beforeEach(bridging);

afterEach(() => {
  document.elementFromPoint = NOWHERE;
  unbridged();
});

/** Where each block's middle is. happy-dom's `getScreenCTM` is the identity,
 *  so a grid point reads as a client pixel and back. */
const MIDDLE = {
  a: centreOf(stored("toy").symbols.a!),
  b: centreOf(stored("toy").symbols.b!),
};

/** A joined session with a train standing in each block and the run held. Two
 *  trains, because a second right-click is about the one the first menu was
 *  not opened over. */
async function standing(): Promise<TcApp> {
  const shell = await joined();
  await said(shell, "tc49/dispatch/state/run", { run: "held" });
  await said(shell, ALLOCATION, {
    trains: { goods: "a", shunter: "b" },
    locks: { a: "goods", b: "shunter" },
    requests: [],
  });
  return shell;
}

/** The drawing surface the run view is painting on. */
function surface(shell: TcApp): SVGSVGElement {
  return running(shell)
    .renderRoot.querySelector("tc-canvas")!
    .renderRoot.querySelector("svg")!;
}

/** The overlay a menu has dropped over the page, in whichever component's
 *  shadow root it was rendered. */
function overlay(part: LitElement): HTMLElement {
  return part.renderRoot.querySelector<HTMLElement>(".dismiss")!;
}

/** A right-click on `on`, and whether the browser was left to put its own menu
 *  up. Cancellable, so `defaultPrevented` means the app suppressed it rather
 *  than the event never having been suppressible. The press goes first: it is
 *  what the overlay dismisses on, and the order is the browser's. */
async function rightClicked(
  shell: TcApp,
  on: Element,
  at: Point,
): Promise<{ native: boolean }> {
  const where = { bubbles: true, cancelable: true, clientX: at.x, clientY: at.y };
  on.dispatchEvent(new MouseEvent("pointerdown", { ...where, button: 2 }));
  const event = new MouseEvent("contextmenu", where);
  on.dispatchEvent(event);
  await settled(shell);
  return { native: !event.defaultPrevented };
}

/** What the run view's menu is offering. */
function offered(shell: TcApp): string[] {
  const menu = running(shell).renderRoot.querySelector("tc-menu")!;
  return [...menu.renderRoot.querySelectorAll("li button")].map((row) =>
    row.querySelector("span")!.textContent!.trim(),
  );
}

/** The item chosen, the way a pointer chooses one. */
async function chose(shell: TcApp, label: string): Promise<void> {
  const menu = running(shell).renderRoot.querySelector("tc-menu")!;
  const row = [...menu.renderRoot.querySelectorAll("li button")].find(
    (one) => one.querySelector("span")!.textContent!.trim() === label,
  )!;
  (row as HTMLButtonElement).click();
  await settled(shell);
}

/** The title on the bar whose menu is down, `null` while none is. */
function down(shell: TcApp): string | null {
  const titles = [...bar(shell).renderRoot.querySelectorAll("button.title")];
  const open = titles.find((one) => one.getAttribute("aria-expanded") === "true");
  return open === undefined ? null : open.textContent!.trim();
}

/**
 * The browser's hit test, stood in for: with a menu open the press lands on
 * the overlay, and what is under the overlay at that point is the drawing.
 * The overlay takes itself out of the way and asks, so the stub answers what
 * the drawing would.
 */
function underneath(shell: TcApp): void {
  const drawing = surface(shell);
  document.elementFromPoint = () => drawing;
}

describe("a right-click while a canvas menu is open", () => {
  it("dismisses that menu and opens one for the train under the pointer", async () => {
    const shell = await standing();
    expect(await rightClicked(shell, surface(shell), MIDDLE.a)).toEqual({
      native: false,
    });
    expect(offered(shell)).toEqual(["Turn around"]);

    underneath(shell);
    const menu = running(shell).renderRoot.querySelector("tc-menu")!;
    expect(await rightClicked(shell, overlay(menu), MIDDLE.b)).toEqual({
      native: false,
    });

    // The second train's menu, not the first's still standing there: choosing
    // it turns around the train that was clicked second.
    expect(offered(shell)).toEqual(["Turn around"]);
    await chose(shell, "Turn around");
    expect(written()).toEqual([
      { topic: "tc49/ui/reversal_wanted", payload: { train: "shunter" } },
    ]);
  });

  /** The overlay's own job, unchanged: a left press outside the menu takes it
   *  down and reaches nothing underneath. */
  it("takes the menu down on a left press and opens nothing", async () => {
    const shell = await standing();
    await rightClicked(shell, surface(shell), MIDDLE.a);
    const menu = running(shell).renderRoot.querySelector("tc-menu")!;

    underneath(shell);
    overlay(menu).dispatchEvent(
      new MouseEvent("pointerdown", {
        bubbles: true,
        cancelable: true,
        clientX: MIDDLE.b.x,
        clientY: MIDDLE.b.y,
      }),
    );
    await settled(shell);

    expect(offered(shell)).toEqual([]);
  });
});

describe("a right-click while the bar's menu is open", () => {
  it("dismisses it and opens the menu for the train under the pointer", async () => {
    const shell = await standing();
    bar(shell).renderRoot.querySelector<HTMLElement>("button.title")!.click();
    await settled(shell);
    expect(down(shell)).toBe("View");

    underneath(shell);
    expect(await rightClicked(shell, overlay(bar(shell)), MIDDLE.a)).toEqual({
      native: false,
    });

    expect(down(shell)).toBeNull();
    expect(offered(shell)).toEqual(["Turn around"]);
  });
});
