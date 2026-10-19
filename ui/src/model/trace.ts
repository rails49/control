/**
 * The bus's payloads: what the broker delivers on a topic, read as the events
 * the panel model applies, and the frames the browser may publish back.
 *
 * The run view's one source is the bus (ADR-0038). A recorded trace is the
 * harness's — the tap writes it, metrics derive from it and benchmarks assert
 * byte-identical replays — and the browser no longer reads one.
 */

import type { Position } from "../symbols.generated.js";

/** One bus event as the model reads it: the topic leaf, and the payload's
 *  own fields flattened beside it. The shape the bench tap writes a trace
 *  line in, minus the tap's own `time` stamp — observation the tap adds for
 *  the harness, and not the `at` a state payload carries of its own
 *  (`Ordering` below, #240). */
export interface TraceEvent {
  event: string;
  [field: string]: unknown;
}

/** One message the browser publishes: the topic, and the payload that goes on
 *  it. A pair and not a wrapper, because the browser is a client of the broker
 *  ([ADR-0059](../../../docs/adr/0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md),
 *  decision 4): what a gesture composes is what MQTT carries, and the session
 *  hands the two straight to `publish`. */
export interface Frame {
  topic: string;
  payload: Record<string, unknown>;
}

/** What a device row's name starts past: the layout interface's own state
 *  prefix, which a device topic carries two levels under where every other
 *  row carries one (`tc49.lib.inventory`,
 *  [ADR-0043](../../../docs/adr/0043-the-layout-interface-is-a-core-app-and-hardware-hangs-under-it-by-address.md)). */
const DEVICE = "tc49/layout/state/";

/** What the model calls the event a message carries: the topic's leaf, except
 *  under the device vocabulary, where it is the two levels past
 *  `tc49/layout/state/`.
 *
 *  The same name `tc49.lib.trace` gives a device row, and for the same reason:
 *  the address is trailing levels a railroad's wiring decides, so the leaf of
 *  `tc49/layout/state/device/sensor/b.A` is `b.A` and says nothing, and
 *  `track` alone would not say which half of the vocabulary a frame is from —
 *  `wanted/track` is what `layout` asked the hardware for and `device/track`
 *  is what the hardware answered (ADR-0043). */
function named(topic: string): string {
  if (topic.startsWith(DEVICE)) {
    const [row, under] = topic.slice(DEVICE.length).split("/");
    if (under !== undefined) return `${row}/${under}`;
  }
  return topic.slice(topic.lastIndexOf("/") + 1);
}

/**
 * The live feed: one message off the broker, read as the event the panel model
 * applies (ui/PANEL.md, #72).
 *
 * A message is a topic and a payload already, and the topic names the event,
 * exactly as BUS.md's inventory has it — so the whole of the browser's side
 * of the contract is here. Retained values arrive as the subscription lands
 * (ADR-0032), which is what a page joining mid-run is fed.
 *
 * A payload that is not a JSON object is dropped rather than thrown — an
 * empty payload is how a retained row is cleared, and a page must not go dark
 * because something published a stray one under `tc49/`.
 */
export class Live {
  read(topic: string, payload: string): TraceEvent | null {
    let body: unknown;
    try {
      body = JSON.parse(payload) as unknown;
    } catch {
      return null;
    }
    if (typeof body !== "object" || body === null || Array.isArray(body)) return null;
    return {
      event: named(topic),
      ...(body as Record<string, unknown>),
    };
  }
}

/** The topics the browser may write, and the frames that carry them
 *  (BUS.md). With anonymous clients a broker cannot tell a page from an
 *  app, so this list is convention rather than enforcement (ADR-0059,
 *  decision 4) — and the browser still writes gestures and never requests,
 *  `request_submitted` included
 *  ([ADR-0036](../../../docs/adr/0036-the-scheduler-is-an-app-the-panel-is-a-view.md)). */
export const REQUEST_WANTED = "tc49/schedule/request_wanted";
export const REVERSAL_WANTED = "tc49/schedule/reversal_wanted";
export const THROTTLE_WANTED = "tc49/layout/throttle_wanted";
export const PLACEMENT_WANTED = "tc49/dispatch/placement_wanted";
export const CANCEL_WANTED = "tc49/dispatch/cancel_wanted";
export const REORDER_WANTED = "tc49/dispatch/reorder_wanted";
export const POINT_WANTED = "tc49/dispatch/point_wanted";
export const POWER_WANTED = "tc49/layout/power_wanted";
export const RAILROAD_WANTED = "tc49/layout/railroad_wanted";
export const DRIVING_WANTED = "tc49/layout/driving_wanted";
export const TAKE_WANTED = "tc49/layout/take_wanted";
export const THROTTLE_ALIVE = "tc49/layout/throttle_alive";

