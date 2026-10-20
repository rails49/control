/**
 * A screen wake lock and a page, as doubles (`src/ui/wake.ts`, #854).
 *
 * The lock counts what it was asked for and what was let go of, and holds a
 * request open until the test answers it, so a suite can say what happens to
 * a lock that arrives after the page stopped wanting it. The page is a
 * `visibilityState` the test sets and the `visibilitychange` it fires.
 */

/** One lock the double handed out, released by the page or by the browser. */
export class Sentinel extends EventTarget {
  released = false;
  readonly type = "screen" as const;
  onrelease = null;

  constructor(private readonly lock: FakeLock) {
    super();
  }

  release(): Promise<void> {
    if (!this.released) {
      this.released = true;
      this.lock.releases += 1;
    }
    return Promise.resolve();
  }

  /** The browser dropping it: the `release` event, which the page did not ask
   *  for. */
  dropped(): void {
    this.released = true;
    this.dispatchEvent(new Event("release"));
  }
}

export class FakeLock {
  requests = 0;
  releases = 0;
  /** Whether a request is answered at once, kept open, or refused. */
  answer: "at once" | "later" | "refused" = "at once";
  /** Every lock handed out, in order. */
  readonly sentinels: Sentinel[] = [];
  private waiting: (() => void)[] = [];

  request(type: "screen"): Promise<WakeLockSentinel> {
    void type;
    this.requests += 1;
    if (this.answer === "refused") {
      return Promise.reject(new DOMException("not allowed", "NotAllowedError"));
    }
    const sentinel = new Sentinel(this);
    this.sentinels.push(sentinel);
    if (this.answer === "at once") return Promise.resolve(sentinel as unknown as WakeLockSentinel);
    return new Promise((resolve) => {
      this.waiting.push(() => resolve(sentinel as unknown as WakeLockSentinel));
    });
  }

  /** Answer the requests kept open, with the locks they were promised. */
  arrive(): void {
    const waiting = this.waiting;
    this.waiting = [];
    for (const resolve of waiting) resolve();
  }

  /** The locks handed out and not released, by the page or the browser. */
  get held(): number {
    return this.sentinels.filter((one) => !one.released).length;
  }
}

/** A page whose visibility the test sets. */
export class FakePage extends EventTarget {
  visibilityState: DocumentVisibilityState = "visible";

  /** Hidden or shown, with the event the browser fires. */
  set(state: DocumentVisibilityState): void {
    this.visibilityState = state;
    this.dispatchEvent(new Event("visibilitychange"));
  }
}
