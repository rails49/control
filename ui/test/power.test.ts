// @vitest-environment happy-dom

/**
 * Commanding track power from the band, end to end through the app
 * (ADR-0051, #293): the press goes out on the socket the run view holds, on
 * `tc49/layout/power_wanted`, which `layout` is what answers.
 *
 * The one press that is not a single frame is OFF. It is the drain trigger
 * and never an immediate cut: it asks the run to drain, watches
 * `tc49/dispatch/state/run` reach `held` with `moving` false, and removes the
 * supply only then (ADR-0062, #408). An abrupt `off` would leave no point
 * position trustworthy and strand whatever was mid-transit; after a completed
 * drain nothing is crossing, nothing is committed, and every grant re-aligns.
 * The wait is dropped by news about the run word and not by news about
 * `moving`: a row whose word has *changed* to `running` is a drain somebody
 * abandoned, where one repeating the word the press was made against is the
 * drain still outstanding, whatever `moving` now says (#441). A row that says
 * nothing about `moving` at all never ends the wait, an older dispatcher's
 * silence being no licence to cut.
 *
 * The other direction is here too: what the hardware says back about the
 * supply on `tc49/layout/state/device/track`, which the band shows as a fault
 * (#602). It is the same band and the same railroad-wide supply, and the one
 * thing the presses cannot say — a station that cuts one district by itself
 * goes on reporting the railroad as powered
 * ([ADR-0050](../../docs/adr/0050-broken-hardware-is-reported-never-worked-around.md)).
 *
 * A DOM test because it crosses the band, the app and the run view's socket.
 * The session itself is `support/session.ts`, shared with the other suites.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-app.js";
import type { TcApp } from "../src/ui/tc-app.js";
import { chips, power, settled } from "./support/shell.js";
import { brokering, joined, said, unbrokered, written } from "./support/session.js";

beforeEach(brokering);

afterEach(unbrokered);

const POWER_WANTED = "tc49/layout/power_wanted";
const RUN_WANTED = "tc49/dispatch/run_wanted";
const STATE_RUN = "tc49/dispatch/state/run";
const STATE_POWER = "tc49/layout/state/power";
/** What the hardware reports about the supply it drives, and what `layout`
 *  asks of it: two rows of the device vocabulary, and only the observed one
 *  carries a reason (BUS.md). */
const DEVICE_TRACK = "tc49/layout/state/device/track";
const WANTED_TRACK = "tc49/layout/state/wanted/track";

/** A joined session whose supply stands at `power`: the control is dead until
 *  the station has said. */
async function powered(power: "on" | "off" = "on"): Promise<TcApp> {
  const shell = await joined();
  await said(shell, STATE_POWER, { power });
  return shell;
}

/** The power toggle or the stop sign, pressed, and everything it set in motion
 *  applied. The toggle asks for `off` while the supply is on and for `on`
 *  otherwise. */
async function pressing(shell: TcApp, which: "toggle" | "stop"): Promise<void> {
  power(shell).shadowRoot!.querySelector<HTMLElement>(which === "toggle" ? ".power" : ".stop")!.click();
  await settled(shell);
}

/** Whether the band's power control says the drain is outstanding. */
function draining(shell: TcApp): boolean {
  return power(shell).state === "draining";
}

/** What the band says is wrong with the supply, `null` while it says
 *  nothing. */
function fault(shell: TcApp): string | null {
  return chips(shell)[0] ?? null;
}

describe("the presses that are one frame", () => {
  /** Returning to `on` releases nothing on its own, so an explicit GO still
   *  follows and this press asks the run for nothing (ADR-0041). */
  it("gives the track power and says nothing about the run", async () => {
    const shell = await powered("off");
    await pressing(shell, "toggle");
    expect(written()).toEqual([{ topic: POWER_WANTED, payload: { power: "on" } }]);
  });

  /** One click and no dialog: an emergency stop that asks "are you sure?" is
   *  not one, and `stopped` is cheap to recover from with the points still
   *  where you left them. */
  it("stops every locomotive on one click", async () => {
    const shell = await powered();
    await pressing(shell, "stop");
    expect(written()).toEqual([{ topic: POWER_WANTED, payload: { power: "stopped" } }]);
  });
});

