// @vitest-environment happy-dom

/**
 * The station clock on the throttle's cab (ui/THROTTLE.md, #852): the
 * browser's local wall time, its hands at the angles a station clock's stand
 * at, redrawn once a second.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../src/ui/tc-clock.js";
import type { TcClock } from "../src/ui/tc-clock.js";

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "setTimeout", "clearTimeout", "Date"] });
  vi.setSystemTime(new Date(2026, 9, 20, 10, 8, 30));
});

afterEach(() => {
  document.body.replaceChildren();
  vi.useRealTimers();
});

async function mounted(): Promise<TcClock> {
  const clock = document.createElement("tc-clock");
  document.body.append(clock);
  await clock.updateComplete;
  return clock;
}

/** Where a hand points, in degrees clockwise from twelve. */
function angle(clock: TcClock, hand: string): number {
  const line = clock.renderRoot.querySelector(`.${hand}`)!;
  return Number(/rotate\(([-\d.]+)/.exec(line.getAttribute("transform")!)![1]);
}

describe("the station clock", () => {
  it("points its hands at the time", async () => {
    const clock = await mounted();
    expect(angle(clock, "hour")).toBe(304);
    expect(angle(clock, "minute")).toBe(51);
    expect(angle(clock, "second")).toBe(180);
  });

  it("moves the second hand once a second", async () => {
    const clock = await mounted();
    vi.advanceTimersByTime(1000);
    await clock.updateComplete;
    expect(angle(clock, "second")).toBe(186);
  });

  it("draws twelve bar markers", async () => {
    const clock = await mounted();
    expect(clock.renderRoot.querySelectorAll(".marker")).toHaveLength(12);
  });
});
