// @vitest-environment happy-dom

/**
 * Commanding power from the band, end to end through the app (ADR-0078,
 * #828): the press goes out on the socket the session holds, on
 * `tc49/layout/power_wanted`, which `layout` is what answers. Every press is
 * one frame. The toggle asks for `on` from `off` and from `draining`, and for
 * `draining` from `on`; the stop sign asks for `off` at once, the emergency
 * stop. The page keeps no wait for the drain: `layout` switches the supply
 * off once nothing is moving, and the toggle shows `state/power` as `layout`
 * says it.
 *
 * The other direction is here too: what the hardware says back about the
 * supply on `tc49/layout/state/device/track`, which the band shows as a fault
 * (#602). It is the same band and the same railroad-wide supply, and the one
 * thing the presses cannot say — a station that cuts one district by itself
 * goes on reporting the railroad as powered
 * ([ADR-0050](../../docs/adr/0050-broken-hardware-is-reported-never-worked-around.md)).
 *
 * A DOM test because it crosses the band, the app and the session's socket.
 * The session itself is `support/session.ts`, shared with the other suites.
 */

import { press } from "@rails49/look/testing";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-app.js";
import type { TcApp } from "../src/ui/tc-app.js";
import { chips, power, settled } from "./support/shell.js";
import { brokering, joined, said, unbrokered, written } from "./support/session.js";

beforeEach(brokering);

afterEach(unbrokered);

const POWER_WANTED = "tc49/layout/power_wanted";
const STATE_POWER = "tc49/layout/state/power";
/** What the hardware reports about the supply it drives, and what `layout`
 *  asks of it: two rows of the device vocabulary, and only the observed one
 *  carries a reason (BUS.md). */
const DEVICE_TRACK = "tc49/layout/state/device/track";
const WANTED_TRACK = "tc49/layout/state/wanted/track";

/** A joined session whose power stands at `power`: the control is dead until
 *  the station has said. */
async function powered(
  power: "on" | "draining" | "off" = "on",
): Promise<TcApp> {
  const shell = await joined();
  await said(shell, STATE_POWER, { power });
  return shell;
}

/** The power toggle or the stop sign, pressed, and everything it set in motion
 *  applied. */
async function pressing(shell: TcApp, which: "toggle" | "stop"): Promise<void> {
  press(power(shell), which);
  await settled(shell);
}

/** What the band says is wrong with the supply, `null` while it says
 *  nothing. */
function fault(shell: TcApp): string | null {
  return chips(shell)[0] ?? null;
}

describe("the power toggle", () => {
  /** One press turns the railroad on (ADR-0078). */
  it("asks for on from off", async () => {
    const shell = await powered("off");
    await pressing(shell, "toggle");
    expect(written()).toEqual([{ topic: POWER_WANTED, payload: { power: "on" } }]);
  });

  /** A person asking for `on` during a drain ends it. */
  it("asks for on from draining", async () => {
    const shell = await powered("draining");
    await pressing(shell, "toggle");
    expect(written()).toEqual([
      { topic: POWER_WANTED, payload: { power: "on" } },
    ]);
  });

  /** The drain, and nothing more: `layout` switches the supply off once
   *  nothing is moving, and the page waits for nothing. */
  it("asks for draining from on", async () => {
    const shell = await powered("on");
    await pressing(shell, "toggle");
    expect(written()).toEqual([
      { topic: POWER_WANTED, payload: { power: "draining" } },
    ]);
  });

  /** What it shows is `state/power`, each of the three, and not the press. */
  it("shows the three states as layout says them", async () => {
    const shell = await powered("on");
    expect(power(shell).state).toBe("on");
    await pressing(shell, "toggle");
    expect(power(shell).state).toBe("on");
    for (const state of ["draining", "off", "on"] as const) {
      await said(shell, STATE_POWER, { power: state });
      expect(power(shell).state).toBe(state);
    }
  });
});

describe("the stop sign", () => {
  /** One click and no dialog: an emergency stop that asks "are you sure?" is
   *  not one. It is `off` at once, without a drain (ADR-0078). */
  it.each(["on", "draining", "off"] as const)(
    "asks for off from %s",
    async (from) => {
      const shell = await powered(from);
      await pressing(shell, "stop");
      expect(written()).toEqual([
        { topic: POWER_WANTED, payload: { power: "off" } },
      ]);
    },
  );
});

/**
 * What the hardware says is wrong with the supply, read off the row it says it
 * on (#602). A district reaches no topic of its own, so a trip the station cut
 * itself is named in the free text of `device/track` and nowhere else — and
 * with the other districts still powered that frame reads `power: on`, which
 * is a railroad with nothing wrong with it to anything reading `power` alone
 * (ADR-0050).
 */
describe("what the hardware says about the supply", () => {
  /** The whole of what says a trip is standing, so the band says it where the
   *  supply is reading as it would with nothing wrong. */
  it("shows a trip as a fault while the rails have power", async () => {
    const shell = await powered();
    await said(shell, "tc49/layout/state/power", { power: "on" });
    await said(shell, DEVICE_TRACK, { power: "on", reason: "district B tripped" });

    expect(fault(shell)).toBe("district B tripped");
    expect(power(shell).state).toBe("on");
  });

  /** And where the supply is gone: a dark railroad reads as one at rest since
   *  #585, so why it is dark is said here or not at all. */
  it("shows one with the supply gone as well", async () => {
    const shell = await powered();
    await said(shell, "tc49/layout/state/power", { power: "off" });
    await said(shell, DEVICE_TRACK, { power: "off", reason: "no station on /dev/ttyACM0" });

    expect(fault(shell)).toBe("no station on /dev/ttyACM0");
  });

  /** The trip holds until somebody resets it, and the frame that stops naming
   *  it is the hardware saying it is over. */
  it("clears the fault on a frame that carries no reason", async () => {
    const shell = await powered();
    await said(shell, DEVICE_TRACK, { power: "on", reason: "district B tripped" });
    await said(shell, DEVICE_TRACK, { power: "on" });

    expect(fault(shell)).toBeNull();
  });

  /** A press writes `power_wanted` and `layout` answers by writing the
   *  desired row, which carries no reason: the two rows share a leaf, and a
   *  page that read them as one would clear the trip on the next press. */
  it("is untouched by what the supply is asked for", async () => {
    const shell = await powered("off");
    await said(shell, DEVICE_TRACK, { power: "on", reason: "district B tripped" });
    await pressing(shell, "toggle");
    await said(shell, WANTED_TRACK, { power: "on" });

    expect(fault(shell)).toBe("district B tripped");
  });

  it("says nothing while the hardware reports nothing wrong", async () => {
    const shell = await powered();
    await said(shell, DEVICE_TRACK, { power: "on" });

    expect(fault(shell)).toBeNull();
  });
});
