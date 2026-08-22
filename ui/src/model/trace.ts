/**
 * The live feed's payloads: the frames the bridge relays, read as the events
 * the panel model applies, and the frames the browser may write back.
 *
 * The run view's one source is the bus (ADR-0038). A recorded trace is the
 * harness's — the tap writes it, metrics derive from it and benchmarks assert
 * byte-identical replays — and the browser no longer reads one.
 */

/** One bus event as the model reads it: the boundary the run had reached, the
 *  topic leaf, and the payload's own fields flattened beside them. The shape
 *  the bench tap writes a trace line in, which is what lets one model serve a
 *  recording and a running railroad alike. */
export interface TraceEvent {
  boundary: number;
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
 * browser's side of the contract is here. Frames are stamped with the latest
 * boundary seen, which is what the bench tap does when it writes a trace.
 *
 * The relay's one other frame is `{error}`: a refused inbound frame, or a
 * socket path naming no scenario (#148). It is the whole of what a session
 * says about itself going wrong, so it comes back to be shown as trouble
 * rather than being dropped. A frame that is neither is dropped rather than
 * thrown — a session must not end because a stray one arrived.
 */
export class Live {
  private at: number | null = null;

  /** The latest boundary the session has reached, `null` before the first. */
  get boundary(): number | null {
    return this.at;
  }

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
    if (typeof payload.boundary === "number") this.at = payload.boundary;
    return {
      event: {
        boundary: this.at ?? 0,
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
export const REQUEST_WANTED = "tc49/ui/request_wanted";
export const REVERSAL_WANTED = "tc49/ui/reversal_wanted";
export const RUN_WANTED = "tc49/ui/run_wanted";

/** How a run stands: the dispatcher will commit nothing while it is `held`,
 *  and a person moves it either way
 *  ([ADR-0037](../../../docs/adr/0037-the-run-is-held-or-running-and-held-blocks-commitment.md)).
 *  A word and not a boolean, on the topic and here. */
export type Run = "held" | "running";

/** What the layout says about whether a train may move at all: `on`, or one
 *  of the two ways of standing still — `stopped` is an emergency stop, every
 *  locomotive told to stand with the track still live, and `off` is the supply
 *  removed
 *  ([ADR-0041](../../../docs/adr/0041-the-layout-says-whether-a-train-may-move.md)).
 *  The two differ for the person recovering, who clears one and switches the
 *  other back on, which is why the panel says which. */
export type Power = "on" | "stopped" | "off";

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

/** A `run_wanted` frame: hold the run, or release it. It says where the run
 *  should stand rather than asking for a change, so a press that agrees with
 *  where it already stands is not a race — and the dispatcher is the one
 *  writer of `state/run`, this being a gesture like the other two. */
export function wanted(run: Run): string {
  return JSON.stringify({ topic: RUN_WANTED, payload: { run } });
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
