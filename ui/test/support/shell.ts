/**
 * The app the DOM suites stand up, and the parts of it they reach for,
 * written once (#131).
 *
 * Five suites each forged their own `globalThis.fetch`, and four of those
 * respelled the same microtask wait with a hand-tuned loop count — `< 5`,
 * `< 8`, `< 5`, `< 10`. The counts were the flake surface: each was tuned to
 * the render depth its own suite happened to need, so a component gaining one
 * await turn broke whichever suite had guessed lowest. Nothing here counts
 * turns for a caller: `quiet` turns the queue until the store has been left
 * alone, under one bound generous enough for every suite. It is private to
 * `settled`, the wait being a DOM suite's alone (#149): a suite driving a
 * model against a fake dependency has the call itself to await, and watching
 * this counter would be waiting on a store nothing put behind `fetch`.
 *
 * Tests only — nothing under `src` imports this, and it defines no element
 * either. A suite's own `import "../src/ui/tc-app.js"` is what registers
 * `tc-app`, and that import is what makes it a DOM suite.
 */

import type { Drawing } from "../../src/model/drawing.js";
import type { Editor } from "../../src/model/editor.js";
import type { Review } from "../../src/model/store.js";
import type { ViewId } from "../../src/model/views.js";
import type { TcApp } from "../../src/ui/tc-app.js";
import type { TcEditor } from "../../src/ui/tc-editor.js";
import type { TcHeader } from "../../src/ui/tc-header.js";
import type { TcMenubar } from "../../src/ui/tc-menubar.js";
import type { TcPanel } from "../../src/ui/tc-panel.js";

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
  /** The ids `/scenarios` lists, which is what the run view asks for. */
  scenarios: string[];
  /** Which railroad a scenario names, which is the one thing the run view
   *  reads a scenario for. */
  layoutOf: (id: string) => string;
  /** What `/drawings/<name>` answers with. */
  read: (name: string) => Drawing;
  /** What `/review` answers with. */
  review: () => Promise<Review>;
  /** A failure every route rejects with instead of answering, which is what a
   *  store that is not running looks like from here. */
  broken: Error | null;
}

/** How often the store has been asked anything. `quiet` watches this instead
 *  of counting turns, so what it waits for is the shell falling silent. */
let asked = 0;

/** Put a store behind `fetch` for the suite, answering `answers` and its own
 *  defaults for the rest. */
export function serving(answers: Partial<Answers> = {}): Answers {
  const store: Answers = {
    drawings: [],
    scenarios: [],
    layoutOf: (id) => id.split("/")[0]!,
    read: (name) => {
      throw new Error(`no drawing '${name}'`);
    },
    review: () => Promise.resolve(CLEAN),
    broken: null,
    ...answers,
  };
  globalThis.fetch = ((path: string) => {
    asked += 1;
    if (store.broken !== null) return Promise.reject(store.broken);
    return answered(store, path).then(
      (body) =>
        ({ ok: true, json: () => Promise.resolve(body) }) as unknown as Response,
    );
  }) as unknown as typeof fetch;
  return store;
}

/** The store's side of one call, over the routes the editor asks
 *  (EDITOR.md#implementation). */
function answered(store: Answers, path: string): Promise<unknown> {
  if (path === "/review") return store.review();
  if (path === "/drawings") return Promise.resolve({ drawings: [...store.drawings] });
  if (path === "/scenarios") {
    return Promise.resolve({ scenarios: [...store.scenarios] });
  }
  if (path.startsWith("/scenarios/")) {
    const id = decodeURIComponent(path.slice("/scenarios/".length));
    return Promise.resolve({ name: id, layout: store.layoutOf(id) });
  }
  const name = decodeURIComponent(path.slice("/drawings/".length));
  return Promise.resolve(store.read(name));
}

/** Turns to keep the queue moving after the last ask: enough for the longest
 *  chain an answer is delivered down, and generous because a microtask costs
 *  nothing. */
const QUIET = 20;

/** The one bound there is: a shell that never stops asking gives the wait up
 *  and fails on its assertion, rather than hanging the run. */
const BOUND = 500;

/** Turn the microtask queue until the store has been left alone: every answer
 *  in flight delivered, and every ask an answer set off answered in turn. */
async function quiet(): Promise<void> {
  let idle = 0;
  for (let turn = 0; idle < QUIET && turn < BOUND; turn++) {
    const was = asked;
    await Promise.resolve();
    idle = asked === was ? idle + 1 : 0;
  }
}

/** Let the store answers in flight settle, then let Lit paint what they said —
 *  the app, the views inside it and what those drew, the band included. */
export async function settled(shell: TcApp): Promise<void> {
  await quiet();
  await painted(shell);
}

/** One element and everything inside its shadow root, painted. The views nest
 *  a level deeper than the band and the bar, so this walks rather than reading
 *  one level. */
async function painted(part: Element): Promise<void> {
  const painting = (part as Element & { updateComplete?: Promise<boolean> })
    .updateComplete;
  if (painting !== undefined) await painting;
  const inside = (part as Element & { renderRoot?: ParentNode }).renderRoot;
  if (inside === undefined) return;
  for (const child of inside.querySelectorAll("*")) await painted(child);
}

/** A mounted app, settled, showing `view`: what every DOM suite starts from.
 *  The view is set the way an operator sets it, in the hash. */
export async function mounted(view: ViewId = "edit"): Promise<TcApp> {
  location.hash = `#${view}`;
  const shell = document.createElement("tc-app");
  document.body.append(shell);
  await settled(shell);
  return shell;
}

/** The editing session the app is holding. It is the component's own, and
 *  reaching through for it is how a DOM suite drives the document. */
export function session(shell: TcApp): Editor {
  return (shell as unknown as { editor: Editor }).editor;
}

/** The band across the top, where what is true of the whole system reads. */
export function band(shell: TcApp): TcHeader {
  return shell.renderRoot.querySelector("tc-header")!;
}

/** The bar under it, which carries the current view's menus. */
export function bar(shell: TcApp): TcMenubar {
  return shell.renderRoot.querySelector("tc-menubar")!;
}

/** The editing view, and whatever it has drawn inside itself. */
export function editing(shell: TcApp): TcEditor {
  return shell.renderRoot.querySelector("tc-editor")!;
}

/** The run view, and whatever it has drawn inside itself. */
export function running(shell: TcApp): TcPanel {
  return shell.renderRoot.querySelector("tc-panel")!;
}

/** One of the editing view's own parts, by tag. The views nest inside the app,
 *  so a suite reaching for a canvas or a dialog says which view's it is. */
export function inside(shell: TcApp, tag: string): Element {
  return editing(shell).renderRoot.querySelector(tag)!;
}

/** An edit, as the canvas reports one. */
export function edited(shell: TcApp): void {
  inside(shell, "tc-canvas").dispatchEvent(
    new CustomEvent("edit", { bubbles: true, composed: true }),
  );
}
