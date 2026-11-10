// @vitest-environment happy-dom

/**
 * The Settings dialog's Sensors tab sets the sensor silence (#1149) and the
 * arrival allowance (#1192): each field shows its value off
 * `tc49/layout/state/settings`, and a commit publishes
 * `tc49/layout/settings_wanted` carrying that field alone. What a
 * commit sends and refuses is `settingChange`'s (`settings.test.ts`); this is
 * the dialog through the app.
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

function row(sensorSilence: number): Record<string, unknown> {
  return {
    at: 1,
    point_gap: 0.5,
    speeds: { clear: 0.6, caution: 0.3 },
    throttle_silence: 5,
    sensor_silence: sensorSilence,
    arrival_allowance: 60,
  };
}

function field(dialog: TcSettings, kind = "silence"): HTMLInputElement {
  return dialog.renderRoot.querySelector<HTMLInputElement>(`div.sensors sl-input.${kind}`)!;
}

async function committed(
  shell: TcApp,
  dialog: TcSettings,
  typed: string,
  kind = "silence",
): Promise<void> {
  const input = field(dialog, kind);
  input.value = typed;
  input.dispatchEvent(new Event("sl-change"));
  await settled(shell);
}

/** The app joined, the layout saying its settings, the dialog up. */
async function heard(): Promise<{ shell: TcApp; dialog: TcSettings }> {
  const shell = await joined();
  await said(shell, STATE_SETTINGS, row(3));
  return { shell, dialog: await settingsOpened(shell) };
}

describe("the Sensors tab", () => {
  it("comes after Throttles", async () => {
    const dialog = await settingsOpened(await joined());
    const tabs = [...dialog.renderRoot.querySelectorAll("sl-tab")].map((tab) =>
      tab.textContent!.trim(),
    );
    expect(tabs.indexOf("Sensors")).toBe(tabs.indexOf("Throttles") + 1);
  });

  it("shows the silence state/settings says", async () => {
    const { dialog } = await heard();
    expect(field(dialog).value).toBe("3");
    expect(field(dialog).disabled).toBe(false);
  });

  it("publishes a commit as one sensor_silence field", async () => {
    const { shell, dialog } = await heard();
    await committed(shell, dialog, "10");
    expect(written()).toEqual([{ topic: SETTINGS_WANTED, payload: { sensor_silence: 10 } }]);
  });

  it("shows the arrival allowance state/settings says, after the silence", async () => {
    const { dialog } = await heard();
    const inputs = [...dialog.renderRoot.querySelectorAll("div.sensors sl-input")];
    expect(inputs.map((input) => input.className)).toEqual(["silence", "allowance"]);
    expect(field(dialog, "allowance").value).toBe("60");
    expect(field(dialog, "allowance").disabled).toBe(false);
  });

  it("publishes a commit as one arrival_allowance field", async () => {
    const { shell, dialog } = await heard();
    await committed(shell, dialog, "90", "allowance");
    expect(written()).toEqual([{ topic: SETTINGS_WANTED, payload: { arrival_allowance: 90 } }]);
  });
});
