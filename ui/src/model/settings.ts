/**
 * When the settings dialog's railroad part is refused, and why (#733, #737,
 * [ADR-0072](../../../docs/adr/0072-the-railroad-is-loaded-from-a-settings-dialog-and-the-store-records-which.md)).
 *
 * Loading another railroad rebuilds the rails a train stands on, so it waits
 * for track power `off`, as it does under ADR-0060 — and where the track has
 * power the press takes it off itself, draining and acting once `off` is read
 * (`Drain`; ADR-0085, decision 5); and it throws away what
 * the page holds of the railroad being left, so it waits for the roster's
 * unsaved edits to be saved. The drawing's are not waited for: the app saves
 * them before the load (ADR-0085, decision 1). A page that has not heard which
 * railroad is loaded has no binding on the other end to ask. New and Copy
 * loaded as… end in a load of what they wrote, so they wait on the same
 * (ADR-0072, decision 4), and Copy on a railroad being loaded to copy.
 *
 * Turning the box off (#745) and Restore wait on the track being dead, as a
 * load does, and drain it the same way. A press is refused over the supply
 * only where the layout has not said where it stands: there is nothing to
 * drain, and nothing to say it went off.
 *
 * Pure functions in `model/` with a test, as the enablement rules beside them
 * are (EDITOR.md#tests): the dialog draws what these say and decides nothing.
 */

import type { Backup } from "./store.js";
import type { Power } from "./trace.js";

/** Why a press waiting on a dead track is refused before the supply is
 *  heard. */
const UNHEARD = "the layout has not said whether the track has power";

/**
 * Why the railroad part is refused, `null` where it is not. The first that
 * holds is the reason:
 *
 * - `loaded` is `null`: the layout has not said which railroad is loaded, so
 *   no binding is there to answer a press;
 * - a railroad is loaded and the layout has not said whether the track has
 *   power: a drain could not be seen to end;
 * - something is unsaved: the load would discard it.
 *
 * Power on or draining refuses nothing: the press drains first (`Drain`).
 *
 * `loaded` is the layout's row as `RunStatus.railroad` has it — `null` not
 * heard, `""` none loaded (#727). With none loaded there are no rails built
 * to change under anything, so power is not asked: a binding with nothing
 * loaded reads no supply, and the first railroad on a new box is loaded from
 * here. `unsaved` is what the load would discard that nothing saves first —
 * `"the roster"`, in `Railroad.unsaved`'s words (`model/railroad.ts`) — and
 * `null` while nothing is.
 */
export function refusal(
  loaded: string | null,
  power: Power | null,
  unsaved: string | null,
): string | null {
  if (loaded === null) return "the layout has not said which railroad is loaded";
  if (loaded !== "" && power === null) return UNHEARD;
  if (unsaved !== null) return `${unsaved} has unsaved edits — save first`;
  return null;
}

/**
 * Why Restore is refused, `null` where it is not. Each is a way the physical
 * layout could come to disagree with the store, and the app wears them because
 * the store hears nothing from the bus (#688). The first that holds is the
 * reason:
 *
 * - `railroad` is `null`: the layout has not said which railroad is loaded, so
 *   nothing says the backup holds the railroad the apps run (#759);
 * - a railroad is loaded and the layout has not said whether the track has
 *   power: a drain could not be seen to end;
 * - `picked` is without the loaded railroad: the apps would go on running a
 *   railroad the store no longer holds.
 *
 * `railroad` is the row as `refusal` reads it. With none loaded (`""`) there
 * is no run to drift from, so any backup will do whatever the supply (#697).
 * Power on or draining refuses nothing: the press drains first (`Drain`).
 * Trains on the layout do not hold it back: the rebuild keeps the ones that
 * still fit (#710, ADR-0071).
 */
