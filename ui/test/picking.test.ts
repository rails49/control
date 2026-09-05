// @vitest-environment happy-dom

/**
 * Choosing a railroad from the band, end to end through the app
 * ([ADR-0060](../../docs/adr/0060-the-railroad-is-chosen-while-the-apps-run-not-at-startup.md)):
 * the press goes out on the client the run view holds, on
 * `tc49/layout/railroad_wanted`, which whichever binding of the layout
 * interface is running is what answers.
 *
 * **It asks and does not load.** The app opens a railroad on one thing and
 * one thing only — `tc49/layout/state/railroad`, the row the answering app
 * publishes (#371) — so a press that is refused, because the rails have
 * power or because the store has no such railroad, leaves the page on the
 * railroad that is still running. The picker is the gesture and the row is
 * the answer, which is the same shape as the band's power presses
 * (ADR-0035).
 *
 * A DOM test because it crosses the band, the app and the run view's client.
 * The session itself is `support/session.ts`, shared with the other suites.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-app.js";
import type { TcApp } from "../src/ui/tc-app.js";
import { band, bar, serving, settled } from "./support/shell.js";
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

/** The railroads this store has, the toy one among them: a picker with one
 *  entry could not tell a choice from a tick. */
const HAS = ["toy", "otira", "reversing-loops"];

beforeEach(() => {
  brokering();
  serving({
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

/** Choose a railroad the way an operator does: the picker down, and a click
 *  on the entry. */
async function pick(shell: TcApp, name: string): Promise<void> {
  const header = band(shell);
  header.renderRoot.querySelector<HTMLElement>("button.chosen")!.click();
  await settled(shell);
  const entries = [...header.renderRoot.querySelectorAll("menu.drawings li button")];
  const entry = entries.find(
    (one) => one.querySelector(".label")!.textContent!.trim() === name,
  ) as HTMLElement | undefined;
  entry?.click();
  await settled(shell);
}

/** What the band names as the loaded railroad. */
function loaded(shell: TcApp): string {
  return band(shell).renderRoot.querySelector(".drawing")!.textContent!.trim();
}

describe("the picker asks on the bus", () => {
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

describe("the picker against the rails", () => {
  /** Track power off is the precondition, and the band reads the row rather
   *  than turning anything off: a train already under a committed route keeps
   *  rolling whatever the software forgets (ADR-0060, ADR-0051). */
  it("asks for nothing while the track has power", async () => {
    const shell = await joined();
    await said(shell, POWER, { power: "on" });

    await pick(shell, "otira");

    expect(written()).toEqual([]);
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

describe("the band's picker against the bar's menus", () => {
  /** The band sits above the bar (`tc-app.styles.ts`), so a press on the
   *  picker lands on it rather than on the overlay the open menu is waiting
   *  for. The menu would be left down with the keyboard still its, so the
   *  picker takes it up. */
  it("takes a menu on the bar up when the picker goes down", async () => {
    const shell = await dark();
    bar(shell).renderRoot.querySelector<HTMLElement>("button.title")!.click();
    await settled(shell);
    expect(bar(shell).renderRoot.querySelector("menu")).not.toBeNull();

    band(shell).renderRoot.querySelector<HTMLElement>("button.chosen")!.click();
    await settled(shell);

    expect(bar(shell).renderRoot.querySelector("menu")).toBeNull();
    expect(band(shell).renderRoot.querySelector("menu.drawings")).not.toBeNull();
  });
});
