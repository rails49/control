/**
 * The throttle model: what the view draws for each train a person could take
 * (ui/THROTTLE.md, [#207](https://github.com/rails49/control/issues/207)).
 *
 * No DOM, and nothing derived that an app already publishes. Which trains
 * there are to drive is the run's picture, which throttle holds each is
 * `layout`'s answer on `tc49/layout/state/taken`, whether its lever does
 * anything is the move the dispatcher granted it, which way a train points is
 * the scheduler's **facing**, the aspect it is reading is the dispatcher's,
 * what a person can switch on it is the railroad's roster, and which of those
 * are on is `layout`'s answer on `tc49/layout/state/functions`. This puts them
 * beside each other train by train, and decides none of them.
 *
 * It holds no slider position: that is the person's, and it lives in the
 * component with the pointer that moves it. Nor is a train chosen without
 * being taken — the one driven is the one `state/taken` names this throttle
 * for.
 */

import type { Aspect } from "../render/artwork.js";
import { blockOf, endOf, type Ahead, type EndRef, type Placed } from "./panel.js";
import type { Fn, TrainDoc } from "./store.js";
import type { Power } from "./trace.js";

/** Who holds a train, as this page sees it: this throttle, another one, or
 *  none (`null`). */
export type Holder = "here" | "elsewhere" | null;

/** One thing a person can switch on a train: its catalogue name, and whether
 *  `state/functions` says it is on. Never what the person last pressed — a
 *  button changes when `layout` says it switched it (ui/THROTTLE.md). */
export interface CabFunction {
  name: string;
  on: boolean;
}

/**
 * One train, as a throttle shows it.
 *
 * `taken` is `layout`'s word and never the view's: a train is taken when
 * `state/taken` names a throttle for it and not when somebody pressed for it
 * (ui/THROTTLE.md).
 */
export interface Cab {
  train: string;
  /** The block it stands in, `null` while it is crossing a transit and
   *  stands in none — on the layout all the same (GLOSSARY.md, **Placed**). */
  block: string | null;
  taken: Holder;
  /** Whether it has a move outstanding: granted and not yet at the sensor it
   *  ends at. The slider drives the train with or without one (ADR-0081), and
   *  goes to rest when one ends, which is where `layout` writes `0.0`. */
  granted: boolean;
  /** The end of its block it points at, `<block>.<end>`, `null` where the
   *  scheduler has said no facing for it. It is the end a train run nose
   *  first leaves by, the reverser at Forward. */
  nose: EndRef | null;
  /** The aspect at that end, `null` where no signal there has been named —
   *  an end that leads nowhere carries none (ADR-0025). */
  aspect: Aspect | null;
  /** The aspect at the block's other end, which a train run tail first
   *  leaves by, the reverser at Reverse; `null` as `aspect` is. */
  tailAspect: Aspect | null;
  /** The model of its first locomotive, which the view draws the train as
   *  (`photoUrl`), `null` where it has none, the roster does not have the
   *  train, or the store's answer leaves the field out. */
  locomotive: string | null;
  /** Whether a car in it carries a camera, as the trains route says; an
   *  answer that leaves the field out is a train with none. Never where the
   *  camera answers: the `camera` app relays its picture (ADR-0082). */
  camera: boolean;
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
   *  them (ADR-0045), in the roster's order, each on or off as
   *  `state/functions` has it. Empty where its cars declare none, which is
   *  most of the stock a railroad owns. */
  functions: readonly CabFunction[];
  /** Whether it is the train this throttle last held, standing free on the
   *  layout: the one the picker offers first, as Take back (ui/THROTTLE.md). */
  last: boolean;
}

/** What the throttle is worked out from: the run's picture, which throttle
 *  `layout` says holds each train, the moves granted, the scheduler's
 *  facing, the dispatcher's aspects and the railroad's roster. Several
 *  sources because they are several apps' answers, and one list, because a
 *  person picking a train to drive is not choosing between them. */
