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
