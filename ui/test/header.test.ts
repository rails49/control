// @vitest-environment happy-dom

/**
 * The band across the top, as the app draws it out of look's elements
 * (ADR-0073): which railroad is loaded, whether it holds unsaved edits, only
 * what a person would act on (#517), the gear, and track power.
 *
 * A DOM test through the app and the run view's session, the band's facts
 * being what those two hand it. Pressing power is `power.test.ts`; what the
 * power control shows is `commands.test.ts`.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../src/ui/tc-app.js";
import type { TcApp } from "../src/ui/tc-app.js";
import {
  band,
  chips,
  edited,
  mounted,
  named,
  power,
  serving,
  session,
  settingsOpened,
  settled,
} from "./support/shell.js";
import { brokering, joined, said, unbrokered } from "./support/session.js";

beforeEach(brokering);

afterEach(unbrokered);

const STATE_POWER = "tc49/layout/state/power";
const DEVICE_TRACK = "tc49/layout/state/device/track";

/** What the band reads, as text, in the order it reads it: its readings and
 *  its chips. The gear and power are not text. */
function readings(shell: TcApp): string[] {
  return [...band(shell).querySelectorAll("look-reading, look-chip")].map((one) =>
    one.textContent!.trim(),
  );
}

describe("what the band names", () => {
  it("names the railroad that is loaded", async () => {
    expect(named(await joined())).toBe("toy");
  });

  it("says plainly when none is", async () => {
    expect(named(await mounted("run"))).toBe("no railroad loaded");
  });

  /** Loading another is the settings dialog's, behind the gear (ADR-0072). */
  it("is text and not a press", async () => {
    const shell = await joined();
    expect(band(shell).querySelector("look-about")!.pressable).toBe(false);
  });

  it("marks a drawing with edits in it, and nothing once it is saved", async () => {
    const shell = await joined("edit");
    const about = band(shell).querySelector("look-about")!;
    expect(about.detail).toBe("");

    session(shell).place("block", [8, 0]);
    edited(shell);
    await settled(shell);
    expect(about.detail).toBe("unsaved");
  });
});

describe("the way into settings", () => {
  it("opens the settings dialog from the gear", async () => {
    const shell = await mounted("run");
    expect((await settingsOpened(shell)).open).toBe(true);
  });
});

describe("what the band says", () => {
  /** Nothing that is going right reads here (#517). The ordinary case: a
   *  session joined, the broker answering, the rails live, the drawing
   *  deriving. Only the session clock is drawn. */
  it("says nothing but the session clock while everything is going right", async () => {
    const shell = await joined();
    await said(shell, STATE_POWER, { power: "on" });
    expect(readings(shell)).toEqual(["session 00:00"]);
  });

  /** A fault reads as a chip, cut short where it is long, so the whole
   *  sentence is its title. */
  it("shows what the hardware says is wrong as a chip with the sentence as its title", async () => {
    const shell = await joined();
    await said(shell, DEVICE_TRACK, { power: "on", reason: "district B tripped" });
    expect(chips(shell)).toEqual(["district B tripped"]);
    expect(band(shell).querySelector("look-chip")!.title).toBe("district B tripped");
  });

  it("shows the store not answering as a chip", async () => {
    serving({ broken: new Error("connection refused") });
    const shell = await mounted("run");
    expect(chips(shell)).toHaveLength(1);
    expect(chips(shell)[0]).toContain("the store is not answering");
  });

  /** The session clock: elapsed time on the page's own clock, until a fast
   *  clock derived from the railroad's configuration replaces it (ADR-0047).
   *  A view reads a clock for scenery, never for control (ADR-0009). */
  it("runs a session clock while a session is joined", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "Date"] });
    try {
      const shell = await joined();
      expect(readings(shell)).toContain("session 00:00");
      vi.advanceTimersByTime(65_000);
      await settled(shell);
      expect(readings(shell)).toContain("session 01:05");
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows no session clock with no session joined", async () => {
    const shell = await mounted("run");
    expect(readings(shell).some((one) => one.startsWith("session"))).toBe(false);
  });
});

/** Track power on the band: where the supply stands, and why the control is
 *  dead where it is (look#12). */
describe("track power", () => {
  it("shows where the supply stands", async () => {
    const shell = await joined();
    for (const state of ["on", "stopped", "off"] as const) {
      await said(shell, STATE_POWER, { power: state });
      expect(power(shell).state).toBe(state);
      expect(power(shell).reason).toBe("");
    }
  });

  it("is dead before the station has said", async () => {
    const shell = await joined();
    expect(power(shell).state).toBe("off");
    expect(power(shell).reason).toBe("Waiting for the station");
  });

  /** A new box has no railroad loaded and no session to join; the control
   *  is there, and dead. */
  it("is dead with no session joined", async () => {
    const shell = await mounted("run");
    expect(power(shell).reason).toBe("Waiting for the station");
  });
});
