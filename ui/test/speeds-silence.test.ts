// @vitest-environment happy-dom

/**
 * The Settings dialog's Driving and Throttles tabs set the driver's speeds and the
 * throttle silence (#1134): their fields show `speeds` and
 * `throttle_silence` off `tc49/layout/state/settings` (#1130), and a commit
 * publishes `tc49/layout/settings_wanted` carrying that field alone (#1131).
 * What a commit sends and refuses is `settingChange`'s (`settings.test.ts`);
 * this is the dialog through the app.
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

  it.each([
    ["driving", "clear", "70", { speeds: { clear: 0.7 } }],
    ["driving", "caution", "45", { speeds: { caution: 0.45 } }],
    ["throttles", "silence", "10", { throttle_silence: 10 }],
  ])("publish a commit in %s %s as that one field", async (tab, which, typed, payload) => {
    const { shell, dialog } = await heard();
    await committed(shell, dialog, tab, which, typed);
    expect(written()).toEqual([{ topic: SETTINGS_WANTED, payload }]);
  });
});