/** What the layout says about whether a train may move at all: `on`;
 *  `draining`, the supply kept on while each moving train stops and nothing
 *  new starts, until `layout` switches it off; or `off`, the supply removed
 *  ([ADR-0078](../../../docs/adr/0078-power-is-on-draining-or-off-and-replaces-go-and-hold.md)).
 *  A word outside the three reads as `off`. */
export type Power = "on" | "draining" | "off";

/** Whether the track has power: `on`, or `draining`, which keeps the supply
 *  on until nothing is moving. A supply not yet heard (`null`) is not live
 *  here; what that means to each rule is the rule's to say. */
export function trackLive(power: Power | null): boolean {
  return power === "on" || power === "draining";
}

/** A `request_wanted` payload: what a drag means. A request minus the two
 *  fields the scheduler owns — no `id`, because the scheduler is the single
 *  minter, and no `depart`, because facing is scheduler state and the drag
 *  never named a departure end. */
export interface Gesture {
  train: string;
  dest: string[];
}

export function gesture(wanted: Gesture): Frame {
  return { topic: REQUEST_WANTED, payload: { ...wanted } };
}

/** A `reversal_wanted` frame: turn this train around where it stands. The
 *  train is the whole payload — the gesture asks for the little arrow in its
 *  block to point the other way, and composes no request at all
 *  ([ADR-0019](../../../docs/adr/0019-facing-is-scheduler-state.md)). */
export function reversal(train: string): Frame {
  return { topic: REVERSAL_WANTED, payload: { train } };
}

/** A `placement_wanted` frame: where a train actually is, said by the person
 *  who can see it. `null` is off the layout — one gesture in two directions,
 *  because putting a locomotive on the track and lifting it off are the same
 *  act with a different destination
 *  ([ADR-0039](../../../docs/adr/0039-a-train-may-be-off-the-layout.md)). The
 *  key is always written: the dispatcher reads it for presence, and a frame
 *  without it is not a train taken off the layout. */
export function placement(train: string, block: string | null): Frame {
  return { topic: PLACEMENT_WANTED, payload: { train, block } };
}

/** A `cancel_wanted` frame: end this request without it arriving. One
 *  waiting is cancelled at once; one underway when the move it has
 *  outstanding ends at its sensor. The requests chained after it go with it
 *  ([ADR-0049](../../../docs/adr/0049-a-request-ends-by-cancellation-as-well-as-by-arrival.md),
 *  [ADR-0080](../../../docs/adr/0080-the-waiting-requests-are-a-list-a-person-orders.md)). */
export function cancellation(id: string): Frame {
  return { topic: CANCEL_WANTED, payload: { id } };
}

/** A `reorder_wanted` frame: move this request in front of `before`, or to
 *  the end of the list the dispatcher serves where `before` is `null`. The
 *  key is always written: a frame without it is dropped, and is not a move
 *  to the end. The dispatcher drops it where either request has started or
 *  is unknown, or where it would put a train's chained request before the
 *  one it follows
 *  ([ADR-0080](../../../docs/adr/0080-the-waiting-requests-are-a-list-a-person-orders.md)). */
export function reorderWanted(id: string, before: string | null): Frame {
  return { topic: REORDER_WANTED, payload: { id, before } };
}

/** What a person asks of a point: the position it should be thrown to, by
 *  the address its motor answers to (ADR-0068). */
export interface PointWanted {
  addr: string;
  position: Position;
}

/** A `point_wanted` frame: throw the point at this address. The dispatcher
 *  is the one that judges it, and drops it with no reply where any point
 *  wearing the address is lit
 *  ([ADR-0068](../../../docs/adr/0068-a-person-throws-a-point-and-the-dispatcher-drops-it-on-a-lit-road.md)). */
export function pointWanted(wanted: PointWanted): Frame {
  return { topic: POINT_WANTED, payload: { ...wanted } };
}

