// @vitest-environment happy-dom

/**
 * The Settings dialog's Automatic driving and Throttles sections set the driver's speeds
 * and the throttle silence (#1134): their fields show `speeds` and
 * `throttle_silence` off `tc49/layout/state/settings` (#1130), and a commit
 * publishes `tc49/layout/settings_wanted` carrying that field alone (#1131).
 * The section's checkboxes do the same for `short_blocks` (#1288) and
 * `without_sensors` (#1322).
 * What a commit sends and refuses is `settingChange`'s (`settings.test.ts`);
 * this is the dialog through the app.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-app.js";
import type { TcApp } from "../src/ui/tc-app.js";
import type { TcSettings } from "../src/ui/tc-settings.js";
import { sections, settingsOpened, settled } from "./support/shell.js";
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
    short_blocks: false,
    without_sensors: false,
  });
  return { shell, dialog: await settingsOpened(shell) };
}

/** The Automatic driving section's checkbox for `short_blocks`. */
function shortBlocks(dialog: TcSettings): HTMLInputElement {
  return dialog.renderRoot.querySelector<HTMLInputElement>("div.driving sl-checkbox.short")!;
}

/** The Automatic driving section's checkbox for `without_sensors`. */
function withoutSensors(dialog: TcSettings): HTMLInputElement {
  return dialog.renderRoot.querySelector<HTMLInputElement>("div.driving sl-checkbox.sensorless")!;
}

describe("the Automatic driving and Throttles sections", () => {
  it("are Automatic driving after Points in Railroad, and Throttles first in Installation", async () => {
    const dialog = await settingsOpened(await joined());
    expect(sections(dialog, "railroad").slice(1, 3)).toEqual([
      "Points (turnouts and slips)",
      "Automatic driving",
    ]);
    expect(sections(dialog, "installation")[0]).toBe("Throttles");
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

describe("the Automatic driving section's short_blocks checkbox (#1288)", () => {
  it("shows short_blocks off state/settings, and can be ticked", async () => {
    const { dialog } = await heard();
    expect(shortBlocks(dialog).checked).toBe(false);
    expect(shortBlocks(dialog).disabled).toBe(false);
  });

  it("publishes a tick as short_blocks alone", async () => {
    const { shell, dialog } = await heard();
    const wanted: unknown[] = [];
    dialog.addEventListener("settings-wanted", (event) =>
      wanted.push((event as CustomEvent).detail),
    );
    const box = shortBlocks(dialog);
    box.checked = true;
    box.dispatchEvent(new Event("sl-change"));
    await settled(shell);
    expect(wanted).toEqual([{ short_blocks: true }]);
    expect(written()).toEqual([{ topic: SETTINGS_WANTED, payload: { short_blocks: true } }]);
  });

  it("is dead while state/settings does not say it", async () => {
    const shell = await joined();
    await said(shell, STATE_SETTINGS, {
      at: 1,
      point_gap: 0.5,
      speeds: { clear: 0.6, caution: 0.3 },
      throttle_silence: 5,
    });
    const dialog = await settingsOpened(shell);
    expect(shortBlocks(dialog).disabled).toBe(true);
    expect(dialog.renderRoot.querySelector("div.driving p.unheard")).not.toBeNull();
  });
});

describe("the Automatic driving section's without_sensors checkbox (#1322)", () => {
  it("shows without_sensors off state/settings, and can be ticked", async () => {
    const { dialog } = await heard();
    expect(withoutSensors(dialog).checked).toBe(false);
    expect(withoutSensors(dialog).disabled).toBe(false);
    expect(withoutSensors(dialog).textContent).toContain("Run without sensors");
  });

  it("publishes a tick as without_sensors alone", async () => {
    const { shell, dialog } = await heard();
    const wanted: unknown[] = [];
    dialog.addEventListener("settings-wanted", (event) =>
      wanted.push((event as CustomEvent).detail),
    );
    const box = withoutSensors(dialog);
    box.checked = true;
    box.dispatchEvent(new Event("sl-change"));
    await settled(shell);
    expect(wanted).toEqual([{ without_sensors: true }]);
    expect(written()).toEqual([{ topic: SETTINGS_WANTED, payload: { without_sensors: true } }]);
  });

  it("is dead while state/settings does not say it", async () => {
    const shell = await joined();
    await said(shell, STATE_SETTINGS, {
      at: 1,
      point_gap: 0.5,
      speeds: { clear: 0.6, caution: 0.3 },
      throttle_silence: 5,
      short_blocks: false,
    });
    const dialog = await settingsOpened(shell);
    expect(withoutSensors(dialog).disabled).toBe(true);
    expect(shortBlocks(dialog).disabled).toBe(false);
  });
});
