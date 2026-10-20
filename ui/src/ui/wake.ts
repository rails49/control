/**
 * The screen kept awake while this page's throttle holds a train
 * (ui/THROTTLE.md, [#854](https://github.com/rails49/control/issues/854)).
 *
 * `layout` releases a train whose throttle has been silent for its silence
 * (ADR-0079), and a phone left lying goes to sleep and stops saying
 * `throttle_alive`. So while the page holds a train — on the condition the
 * session's beat runs on, `state/taken` naming this throttle — it holds a
 * screen wake lock, one for any number of trains.
 *
 * The browser drops the lock itself while the page is hidden, and may drop it
 * while the page is shown; it is asked for again when the page is next shown
 * or holding next starts, and never in a loop. A browser with no wake lock, or
 * one that refuses, changes nothing else: no message, no retry.
 *
 * The lock and the document are arguments, so a test passes doubles.
 */

/** The part of `navigator.wakeLock` this asks. */
export type Lock = Pick<WakeLock, "request">;

/** The part of the document this watches. */
export interface Page {
  readonly visibilityState: DocumentVisibilityState;
  addEventListener(type: "visibilitychange", listener: () => void): void;
  removeEventListener(type: "visibilitychange", listener: () => void): void;
}

export class Wake {
  /** Whether the page holds a train, as last said. */
  private holding = false;
  /** The lock held, `null` with none or with the browser having dropped it. */
  private sentinel: WakeLockSentinel | null = null;
  /** A request the browser has not answered yet. */
  private pending = false;

  constructor(
    private readonly lock: Lock | undefined,
    private readonly page: Page,
  ) {
    page.addEventListener("visibilitychange", this.shown);
  }

  /** Whether the page holds a train now. Said on every render; only a change
   *  does anything. */
  hold(holding: boolean): void {
    if (holding === this.holding) return;
    this.holding = holding;
    if (holding) this.ask();
    else this.let();
  }

  /** The app leaving the page: the lock let go, and the page no longer
   *  watched. */
  end(): void {
    this.page.removeEventListener("visibilitychange", this.shown);
    this.hold(false);
  }

  /** Hidden, the browser has dropped the lock; shown again while holding, it
   *  is asked for again. */
  private readonly shown = (): void => {
    if (this.page.visibilityState === "visible") {
      if (this.holding) this.ask();
    } else {
      this.sentinel = null;
    }
  };

  private ask(): void {
    if (this.lock === undefined || this.sentinel !== null || this.pending) return;
    if (this.page.visibilityState !== "visible") return;
    let asked: Promise<WakeLockSentinel>;
    try {
      asked = this.lock.request("screen");
    } catch {
      return;
    }
    this.pending = true;
    asked.then(
      (sentinel) => {
        this.pending = false;
        if (!this.holding) {
          void sentinel.release().catch(() => {});
          return;
        }
        this.sentinel = sentinel;
        sentinel.addEventListener("release", () => {
          if (this.sentinel === sentinel) this.sentinel = null;
        });
      },
      () => {
        this.pending = false;
      },
    );
  }

  private let(): void {
    const sentinel = this.sentinel;
    this.sentinel = null;
    if (sentinel !== null) void sentinel.release().catch(() => {});
  }
}
