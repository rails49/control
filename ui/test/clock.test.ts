// @vitest-environment happy-dom

/**
 * The station clock (ui/THROTTLE.md, #852, ADR-0090): the fast clock it is
 * handed, its hands at the angles a station clock's stand at, and no hands
 * with no time to draw.
 */

import { afterEach, describe, expect, it } from "vitest";

import "../src/ui/tc-clock.js";
import type { TcClock } from "../src/ui/tc-clock.js";

afterEach(() => {
  document.body.replaceChildren();
});

/** 10:08:30, as `state/clock` says it. */
const TEN_PAST = 10 * 3600 + 8 * 60 + 30;

async function mounted(time: number | null, plain = false): Promise<TcClock> {
  const clock = document.createElement("tc-clock");
  clock.time = time;
  clock.plain = plain;
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
    const clock = await mounted(TEN_PAST);
    expect(angle(clock, "hour")).toBe(304);
    expect(angle(clock, "minute")).toBe(51);
    expect(angle(clock, "second")).toBe(180);
  });

  /** It reads no clock of its own: the hands move when the row does. */
  it("moves when it is handed the next time", async () => {
    const clock = await mounted(TEN_PAST);
    clock.time = TEN_PAST + 8;
    await clock.updateComplete;
    expect(angle(clock, "second")).toBe(228);
  });

  it("reads the afternoon on the same face", async () => {
    const clock = await mounted(TEN_PAST + 12 * 3600);
    expect(angle(clock, "hour")).toBe(304);
  });

  it("draws twelve bar markers", async () => {
    const clock = await mounted(TEN_PAST);
    expect(clock.renderRoot.querySelectorAll(".marker")).toHaveLength(12);
  });

  it("draws its face with no hands with no time", async () => {
    const clock = await mounted(null);
    expect(clock.renderRoot.querySelector(".face")).not.toBeNull();
    expect(clock.renderRoot.querySelectorAll(".hour, .minute, .second")).toHaveLength(0);
  });

  it("draws no second hand where it is plain", async () => {
    const clock = await mounted(TEN_PAST, true);
    expect(clock.renderRoot.querySelector(".minute")).not.toBeNull();
    expect(clock.renderRoot.querySelector(".second")).toBeNull();
  });
});