export function restoreRefusal(
  railroad: string | null,
  power: Power | null,
  picked: Backup | undefined,
): string | null {
  if (railroad === null) return "the layout has not said which railroad is loaded";
  if (railroad === "") return null;
  if (power === null) return UNHEARD;
  if (picked !== undefined && !picked.railroads.includes(railroad)) {
    return `this backup has no ${railroad} — load another railroad first`;
  }
  return null;
}

/**
 * Why Copy loaded as… is refused, `null` where it is not: everything
 * `refusal` holds, and then a row naming `""` — nothing is loaded, so there
 * is nothing to copy. The first railroad on a new box is New's, not Copy's.
 */
export function copyRefusal(
  loaded: string | null,
  power: Power | null,
  unsaved: string | null,
): string | null {
  const refused = refusal(loaded, power, unsaved);
  if (refused !== null) return refused;
  if (loaded === "") return "no railroad is loaded to copy";
  return null;
}

/**
 * Why turning the box off is refused, `null` where it is not: the layout has
 * not said whether the track has power. Power on or draining refuses
 * nothing: the press drains first (`Drain`).
 */
export function boxRefusal(power: Power | null): string | null {
  return power === null ? UNHEARD : null;
}

/**
 * A press that needs the track dead — Load, Restore, turning the box off —
 * held until `tc49/layout/state/power` reads `off`
 * ([ADR-0085](../../../docs/adr/0085-the-editor-saves-when-it-is-left-and-a-railroad-can-be-named-without-being-built.md),
 * decision 5). The dialog asks for the drain `begin` answers with, says
 * "stopping trains…" with the stop sign beside it while `waiting`, and hands
 * each power it reads to `heard`.
 *
 * A drain has no time limit, so the person can always end the wait: the stop
 * sign takes power `off` at once and the action follows; closing the dialog
 * `abandon`s it, power staying as it is; and ON pressed on the band ends the
 * drain, power reading `on` again after `draining`, which abandons it too —
 * the person changed their mind. One action is held at a time; a second
 * `begin` replaces the first.
 */
export class Drain {
  private held: (() => void) | null = null;

  /** Whether the held action has seen the drain under way. Power reads `on`
   *  between the ask and `layout`'s answer, and only `on` after `draining` is
   *  the drain ended. */
  private drained = false;

  /** Whether an action is held, waiting on `off`. */
  get waiting(): boolean {
    return this.held !== null;
  }

  /**
   * A press: `act` at once where `power` is `off` or `null` — `null` being a
   * press that does not wait on the supply, as a load with none loaded — and
   * otherwise held. Answers what to ask `layout` for: `draining` from `on`,
   * nothing where the track is already draining or dead.
   */
  begin(power: Power | null, act: () => void): Power | null {
    if (power === null || power === "off") {
      this.held = null;
      act();
      return null;
    }
    this.held = act;
    this.drained = power === "draining";
    return power === "on" ? "draining" : null;
  }

  /** The power as `layout` now says it: `off` acts, `on` after `draining`
   *  abandons. A supply gone unheard (`null`) keeps the wait. */
  heard(power: Power | null): void {
    const act = this.held;
    if (act === null) return;
    if (power === "off") {
      this.held = null;
      act();
    } else if (power === "draining") {
      this.drained = true;
    } else if (power === "on" && this.drained) {
      this.held = null;
    }
  }

  /** The wait given up: nothing is acted on, and power is not asked for. */
  abandon(): void {
    this.held = null;
  }
}

/** Where a pick stands on the page: the drawing it holds (`Filing.opened`,
 *  `""` for none), and what the session reads off the run
 *  (`RunStatus.railroad`, `built` and `allocated`). */
export interface Landing {
  opened: string;
  railroad: string | null;
  built: boolean;
  allocated: boolean;
}

/**
 * Whether the railroad `wanted` has landed, so the dialog that asked for it
 * closes (#902): the page holds its drawing, the layout's row names it, and
 * `tc49/dispatch/state/allocation` has arrived since — the dispatcher being
 * the last app to build on a load. A row saying nothing was built has no
 * dispatcher on the railroad to say anything (ADR-0085, decision 4), so the
 * drawing and the row are the whole of it there.
 */