export interface Driving {
  placed: readonly Placed[];
  /** train → the id of the throttle holding it (`state/taken`). */
  taken: ReadonlyMap<string, string>;
  /** This page's throttle id, which says which of those is this one. */
  throttle: string;
  /** train → function name → on (`state/functions`); a name it does not
   *  give is off. */
  functions: ReadonlyMap<string, ReadonlyMap<string, boolean>>;
  /** The trains with a move outstanding. */
  granted: ReadonlySet<string>;
  noses: ReadonlyMap<string, EndRef>;
  aspects: ReadonlyMap<EndRef, Aspect>;
  ahead: ReadonlyMap<string, readonly Ahead[]>;
  /** The trains with a request in flight, as the run's picture has it. */
  inFlight: ReadonlySet<string>;
  stock: Record<string, TrainDoc>;
  /** The train `state/taken` most recently named this throttle for, `null`
   *  where it has named it for none. The session keeps it; this only puts
   *  its cab first. */
  last: string | null;
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
 *
 * One train goes ahead of the order: the last one this throttle held, while
 * it is placed and no throttle holds it, marked `last` — the picker's Take
 * back. Held by anybody, it takes its place by name like the others.
 */
export function cabs(driving: Driving): Cab[] {
  const {
    placed,
    taken,
    throttle,
    functions,
    granted,
    noses,
    aspects,
    ahead,
    inFlight,
    stock,
    last,
  } = driving;
  const all: Cab[] = [...placed]
    .sort((one, other) => one.train.localeCompare(other.train))
    .map(({ train, block }) => {
      const nose = noses.get(train) ?? null;
      const holder = taken.get(train);
      return {
        train,
        block,
        taken: holder === undefined ? null : holder === throttle ? "here" : "elsewhere",
        granted: granted.has(train),
        nose,
        aspect: (nose === null ? undefined : aspects.get(nose)) ?? null,
        tailAspect: (nose === null ? undefined : aspects.get(tail(nose))) ?? null,
        ahead: ahead.get(train) ?? [],
        inFlight: inFlight.has(train),
        functions: switches(stock[train]?.functions ?? [], functions.get(train)),
        locomotive: stock[train]?.locomotive ?? null,
        camera: stock[train]?.camera === true,
        last: train === last && holder === undefined,
      };
    });
  return [...all.filter((cab) => cab.last), ...all.filter((cab) => !cab.last)];
}

/** A train's functions by name, each on where `state/functions` says so for
 *  it and off everywhere else. */
function switches(
  declared: readonly Fn[],
  on: ReadonlyMap<string, boolean> | undefined,
): CabFunction[] {
  return declared.map(({ name }) => ({ name, on: on?.get(name) === true }));
}

/** The other end of the block a nose is at: `a.A` for `a.B`. A block has
 *  the two ends a facing runs between (GLOSSARY.md, **Facing**). */
function tail(nose: EndRef): EndRef {
  return `${blockOf(nose)}.${endOf(nose) === "A" ? "B" : "A"}`;
}

/** What a person is told when a gesture would go nowhere, by what the track
 *  is doing. Each names the action that clears it: switching the supply back
 *  on (ADR-0078). */
export const STILL: Record<Power, string | null> = {
  on: null,
  draining: "the railroad is draining — switch it on to drive",
  off: "the track has no power — switch it on to drive",
};

/**
 * Why nothing can be driven, `null` where something can. Only one is ever
 * shown, the first that holds: no broker answering — `linked` is the session's
 * `connected`, false before the first connect and after the broker closes, and
 * a gesture then is swallowed; the words follow `gone()` (`model/session.ts`),
 * which the band shows for the same state — then the track as the layout last
 * said it.
 * A supply not yet heard (`null`) is refused: a train moves only on `on`
 * (ui/THROTTLE.md).
 */
export function driveRefusal(linked: boolean, power: Power | null): string | null {
  if (!linked) return "no broker answering — is the bus running?";
  if (power === null) return "the layout has not said whether the track is live";
  return STILL[power];
}

/** The narrowest a train's column of driving controls is drawn, in CSS
 *  pixels: arrangement A with its slider upright beside it. */
export const COLUMN_PX = 360;

/** The width of the take column, the clock and the trains to take. */
export const TAKE_PX = 260;

/** The gap between columns. */
export const GAP_PX = 14;

/**
 * How many trains' columns fit side by side beside the take column in a view
 * `width` pixels wide, never fewer than none (ui/THROTTLE.md,
 * [#855](https://github.com/rails49/control/issues/855)). None is a phone:
 * no take column, and each held train's controls one below the other.
 */
export function columns(width: number): number {
  return Math.max(0, Math.floor((width - TAKE_PX) / (COLUMN_PX + GAP_PX)));
}
