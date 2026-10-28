// @vitest-environment happy-dom

/**
 * The Settings dialog's Points tab sets the point gap (#1128): its field
 * shows `point_gap` off `tc49/layout/state/settings` (#1125), and a commit
 * publishes `tc49/layout/settings_wanted` (#1126). What a commit sends is
 * `gapChange`'s (`settings.test.ts`); this is the dialog through the app.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-app.js";
import type { TcApp } from "../src/ui/tc-app.js";
import type { TcSettings } from "../src/ui/tc-settings.js";
import { settingsOpened, settled } from "./support/shell.js";
import { brokering, joined, said, unbrokered, written } from "./support/session.js";

beforeEach(brokering);

afterEach(unbrokered);

const STATE_SETTINGS = "tc49/layout/state/settings";
const SETTINGS_WANTED = "tc49/layout/settings_wanted";

/** The tab's one field. */
function field(dialog: TcSettings): HTMLInputElement {
  return dialog.renderRoot.querySelector<HTMLInputElement>("div.points sl-input.gap")!;
}

/** What the tab says beneath the field, hint by hint. */
function hints(dialog: TcSettings): string[] {
  return [...dialog.renderRoot.querySelectorAll("div.points .hint")].map((one) =>
    one.textContent!.trim(),
  );
}

/** `typed` committed in the field, as a change and not a keystroke. */
async function committed(shell: TcApp, dialog: TcSettings, typed: string): Promise<void> {
  const input = field(dialog);
  input.value = typed;
  input.dispatchEvent(new Event("sl-change"));
  await settled(shell);
}

/** The app joined, the layout saying a point gap of `gap`, the dialog up. */
async function gapped(gap: number): Promise<{ shell: TcApp; dialog: TcSettings }> {
  const shell = await joined();
  await said(shell, STATE_SETTINGS, { at: 1, point_gap: gap });
  return { shell, dialog: await settingsOpened(shell) };
}

describe("the Points tab", () => {
  it("comes after Railroad", async () => {
    const dialog = await settingsOpened(await joined());
    const tabs = [...dialog.renderRoot.querySelectorAll("sl-tab")].map((tab) =>
      tab.textContent!.trim(),
    );
    expect(tabs.slice(0, 2)).toEqual(["Railroad", "Points"]);
  });

  it("shows the point gap state/settings says", async () => {
    const { dialog } = await gapped(0.8);
    expect(field(dialog).value).toBe("0.8");
    expect(field(dialog).disabled).toBe(false);
  });

  it("follows the row as it changes", async () => {
    const { shell, dialog } = await gapped(0.8);
    await said(shell, STATE_SETTINGS, { at: 2, point_gap: 1.5 });
    expect(field(dialog).value).toBe("1.5");
  });

  it("says that 0 means no wait", async () => {
    const { dialog } = await gapped(0.5);
    expect(hints(dialog)[0]).toMatch(/^0 means no wait/);
  });

  it("is disabled, and says why, with no state/settings heard", async () => {
    const dialog = await settingsOpened(await joined());
    expect(field(dialog).disabled).toBe(true);
    expect(hints(dialog)).toContain("the layout has not said its settings");
  });

  it("publishes settings_wanted with the gap a commit changed it to", async () => {
    const { shell, dialog } = await gapped(0.8);
    await committed(shell, dialog, "1.2");
    expect(written()).toEqual([{ topic: SETTINGS_WANTED, payload: { point_gap: 1.2 } }]);
  });

  it("publishes nothing for a gap above 5 seconds, and says why", async () => {
    const { shell, dialog } = await gapped(0.8);
    await committed(shell, dialog, "7");
    expect(written()).toEqual([]);
    expect(hints(dialog)).toContain("the time between point commands is from 0 to 5 seconds");
  });

  it("drops the reason once a gap goes", async () => {
    const { shell, dialog } = await gapped(0.8);
    await committed(shell, dialog, "7");
    await committed(shell, dialog, "2");
    expect(written()).toEqual([{ topic: SETTINGS_WANTED, payload: { point_gap: 2 } }]);
    expect(hints(dialog).some((one) => one.startsWith("the time"))).toBe(false);
  });

  it("keeps a refused gap in the field with the reason, however often it is committed", async () => {
    const { shell, dialog } = await gapped(0.8);
    for (const _ of [1, 2]) {
      await committed(shell, dialog, "7");
      expect(field(dialog).value).toBe("7");
      expect(hints(dialog)).toContain("the time between point commands is from 0 to 5 seconds");
    }
    expect(written()).toEqual([]);
  });

  it("shows a new gap the row says over a refused one, and no reason", async () => {
    const { shell, dialog } = await gapped(0.8);
    await committed(shell, dialog, "7");
    await said(shell, STATE_SETTINGS, { at: 2, point_gap: 1.5 });
    expect(field(dialog).value).toBe("1.5");
    expect(hints(dialog).some((one) => one.startsWith("the time"))).toBe(false);
  });

  it("publishes a gap committed after a refused one, and drops the reason", async () => {
    const { shell, dialog } = await gapped(0.8);
    await committed(shell, dialog, "7");
    await committed(shell, dialog, "1.2");
    expect(written()).toEqual([{ topic: SETTINGS_WANTED, payload: { point_gap: 1.2 } }]);
    expect(hints(dialog).some((one) => one.startsWith("the time"))).toBe(false);
  });

  it("publishes nothing where the gap committed is the one the row says", async () => {
    const { shell, dialog } = await gapped(0.8);
    await committed(shell, dialog, "0.8");
    expect(written()).toEqual([]);
  });
});
