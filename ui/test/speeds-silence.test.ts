// @vitest-environment happy-dom

/**
 * The Settings dialog's Driving and Throttles tabs set the driver's speeds and the
 * throttle silence (#1134): their fields show `speeds` and
 * `throttle_silence` off `tc49/layout/state/settings` (#1130), and a commit
 * publishes `tc49/layout/settings_wanted` carrying that field alone (#1131).
 * What a commit sends is `speedChange`'s and `silenceChange`'s
 * (`settings.test.ts`); this is the dialog through the app.
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

/** A field by its tab and class: `driving` `clear` or `caution`, `throttles`
 *  `silence`. */
function field(dialog: TcSettings, tab: string, which: string): HTMLInputElement {
  return dialog.renderRoot.querySelector<HTMLInputElement>(`div.${tab} sl-input.${which}`)!;
}

/** What a tab says beneath its fields, hint by hint. */
function hints(dialog: TcSettings, tab: string): string[] {
  return [...dialog.renderRoot.querySelectorAll(`div.${tab} .hint`)].map((one) =>
    one.textContent!.trim(),
  );
}

/** `typed` committed in a field, as a change and not a keystroke. */
async function committed(
  shell: TcApp,
  dialog: TcSettings,
  tab: string,
  which: string,
  typed: string,
): Promise<void> {
  const input = field(dialog, tab, which);
  input.value = typed;
  input.dispatchEvent(new Event("sl-change"));
  await settled(shell);
}

/** The app joined, the layout saying its settings, the dialog up. */
async function heard(): Promise<{ shell: TcApp; dialog: TcSettings }> {
  const shell = await joined();
  await said(shell, STATE_SETTINGS, {
    at: 1,
    point_gap: 0.5,
    speeds: { clear: 0.6, caution: 0.3 },
    throttle_silence: 5,
  });
  return { shell, dialog: await settingsOpened(shell) };
}

describe("the Driving and Throttles tabs", () => {
  it("come after Points, in that order", async () => {
    const dialog = await settingsOpened(await joined());
    const tabs = [...dialog.renderRoot.querySelectorAll("sl-tab")].map((tab) =>
      tab.textContent!.trim(),
    );
    expect(tabs.slice(1, 4)).toEqual(["Points", "Driving", "Throttles"]);
  });

  it("show the speeds in percent and the silence in seconds state/settings says", async () => {
    const { dialog } = await heard();
    expect(field(dialog, "driving", "clear").value).toBe("60");
    expect(field(dialog, "driving", "caution").value).toBe("30");
    expect(field(dialog, "throttles", "silence").value).toBe("5");
    expect(field(dialog, "driving", "clear").disabled).toBe(false);
    expect(field(dialog, "throttles", "silence").disabled).toBe(false);
  });

  it("are disabled, and say why, with no state/settings heard", async () => {
    const dialog = await settingsOpened(await joined());
    expect(field(dialog, "driving", "clear").disabled).toBe(true);
    expect(field(dialog, "driving", "caution").disabled).toBe(true);
    expect(field(dialog, "throttles", "silence").disabled).toBe(true);
    expect(hints(dialog, "driving")).toContain("the layout has not said its settings");
    expect(hints(dialog, "throttles")).toContain("the layout has not said its settings");
  });

  it("say the silence applies whatever railroad is loaded", async () => {
    const { dialog } = await heard();
    expect(hints(dialog, "throttles")).toContain("This applies whatever railroad is loaded.");
  });

  it("publish the one speed a commit changed, as a fraction", async () => {
    const { shell, dialog } = await heard();
    await committed(shell, dialog, "driving", "caution", "45");
    expect(written()).toEqual([{ topic: SETTINGS_WANTED, payload: { speeds: { caution: 0.45 } } }]);
  });

  it("publish the silence a commit changed it to", async () => {
    const { shell, dialog } = await heard();
    await committed(shell, dialog, "throttles", "silence", "10");
    expect(written()).toEqual([{ topic: SETTINGS_WANTED, payload: { throttle_silence: 10 } }]);
  });

  it("publish nothing for a silence of 1 second, and say why", async () => {
    const { shell, dialog } = await heard();
    await committed(shell, dialog, "throttles", "silence", "1");
    expect(written()).toEqual([]);
    expect(hints(dialog, "throttles")).toContain(
      "how long a throttle may go silent is from 2 to 60 seconds",
    );
  });

  it.each(["0", "101"])("publish nothing for a speed of %s, and say why", async (typed) => {
    const { shell, dialog } = await heard();
    await committed(shell, dialog, "driving", "clear", typed);
    expect(written()).toEqual([]);
    expect(hints(dialog, "driving")).toContain("the speed at clear is from 1 to 100 percent");
  });

  it.each([
    ["driving", "clear", "101", "the speed at clear is from 1 to 100 percent"],
    ["driving", "caution", "101", "the speed at caution is from 1 to 100 percent"],
    ["throttles", "silence", "1", "how long a throttle may go silent is from 2 to 60 seconds"],
  ])(
    "keep a refused %s %s in the field with the reason, however often it is committed",
    async (tab, which, typed, reason) => {
      const { shell, dialog } = await heard();
      for (const _ of [1, 2]) {
        await committed(shell, dialog, tab, which, typed);
        expect(field(dialog, tab, which).value).toBe(typed);
        expect(hints(dialog, tab)).toContain(reason);
      }
      expect(written()).toEqual([]);
    },
  );

  it("drop a field's reason once it sends, keeping the other's", async () => {
    const { shell, dialog } = await heard();
    await committed(shell, dialog, "driving", "clear", "0");
    await committed(shell, dialog, "driving", "caution", "101");
    await committed(shell, dialog, "driving", "clear", "70");
    expect(written()).toEqual([{ topic: SETTINGS_WANTED, payload: { speeds: { clear: 0.7 } } }]);
    const said = hints(dialog, "driving");
    expect(said).not.toContain("the speed at clear is from 1 to 100 percent");
    expect(said).toContain("the speed at caution is from 1 to 100 percent");
  });

  it("publish nothing where the value committed is the one the row says", async () => {
    const { shell, dialog } = await heard();
    await committed(shell, dialog, "driving", "clear", "60");
    await committed(shell, dialog, "throttles", "silence", "5");
    expect(written()).toEqual([]);
  });

  it("follow the row as it changes", async () => {
    const { shell, dialog } = await heard();
    await said(shell, STATE_SETTINGS, {
      at: 2,
      point_gap: 0.5,
      speeds: { clear: 0.8, caution: 0.45 },
      throttle_silence: 10,
    });
    expect(field(dialog, "driving", "clear").value).toBe("80");
    expect(field(dialog, "driving", "caution").value).toBe("45");
    expect(field(dialog, "throttles", "silence").value).toBe("10");
  });
});
