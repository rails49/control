// @vitest-environment happy-dom

/**
 * The Settings dialog's Sensors tab sets the sensor silence (#1149): its one
 * field shows `sensor_silence` off `tc49/layout/state/settings`, and a commit
 * publishes `tc49/layout/settings_wanted` carrying that field alone. What a
 * commit sends is `sensorSilenceChange`'s (`settings.test.ts`); this is the
 * dialog through the app.
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
const UNHEARD = "the layout has not said its settings";

function row(sensorSilence: number): Record<string, unknown> {
  return {
    at: 1,
    point_gap: 0.5,
    speeds: { clear: 0.6, caution: 0.3 },
    throttle_silence: 5,
    sensor_silence: sensorSilence,
  };
}

function field(dialog: TcSettings): HTMLInputElement {
  return dialog.renderRoot.querySelector<HTMLInputElement>("div.sensors sl-input.silence")!;
}

function hints(dialog: TcSettings): string[] {
  return [...dialog.renderRoot.querySelectorAll("div.sensors .hint")].map((one) =>
    one.textContent!.trim(),
  );
}

async function committed(shell: TcApp, dialog: TcSettings, typed: string): Promise<void> {
  const input = field(dialog);
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

  it("is disabled, and says why, with no state/settings heard", async () => {
    const dialog = await settingsOpened(await joined());
    expect(field(dialog).disabled).toBe(true);
    expect(hints(dialog)).toContain(UNHEARD);
  });

  it("says the silence applies whatever railroad is loaded", async () => {
    const { dialog } = await heard();
    expect(hints(dialog)).toContain("This applies whatever railroad is loaded.");
  });

  it("publishes a commit as one sensor_silence field", async () => {
    const { shell, dialog } = await heard();
    await committed(shell, dialog, "10");
    expect(written()).toEqual([{ topic: SETTINGS_WANTED, payload: { sensor_silence: 10 } }]);
  });

  it("follows the row as it changes", async () => {
    const { shell, dialog } = await heard();
    await said(shell, STATE_SETTINGS, row(10));
    expect(field(dialog).value).toBe("10");
  });

  it("publishes nothing for a silence of 1 second, keeping it beside the reason", async () => {
    const { shell, dialog } = await heard();
    for (const _ of [1, 2]) {
      await committed(shell, dialog, "1");
      expect(field(dialog).value).toBe("1");
      expect(hints(dialog)).toContain("how long a sensor may go unheard is from 2 to 60 seconds");
    }
    expect(written()).toEqual([]);
  });

  it("publishes nothing where the value committed is the one the row says", async () => {
    const { shell, dialog } = await heard();
    await committed(shell, dialog, "3");
    expect(written()).toEqual([]);
  });

  it("is left alone by a refusal in the Throttles tab", async () => {
    const { shell, dialog } = await heard();
    const silence = dialog.renderRoot.querySelector<HTMLInputElement>(
      "div.throttles sl-input.silence",
    )!;
    silence.value = "1";
    silence.dispatchEvent(new Event("sl-change"));
    await settled(shell);
    expect(hints(dialog)).not.toContain(
      "how long a sensor may go unheard is from 2 to 60 seconds",
    );
    expect(field(dialog).value).toBe("3");
  });
});
