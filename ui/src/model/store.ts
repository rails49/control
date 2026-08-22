/**
 * The store's routes (EDITOR.md, PANEL.md), the shapes they answer with, and
 * nothing else.
 *
 * `review` is the whole of the editor's view of topology: red pins, the portal
 * labels that pair with nothing, the junctions as symbol groups, the derived
 * layout, its explanation, the refusal where there is one, and the way that
 * refusal is about where it is about one. A drawing with a red pin is the
 * normal state mid-edit, so a refusal arrives inside a 200 and is read rather
 * than caught.
 */

import type { Drawing } from "./drawing.js";

export interface Junction {
  /** `null` where the drawing has not settled one. */
  name: string | null;
  /** What its symbols write as `connection`: nothing is a junction to be
   *  minted, several is a disagreement someone typed. */
  names: string[];
  symbols: string[];
}

/** A way from one block end to another crossing no connection symbol. It is a
 *  connection in itself, and one of its own wires carries the name. */
export interface Joint {
  ends: [string, string];
  wires: [string, string][];
  name: string | null;
  names: string[];
}

export interface Transit {
  ends: [string, string];
  /** The symbols and legs the way took, in order. */
  way: [string, string][];
}

export interface Exclusive {
  transits: [string, string];
  /** The symbols the two ways share that stop them running together. */
  shared: string[];
}

export interface Explained {
  layout: string;
  connections: Record<
    string,
    { transits: Record<string, Transit>; exclusive: Exclusive[] }
  >;
}

export interface Layout {
  layout: string;
  units?: string;
  blocks: Record<string, { length: number }>;
  connections: Record<
    string,
    { transits: Record<string, [string, string]>; concurrent?: [string, string][] }
  >;
}

/**
 * The pair of block ends a transit resource joins, or `undefined` where this
 * layout has no such connection or no such transit within it.
 *
 * A resource is written `<connection>.<transit>` on the bus, and what that
 * means is the layout's: a view that split the string and walked the two
 * levels itself would be a second party deciding it. `undefined` is not a
 * fault — a page can be showing another railroad than the picture is about
 * (#175).
 */
export function transitEnds(
  layout: Layout,
  resource: string,
): [string, string] | undefined {
  const [connection, transit] = resource.split(".");
  return layout.connections[connection]?.transits[transit];
}

/** A portal label not worn by exactly two portals — worn once, or worn three
 *  times and more — with the portals wearing it. A label pairs exactly two, so
 *  both are one fault. The refusal names one label and stops, which is why
 *  this is a list. */
export interface UnpairedPortal {
  label: string;
  portals: string[];
}

/** One address wanted in both positions at once. Points sharing an `addr`
 *  answer to one accessory output and move together, so a way needing two of
 *  them set differently cannot be thrown, and two ways declared concurrent
 *  cannot be thrown at once. `transits` is one way for the first and the two
 *  for the second. */
export interface MotorFault {
  connection: string;
  addr: string;
  transits: string[];
  positions: Record<string, string[]>;
}

export interface Review {
  red_pins: string[];
  unpaired_portals: UnpairedPortal[];
  junctions: Junction[];
  joints: Joint[];
  motor_faults: MotorFault[];
  layout: Layout | null;
  explain: Explained | null;
  refused: string | null;
  /** The way or ways a refusal is about, walked where derivation refused. A
   *  refusal about anything else offends no way and this is empty. */
  offending: Transit[];
}

/** What a drawing the store has not answered for yet reads as: nothing red,
 *  nothing unpaired, nothing derived. A surface painting before the first
 *  answer has arrived reads this rather than branching on a null. */
export const UNREVIEWED: Review = {
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

export async function listDrawings(): Promise<string[]> {
  return (await ask<{ drawings: string[] }>("GET", "/drawings")).drawings;
}

export async function readDrawing(name: string): Promise<Drawing> {
  return await ask<Drawing>("GET", `/drawings/${encodeURIComponent(name)}`);
}

export async function saveDrawing(drawing: Drawing): Promise<void> {
  await ask("PUT", `/drawings/${encodeURIComponent(drawing.drawing)}`, drawing);
}

export async function review(drawing: Drawing): Promise<Review> {
  return await ask<Review>("POST", "/review", drawing);
}

/** The scenario a live session was started from. The panel reads it for one
 *  thing, which drawing to render: nothing retained says which railroad a
 *  session runs, and a topic that did would be the bridge describing the run
 *  (#67, ADR-0036). Stock, placement and facing come off the bus. */
export interface ScenarioDoc {
  name: string;
  layout: string;
}

export async function listScenarios(): Promise<string[]> {
  return (await ask<{ scenarios: string[] }>("GET", "/scenarios")).scenarios;
}

export async function readScenario(id: string): Promise<ScenarioDoc> {
  return await ask<ScenarioDoc>("GET", `/scenarios/${id}`);
}

async function ask<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    ...(body === undefined
      ? {}
      : {
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }),
  });
  const payload = (await response.json()) as T & { error?: string };
  if (!response.ok) {
    throw new Error(payload.error ?? `${method} ${path}: ${response.status}`);
  }
  return payload;
}
