/**
 * The broker, as far as the run view uses one: a page connects, subscribes,
 * is answered with the retained rows, is delivered whatever is published
 * after that, and publishes its own gestures back.
 *
 * **It stands where MQTT.js does.** `vite.config.ts` puts this module behind
 * the bare specifier `mqtt` for the test run, so the view's own client is the
 * one thing standing in and what a suite drives is the broker's side of it —
 * which is the side the suites are about. The surface below is the whole of
 * what `tc-panel` asks of MQTT.js: `connect`, `on`, `subscribe`, `publish`
 * and `end`. Reconnecting is the library's and is driven here by hand:
 * `closes()` then `opens()` is what it does on its own.
 *
 * Tests only, and it registers nothing: a suite reaches it through
 * `session.ts`, which re-exports it beside the toy railroad.
 */

/** Whether a topic is one a filter names, over the two wildcards MQTT has.
 *  `tc49/#` is the only filter the view subscribes, but a double that
 *  answered every filter with everything would hide a view that subscribed
 *  the wrong one. */
export function matches(filter: string, topic: string): boolean {
  const wanted = filter.split("/");
  const levels = topic.split("/");
  for (let i = 0; i < wanted.length; i++) {
    if (wanted[i] === "#") return true;
    if (i >= levels.length) return false;
    if (wanted[i] === "+") continue;
    if (wanted[i] !== levels[i]) return false;
  }
  return wanted.length === levels.length;
}

export class Broker {
  /** The client the view opened last, which is the one a suite drives. */
  static last: Broker | null = null;
  /** Every client the view has opened this test, so a suite can ask how many
   *  it left open — one page must be fed by exactly one. */
  static opened: Broker[] = [];

  /** What the page published, in the order it did: the topic and the payload
   *  as text, exactly as MQTT carries them. */
  readonly published: { topic: string; payload: string }[] = [];
  /** The filters the page subscribed. */
  readonly subscriptions: string[] = [];
  /** The last value of each retained topic, which is what answers a
   *  subscription (ADR-0032, ADR-0059 decision 3). */
  readonly retained = new Map<string, string>();
  connected = false;
  ended = false;

  private readonly listeners = new Map<string, ((...args: never[]) => void)[]>();

  constructor(readonly url: string) {
    Broker.last = this;
    Broker.opened.push(this);
  }

  // --- what the client offers the view -------------------------------------

  on(name: string, listener: (...args: never[]) => void): this {
    this.listeners.set(name, [...(this.listeners.get(name) ?? []), listener]);
    return this;
  }

  subscribe(filter: string): this {
    this.subscriptions.push(filter);
    for (const [topic, payload] of this.answering()) {
      if (matches(filter, topic)) this.delivers(topic, payload);
    }
    return this;
  }

  /** The retained rows in the order a subscription is answered with them.
   *
   *  **The railroad row goes last, deliberately.** The contract fixes no
   *  order (SYSTEM.md rule 2), and a view that treats that row as the one
   *  that starts everything will drop whatever the broker handed over before
   *  it. Every suite here used to retain the railroad row first, so the
   *  ordering was fixed in the friendly direction and a whole class of bug
   *  was invisible — a page opening on a held run over an empty picture,
   *  which no event ever repairs (#380).
   *
   *  Fixed and not shuffled: a random order trades an invisible bug for an
   *  irreproducible failure. `sort` is stable, so every other row keeps the
   *  order it was retained in. */
  private answering(): [string, string][] {
    const railroad = "tc49/layout/state/railroad";
    return [...this.retained].sort(
      ([a], [b]) => Number(a === railroad) - Number(b === railroad),
    );
  }

  publish(topic: string, payload: string): this {
    this.published.push({ topic, payload });
    return this;
  }

  end(): this {
    this.ended = true;
    this.connected = false;
    return this;
  }

  // --- what a suite drives -------------------------------------------------

  /** The connection lands. Every retained row the broker holds follows, as
   *  the page's subscription is answered. */
  opens(): void {
    this.connected = true;
    this.raise("connect");
  }

  /** The broker goes, which is what the page sees of a container restarting
   *  or a network that dropped. */
  closes(): void {
    this.connected = false;
    this.raise("close");
  }

  /** There is nothing at the address at all. */
  fails(): void {
    this.raise("error", new Error(`connect ECONNREFUSED ${this.url}`));
  }

  /** What the railroad says, on a topic. A state row is retained and answers
   *  the next subscription; an event is delivered to whoever is listening now
   *  and never replayed (SYSTEM.md rule 2, ADR-0059 decision 1). */
  says(topic: string, payload: Record<string, unknown>): void {
    const body = JSON.stringify(payload);
    if (topic.includes("/state/")) this.retained.set(topic, body);
    if (this.connected) this.delivers(topic, body);
  }

  /** A retained row already on the broker before this page connected: what
   *  every app that is already running has left there. */
  retains(topic: string, payload: Record<string, unknown>): void {
    this.retained.set(topic, JSON.stringify(payload));
  }

  private delivers(topic: string, payload: string): void {
    // Bytes, as MQTT carries them and as MQTT.js hands them over: the view
    // decodes, so a double handing over a string would let a decode that is
    // wrong pass.
    this.raise("message", topic, new TextEncoder().encode(payload));
  }

  private raise(name: string, ...args: unknown[]): void {
    for (const listener of this.listeners.get(name) ?? []) {
      (listener as (...given: unknown[]) => void)(...args);
    }
  }
}

/** `mqtt.connect`, which is the whole of the module's surface here. The
 *  options are the library's business and are not read: what they ask for —
 *  a clean session, and a retry interval — is what the library does with
 *  them, and this double is the broker rather than the library. */
export function connect(url: string, _options?: unknown): Broker {
  return new Broker(url);
}

export default { connect };
