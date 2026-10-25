// @vitest-environment happy-dom

/**
 * The band across the top, as the app draws it out of look's elements
 * (ADR-0073): which railroad is loaded, whether it holds unsaved edits, only
 * what a person would act on (#517), the gear, and track power.
 *
 * A DOM test through the app and its session, the band's facts
 * being what those two hand it. Pressing power is `power.test.ts`; what the
 * power control shows is `commands.test.ts`.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

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
import type { TcBandClock } from "../src/ui/tc-band-clock.js";
import {
  Broker,
  brokering,
  joined,
  RAILROAD,
  said,
  unbrokered,
  written,
} from "./support/session.js";

beforeEach(brokering);

afterEach(unbrokered);

const STATE_POWER = "tc49/layout/state/power";
const DEVICE_TRACK = "tc49/layout/state/device/track";
const STATE_CLOCK = "tc49/layout/state/clock";
const CLOCK_WANTED = "tc49/layout/clock_wanted";

/** What the band reads, as text, in the order it reads it: its readings and
 *  its chips. The gear and power are not text. */
function readings(shell: TcApp): string[] {
  return [...band(shell).querySelectorAll("look-reading, look-chip")].map((one) =>
    one.textContent!.trim(),
  );
}

describe("what the band names", () => {
  /** After look's mark, the UI by its name (org ADR-0019), then the railroad. */
  it("names the UI, control", async () => {
    expect(band(await joined()).ui).toBe("control");
  });

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
   *  deriving. */
  it("says nothing while everything is going right", async () => {
    const shell = await joined();
    await said(shell, STATE_POWER, { power: "on" });
    await said(shell, STATE_CLOCK, { at: 1, time: 36_000, speed_up: 1 });
    expect(readings(shell)).toEqual([]);
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

  /** The session clock is gone: the fast clock is where it was (ADR-0090). */
  it("runs no session clock", async () => {
    const shell = await joined();
    expect(band(shell).textContent).not.toContain("session");
  });
});

/** The railroad's fast clock on the band (ADR-0090, decision 6): drawn off
 *  `state/clock` alone, and set from its dialog with `clock_wanted`. */
describe("the fast clock", () => {
  /** 10:08:30 by the railroad's clock. */
  const TEN_PAST = 10 * 3600 + 8 * 60 + 30;

  function face(shell: TcApp): HTMLButtonElement | null {
    return bandClock(shell).renderRoot.querySelector<HTMLButtonElement>("button.face");
  }

  function bandClock(shell: TcApp): TcBandClock {
    return band(shell).querySelector("tc-band-clock")!;
  }

  async function ticking(time = TEN_PAST, speedUp = 1): Promise<TcApp> {
    const shell = await joined();
    await said(shell, STATE_CLOCK, { at: 1, time, speed_up: speedUp });
    await bandClock(shell).updateComplete;
    return shell;
  }

  /** The dialog, opened from the face. */
  async function opened(shell: TcApp): Promise<TcBandClock> {
    face(shell)!.click();
    const clock = bandClock(shell);
    await clock.updateComplete;
    return clock;
  }

  async function typed(clock: TcBandClock, field: string, value: string): Promise<void> {
    const input = clock.renderRoot.querySelector<HTMLInputElement>(`sl-input.${field}`)!;
    input.value = value;
    input.dispatchEvent(new Event("sl-input"));
    await clock.updateComplete;
  }

  function saveButton(clock: TcBandClock): HTMLButtonElement {
    return clock.renderRoot.querySelector<HTMLButtonElement>("sl-button.save")!;
  }

  it("draws a face with hour and minute hands and the time as its tooltip", async () => {
    const shell = await ticking();
    const drawn = face(shell)!;
    expect(drawn.title).toBe("10:08");
    const hands = drawn.querySelector("tc-clock")!;
    expect(hands.time).toBe(TEN_PAST);
  });

  it("says the speed-up beside the face where it is not 1", async () => {
    expect(face(await ticking())!.textContent!.trim()).toBe("");
    unbrokered();
    brokering();
    expect(face(await ticking(TEN_PAST, 8))!.textContent!.trim()).toBe("×8");
  });

  it("moves when state/clock does, and reads no clock of its own", async () => {
    const shell = await ticking();
    await said(shell, STATE_CLOCK, { at: 2, time: TEN_PAST + 60, speed_up: 1 });
    await bandClock(shell).updateComplete;
    expect(face(shell)!.title).toBe("10:09");
  });

  it("shows no clock before state/clock, with none loaded, or with the broker gone", async () => {
    expect(face(await joined())).toBeNull();

    const shell = await ticking();
    await said(shell, RAILROAD, { name: "" });
    await bandClock(shell).updateComplete;
    expect(face(shell)).toBeNull();

    await said(shell, RAILROAD, { name: "toy" });
    await said(shell, STATE_CLOCK, { at: 3, time: TEN_PAST, speed_up: 1 });
    await bandClock(shell).updateComplete;
    expect(face(shell)).not.toBeNull();
    Broker.last!.closes();
    await settled(shell);
    await bandClock(shell).updateComplete;
    expect(face(shell)).toBeNull();
  });

  it("opens a dialog with the time and the speed-up", async () => {
    const clock = await opened(await ticking(TEN_PAST, 8));
    expect(clock.renderRoot.querySelector("look-dialog")).not.toBeNull();
    const field = (name: string) =>
      clock.renderRoot.querySelector<HTMLInputElement>(`sl-input.${name}`)!.value;
    expect(field("time")).toBe("10:08");
    expect(field("speed-up")).toBe("8");
  });

  it("publishes only the speed-up where only it was changed", async () => {
    const shell = await ticking();
    const clock = await opened(shell);
    await typed(clock, "speed-up", "1.5");
    saveButton(clock).click();
    await settled(shell);
    expect(written()).toEqual([{ topic: CLOCK_WANTED, payload: { speed_up: 1.5 } }]);
    expect(clock.renderRoot.querySelector("look-dialog")).toBeNull();
  });

  it("publishes only the time where only it was changed", async () => {
    const shell = await ticking(TEN_PAST, 4);
    const clock = await opened(shell);
    await typed(clock, "time", "06:30");
    saveButton(clock).click();
    await settled(shell);
    expect(written()).toEqual([
      { topic: CLOCK_WANTED, payload: { time: 6 * 3600 + 30 * 60 } },
    ]);
  });

  it("publishes nothing where nothing was changed", async () => {
    const shell = await ticking();
    const clock = await opened(shell);
    saveButton(clock).click();
    await settled(shell);
    expect(written()).toEqual([]);
  });

  it("will not save a speed-up that is not above 0", async () => {
    const clock = await opened(await ticking());
    await typed(clock, "speed-up", "0");
    expect(saveButton(clock).disabled).toBe(true);
  });
});

/** Track power on the band: where the supply stands, and why the control is
 *  dead where it is (look#12). */
describe("track power", () => {
  it("shows where the supply stands", async () => {
    const shell = await joined();
    for (const state of ["on", "draining", "off"] as const) {
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
