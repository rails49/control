/**
 * The shell the editor's DOM suites stand up, written once (#131).
 *
 * Five suites each forged their own `globalThis.fetch`, and four of those
 * respelled the same microtask wait with a hand-tuned loop count — `< 5`,
 * `< 8`, `< 5`, `< 10`. The counts were the flake surface: each was tuned to
 * the render depth its own suite happened to need, so a component gaining one
 * await turn broke whichever suite had guessed lowest. Nothing here counts
 * turns for a caller: `quiet` turns the queue until the store has been left
 * alone, under one bound generous enough for every suite.
 *
 * Tests only — nothing under `src` imports this, and it defines no element
 * either. A suite's own `import "../src/ui/tc-editor.js"` is what registers
 * `tc-editor`, and that import is what makes it a DOM suite.
 */

import type { Drawing } from "../../src/model/drawing.js";
import type { Editor } from "../../src/model/editor.js";
import type { Review } from "../../src/model/store.js";
import type { TcEditor } from "../../src/ui/tc-editor.js";

/** A drawing the store is happy with: nothing to report. */
export const CLEAN: Review = {
  red_pins: [],
  unpaired_portals: [],
  junctions: [],
  joints: [],
  motor_faults: [],
  layout: null,
  explain: null,
  refused: null,
  offending: [],
};

/** What the store answers on each of the routes the editor asks. A suite
 *  hands `serving` the ones it cares about and leaves the rest, and swaps any
 *  of them mid-test on the handle it gets back. */
export interface Answers {
  /** The names `/drawings` lists. */
  drawings: string[];
  /** What `/drawings/<name>` answers with. */
  read: (name: string) => Drawing;
  /** What `/review` answers with. */
  review: () => Promise<Review>;
  /** A failure every route rejects with instead of answering, which is what a
   *  store that is not running looks like from here. */
  broken: Error | null;
  /** What was saved, in the order it was written: the only way to see that a
   *  save happened at all. */
  written: Drawing[];
}

/** How often the store has been asked anything. `quiet` watches this instead
 *  of counting turns, so what it waits for is the shell falling silent. */
let asked = 0;

/** Put a store behind `fetch` for the suite, answering `answers` and its own
 *  defaults for the rest. */
export function serving(answers: Partial<Answers> = {}): Answers {
  const store: Answers = {
    drawings: [],
    read: (name) => {
      throw new Error(`no drawing '${name}'`);
    },
    review: () => Promise.resolve(CLEAN),
    broken: null,
    written: [],
    ...answers,
  };
  globalThis.fetch = ((path: string, sent: RequestInit = {}) => {
    asked += 1;
    if (store.broken !== null) return Promise.reject(store.broken);
    return answered(store, path, sent).then(
      (body) =>
        ({ ok: true, json: () => Promise.resolve(body) }) as unknown as Response,
    );
  }) as unknown as typeof fetch;
  return store;
}

/** The store's side of one call (EDITOR.md#implementation). */
function answered(
  store: Answers,
  path: string,
  sent: RequestInit,
): Promise<unknown> {
  if (path === "/review") return store.review();
  if (path === "/drawings") return Promise.resolve({ drawings: [...store.drawings] });
  if (sent.method === "PUT") {
    store.written.push(JSON.parse(sent.body as string) as Drawing);
    return Promise.resolve({});
  }
  return Promise.resolve(store.read(decodeURIComponent(path.slice("/drawings/".length))));
}

/** Turns to keep the queue moving after the last ask: enough for the longest
 *  chain an answer is delivered down, and generous because a microtask costs
 *  nothing. */
const QUIET = 20;

/** The one bound there is, so a shell that asks forever fails the run rather
 *  than hanging it. */
const BOUND = 500;

/** Turn the microtask queue until the store has been left alone: every answer
 *  in flight delivered, and every ask an answer set off answered in turn. */
export async function quiet(): Promise<void> {
  let idle = 0;
  for (let turn = 0; idle < QUIET && turn < BOUND; turn++) {
    const was = asked;
    await Promise.resolve();
    idle = asked === was ? idle + 1 : 0;
  }
}

/** Let the store answers in flight settle, then let Lit paint what they said —
 *  the shell and what it drew inside it, the band included. */
export async function settled(shell: TcEditor): Promise<void> {
  await quiet();
  await shell.updateComplete;
  for (const part of shell.renderRoot.querySelectorAll("*")) {
    const painting = (part as Element & { updateComplete?: Promise<boolean> })
      .updateComplete;
    if (painting !== undefined) await painting;
  }
}

/** A mounted editor, settled: what every DOM suite starts from. */
export async function mounted(): Promise<TcEditor> {
  const shell = document.createElement("tc-editor");
  document.body.append(shell);
  await settled(shell);
  return shell;
}

/** The editor the shell is holding. It is the component's own, and reaching
 *  through for it is how a DOM suite drives the document. */
export function session(shell: TcEditor): Editor {
  return (shell as unknown as { editor: Editor }).editor;
}