export function arrived(wanted: string, now: Landing): boolean {
  if (now.opened !== wanted || now.railroad !== wanted) return false;
  return !now.built || now.allocated;
}

/** How long a pick waits for `arrived` once the railroad is asked for. A
 *  load takes a few seconds with the store answering promptly (#902). */
export const ANSWER_MS = 15_000;

/** What the picked row says where `ANSWER_MS` passed without `arrived`. */
export const UNANSWERED = "the layout did not answer";

/** What a dialog says while a `Drain` waits, beside the stop sign. */
export const STOPPING = "stopping trains…";

/** The longest point gap a person may set, in seconds, as `layout` takes it
 *  (`POINT_GAP_MAX_S`, `tc49.lib.settings`). */
export const POINT_GAP_MAX_S = 5;

/** The shortest and longest throttle silence a person may set, in seconds,
 *  as `layout` takes it (`THROTTLE_SILENCE_MIN_S`, `THROTTLE_SILENCE_MAX_S`,
 *  `tc49.lib.settings`). */
export const THROTTLE_SILENCE_MIN_S = 2;
export const THROTTLE_SILENCE_MAX_S = 60;

/** The shortest and longest sensor silence a person may set, in seconds, as
 *  `layout` takes it (`SENSOR_SILENCE_MIN_S`, `SENSOR_SILENCE_MAX_S`,
 *  `tc49.lib.settings`). */
export const SENSOR_SILENCE_MIN_S = 2;
export const SENSOR_SILENCE_MAX_S = 60;

/** What a settings tab says while `tc49/layout/state/settings` is unheard, or
 *  its field there unreadable: there is no value to show, and nothing to
 *  change it from. */
export const SETTINGS_UNHEARD = "the layout has not said its settings";

/** What a commit in the Settings dialog asks `layout` for: the payload of
 *  `tc49/layout/settings_wanted`, each field optional and the one committed
 *  alone present (#1126, #1131). */
export interface SettingsChange {
  point_gap?: number;
  speeds?: Partial<Speeds>;
  throttle_silence?: number;
  sensor_silence?: number;
}

/** The driver's speeds, each a fraction of the locomotive's top speed above
 *  `0` and at most `1`, as `tc49/layout/state/settings` says them (#1130). */
export interface Speeds {
  clear: number;
  caution: number;
}

/**
 * `tc49/layout/state/settings` as the Settings dialog reads it (#1185): the
 * point gap and the two silences in seconds, the speeds as fractions. BUS.md
 * says every field is present; one that does not read as `layout` could have
 * meant it is `null` on its own, and disables only its own input.
 */
export interface LayoutSettings {
  pointGap: number | null;
  speeds: { clear: number | null; caution: number | null };
  throttleSilence: number | null;
  sensorSilence: number | null;
}

/**
 * What a `tc49/layout/state/settings` payload says, field by field: the point
 * gap a number from `0` to `POINT_GAP_MAX_S`, each silence a number within
 * its bounds, and the speeds `clear` and `caution` both, each above `0` and at
 * most `1` — a `speeds` that does not read so leaves both `null`.
 */
export function settingsOf(payload: Record<string, unknown>): LayoutSettings {
  const speeds = speedsOf(payload["speeds"]);
  return {
    pointGap: within(payload["point_gap"], 0, POINT_GAP_MAX_S),
    speeds: { clear: speeds?.clear ?? null, caution: speeds?.caution ?? null },
    throttleSilence: within(
      payload["throttle_silence"],
      THROTTLE_SILENCE_MIN_S,
      THROTTLE_SILENCE_MAX_S,
    ),
    sensorSilence: within(payload["sensor_silence"], SENSOR_SILENCE_MIN_S, SENSOR_SILENCE_MAX_S),
  };
}

/** `value` where it is a number from `min` to `max`, `null` otherwise. */
function within(value: unknown, min: number, max: number): number | null {
  return typeof value === "number" && value >= min && value <= max ? value : null;
}

