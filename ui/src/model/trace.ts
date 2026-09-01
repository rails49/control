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
export const RUN_WANTED = "tc49/dispatch/run_wanted";
export const PLACEMENT_WANTED = "tc49/dispatch/placement_wanted";
export const POWER_WANTED = "tc49/layout/power_wanted";

/** How a run stands: the dispatcher will commit nothing while it is `held`,
 *  and a person moves it either way
 *  ([ADR-0037](../../../docs/adr/0037-the-run-is-held-or-running-and-held-blocks-commitment.md)).
 *  An enum and not a boolean, on the topic and here. */
export type Run = "held" | "running";

/** What the layout says about whether a train may move at all: `on`, or one
 *  of the two ways of standing still — `stopped` is an emergency stop, every
 *  locomotive told to stand with the track still live, and `off` is the supply
 *  removed
 *  ([ADR-0041](../../../docs/adr/0041-the-layout-says-whether-a-train-may-move-and-the-run-holds-when-it-may-not.md)).
 *  The two differ for the person recovering, who clears one and switches the
 *  other back on, which is why the panel says which. */
export type Power = "on" | "stopped" | "off";

/** The ordinary shutdown: the run launches nothing more, lets what is
 *  crossing finish, and settles at `held`. A third value of `run` and not a
 *  state of its own
 *  ([#123](https://github.com/rails49/control/issues/123)), and the
 *  dispatcher's half of it is
 *  [#294](https://github.com/rails49/control/issues/294). It is written here
 *  because OFF is the drain trigger
 *  ([ADR-0051](../../../docs/adr/0051-the-panel-commands-track-power-and-the-operator-is-the-backstop.md)),
 *  and it is written and never read: `state/run` reads back `held` or
 *  `running`, and what the OFF sequence waits for is `held`. */
export const DRAINING = "draining";

/** What a `run_wanted` may name: where the run should stand. The two values
 *  the run reads back, and the drain that ends at the first of them. */
export type RunWanted = Run | typeof DRAINING;

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

/** A `run_wanted` frame: hold the run, or release it. It says where the run
 *  should stand rather than asking for a change, so a press that agrees with
 *  where it already stands is not a race — and the dispatcher is the one
 *  writer of `state/run`, this being a gesture like the other two. */
export function runWanted(run: RunWanted): string {
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
