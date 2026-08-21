/**
 * A recorded trace: the JSONL the bench tap writes (SYSTEM.md), parsed and
 * stepped one grant boundary at a time.
 *
 * Each line is one bus event stamped with the latest boundary the tap had
 * seen, so a step is simply every line sharing the next stamp: the placement
 * locks a trace opens with belong to boundary 0's step, and everything a
 * boundary caused lands in that boundary's.
 */

/** One recorded bus event: the tap's boundary stamp, the topic leaf, and the
 *  payload's own fields flattened beside them. */
export interface TraceEvent {
  boundary: number;
  event: string;
  [field: string]: unknown;
}

/** Parse a trace file. A line that is not an event is refused by line number:
 *  a trace is a machine-written artefact, and a bad line is the wrong file
 *  rather than something to skim past. */
export function parseTrace(text: string): TraceEvent[] {
  const events: TraceEvent[] = [];
  const lines = text.split("\n");
  for (let at = 0; at < lines.length; at++) {
    const line = lines[at]!.trim();
    if (line === "") continue;
    let parsed: unknown;
    try {
      parsed = JSON.parse(line);
    } catch {
      throw new Error(`line ${at + 1} is not JSON`);
    }
    const event = parsed as TraceEvent;
    if (typeof event?.boundary !== "number" || typeof event?.event !== "string") {
      throw new Error(`line ${at + 1} is not a trace event`);
    }
    events.push(event);
  }
  return events;
}

/** A cursor over a parsed trace, advanced one boundary stamp at a time. */
export class Replay {
  private at = 0;

  constructor(private readonly events: readonly TraceEvent[]) {}

  /** The stamp of the last step taken, `null` before the first. */
  get boundary(): number | null {
    return this.at === 0 ? null : this.events[this.at - 1]!.boundary;
  }

  get done(): boolean {
    return this.at >= this.events.length;
  }

  /** Every event of the next stamp, empty at the end. */
  step(): TraceEvent[] {
    if (this.done) return [];
    const stamp = this.events[this.at]!.boundary;
    const from = this.at;
    while (!this.done && this.events[this.at]!.boundary === stamp) this.at++;
    return this.events.slice(from, this.at);
  }

  restart(): void {
    this.at = 0;
  }
}

/** What a frame from the relay turned out to be: an event to apply, or the
 *  relay's refusal to show. */
export type Heard = { event: TraceEvent } | { error: string };

/**
 * The live feed: the bridge's frames read as the same events a trace holds
 * (ui/PANEL.md, #72).
 *
 * The relay carries `{topic, payload}` and nothing else — the topic leaf is
 * the event, exactly as SYSTEM.md's inventory has it — so the whole of the
 * browser's side of the contract is here, and `Panel.apply` cannot tell a
 * live session from a replay. Frames are stamped with the latest boundary
 * seen, which is what the bench tap does when it writes a trace.
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

/** A `request_submitted` payload: what the scheduler composes out of a
 *  gesture, and what comes back as an event. Ends are written
 *  `<block>.<end>` throughout. */
export interface Submission {
  id: string;
  train: string;
  depart: string;
  dest: string[];
}
