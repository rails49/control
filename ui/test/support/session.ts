/**
 * A live session, as a DOM suite stands one up: the toy railroad it runs on,
 * the broker it runs on, and the app joined to it.
 *
 * It sits beside `shell.ts` for the same reason that one exists (#131): the
 * scaffolding is the flake surface, and a second suite needing a joined
 * session should get the one that is already known to work rather than write
 * another. The broker is the one thing standing in (`broker.ts`), and it is
 * re-exported here so a suite reaches for one module.
 *
 * Tests only, and it defines no element: a suite's own
 * `import "../src/ui/tc-app.js"` is what registers `tc-app`.
 */

import type { Drawing } from "../../src/model/drawing.js";
import { centreOf, type Point } from "../../src/model/geometry.js";
import type { Explained, Layout, Review } from "../../src/model/store.js";
import type { ViewId } from "../../src/model/views.js";
import type { TcApp } from "../../src/ui/tc-app.js";
import { Broker } from "./broker.js";
import { CLEAN, mounted, serving, settled } from "./shell.js";

export { Broker } from "./broker.js";

/** The row the layout interface publishes to say which railroad this broker
 *  runs (#371). It is the whole of the page's choice of railroad. */
export const RAILROAD = "tc49/layout/state/railroad";

/** The toy railroad's roster: two trains, long enough to be a number on the
 *  pane and short enough for either block. `goods` is the one the suites below
 *  place; `shunter` is the train that is off the layout, which is an ordinary
 *  state and not a fault (ADR-0039). */
export const STOCK = {
  goods: {
    length: 400,
    // What a person driving `goods` can switch, by the names a catalogue
    // gives them: the throttle's whole source for its buttons (ADR-0045).
    functions: [
      { name: "headlights", values: ["off", "on"] },
      { name: "vacuum", values: ["off", "low", "high"] },
    ],
  },
  // Nothing to switch, which is most of the stock a railroad owns.
  shunter: { length: 200 },
};

/** Two blocks and nothing joining them: enough to derive, enough to paint, and
 *  enough for a train to stand, be dragged and be disputed in. */
export const LAYOUT: Layout = {
  layout: "toy",
  blocks: { a: { length: 1000 }, b: { length: 1000 } },
  connections: {},
};

export const EXPLAIN: Explained = { layout: "toy", connections: {} };

/** What the store says the toy railroad means: it derives, and nothing about
 *  it is wrong. */
export const DERIVES: Review = { ...CLEAN, layout: LAYOUT, explain: EXPLAIN };

/** The drawing the toy layout derives from, as the store answers with it. */
export function stored(name: string): Drawing {
  return {
    drawing: name,
    symbols: { a: { kind: "block", at: [0, 0] }, b: { kind: "block", at: [4, 0] } },
    wires: [],
  };
}

/** Where each block's middle is. happy-dom's `getScreenCTM` is the identity,
 *  so a grid point reads as a client pixel and back. It sits here rather than
 *  beside the accessors in `shell.ts`, being a fact about the toy drawing
 *  above and not about the app. */
export const MIDDLE = {
  a: centreOf(stored("toy").symbols.a!),
  b: centreOf(stored("toy").symbols.b!),
};

/** A square the drawing above puts no symbol on, far from both blocks, where
 *  a right-click opens no menu of ours and still suppresses the browser's.
 *  Beside `MIDDLE` for the same reason: a fact about that drawing. */
export const PAPER: Point = { x: 2, y: 6 };

/** The broker behind `mqtt` reset, and the toy railroad behind the store:
 *  what a suite about a live session needs before each test. */
export function brokering(): void {
  Broker.last = null;
  Broker.opened = [];
  serving({
    drawings: ["toy"],
    rosterOf: () => STOCK,
    read: stored,
    review: () => Promise.resolve(DERIVES),
  });
}

/** The broker let go of, and the page cleared. Clearing the page is what ends
 *  the connection: the view holds it for as long as it is on screen. */
export function unbrokered(): void {
  document.body.replaceChildren();
  Broker.last = null;
  Broker.opened = [];
}

/** The railroad this broker runs, on the retained row that says so (#371).
 *  It is the only thing that loads one — the band has no picker, switching
 *  railroads being restarting the apps (ADR-0059, decision 2) — so a session
 *  is stood up, and swapped, by the broker saying which railroad it is and
 *  nothing else. */
export async function loads(shell: TcApp, railroad: string): Promise<void> {
  const broker = Broker.last!;
  if (broker.connected) {
    broker.says(RAILROAD, { name: railroad });
  } else {
    broker.retains(RAILROAD, { name: railroad });
    broker.opens();
  }
  await settled(shell);
}

/** An app with the toy railroad loaded and the broker answering, showing the
 *  run view or another: the session is the run view's whichever is on screen,
 *  so a suite about the throttle joins the same way (ui/THROTTLE.md). */
export async function joined(view: ViewId = "run"): Promise<TcApp> {
  const shell = await mounted(view);
  await loads(shell, "toy");
  return shell;
}

/** What the railroad has published, applied. */
export async function said(
  shell: TcApp,
  topic: string,
  payload: Record<string, unknown>,
): Promise<void> {
  Broker.last!.says(topic, payload);
  await settled(shell);
}

/** The payloads the browser has published to the bus, each with the topic it
 *  went out on. */
export function written(): unknown[] {
  return (Broker.last?.published ?? []).map(({ topic, payload }) => ({
    topic,
    payload: JSON.parse(payload) as unknown,
  }));
}
