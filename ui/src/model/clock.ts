/**
 * The railroad's fast clock, as a page draws it: what `tc49/layout/state/clock`
 * says, read and worded, and what `tc49/layout/clock_wanted` asks
 * ([ADR-0090](../../../docs/adr/0090-layout-publishes-the-fast-clock-and-the-railroad-keeps-its-start-and-speed-up.md)).
 *
 * The clock counts days from 0 ([#1363](https://github.com/rails49/control/issues/1363)):
 * a time is fast seconds since midnight of day 0, with no upper limit. Where
 * a person reads or types one it is written `[<day>d]HH:MM`, the day a whole
 * number without leading zeros and left out on day 0: `06:00` and `0d06:00`
 * are the same time, and `1d06:00` is a day later. `timeOf` and `written` are
 * the one parser and formatter of that form.
 *
 * `layout` publishes the clock once a real second and every page draws the
 * time it is sent: nothing here reads a wall clock, so two tablets whose
 * clocks disagree still show one time (ADR-0009). It is scenery, never
 * control (ADR-0044).
 *
 * No DOM, as nothing under `model/` has (docs/ARCHITECTURE.md).
 */

import type { TraceEvent } from "./trace.js";

/** Seconds in a day. */
export const DAY_S = 86_400;

/** The fast clock as `state/clock` last said it: the time in fast seconds
 *  since midnight of day 0, and fast seconds per real second (BUS.md). */
export interface FastClock {
  time: number;
  speedUp: number;
}

/** What a person changed in the clock's dialog: a time, a speed-up, or
 *  both. A field left out leaves that part of the clock as it is. */
export interface ClockChange {
  time?: number;
  speedUp?: number;
}

/** A `state/clock` payload read, or `null` where it is not one: `time` an
 *  integer, 0 or more, and `speed_up` a number greater than 0. */
export function clockOf(event: TraceEvent): FastClock | null {
  const { time, speed_up: speedUp } = event as unknown as { time?: unknown; speed_up?: unknown };
  if (!whole(time) || !speedy(speedUp)) return null;
  return { time, speedUp };
}

/** Whether two readings say the same thing. */
export function sameClock(was: FastClock | null, now: FastClock | null): boolean {
  if (was === null || now === null) return was === now;
  return was.time === now.time && was.speedUp === now.speedUp;
}

/** A time's time of day as `HH:MM`, the day and the seconds dropped. */
export function hhmm(time: number): string {
  const ofDay = time % DAY_S;
  const h = String(Math.floor(ofDay / 3600)).padStart(2, "0");
  const m = String(Math.floor((ofDay % 3600) / 60)).padStart(2, "0");
  return `${h}:${m}`;
}

/** A time as `[<day>d]HH:MM`, the seconds dropped and day 0 written without
 *  `0d`. */
export function written(time: number): string {
  const day = Math.floor(time / DAY_S);
  return day === 0 ? hhmm(time) : `${day}d${hhmm(time)}`;
}

/** `[<day>d]HH:MM` as seconds since midnight of day 0, `null` where it is no
 *  time: a day with a leading zero, an hour past 23 or a minute past 59. The
 *  hour may be typed with one digit. */
export function timeOf(words: string): number | null {
  const parts = /^(?:(0|[1-9]\d*)d)?(\d{1,2}):(\d{2})$/.exec(words.trim());
  if (parts === null) return null;
  const day = Number(parts[1] ?? 0);
  const h = Number(parts[2]);
  const m = Number(parts[3]);
  return h < 24 && m < 60 ? day * DAY_S + h * 3600 + m * 60 : null;
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

function whole(time: unknown): time is number {
  return typeof time === "number" && Number.isInteger(time) && time >= 0;
}

function speedy(speedUp: unknown): speedUp is number {
  return typeof speedUp === "number" && Number.isFinite(speedUp) && speedUp > 0;
}
