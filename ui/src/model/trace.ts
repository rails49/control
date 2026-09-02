/**
 * The live feed's payloads: the frames the bridge relays, read as the events
 * the panel model applies, and the frames the browser may write back.
 *
 * The run view's one source is the bus (ADR-0038). A recorded trace is the
 * harness's — the tap writes it, metrics derive from it and benchmarks assert
 * byte-identical replays — and the browser no longer reads one.
 */

/** One bus event as the model reads it: the topic leaf, and the payload's
 *  own fields flattened beside it. The shape the bench tap writes a trace
 *  line in, minus the tap's own `time` stamp — observation the tap adds for
 *  the harness, and not the `at` a state payload carries of its own
 *  (`Ordering` below, #240). */
export interface TraceEvent {
  event: string;
  [field: string]: unknown;
}

/** What a frame from the relay turned out to be: an event to apply, or the
 *  relay's refusal to show. */
export type Heard = { event: TraceEvent } | { error: string };

/**
 * The live feed: the bridge's frames read as the events the panel model
 * applies (ui/PANEL.md, #72).
 *
 * The relay carries `{topic, payload}` and nothing else — the topic leaf is
 * the event, exactly as SYSTEM.md's inventory has it — so the whole of the
 * browser's side of the contract is here.
 *
 * The relay's one other frame is `{error}`: a refused inbound frame, or a
 * socket path naming no railroad (#148, #171). It is the whole of what a session
 * says about itself going wrong, so it comes back to be shown as trouble
 * rather than being dropped. A frame that is neither is dropped rather than
 * thrown — a session must not end because a stray one arrived.
 */
export class Live {
  read(message: string): Heard | null {
    let frame: { topic?: unknown; payload?: unknown; error?: unknown };
    try {
      frame = JSON.parse(message) as typeof frame;
    } catch {
      return null;
    }
    if (typeof frame?.error === "string") return { error: frame.error };
    if (typeof frame?.topic !== "string" || typeof frame?.payload !== "object") {
      return null;
    }
    const payload = (frame.payload ?? {}) as Record<string, unknown>;
    return {
      event: {
        event: frame.topic.slice(frame.topic.lastIndexOf("/") + 1),
        ...payload,
      },
    };
  }
}

/** The topics the browser may write, and the frames that carry them
 *  (SYSTEM.md, the bridge). Anything else inbound the relay refuses,
 *  `request_submitted` included: the browser writes gestures and never
 *  requests ([ADR-0036](../../../docs/adr/0036-the-scheduler-is-an-app-the-panel-is-a-view.md)). */
export const REQUEST_WANTED = "tc49/schedule/request_wanted";
export const REVERSAL_WANTED = "tc49/schedule/reversal_wanted";
export const MODE_WANTED = "tc49/layout/mode_wanted";
export const THROTTLE_WANTED = "tc49/layout/throttle_wanted";
export const RUN_WANTED = "tc49/dispatch/run_wanted";
export const PLACEMENT_WANTED = "tc49/dispatch/placement_wanted";
export const POWER_WANTED = "tc49/layout/power_wanted";

/** How a run stands: the dispatcher will commit nothing while it is `held`,
 *  it commits everything while it is `running`, and while it is `draining` it
 *  grants the trains already moving and launches nothing
 *  ([ADR-0037](../../../docs/adr/0037-the-run-is-held-or-running-and-held-blocks-commitment.md),
 *  [#294](https://github.com/rails49/control/issues/294)).
 *  An enum and not a boolean, on the topic and here — which is what let the
 *  drain take a third value rather than invent a state of its own. The same
 *  three a person's `run_wanted` may name. */
export type Run = "held" | "running" | "draining";

/** What the layout says about whether a train may move at all: `on`, or one
 *  of the two ways of standing still — `stopped` is an emergency stop, every
 *  locomotive told to stand with the track still live, and `off` is the supply
 *  removed
 *  ([ADR-0041](../../../docs/adr/0041-the-layout-says-whether-a-train-may-move-and-the-run-holds-when-it-may-not.md)).
 *  The two differ for the person recovering, who clears one and switches the
 *  other back on, which is why the panel says which. */
export type Power = "on" | "stopped" | "off";

/** The ordinary shutdown: the run launches nothing more, lets what is
 *  crossing finish, and settles at `held`. Named because OFF is the drain
 *  trigger and this is the word it writes
 *  ([ADR-0051](../../../docs/adr/0051-the-panel-commands-track-power-and-the-operator-is-the-backstop.md)),
 *  and what the OFF sequence then waits for is `held`, which the dispatcher
 *  writes itself when the drain completes
 *  ([#294](https://github.com/rails49/control/issues/294)). `state/run` reads
 *  it back like any other value of the run. */
export const DRAINING = "draining";

/** A `request_wanted` payload: what a drag means. A request minus the two
 *  fields the scheduler owns — no `id`, because the scheduler is the single
 *  minter, and no `depart`, because facing is scheduler state and the drag
 *  never named a departure end. */
export interface Gesture {
  train: string;
  dest: string[];
}

export function gesture(wanted: Gesture): string {
  return JSON.stringify({ topic: REQUEST_WANTED, payload: wanted });
}

/** A `reversal_wanted` frame: turn this train around where it stands. The
 *  train is the whole payload — the gesture asks for the little arrow in its
 *  block to point the other way, and composes no request at all
 *  ([ADR-0019](../../../docs/adr/0019-facing-is-scheduler-state.md)). */