function speedsOf(speeds: unknown): Speeds | null {
  if (typeof speeds !== "object" || speeds === null) return null;
  const { clear, caution } = speeds as Record<string, unknown>;
  if (!isSpeed(clear) || !isSpeed(caution)) return null;
  return { clear, caution };
}

function isSpeed(value: unknown): value is number {
  return typeof value === "number" && value > 0 && value <= 1;
}

/** A speed as the Driving tab shows it: percent of the locomotive's top
 *  speed. Rounded off at the fourth decimal so `0.07` shows `7` and not the
 *  float `7.000000000000001`. */
export function percentOf(fraction: number): number {
  return Math.round(fraction * 1e6) / 1e4;
}

/** The inputs of the Settings dialog's setting tabs, one per value the row
 *  holds. */
export type SettingField = "gap" | "clear" | "caution" | "silence" | "sensorSilence";

/** One input of a setting tab: how it is drawn, what it refuses, and what it
 *  reads and sends. */
export interface SettingSpec {
  /** The input's label. */
  readonly label: string;
  /** The input's class, which a tab's layout and a test find it by. */
  readonly class: string;
  /** The bounds a value is taken within, the ends included, as `layout`
   *  takes it; the step is how the input moves, not a rule. */
  readonly min: number;
  readonly max: number;
  readonly step: number;
  /** What the value is counted in; the input's suffix is `s` or `%`. */
  readonly unit: "seconds" | "percent";
  /** The phrase the field's refusals start with. */
  readonly what: string;
  /** The value as the field shows it, `null` where the row has none. */
  of(settings: LayoutSettings): number | null;
  /** The `settings_wanted` payload for a value as typed. */
  wanted(value: number): SettingsChange;
}

/** Each input of the setting tabs (#1128, #1134, #1149). */
export const SETTING_FIELDS: Record<SettingField, SettingSpec> = {
  gap: {
    label: "Time between point commands",
    class: "gap",
    min: 0,
    max: POINT_GAP_MAX_S,
    step: 0.1,
    unit: "seconds",
    what: "the time between point commands",
    of: (settings) => settings.pointGap,
    wanted: (value) => ({ point_gap: value }),
  },
  clear: {
    label: "Speed at clear",
    class: "clear",
    min: 1,
    max: 100,
    step: 1,
    unit: "percent",
    what: "the speed at clear",
    of: (settings) => percentIn(settings.speeds.clear),
    wanted: (value) => ({ speeds: { clear: value / 100 } }),
  },
  caution: {
    label: "Speed at caution",
    class: "caution",
    min: 1,
    max: 100,
    step: 1,
    unit: "percent",
    what: "the speed at caution",
    of: (settings) => percentIn(settings.speeds.caution),
    wanted: (value) => ({ speeds: { caution: value / 100 } }),
  },
  silence: {
    label: "Let go of a silent throttle's trains after",
    class: "silence",
    min: THROTTLE_SILENCE_MIN_S,
    max: THROTTLE_SILENCE_MAX_S,
    step: 1,
    unit: "seconds",
    what: "how long a throttle may go silent",
    of: (settings) => settings.throttleSilence,
    wanted: (value) => ({ throttle_silence: value }),
  },
  sensorSilence: {
    label: "Call a sensor unknown once unheard for",
    class: "silence",
    min: SENSOR_SILENCE_MIN_S,
    max: SENSOR_SILENCE_MAX_S,
    step: 1,
    unit: "seconds",
    what: "how long a sensor may go unheard",
    of: (settings) => settings.sensorSilence,
    wanted: (value) => ({ sensor_silence: value }),
  },
};

function percentIn(fraction: number | null): number | null {
  return fraction === null ? null : percentOf(fraction);
}

/** The value `field` has in `settings`, `null` while the row is unheard or
 *  its field unreadable. */
