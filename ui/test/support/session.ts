/**
 * A live session, as a DOM suite stands one up: the toy railroad it runs on,
 * the fake bridge, and the app joined to it.
 *
 * It sits beside `shell.ts` for the same reason that one exists (#131): the
 * scaffolding is the flake surface, and a second suite needing a joined
 * session should get the one that is already known to work rather than write
 * another. The bridge is the one thing standing in — a `WebSocket` that
 * records what was sent and lets a test deliver the frames a session would.
 *
 * Tests only, and it defines no element: a suite's own
 * `import "../src/ui/tc-app.js"` is what registers `tc-app`.
 */

import type { Drawing } from "../../src/model/drawing.js";
import type { Explained, Layout, Review } from "../../src/model/store.js";
import type { TcApp } from "../../src/ui/tc-app.js";
import { band, CLEAN, mounted, serving, settled } from "./shell.js";

/** The toy railroad's roster: two trains, long enough to be a number on the
 *  pane and short enough for either block. `goods` is the one the suites below
 *  place; `shunter` is the train that is off the layout, which is an ordinary
 *  state and not a fault (ADR-0039). */
export const STOCK = { goods: { length: 400 }, shunter: { length: 200 } };

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

/** The bridge, as far as the run view uses one: it opens, it is sent frames,
 *  and it delivers them. */
export class Bridge {
  static last: Bridge | null = null;

  readonly sent: string[] = [];
  private readonly listeners = new Map<string, ((event: unknown) => void)[]>();

  constructor(readonly url: string) {
    Bridge.last = this;
  }

  addEventListener(name: string, listener: (event: unknown) => void): void {
    this.listeners.set(name, [...(this.listeners.get(name) ?? []), listener]);
  }

  send(frame: string): void {
    this.sent.push(frame);
  }

  close(): void {
    this.raise("close", {});
  }

  /** What the session says, in the frames the relay carries. */
  says(topic: string, payload: Record<string, unknown>): void {
    this.raise("message", { data: JSON.stringify({ topic, payload }) });
  }

  raise(name: string, event: Record<string, unknown>): void {
    for (const listener of this.listeners.get(name) ?? []) listener(event);
  }
}

const REAL = globalThis.WebSocket;

/** Put the fake bridge behind `WebSocket` and the toy railroad behind the
 *  store: what a suite about a live session needs before each test. */
export function bridging(): void {
  Bridge.last = null;
  globalThis.WebSocket = Bridge as unknown as typeof WebSocket;
  serving({
    drawings: ["toy"],
    rosterOf: () => STOCK,
    read: stored,
    review: () => Promise.resolve(DERIVES),
  });
}

/** The real `WebSocket` back, and the page cleared. */
export function unbridged(): void {
  globalThis.WebSocket = REAL;
  document.body.replaceChildren();
}

/** The band's picker, pressed. It is the only thing that loads a railroad
 *  (#171), and the run view joins whatever the app holds — so a session is
 *  stood up, and swapped, by loading a railroad and nothing else. */
export async function loads(shell: TcApp, railroad: string): Promise<void> {
  band(shell).dispatchEvent(
    new CustomEvent<string>("railroad-wanted", {
      detail: railroad,
      bubbles: true,
      composed: true,
    }),
  );
  await settled(shell);
  Bridge.last!.raise("open", {});
  await settled(shell);
}

/** An app in the run view with the toy railroad loaded and the bridge open. */
export async function joined(): Promise<TcApp> {
  const shell = await mounted("run");
  await loads(shell, "toy");
  return shell;
}

/** What the session has published, applied. */
export async function said(
  shell: TcApp,
  topic: string,
  payload: Record<string, unknown>,
): Promise<void> {
  Bridge.last!.says(topic, payload);
  await settled(shell);
}

/** The payloads the browser has written to the bus. */
export function written(): unknown[] {
  return (Bridge.last?.sent ?? []).map((frame) => JSON.parse(frame));
}
