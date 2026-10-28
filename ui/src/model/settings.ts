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

/** What the Points tab says while `tc49/layout/state/settings` is unheard:
 *  there is no gap to show, and nothing to change it from. */
export const SETTINGS_UNHEARD = "the layout has not said its settings";

/**
 * What a committed point gap does (#1128): `{ sent }`, the seconds to publish
 * on `tc49/layout/settings_wanted`; `{ refused }`, why nothing goes; or
 * `null`, where nothing was changed and nothing is owed.
 *
 * `typed` is the field as committed and `heard` the `point_gap` of
 * `tc49/layout/state/settings`, `null` while that row is unheard. The first
 * that holds is the answer:
 *
 * - `heard` is `null`: the layout has not said its settings, so there is no
 *   gap to change and nobody to say the change was taken;
 * - `typed` is not a number of seconds;
 * - it is below `0` or above `POINT_GAP_MAX_S`: `layout` would drop it;
 * - it is the gap the row already says: nothing changed.
 *
 * The field's step of `0.1` is how it moves, not a rule: `layout` takes any
 * number in range, so `0.25` goes as typed.
 */
export function gapChange(
  typed: string,
  heard: number | null,
): { sent: number } | { refused: string } | null {
  if (heard === null) return { refused: SETTINGS_UNHEARD };
  const words = typed.trim();
  const gap = Number(words);
  if (words === "" || !Number.isFinite(gap)) {
    return { refused: "the time between point commands is a number of seconds" };
  }
  if (gap < 0 || gap > POINT_GAP_MAX_S) {
    return {
      refused: `the time between point commands is from 0 to ${POINT_GAP_MAX_S} seconds`,
    };
  }
  if (gap === heard) return null;
  return { sent: gap };
}

/** The point gap a `tc49/layout/state/settings` payload says, in seconds,
 *  `null` where it says none that `layout` could have meant: a number from
 *  `0` to `POINT_GAP_MAX_S`. */
export function pointGapOf(payload: Record<string, unknown>): number | null {
  const gap = payload["point_gap"];
  if (typeof gap !== "number" || !Number.isFinite(gap)) return null;
  return gap >= 0 && gap <= POINT_GAP_MAX_S ? gap : null;
}
