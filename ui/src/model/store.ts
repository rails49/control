/**
 * The store's four routes (EDITOR.md), and nothing else.
 *
 * `review` is the whole of the editor's view of topology: red pins, the
 * junctions as symbol groups, the derived layout, its explanation, and the
 * refusal where there is one. A drawing with a red pin is the normal state
 * mid-edit, so a refusal arrives inside a 200 and is read rather than caught.
 */

import type { Drawing } from "./drawing.js";

export interface Junction {
  /** `null` where the drawing has not settled one. */
  name: string | null;
  symbols: string[];
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

export interface Review {
  red_pins: string[];
  junctions: Junction[];
  layout: Layout | null;
  explain: Explained | null;
  refused: string | null;
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
