/**
 * The throttle model: what the view draws for each train a person could take
 * (ui/THROTTLE.md, [#207](https://github.com/rails49/control/issues/207)).
 *
 * No DOM, and nothing derived that an app already publishes. Which trains
 * there are to drive is the run's picture, who drives each is `layout`'s
 * answer on `tc49/layout/state/mode`, which way a train points is the
 * scheduler's **facing**, the aspect it is reading is the dispatcher's, and
 * what a person can switch on it is the railroad's roster. This puts the five
 * beside each other train by train, and decides none of them.
 *
 * It holds no lever position and no chosen train: those are the person's, and
 * they live in the component with the pointer that moves them.
 */

import type { Aspect } from "../render/artwork.js";
import type { Ahead, EndRef, Placed } from "./panel.js";
import type { Fn, TrainDoc } from "./store.js";
import type { Mode } from "./trace.js";

/**
 * One train, as a throttle shows it.
 *
 * `mode` is `layout`'s word and never the view's: a train is taken when the
 * mode topic says `manual` and not when somebody pressed for it
 * (ui/THROTTLE.md).
 */
export interface Cab {
  train: string;
  /** The block it stands in, `null` while it is crossing a transit and
   *  stands in none — on the layout all the same (CONTEXT.md, **Placed**). */
  block: string | null;
  mode: Mode;
  /** The end of its block it points at, `<block>.<end>`, `null` where the
   *  scheduler has said no facing for it. It is the way `+` runs, which is
   *  why the view draws it before anything moves. */
  nose: EndRef | null;
  /** The aspect at that end, `null` where no signal there has been named —
   *  an end that leads nowhere carries none (ADR-0025). */
  aspect: Aspect | null;
  /** The blocks on the road in front of it, nearest first. */
  ahead: readonly Ahead[];
  /** Whether it has a request in flight, which is what greys turning it
   *  round: the request departs the end the facing named when it was
   *  composed, so a flip under it would leave the train pointing one way and
   *  leaving the other ([#295](https://github.com/rails49/control/issues/295)).
   *  The same pre-judgement the run view's menu makes, from the same
   *  reading. */
  inFlight: boolean;
  /** What a person driving it can switch, by the names the catalogue gives
   *  them (ADR-0045). Empty where its cars declare none, which is most of the
   *  stock a railroad owns. */
  functions: readonly Fn[];
}

/** What the throttle is worked out from: the run's picture, `layout`'s modes,
 *  the scheduler's facing, the dispatcher's aspects and the railroad's
 *  roster. Five sources because they are five apps' answers, and one list,
 *  because a person picking a train to drive is not choosing between them. */
export interface Driving {
  placed: readonly Placed[];
  modes: ReadonlyMap<string, Mode>;
  noses: ReadonlyMap<string, EndRef>;
  aspects: ReadonlyMap<EndRef, Aspect>;
  ahead: ReadonlyMap<string, readonly Ahead[]>;
  /** The trains with a request in flight, as the run's picture has it. */
  inFlight: ReadonlySet<string>;
  stock: Record<string, TrainDoc>;
}

/**
 * The trains there are to drive, in the order they are offered: **the trains
 * the railroad has placed**, ordered by name.
 *
 * Placement is the whole of the rule. A train off the layout has nothing for
 * a throttle to move ([ADR-0039](../../../docs/adr/0039-a-train-may-be-off-the-layout.md)),
 * and the roster's other trains are the run view's pane to place from, not
 * this view's to drive.
 *
 * A train the picture has and the roster does not still gets a cab, with
 * nothing to switch: it is on the layout, and a view that hid it would hide
 * the thing the operator can see — the same rule the roster pane keeps.
 */
export function cabs(driving: Driving): Cab[] {
  const { placed, modes, noses, aspects, ahead, inFlight, stock } = driving;
  return [...placed]
    .sort((one, other) => one.train.localeCompare(other.train))
    .map(({ train, block }) => {
      const nose = noses.get(train) ?? null;
      return {
        train,
        block,
        mode: modes.get(train) ?? "automatic",
        nose,
        aspect: (nose === null ? undefined : aspects.get(nose)) ?? null,
        ahead: ahead.get(train) ?? [],
        inFlight: inFlight.has(train),
        functions: stock[train]?.functions ?? [],
      };
    });
}
