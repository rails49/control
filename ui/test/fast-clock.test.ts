/**
 * The fast clock as a page reads and words it (`model/clock.ts`, ADR-0090):
 * `state/clock` read, a time of day as `HH:MM`, and what a person types in the
 * clock's dialog. No DOM.
 */

import { describe, expect, it } from "vitest";

import { clockOf, faster, hhmm, speedUpOf, timeOf } from "../src/model/clock.js";

describe("reading state/clock", () => {
  it("reads the time of day and the speed-up", () => {
    expect(clockOf({ event: "clock", at: 4, time: 36_000, speed_up: 8 })).toEqual({
      time: 36_000,
      speedUp: 8,
    });
  });

  it("refuses a time that is not a time of day, and a speed-up not above 0", () => {
    for (const payload of [
      { time: 86_400, speed_up: 1 },
      { time: -1, speed_up: 1 },
      { time: 1.5, speed_up: 1 },
      { time: "10:00", speed_up: 1 },
      { time: 60, speed_up: 0 },
      { time: 60, speed_up: -2 },
      { time: 60 },
      { speed_up: 1 },
    ]) {
      expect(clockOf({ event: "clock", ...payload })).toBeNull();
    }
  });
});

describe("wording the clock", () => {
  it("writes a time of day as HH:MM, the seconds dropped", () => {
    expect(hhmm(0)).toBe("00:00");
    expect(hhmm(9 * 3600 + 5 * 60 + 59)).toBe("09:05");
    expect(hhmm(86_399)).toBe("23:59");
  });

  it("says the speed-up beside the face only where it is not 1", () => {
    expect(faster(1)).toBe("");
    expect(faster(8)).toBe("×8");
    expect(faster(1.5)).toBe("×1.5");
  });
});

describe("what a person types", () => {
  it("reads HH:MM as seconds since midnight", () => {
    expect(timeOf("06:30")).toBe(6 * 3600 + 30 * 60);
    expect(timeOf("6:30")).toBe(6 * 3600 + 30 * 60);
    expect(timeOf("23:59")).toBe(86_340);
  });

  it("refuses what is not a time of day", () => {
    for (const words of ["24:00", "12:60", "noon", "", "12:5"]) {
      expect(timeOf(words)).toBeNull();
    }
  });

  it("reads a speed-up above 0, decimals allowed", () => {
    expect(speedUpOf("8")).toBe(8);
    expect(speedUpOf("1.5")).toBe(1.5);
    for (const words of ["0", "-1", "", "fast", "Infinity"]) {
      expect(speedUpOf(words)).toBeNull();
    }
  });
});
