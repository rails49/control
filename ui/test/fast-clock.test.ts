/**
 * The fast clock as a page reads and words it (`model/clock.ts`, ADR-0090,
 * #1363): `state/clock` read, a time of day as `HH:MM`, a time as
 * `[<day>d]HH:MM`, and what a person types in the clock's dialog. No DOM.
 */

import { describe, expect, it } from "vitest";

import { clockOf, faster, hhmm, speedUpOf, timeOf, written } from "../src/model/clock.js";

describe("reading state/clock", () => {
  it("reads the time of day and the speed-up", () => {
    expect(clockOf({ event: "clock", at: 4, time: 36_000, speed_up: 8 })).toEqual({
      time: 36_000,
      speedUp: 8,
    });
  });

  it("reads a time on any day", () => {
    expect(clockOf({ event: "clock", time: 2 * 86_400 + 21_600, speed_up: 8 })).toEqual({
      time: 2 * 86_400 + 21_600,
      speedUp: 8,
    });
  });

  it("refuses a time that is not a whole time of 0 or more, and a speed-up not above 0", () => {
    for (const payload of [
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

  it("writes only the time of day of a time on a later day", () => {
    expect(hhmm(2 * 86_400 + 21_600)).toBe("06:00");
  });

  it("writes a time as its day and time of day, day 0 without 0d", () => {
    expect(written(21_600)).toBe("06:00");
    expect(written(86_400 + 21_600 + 59)).toBe("1d06:00");
    expect(written(12 * 86_400)).toBe("12d00:00");
  });

  it("says the speed-up beside the face only where it is not 1", () => {
    expect(faster(1)).toBe("");
    expect(faster(8)).toBe("×8");
    expect(faster(1.5)).toBe("×1.5");
  });
});

describe("what a person types", () => {
  it("reads HH:MM as seconds since midnight of day 0", () => {
    expect(timeOf("06:30")).toBe(6 * 3600 + 30 * 60);
    expect(timeOf("6:30")).toBe(6 * 3600 + 30 * 60);
    expect(timeOf("23:59")).toBe(86_340);
  });

  it("reads a day before the time of day", () => {
    expect(timeOf("1d06:00")).toBe(86_400 + 21_600);
    expect(timeOf("0d06:00")).toBe(21_600);
    expect(timeOf("12d00:00")).toBe(12 * 86_400);
  });

  it("reads what it writes", () => {
    for (const time of [0, 21_600, 86_400 + 21_600, 3 * 86_400 + 86_340]) {
      expect(timeOf(written(time))).toBe(time);
    }
  });

  it("refuses what is not a time", () => {
    for (const words of ["24:00", "06:60", "12:60", "01d06:00", "d06:00", "1d", "-1d06:00", "noon", "", "12:5"]) {
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