function valueOf(field: SettingField, settings: LayoutSettings | null): number | null {
  return settings === null ? null : SETTING_FIELDS[field].of(settings);
}

/**
 * What a commit in `field` does (#1128, #1134, #1149): `{ sent }`, the
 * `settings_wanted` payload carrying that one field; `{ refused }`, why
 * nothing goes; or `null`, where nothing changed and nothing is owed.
 *
 * `typed` is the field as committed, a speed in percent, and `settings` the
 * row, `null` while unheard. The first that holds is the answer:
 *
 * - the row is unheard, or its value for `field` unreadable: there is nothing
 *   to change and nobody to say the change was taken;
 * - `typed` is not a number;
 * - it is outside the field's `min` to `max`: `layout` would drop it;
 * - it is the value the row already says: nothing changed.
 *
 * The field's step is how it moves, not a rule: `layout` takes any number in
 * range, so a gap of `0.25` or a speed of `45.5` goes as typed.
 */
export function settingChange(
  field: SettingField,
  typed: string,
  settings: LayoutSettings | null,
): { sent: SettingsChange } | { refused: string } | null {
  const spec = SETTING_FIELDS[field];
  const heard = valueOf(field, settings);
  if (heard === null) return { refused: SETTINGS_UNHEARD };
  const words = typed.trim();
  const value = Number(words);
  if (words === "" || !Number.isFinite(value)) {
    return {
      refused:
        spec.unit === "seconds"
          ? `${spec.what} is a number of seconds`
          : `${spec.what} is a number, in percent`,
    };
  }
  if (value < spec.min || value > spec.max) {
    return { refused: `${spec.what} is from ${spec.min} to ${spec.max} ${spec.unit}` };
  }
  if (value === heard) return null;
  return { sent: spec.wanted(value) };
}

/** A commit a field's rule refused (#1137): the text typed, which the field
 *  goes on showing, why it was refused, and what the row said for the field
 *  then. */
export interface Refused {
  readonly typed: string;
  readonly reason: string;
  readonly heard: string;
}

/** The commits refused in each field that still stand (#1137). */
export type Refusals = Partial<Record<SettingField, Refused>>;

/** What the row says for `field`, as its field shows it: `""` while the row
 *  is unheard or the field unreadable. */
function heardIn(field: SettingField, settings: LayoutSettings | null): string {
  const value = valueOf(field, settings);
  return value === null ? "" : String(value);
}

/**
 * What `field` shows (#1137): the text of a refused commit while it stands,
 * however often it is committed again, and the row's value otherwise, `""`
 * where the row has none.
 */
export function shownIn(
  refusals: Refusals,
  field: SettingField,
  settings: LayoutSettings | null,
): string {
  return refusals[field]?.typed ?? heardIn(field, settings);
}

/**
 * `typed` committed in `field`: `sent`, the payload to publish where
 * `settingChange` sends it, and the refusals with `field`'s replaced — by this
 * commit where it is refused, dropped where it is not. Other fields' stand.
 */
export function committed(
  refusals: Refusals,
  field: SettingField,
  typed: string,
  settings: LayoutSettings | null,
): { refusals: Refusals; sent: SettingsChange | null } {
  const change = settingChange(field, typed, settings);
  const others = { ...refusals };
  delete others[field];
  if (change !== null && "refused" in change) {
    const refused = { typed, reason: change.refused, heard: heardIn(field, settings) };
    return { refusals: { ...others, [field]: refused }, sent: null };
  }
  return { refusals: others, sent: change === null ? null : change.sent };
}

/** Each refusal dropped where the row now says a different value for its
 *  field than it did when the commit was refused; `refusals` itself where
 *  none is. */
export function reheard(refusals: Refusals, settings: LayoutSettings | null): Refusals {
  const kept = Object.entries(refusals).filter(
    ([field, refused]) => heardIn(field as SettingField, settings) === refused.heard,
  );
  return kept.length === Object.keys(refusals).length ? refusals : Object.fromEntries(kept);
}
