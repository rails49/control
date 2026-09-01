// @vitest-environment happy-dom

/**
 * Commanding track power from the band, end to end through the app
 * (ADR-0051, #293): the press goes out on the socket the run view holds, on
 * `tc49/layout/power_wanted`, which `layout` is what answers.
 *
 * The one press that is not a single frame is OFF. It is the drain trigger
 * and never an immediate cut: it asks the run to drain, watches
 * `tc49/dispatch/state/run` reach `held`, and removes the supply only then.
 * An abrupt `off` would leave no point position trustworthy and strand
 * whatever was mid-transit; after a completed drain nothing is crossing,
 * nothing is committed, and every grant re-aligns.
 *
 * A DOM test because it crosses the band, the app and the run view's socket.
 * The session itself is `support/session.ts`, shared with the other suites.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-app.js";
import type { TcApp } from "../src/ui/tc-app.js";
import { band, settled } from "./support/shell.js";
import { bridging, joined, said, unbridged, written } from "./support/session.js";

beforeEach(bridging);

afterEach(unbridged);

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

  it("removes the supply once the run reads held", async () => {
    const shell = await joined();
    await said(shell, STATE_RUN, { run: "running" });
    await press(shell, 2);

    await said(shell, STATE_RUN, { run: "held" });

    expect(written()).toEqual([
      { topic: RUN_WANTED, payload: { run: "draining" } },
      { topic: POWER_WANTED, payload: { power: "off" } },
    ]);
    expect(off(shell)).toBe("OFF");
  });

  /** The dispatcher answering a held run with `held` publishes no frame, so
   *  the wait would never end — and there is nothing left to drain anyway:
   *  nothing is crossing and nothing is committed, which is the whole of what
   *  the wait waits for. */
  it("removes it at once where the run already reads held", async () => {
    const shell = await joined();
    await said(shell, STATE_RUN, { run: "held" });

    await press(shell, 2);

    expect(written()).toEqual([
      { topic: RUN_WANTED, payload: { run: "draining" } },
      { topic: POWER_WANTED, payload: { power: "off" } },
    ]);
  });

  /** The railroad stays powered, and the button says why it is still there.
   *  A drain that never lands is exactly the case an abrupt cut would have
   *  hidden. */
  it("leaves the railroad powered while the run never settles", async () => {
    const shell = await joined();
    await said(shell, STATE_RUN, { run: "running" });
    await press(shell, 2);

    await said(shell, "tc49/dispatch/state/aspects", { aspects: {} });
    await said(shell, STATE_RUN, { run: "running" });

    expect(written()).toEqual([{ topic: RUN_WANTED, payload: { run: "draining" } }]);
    expect(off(shell)).toBe("DRAINING…");
  });

  /** The person has said what they want the supply to do, so the cut the
   *  earlier press would have made later is abandoned: a supply going away
   *  out of a press that has been moved on from is the surprise this button
   *  exists to avoid. */
  it("abandons the wait when ON is pressed instead", async () => {
    const shell = await joined();
    await said(shell, STATE_RUN, { run: "running" });
    await press(shell, 2);

    await press(shell, 0);
    await said(shell, STATE_RUN, { run: "held" });

    expect(written()).toEqual([
      { topic: RUN_WANTED, payload: { run: "draining" } },
      { topic: POWER_WANTED, payload: { power: "on" } },
    ]);
    expect(off(shell)).toBe("OFF");
  });
});
