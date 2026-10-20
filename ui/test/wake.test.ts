/**
 * The screen wake lock the page holds while its throttle holds a train
 * (ui/THROTTLE.md, #854), driven with a lock and a page as doubles: what was
 * requested, what was released, and that a browser with no lock or one that
 * refuses changes nothing else.
 *
 * `throttle.test.ts` keeps it end to end through the app, off `state/taken`.
 */

import { describe, expect, it } from "vitest";

import { Wake } from "../src/ui/wake.js";
import { FakeLock, FakePage } from "./support/wake.js";

/** Promise callbacks run, so a request answered at once has landed. */
async function flushed(): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

function waking(): { lock: FakeLock; page: FakePage; wake: Wake } {
  const lock = new FakeLock();
  const page = new FakePage();
  return { lock, page, wake: new Wake(lock, page) };
}

describe("holding", () => {
  it("requests one lock when it starts, and none for a second train", async () => {
    const { lock, wake } = waking();
    wake.hold(true);
    await flushed();
    wake.hold(true);
    await flushed();
    expect(lock.requests).toBe(1);
    expect(lock.held).toBe(1);
  });

  it("releases the lock when it ends", async () => {
    const { lock, wake } = waking();
    wake.hold(true);
    await flushed();
    wake.hold(false);
    await flushed();
    expect(lock.releases).toBe(1);
    expect(lock.held).toBe(0);
  });

  /** The page let go before the browser answered: the lock that arrives is
   *  one nobody wants. */
  it("releases a lock that arrives after it ended", async () => {
    const { lock, wake } = waking();
    lock.answer = "later";
    wake.hold(true);
    await flushed();
    wake.hold(false);
    await flushed();
    lock.arrive();
    await flushed();
    expect(lock.releases).toBe(1);
    expect(lock.held).toBe(0);
  });
});

describe("the page hidden", () => {
  /** The browser drops the lock itself while the page is hidden. */
  it("requests again when shown while holding", async () => {
    const { lock, page, wake } = waking();
    wake.hold(true);
    await flushed();
    page.set("hidden");
    lock.sentinels[0]!.dropped();
    page.set("visible");
    await flushed();
    expect(lock.requests).toBe(2);
    expect(lock.held).toBe(1);
  });

  it("requests nothing when shown after holding ended", async () => {
    const { lock, page, wake } = waking();
    wake.hold(true);
    await flushed();
    page.set("hidden");
    lock.sentinels[0]!.dropped();
    wake.hold(false);
    page.set("visible");
    await flushed();
    expect(lock.requests).toBe(1);
  });
});

describe("the browser dropping the lock while shown", () => {
  it("requests nothing until the page is next shown", async () => {
    const { lock, page, wake } = waking();
    wake.hold(true);
    await flushed();
    lock.sentinels[0]!.dropped();
    await flushed();
    expect(lock.requests).toBe(1);

    page.set("hidden");
    page.set("visible");
    await flushed();
    expect(lock.requests).toBe(2);
  });
});

describe("no lock to have", () => {
  it("throws nothing with no wake lock", async () => {
    const page = new FakePage();
    const wake = new Wake(undefined, page);
    expect(() => {
      wake.hold(true);
      page.set("hidden");
      page.set("visible");
      wake.hold(false);
      wake.end();
    }).not.toThrow();
    await flushed();
  });

  it("throws nothing on a refusal, and asks again when holding next starts", async () => {
    const { lock, wake } = waking();
    lock.answer = "refused";
    wake.hold(true);
    await flushed();
    wake.hold(false);
    lock.answer = "at once";
    wake.hold(true);
    await flushed();
    expect(lock.requests).toBe(2);
    expect(lock.held).toBe(1);
  });
});

describe("end", () => {
  it("releases the lock", async () => {
    const { lock, page, wake } = waking();
    wake.hold(true);
    await flushed();
    wake.end();
    await flushed();
    expect(lock.held).toBe(0);

    page.set("hidden");
    page.set("visible");
    await flushed();
    expect(lock.requests).toBe(1);
  });
});
