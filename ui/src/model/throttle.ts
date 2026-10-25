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
 * being taken — the one a panel drives is the one `state/taken` names that
 * panel's throttle for. Which throttle that is, is the panel's to compare: a
 * cab names the holder's id and no more (ADR-0089).
 */

import type { Aspect } from "../render/artwork.js";
import { blockOf, endOf, type Ahead, type EndRef, type Placed } from "./panel.js";
import type { Fn, TrainDoc } from "./store.js";
import type { Power } from "./trace.js";

/** One thing a person can switch on a train: its catalogue name, how its
 *  button answers, and whether `state/functions` says it is on. Never what
 *  the person last pressed — a button changes when `layout` says it switched
 *  it (ui/THROTTLE.md). */
export interface CabFunction {
  name: string;
  /** `latching`, on at one press and off at the next, or `momentary`, on
   *  only while its button is held, like a horn (GLOSSARY.md, **Function**).
   *  Whatever the trains route says that is not `momentary` — `latching`, or
   *  nothing from a store older than #977 — latches. */
  mode: "latching" | "momentary";
  on: boolean;
}

/**
 * One train, as a throttle shows it.
 *
 * `holder` is `layout`'s word and never the view's: a train is taken when
 * `state/taken` names a throttle for it and not when somebody pressed for it
 * (ui/THROTTLE.md).
 */
export interface Cab {
  train: string;
  /** The block it stands in, `null` while it is crossing a transit and
   *  stands in none — on the layout all the same (GLOSSARY.md, **Placed**). */
  block: string | null;
  /** The id of the throttle `state/taken` names for it, `null` where it
   *  names none. Which panel that is, if any, each panel works out by
   *  comparing it with its own id (ADR-0089). */
  holder: string | null;
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
  /** Its cars' addresses, head first, as the trains route says; empty where
   *  none has one or the answer leaves the field out. Shown, never written
   *  (#1033). */
  addresses: readonly string[];
  /** Whether a car in it carries a camera, as the trains route says; an
   *  answer that leaves the field out is a train with none. Never where the
   *  camera answers: the `camera` app relays its picture (ADR-0082). */
  camera: boolean;
  /** The blocks on the road in front of it, nearest first. */
  ahead: readonly Ahead[];
  /** What a person driving it can switch, by the names the catalogue gives
   *  them (ADR-0045), in the roster's order, each on or off as
   *  `state/functions` has it. Empty where its cars declare none, which is
   *  most of the stock a railroad owns. */
  functions: readonly CabFunction[];
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
  /** train → function name → on (`state/functions`); a name it does not
   *  give is off. */
  functions: ReadonlyMap<string, ReadonlyMap<string, boolean>>;
  /** The trains with a move outstanding. */
  granted: ReadonlySet<string>;
  noses: ReadonlyMap<string, EndRef>;
  aspects: ReadonlyMap<EndRef, Aspect>;
  ahead: ReadonlyMap<string, readonly Ahead[]>;
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
  const {
    placed,
    taken,
    functions,
    granted,
    noses,
    aspects,
    ahead,
    stock,
  } = driving;
  return [...placed]
    .sort((one, other) => one.train.localeCompare(other.train))
    .map(({ train, block }) => {
      const nose = noses.get(train) ?? null;
      return {
        train,
        block,
        holder: taken.get(train) ?? null,
        granted: granted.has(train),
        nose,
        aspect: (nose === null ? undefined : aspects.get(nose)) ?? null,
        tailAspect: (nose === null ? undefined : aspects.get(tail(nose))) ?? null,
        ahead: ahead.get(train) ?? [],
        functions: switches(stock[train]?.functions ?? [], functions.get(train)),
        locomotive: stock[train]?.locomotive ?? null,
        addresses: stock[train]?.addresses ?? [],
        camera: stock[train]?.camera === true,
      };
    });
}

/** A train's functions by name, each with its mode, and on where
 *  `state/functions` says so for it and off everywhere else. */
function switches(
  declared: readonly Fn[],
  on: ReadonlyMap<string, boolean> | undefined,
): CabFunction[] {
  return declared.map(({ name, mode }) => ({
    name,
    mode: mode === "momentary" ? "momentary" : "latching",
    on: on?.get(name) === true,
  }));
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

/** The widest a throttle's panel is drawn, in CSS pixels: a phone held
 *  upright. A view no wider is one panel exactly its width. */
export const PANEL_PX = 440;

/** The narrowest a panel is drawn side by side with another. */
const NARROWEST_PX = 360;

/** The gap between panels side by side. */
const GAP_PX = 20;

/** The margin round a row of panels, on each side. */
const MARGIN_PX = 8;

/** How a throttle view `width` pixels wide lays out its panels: how many
 *  stand side by side, how wide each is, and whether it is `single` — a
 *  phone, one panel the view's whole width with no margin and no gap. */
export interface Panels {
  count: number;
  width: number;
  single: boolean;
}

/**
 * How many throttles a view `width` pixels wide shows side by side, and how
 * wide each is (ui/THROTTLE.md, ADR-0089). Each panel is the size of a phone
 * screen: no wider than `PANEL_PX`, and no narrower than 360 px beside
 * another. Side by side the row has an 8 px margin, 20 px between panels, and
 * is centred.
 */
export function panels(width: number): Panels {
  if (width <= PANEL_PX) return { count: 1, width, single: true };
  const content = width - 2 * MARGIN_PX;
  const count = Math.max(1, Math.floor((content + GAP_PX) / (NARROWEST_PX + GAP_PX)));
  return {
    count,
    width: Math.min(PANEL_PX, Math.floor((content - GAP_PX * (count - 1)) / count)),
    single: false,
  };
}

/** The shortest and tallest a panel is drawn, in CSS pixels. */
const SHORTEST_PX = 560;
const TALLEST_PX = 834;

/** How tall a panel is in a view `height` pixels tall: the view's height,
 *  less the row's margin top and bottom where it is not `single`, clamped
 *  to 560–834 px. A view too short for it scrolls. */
export function panelHeight(height: number, single: boolean): number {
  const room = single ? height : height - 2 * MARGIN_PX;
  return Math.min(TALLEST_PX, Math.max(SHORTEST_PX, room));
}
