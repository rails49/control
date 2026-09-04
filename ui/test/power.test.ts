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
 * A row reading `running` while the wait stands is a drain somebody
 * abandoned, and drops it; a row that says nothing about `moving` at all
 * never ends it, an older dispatcher's silence being no licence to cut.
 *
 * A DOM test because it crosses the band, the app and the run view's socket.
 * The session itself is `support/session.ts`, shared with the other suites.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-app.js";
import type { TcApp } from "../src/ui/tc-app.js";
import { band, settled } from "./support/shell.js";
import { brokering, joined, said, unbrokered, written } from "./support/session.js";

beforeEach(brokering);

afterEach(unbrokered);

const POWER_WANTED = "tc49/layout/power_wanted";
const RUN_WANTED = "tc49/dispatch/run_wanted";
const STATE_RUN = "tc49/dispatch/state/run";

/** ON, STOP and OFF, in the order the band draws them. */
function presses(shell: TcApp): HTMLButtonElement[] {
  return [...band(shell).renderRoot.querySelectorAll<HTMLButtonElement>("button.press")];
}

/** One of them, pressed, and everything it set in motion applied. */
async function press(shell: TcApp, which: 0 | 1 | 2): Promise<void> {
  presses(shell)[which]!.click();
  await settled(shell);
}

/** What the band's OFF is saying. */
function off(shell: TcApp): string {
  return presses(shell)[2]!.textContent!.trim();
}

describe("the presses that are one frame", () => {
  /** Returning to `on` releases nothing on its own, so an explicit GO still
   *  follows and this press asks the run for nothing (ADR-0041). */
  it("gives the track power and says nothing about the run", async () => {
    const shell = await joined();
    await press(shell, 0);
    expect(written()).toEqual([{ topic: POWER_WANTED, payload: { power: "on" } }]);
  });

  /** One click and no dialog: an emergency stop that asks "are you sure?" is
   *  not one, and `stopped` is cheap to recover from with the points still
   *  where you left them. */
  it("stops every locomotive on one click", async () => {
    const shell = await joined();
    await press(shell, 1);
    expect(written()).toEqual([{ topic: POWER_WANTED, payload: { power: "stopped" } }]);
  });
});

describe("OFF is the drain trigger", () => {
  it("asks the run to drain and leaves the supply alone", async () => {
    const shell = await joined();
    await said(shell, STATE_RUN, { run: "running" });

    await press(shell, 2);

    expect(written()).toEqual([{ topic: RUN_WANTED, payload: { run: "draining" } }]);
    expect(off(shell)).toBe("DRAINING…");
  });

  /** The word alone is not the wait's answer. A held run can be moving — a
   *  move already granted runs to its sensor — and cutting there strands it
   *  where no sensor will ever say it stopped (ADR-0062). */
  it("removes the supply once the run reads held with nothing moving", async () => {
    const shell = await joined();
    await said(shell, STATE_RUN, { run: "running", moving: true });
    await press(shell, 2);

    await said(shell, STATE_RUN, { run: "held", moving: true });
    expect(written()).toEqual([{ topic: RUN_WANTED, payload: { run: "draining" } }]);
    expect(off(shell)).toBe("DRAINING…");

    await said(shell, STATE_RUN, { run: "held", moving: false });

    expect(written()).toEqual([
      { topic: RUN_WANTED, payload: { run: "draining" } },
      { topic: POWER_WANTED, payload: { power: "off" } },
    ]);
    expect(off(shell)).toBe("OFF");
  });

  /** OFF asks for a drain from a held run too: it is the moving that decides,
   *  and a person's HOLD writes `held` with trains still rolling. */
  it("asks a held run to drain and waits while it is moving", async () => {
    const shell = await joined();
    await said(shell, STATE_RUN, { run: "held", moving: true });

    await press(shell, 2);
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
    const shell = await joined();
    await said(shell, STATE_RUN, { run: "held", moving: false });

    await press(shell, 2);

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
    const shell = await joined();
    await said(shell, STATE_RUN, { run: "running", moving: true });
    await press(shell, 2);

    await said(shell, STATE_RUN, { run: "held" });

    expect(written()).toEqual([{ topic: RUN_WANTED, payload: { run: "draining" } }]);
    expect(off(shell)).toBe("DRAINING…");
  });

  /** The same silence at the press: a run held by a dispatcher that says
   *  nothing about moving is asked to drain like any other, and the supply
   *  stays until a row says `moving: false`. */
  it("waits where a held run says nothing about moving", async () => {
    const shell = await joined();
    await said(shell, STATE_RUN, { run: "held" });

    await press(shell, 2);

    expect(written()).toEqual([{ topic: RUN_WANTED, payload: { run: "draining" } }]);
    expect(off(shell)).toBe("DRAINING…");
  });

  /** The railroad stays powered, and the button says why it is still there.
   *  A drain that never lands is exactly the case an abrupt cut would have
   *  hidden. */
  it("leaves the railroad powered while the run never settles", async () => {
    const shell = await joined();
    await said(shell, STATE_RUN, { run: "running", moving: true });
    await press(shell, 2);

    await said(shell, "tc49/dispatch/state/aspects", { aspects: {} });
    await said(shell, STATE_RUN, { run: "draining", moving: true });

    expect(written()).toEqual([{ topic: RUN_WANTED, payload: { run: "draining" } }]);
    expect(off(shell)).toBe("DRAINING…");
  });

  /** A run reading `running` while the wait stands is a drain somebody
   *  abandoned — a GO on this panel or on another — and the wait goes with
   *  it. Left standing, the HOLD that came hours later would cut the power
   *  out of a press the person had moved on from (ADR-0062). */
  it("drops the wait when the run is released", async () => {
    const shell = await joined();
    await said(shell, STATE_RUN, { run: "running", moving: true });
    await press(shell, 2);

    await said(shell, STATE_RUN, { run: "running", moving: true });
    await said(shell, STATE_RUN, { run: "held", moving: false });

    expect(written()).toEqual([{ topic: RUN_WANTED, payload: { run: "draining" } }]);
    expect(off(shell)).toBe("OFF");
  });

  /** The person has said what they want the supply to do, so the cut the
   *  earlier press would have made later is abandoned: a supply going away
   *  out of a press that has been moved on from is the surprise this button
   *  exists to avoid. */
  it("abandons the wait when ON is pressed instead", async () => {
    const shell = await joined();
    await said(shell, STATE_RUN, { run: "running", moving: true });
    await press(shell, 2);

    await press(shell, 0);
    await said(shell, STATE_RUN, { run: "held", moving: false });

    expect(written()).toEqual([
      { topic: RUN_WANTED, payload: { run: "draining" } },
      { topic: POWER_WANTED, payload: { power: "on" } },
    ]);
    expect(off(shell)).toBe("OFF");
  });
});
