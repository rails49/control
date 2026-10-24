/**
 * The railroad's fast clock, as a page draws it: what `tc49/layout/state/clock`
 * says, read and worded, and what `tc49/layout/clock_wanted` asks
 * ([ADR-0090](../../../docs/adr/0090-layout-publishes-the-fast-clock-and-the-railroad-keeps-its-start-and-speed-up.md)).
 *
 * `layout` publishes the clock once a real second and every page draws the
 * time it is sent: nothing here reads a wall clock, so two tablets whose
 * clocks disagree still show one time (ADR-0009). It is scenery, never
 * control (ADR-0044).
 *
 * No DOM, as nothing under `model/` has (docs/ARCHITECTURE.md).
 */

import type { TraceEvent } from "./trace.js";

/** Seconds in a day: the clock is a time of day and wraps at midnight. */
export const DAY_S = 86_400;

/** The fast clock as `state/clock` last said it: the time of day in fast
 *  seconds since midnight, and fast seconds per real second (BUS.md). */
export interface FastClock {
  time: number;
  speedUp: number;
}

/** What a person changed in the clock's dialog: a time of day, a speed-up,
 *  or both. A field left out leaves that part of the clock as it is. */
export interface ClockChange {
  time?: number;
  speedUp?: number;
}

/** A `state/clock` payload read, or `null` where it is not one: `time` an
 *  integer `0` to `86399` and `speed_up` a number greater than 0. */
export function clockOf(event: TraceEvent): FastClock | null {
  const { time, speed_up: speedUp } = event as unknown as { time?: unknown; speed_up?: unknown };
  if (!timeOfDay(time) || !speedy(speedUp)) return null;
  return { time, speedUp };
}

/** Whether two readings say the same thing. */
export function sameClock(was: FastClock | null, now: FastClock | null): boolean {
  if (was === null || now === null) return was === now;
  return was.time === now.time && was.speedUp === now.speedUp;
}

/** A time of day as `HH:MM`, the seconds dropped. */
export function hhmm(time: number): string {
  const h = String(Math.floor(time / 3600)).padStart(2, "0");
  const m = String(Math.floor((time % 3600) / 60)).padStart(2, "0");
  return `${h}:${m}`;
}

/** `HH:MM` as seconds since midnight, `null` where it is not a time of day. */
export function timeOf(words: string): number | null {
  const parts = /^(\d{1,2}):(\d{2})$/.exec(words.trim());
  if (parts === null) return null;
  const h = Number(parts[1]);
  const m = Number(parts[2]);
  return h < 24 && m < 60 ? h * 3600 + m * 60 : null;
}

/** A speed-up as typed, `null` where it is not a number greater than 0. */
export function speedUpOf(words: string): number | null {
  const typed = words.trim();
  const speedUp = typed === "" ? NaN : Number(typed);
  return speedy(speedUp) ? speedUp : null;
}

/** What the band writes beside the face: `×8`, and nothing at a speed-up of
 *  1, which is the clock running as fast as any other. */
export function faster(speedUp: number): string {
  return speedUp === 1 ? "" : `×${speedUp}`;
}

function timeOfDay(time: unknown): time is number {
  return typeof time === "number" && Number.isInteger(time) && time >= 0 && time < DAY_S;
}

function speedy(speedUp: unknown): speedUp is number {
  return typeof speedUp === "number" && Number.isFinite(speedUp) && speedUp > 0;
}
