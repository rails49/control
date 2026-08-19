/**
 * The store's routes (EDITOR.md, PANEL.md), and nothing else.
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

/** A portal label not worn by exactly two portals — worn once, or worn three
 *  times and more — with the portals wearing it. A label pairs exactly two, so
 *  both are one finding. The refusal names one label and stops, which is why
 *  this is a list. */
export interface UnpairedPortal {
  label: string;
  portals: string[];
}

export interface Review {
  red_pins: string[];
  unpaired_portals: UnpairedPortal[];
  junctions: Junction[];
  joints: Joint[];
  layout: Layout | null;
  explain: Explained | null;
  refused: string | null;
  /** The way or ways a refusal is about, walked where derivation refused. A
   *  refusal about anything else offends no way and this is empty. */
  offending: Transit[];
}

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

/** A live session's stock, placement and facing: the scenario the session was
 *  started from (PANEL.md, ADR-0019). The bridge relays the bus and says
 *  nothing about the run, so the panel reads this to know where the trains
 *  stand and which way they face before the first event arrives. */
export interface ScenarioDoc {
  name: string;
  layout: string;
  trains: Record<string, { length: number; at: string; facing: string }>;
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