export function reversal(train: string): string {
  return JSON.stringify({ topic: REVERSAL_WANTED, payload: { train } });
}

/** A `placement_wanted` frame: where a train actually is, said by the person
 *  who can see it. `null` is off the layout — one gesture in two directions,
 *  because putting a locomotive on the track and lifting it off are the same
 *  act with a different destination
 *  ([ADR-0039](../../../docs/adr/0039-a-train-may-be-off-the-layout.md)). The
 *  key is always written: the dispatcher reads it for presence, and a frame
 *  without it is not a train taken off the layout. */
export function placement(train: string, block: string | null): string {
  return JSON.stringify({ topic: PLACEMENT_WANTED, payload: { train, block } });
}

/** A `run_wanted` frame: hold the run, release it, or drain it. It says where
 *  the run should stand rather than asking for a change, so a press that
 *  agrees with where it already stands is not a race — and the dispatcher is
 *  the one writer of `state/run`, this being a gesture like the other two. */
export function runWanted(run: Run): string {
  return JSON.stringify({ topic: RUN_WANTED, payload: { run } });
}

/** A `power_wanted` frame: give the track power, stop every locomotive where
 *  it stands, or remove the supply. The same three values the layout reports
 *  on `state/power`, in the command direction — one topic and one axis, so no
 *  consumer has to decide what powered-off-and-emergency-stopped means
 *  (ADR-0041, ADR-0051).
 *
 *  It names where the power should stand rather than asking for a change, as
 *  `run_wanted` does, so a press that agrees with where it already stands is
 *  not a race. `layout` is what answers it, and a page never reaches the
 *  hardware itself. */
export function powerWanted(power: Power): string {
  return JSON.stringify({ topic: POWER_WANTED, payload: { power } });
}

/** Who turns a train's throttle: `automatic` at rest, `manual` while a person
 *  has taken it in a throttle and until they give it back
 *  ([#207](https://github.com/rails49/control/issues/207)). The same two words
 *  the `mode_wanted` gesture names and every entry of the `modes` map on
 *  `tc49/layout/state/mode` carries. Not said of the *system*, which is
 *  **held** or **running** and a different thing on a different topic
 *  (CONTEXT.md). */
export type Mode = "automatic" | "manual";

/** A `mode_wanted` frame: take this train in a throttle, or give it back. It
 *  names where the mode should stand rather than asking for a change, as
 *  `run_wanted` and `power_wanted` do, so a second `manual` on a train
 *  already taken is not a race — and the view goes on reading who drives off
 *  `state/mode`, which `layout` writes and this never assumes (ADR-0035).
 *
 *  The train is always named here. `train: null` on the topic hands over
 *  **every** train at once, which is a thing a person does to a railroad and
 *  not to the train they have picked, so no gesture of this view writes it. */
export function modeWanted(train: string, mode: Mode): string {
  return JSON.stringify({ topic: MODE_WANTED, payload: { train, mode } });
}

/** A `throttle_wanted` frame: how fast a person is driving a train, `-1.0`
 *  … `1.0` as a fraction of that train's maximum, `0.0` being stop.
 *
 *  **Signed for the train and not for a locomotive**: positive is the way the
 *  train points, so one lever drives a top-and-tail set and `layout` composes
 *  the sign each car's decoder is given out of the train's facing and the way
 *  round that car is coupled (CONTEXT.md, **Throttle**; ADR-0045). Which
 *  address it reaches is `layout`'s and no view's. */
export function throttleWanted(train: string, speed: number): string {
  return JSON.stringify({ topic: THROTTLE_WANTED, payload: { train, speed } });
}

/** A `request_submitted` payload: what the scheduler composes out of a
 *  gesture, and what comes back as an event. Ends are written
 *  `<block>.<end>` throughout. */
export interface Submission {
  id: string;
  train: string;
  depart: string;
  dest: string[];
}


/** The leaves of the state topics: the events that carry a last value rather
 *  than reporting something that happened (SYSTEM.md, rule 2).
 *
 *  A leaf and not a topic because the relay hands the model the leaf alone,
 *  which is all `Live` keeps of a frame. The list is the state rows of
 *  `tc49.lib.inventory` and cannot drift from them: a Python test reads it
 *  out of this file and asserts the two match. The device rows under
 *  `tc49/layout/state/wanted/` are not here — a device topic is named by its
 *  row and its address rather than by a leaf, and no view reads one
 *  ([ADR-0043](../../../docs/adr/0043-the-layout-interface-is-a-core-app-and-hardware-hangs-under-it-by-address.md)). */
export const STATE_LEAVES: ReadonlySet<string> = new Set([
  "power",
  "mode",
  "exhausted",
  "facing",
  "run",
  "aspects",
  "disputed",
  "allocation",
]);

/**
 * The stamps a view holds, one per state leaf: what it takes to keep the
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
 * State leaves only. An event reports something that happened and is never
 * replayed, so there is no held value for a late one to lose to, and a
 * repeated sensor reading must go on arriving.
 */
export class Ordering {
  private held = new Map<string, number>();

  /** Whether this event is the one to keep. */
  accepts(event: TraceEvent): boolean {
    if (!STATE_LEAVES.has(event.event)) return true;
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