/** A `power_wanted` frame: give the track power, drain it, or remove the
 *  supply at once. The same three values the layout reports on `state/power`,
 *  in the command direction — one topic and one axis (ADR-0051, ADR-0078).
 *
 *  It names where the power should stand rather than asking for a change, so
 *  a press that agrees with where it already stands is
 *  not a race. `layout` is what answers it, and a page never reaches the
 *  hardware itself. */
export function powerWanted(power: Power): Frame {
  return { topic: POWER_WANTED, payload: { power } };
}

/** A `railroad_wanted` frame: load this railroad, the apps staying up. The
 *  gesture behind `tc49/layout/state/railroad`: which railroad the apps run is
 *  a person's choice made **while they run**, so a railroad can be created
 *  from the app and a box wired to steel can carry more than one track plan
 *  over its life
 *  ([ADR-0060](../../../docs/adr/0060-the-railroad-is-chosen-while-the-apps-run-not-at-startup.md)).
 *
 *  The name is the railroad as the store lists it. Whichever binding of the
 *  layout interface is running answers it and publishes the row; the page goes
 *  on reading which railroad is loaded off that row and never off its own
 *  press (ADR-0035), so a gesture that is refused leaves the page showing the
 *  railroad that is still running.
 *
 *  **Track power off is the precondition**, and the settings dialog is what
 *  says so: its list is dead while the rails have power
 *  (`model/settings.ts`), because with the power off nothing moves and no
 *  turnout throws, and the person who turns it back on is the one confirming
 *  the rails match the drawing just loaded (ADR-0051). */
export function railroadWanted(railroad: string): Frame {
  return { topic: RAILROAD_WANTED, payload: { railroad } };
}

/** Who drives the trains, said once for the whole railroad: `manual`, where
 *  people drive every train from throttles, or `automatic`, where the driver
 *  drives every train no throttle holds. The dispatcher routes the same in
 *  both
 *  ([ADR-0079](../../../docs/adr/0079-the-railroad-has-one-driving-mode-and-a-train-one-throttle.md)).
 *  The value of `driving` on `tc49/layout/state/driving` and on the
 *  `driving_wanted` gesture; the railroad comes up `manual`, and an
 *  unreadable `state/driving` reads as `manual`. */
export type DrivingMode = "manual" | "automatic";

/** A `driving_wanted` frame: switch the railroad's driving mode. It names
 *  where the mode should stand rather than asking for a change, as
 *  `power_wanted` does, and is accepted at any power. The view goes on reading
 *  the mode off `state/driving`, which `layout` writes and this never assumes
 *  (ADR-0035). */
export function drivingWanted(driving: DrivingMode): Frame {
  return { topic: DRIVING_WANTED, payload: { driving } };
}

/** A `throttle_wanted` frame: how fast a person is driving a train, `-1.0`
 *  … `1.0` as a fraction of that train's maximum, `0.0` being stop.
 *
 *  **Signed for the train and not for a locomotive**: positive is the way the
 *  train points, so one lever drives a top-and-tail set and `layout` composes
 *  the sign each car's decoder is given out of the train's facing and the way
 *  round that car is coupled (CONTEXT.md, **Throttle**; ADR-0045). Which
 *  address it reaches is `layout`'s and no view's.
 *
 *  `throttle` is the id of the throttle turning the lever, and `layout`
 *  applies the speed only where that throttle holds the train
 *  ([ADR-0079](../../../docs/adr/0079-the-railroad-has-one-driving-mode-and-a-train-one-throttle.md)).
 *  Left out, the frame carries no `throttle` field. */
export function throttleWanted(train: string, speed: number, throttle?: string): Frame {
  return {
    topic: THROTTLE_WANTED,
    payload: throttle === undefined ? { train, speed } : { train, speed, throttle },
  };
}

/** A `take_wanted` frame: this throttle is to hold the train, or, with
 *  `null`, the train is released whoever holds it — the force release a panel
 *  makes is the same frame. A take of a train another throttle holds is
 *  dropped, so the view reads who holds it off `state/taken`, which `layout`
 *  writes and this never assumes (ADR-0035,
 *  [ADR-0079](../../../docs/adr/0079-the-railroad-has-one-driving-mode-and-a-train-one-throttle.md)).
 *
 *  A throttle is named by the id its page mints when it opens, a random
 *  string: it names the throttle holding a train, not who sent a frame. */
export function takeWanted(train: string, throttle: string | null): Frame {
  return { topic: TAKE_WANTED, payload: { train, throttle } };
}

