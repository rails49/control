/**
 * A recorded trace: the JSONL the bench tap writes (SYSTEM.md), parsed and
 * stepped tick by tick.
 *
 * Each line is one bus event stamped with the latest tick the tap had seen,
 * so a step is simply every line sharing the next stamp: the placement locks
 * a trace opens with belong to tick 0's step, and everything a tick caused
 * lands in that tick's.
 */

/** One recorded bus event: the tap's tick stamp, the topic leaf, and the
 *  payload's own fields flattened beside them. */
export interface TraceEvent {
  tick: number;
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
    if (typeof event?.tick !== "number" || typeof event?.event !== "string") {
      throw new Error(`line ${at + 1} is not a trace event`);
    }
    events.push(event);
  }
  return events;
}

/** A cursor over a parsed trace, advanced one tick stamp at a time. */
export class Replay {
  private at = 0;

  constructor(private readonly events: readonly TraceEvent[]) {}

  /** The stamp of the last step taken, `null` before the first. */
  get tick(): number | null {
    return this.at === 0 ? null : this.events[this.at - 1]!.tick;
  }

  get done(): boolean {
    return this.at >= this.events.length;
  }

  /** Every event of the next stamp, empty at the end. */
  step(): TraceEvent[] {
    if (this.done) return [];
    const stamp = this.events[this.at]!.tick;
    const from = this.at;
    while (!this.done && this.events[this.at]!.tick === stamp) this.at++;
    return this.events.slice(from, this.at);
  }

  restart(): void {
    this.at = 0;
  }
}

/**
 * The live feed: the bridge's frames read as the same events a trace holds
 * (ui/PANEL.md, #72).
 *
 * The relay carries `{topic, payload}` and nothing else — the topic leaf is
 * the event, exactly as SYSTEM.md's inventory has it — so the whole of the
 * browser's side of the contract is here, and `Panel.apply` cannot tell a
 * live session from a replay. Frames are stamped with the latest tick seen,
 * which is what the bench tap does when it writes a trace.
 *
 * A frame that is not one is dropped rather than thrown: the bridge answers a
 * refused frame with an `{error}` of its own, and a session must not end
 * because one arrived.
 */
export class Live {
  private at: number | null = null;

  /** The latest tick the session has reached, `null` before the first. */
  get tick(): number | null {
    return this.at;
  }

  read(message: string): TraceEvent | null {
    let frame: { topic?: unknown; payload?: unknown };
    try {
      frame = JSON.parse(message) as { topic?: unknown; payload?: unknown };
    } catch {
      return null;
    }
    if (typeof frame?.topic !== "string" || typeof frame?.payload !== "object") {
      return null;
    }
    const payload = (frame.payload ?? {}) as Record<string, unknown>;
    if (typeof payload.tick === "number") this.at = payload.tick;
    return {
      tick: this.at ?? 0,
      event: frame.topic.slice(frame.topic.lastIndexOf("/") + 1),
      ...payload,
    };
  }
}

/** The one topic the browser may write, and the frame that carries it
 *  (SYSTEM.md, the bridge). Anything else inbound the relay refuses. */
export const INBOUND = "tc49/schedule/request_submitted";

export function submission(payload: Record<string, unknown>): string {
  return JSON.stringify({ topic: INBOUND, payload });
}