describe("OFF is the drain trigger", () => {
  it("asks the run to drain and leaves the supply alone", async () => {
    const shell = await powered();
    await said(shell, STATE_RUN, { run: "running" });

    await pressing(shell, "toggle");

    expect(written()).toEqual([{ topic: RUN_WANTED, payload: { run: "draining" } }]);
    expect(draining(shell)).toBe(true);
  });

  /** The word alone is not the wait's answer. A held run can be moving — a
   *  move already granted runs to its sensor — and cutting there strands it
   *  where no sensor will ever say it stopped (ADR-0062). */
  it("removes the supply once the run reads held with nothing moving", async () => {
    const shell = await powered();
    await said(shell, STATE_RUN, { run: "running", moving: true });
    await pressing(shell, "toggle");

    await said(shell, STATE_RUN, { run: "held", moving: true });
    expect(written()).toEqual([{ topic: RUN_WANTED, payload: { run: "draining" } }]);
    expect(draining(shell)).toBe(true);

    await said(shell, STATE_RUN, { run: "held", moving: false });

    expect(written()).toEqual([
      { topic: RUN_WANTED, payload: { run: "draining" } },
      { topic: POWER_WANTED, payload: { power: "off" } },
    ]);
    expect(draining(shell)).toBe(false);
  });

  /** OFF asks for a drain from a held run too: it is the moving that decides,
   *  and a person's HOLD writes `held` with trains still rolling. */
  it("asks a held run to drain and waits while it is moving", async () => {
    const shell = await powered();
    await said(shell, STATE_RUN, { run: "held", moving: true });

    await pressing(shell, "toggle");
    expect(written()).toEqual([{ topic: RUN_WANTED, payload: { run: "draining" } }]);

    await said(shell, STATE_RUN, { run: "held", moving: false });

    expect(written()).toEqual([
      { topic: RUN_WANTED, payload: { run: "draining" } },
      { topic: POWER_WANTED, payload: { power: "off" } },
    ]);
  });

  /** The dispatcher answering a held run with `held` publishes no frame, so
   *  the wait would never end — and there is nothing left to drain anyway:
   *  the run is held and nothing is moving, which is the whole of what the
   *  wait waits for. */
  it("removes it at once where the run is held and nothing moves", async () => {
    const shell = await powered();
    await said(shell, STATE_RUN, { run: "held", moving: false });

    await pressing(shell, "toggle");

    expect(written()).toEqual([
      { topic: RUN_WANTED, payload: { run: "draining" } },
      { topic: POWER_WANTED, payload: { power: "off" } },
    ]);
  });

  /** An older dispatcher publishes the word alone, and a row that says
   *  nothing about what is under way never lets this button cut: the wait
   *  goes on standing, which costs a word on a button, where cutting on it
   *  would cost a train stranded where no sensor will ever say it stopped. */
  it("never cuts on a row that says nothing about moving", async () => {
    const shell = await powered();
    await said(shell, STATE_RUN, { run: "running", moving: true });
    await pressing(shell, "toggle");

    await said(shell, STATE_RUN, { run: "held" });

    expect(written()).toEqual([{ topic: RUN_WANTED, payload: { run: "draining" } }]);
    expect(draining(shell)).toBe(true);
  });

  /** The same silence at the press: a run held by a dispatcher that says
   *  nothing about moving is asked to drain like any other, and the supply
   *  stays until a row says `moving: false`. */
  it("waits where a held run says nothing about moving", async () => {
    const shell = await powered();
    await said(shell, STATE_RUN, { run: "held" });

    await pressing(shell, "toggle");

    expect(written()).toEqual([{ topic: RUN_WANTED, payload: { run: "draining" } }]);
    expect(draining(shell)).toBe(true);
  });

  /** The railroad stays powered, and the button says why it is still there.
   *  A drain that never lands is exactly the case an abrupt cut would have
   *  hidden. */
  it("leaves the railroad powered while the run never settles", async () => {
    const shell = await powered();
    await said(shell, STATE_RUN, { run: "running", moving: true });
    await pressing(shell, "toggle");

    await said(shell, "tc49/dispatch/state/aspects", { aspects: {} });
    await said(shell, STATE_RUN, { run: "draining", moving: true });

    expect(written()).toEqual([{ topic: RUN_WANTED, payload: { run: "draining" } }]);
    expect(draining(shell)).toBe(true);
  });

  /** The run word changing back to `running` while the wait stands is a drain
   *  somebody abandoned — a GO on this panel or on another — and the wait goes
   *  with it. Left standing, the HOLD that came hours later would cut the
   *  power out of a press the person had moved on from (ADR-0062). The
   *  dispatcher answers the drain before anybody can release it, so the word
   *  leaves `running` on the way: a `running` row twice over is a sequence no
   *  dispatcher publishes, it comparing the whole row before it writes. */
  it("drops the wait when the run is released", async () => {
    const shell = await powered();
    await said(shell, STATE_RUN, { run: "running", moving: true });
    await pressing(shell, "toggle");

    await said(shell, STATE_RUN, { run: "draining", moving: true });
    await said(shell, STATE_RUN, { run: "running", moving: true });
    expect(draining(shell)).toBe(false);

    await said(shell, STATE_RUN, { run: "held", moving: false });

    expect(written()).toEqual([{ topic: RUN_WANTED, payload: { run: "draining" } }]);
    expect(draining(shell)).toBe(false);
  });

  /** The last train arriving republishes the run word the press was made
   *  against, `moving` having moved under it (#406): the drain is still
   *  outstanding, and reading the value rather than the change would drop the
   *  wait here and leave the railroad powered with nothing on screen saying
   *  so. */
  it("keeps the wait where the last train arrives under a running run", async () => {
    const shell = await powered();
    await said(shell, STATE_RUN, { run: "running", moving: true });
    await pressing(shell, "toggle");

    await said(shell, STATE_RUN, { run: "running", moving: false });
    expect(written()).toEqual([{ topic: RUN_WANTED, payload: { run: "draining" } }]);
    expect(draining(shell)).toBe(true);

    await said(shell, STATE_RUN, { run: "held", moving: false });

    expect(written()).toEqual([
      { topic: RUN_WANTED, payload: { run: "draining" } },
      { topic: POWER_WANTED, payload: { power: "off" } },
    ]);
    expect(draining(shell)).toBe(false);
  });

  /** `draining` with nothing moving is the drain answered and not the drain
   *  landed: the dispatcher writes the `held` this button waits for itself, at
   *  the first moment no train is left, and until it does there is a run word
   *  that still commits nothing of its own. */
  it("keeps the wait where the drain is answered with nothing moving", async () => {
    const shell = await powered();
    await said(shell, STATE_RUN, { run: "running", moving: true });
    await pressing(shell, "toggle");

    await said(shell, STATE_RUN, { run: "draining", moving: false });

    expect(written()).toEqual([{ topic: RUN_WANTED, payload: { run: "draining" } }]);
    expect(draining(shell)).toBe(true);
  });

  /** The person has said what they want the supply to do, so the cut the
   *  earlier press would have made later is abandoned: a supply going away
   *  out of a press that has been moved on from is the surprise this button
   *  exists to avoid. */
  it("abandons the wait when ON is pressed instead", async () => {
    const shell = await powered();
    await said(shell, STATE_RUN, { run: "running", moving: true });
    await pressing(shell, "toggle");

    await pressing(shell, "toggle");
    await said(shell, STATE_RUN, { run: "held", moving: false });

    expect(written()).toEqual([
      { topic: RUN_WANTED, payload: { run: "draining" } },
      { topic: POWER_WANTED, payload: { power: "on" } },
    ]);
    expect(draining(shell)).toBe(false);
  });
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