/** A `throttle_alive` frame: this throttle is still here. A throttle says it
 *  once a second while it holds a train, and `layout` releases every train
 *  of one it has not heard for 5 s, so a phone gone to sleep does not leave
 *  a train running at its last speed (ADR-0079). */
export function throttleAlive(throttle: string): Frame {
  return { topic: THROTTLE_ALIVE, payload: { throttle } };
}

/** A `request_submitted` payload: what the scheduler composes out of a
 *  gesture, and what comes back as an event. Ends are written
 *  `<block>.<end>` throughout.
 *
 *  `after` is the id of the train's request this one follows, and is absent
 *  where it follows none. With it `depart` is `null`: the request starts
 *  where the one it follows ends, the dispatcher choosing the departure end
 *  once that one has arrived
 *  ([#820](https://github.com/rails49/control/issues/820)). */
export interface Submission {
  id: string;
  train: string;
  depart: string | null;
  dest: string[];
  after?: string;
}


/** The names of the state topics: the events that carry a last value rather
 *  than reporting something that happened (BUS.md, rule 2).
 *
 *  A name and not a topic because the relay hands the model the name alone,
 *  which is all `Live` keeps of a frame. The list is the state rows of
 *  `tc49.lib.inventory` and cannot drift from them: a Python test reads it
 *  out of this file and asserts the two match. The device rows are here only
 *  where a view reads one, which is `device/track` and nothing else — a
 *  device topic is named by its row and the address under it rather than by a
 *  leaf, so the one a view reads is named as `Live` names it
 *  ([ADR-0043](../../../docs/adr/0043-the-layout-interface-is-a-core-app-and-hardware-hangs-under-it-by-address.md),
 *  [#602](https://github.com/rails49/control/issues/602)).
 *
 *  `moving` is the dispatcher's `state/moving`: a boolean, true while any
 *  train is active or crossing, and a payload that cannot be read says `true`
 *  ([ADR-0078](../../../docs/adr/0078-power-is-on-draining-or-off-and-replaces-go-and-hold.md)). */
export const STATE_NAMES: ReadonlySet<string> = new Set([
  "railroad",
  "power",
  "driving",
  "taken",
  "exhausted",
  "facing",
  "moving",
  "aspects",
  "disputed",
  "unfit",
  "allocation",
  "device/track",
]);

/**
 * The stamps a view holds, one per state name: what it takes to keep the
 * later of two values of one state topic whichever order they arrive in
 * (#240).
 *
 * The browser's half of the rule the dispatcher keeps in `tc49.lib.payload`.
 * MQTT promises order from one publisher on one topic, and not across that
 * publisher's reconnect or a retransmission, so a pair delivered backwards
 * would leave a page showing the older value for good — a signal's aspects,
 * or a track with no power in it.
 *
 * Later wins, an equal stamp replaces, and an earlier one is ignored. An
 * unstamped value is taken and clears the held stamp, so ordering restarts
 * from the next stamped value: the publisher owns the value, and a held
 * stamp must not go on refusing values whose own stamp is gone. A boolean is
 * not a stamp — JSON `true` is not one second.
 *
 * State names only. An event reports something that happened and is never
 * replayed, so there is no held value for a late one to lose to, and a
 * repeated sensor reading must go on arriving.
 */
export class Ordering {
  private held = new Map<string, number>();

  /** Whether this event is the one to keep. */
  accepts(event: TraceEvent): boolean {
    if (!STATE_NAMES.has(event.event)) return true;
    const at = stamp(event);
    if (at === null) {
      this.held.delete(event.event);
      return true;
    }
    const last = this.held.get(event.event);
    if (last !== undefined && at < last) return false;
    this.held.set(event.event, at);
    return true;
  }

  /** Forget every stamp: a page rejoining meets a session whose clock starts
   *  where that session started, and stamps from the last one would refuse
   *  everything the new one says. */
  reset(): void {
    this.held.clear();
  }
}

/** The instant a state payload states it was published at, or `null` where
 *  it states none — seconds since the session started, the run clock's own
 *  reading. A boolean is not a number here, so the one check that keeps a
 *  string out keeps `true` out too; the Python reader has to refuse it in a
 *  line of its own, `True` being an `int` there. */
function stamp(event: TraceEvent): number | null {
  const at = event["at"];
  return typeof at === "number" ? at : null;
}
