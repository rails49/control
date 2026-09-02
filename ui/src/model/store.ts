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

/**
 * A railroad's roster: every train it owns, whether on the layout or off it
 * ([ADR-0039](../../../docs/adr/0039-a-train-may-be-off-the-layout.md)).
 *
 * An asset of the railroad rather than a fact about the run, which is the line
 * [ADR-0010](../../../docs/adr/0010-asset-store-serves-coarse-read-only-documents.md)
 * draws: the store says what stock there is and how long each train is, the
 * bus says where it stands. Read-only here — editing a roster is another
 * screen's.
 */
export interface RosterDoc {
  roster: string;
  trains: Record<string, TrainDoc>;
}

/** One train on the roster: how long it is, and what a person driving it can
 *  switch. Both are **derived from the cars it is made of** and neither is
 *  authored, so the pair arrives together
 *  ([ADR-0045](../../../docs/adr/0045-the-railroad-owns-cars-and-a-train-is-an-ordered-list-of-them.md)).
 *  The cars themselves, their addresses and which DCC number each function
 *  sits on are not here: a decoder detail is no view's (ui/THROTTLE.md). */
export interface TrainDoc {
  length: number;
  /** Absent from an older store's answer, which is a train with nothing to
   *  switch rather than a document to refuse. */
  functions?: Fn[];
}

/** One thing a person can switch on a train, by the name the catalogue gives
 *  it: `headlights`, `vacuum`. `values` is what it can be in, **first entry
 *  first** — that is the one it is in when nothing has been commanded, which
 *  is why it is a list and not a set (`tc49.lib.roster.Function`). */
export interface Fn {
  name: string;
  values: string[];
}

export async function readRoster(railroad: string): Promise<RosterDoc> {
  return await ask<RosterDoc>("GET", `/rosters/${encodeURIComponent(railroad)}`);
}

/**
 * One backup: what to name to come back to it, the message naming the
 * documents that moved, and when it was made. Straight off `git log`, which is
 * where the app's knowledge of history begins and ends
 * ([ADR-0053](../../../docs/adr/0053-backup-drives-git-and-does-not-own-it.md)).
 */
export interface Backup {
  commit: string;
  said: string;
  when: string;
}

/**
 * Where backup stands over the store the server has open: whether it can back
 * up at all, whether it is doing so, what is waiting and what there is to come
 * back to.
 *
 * `ok` and `said` are on the answer to a **press** — backing up now, or
 * restoring — and absent from a plain read. `said` is git's own words, passed
 * through: this app knows nothing about a rejected push or a missing remote
 * beyond being able to show what git called it.
 */
export interface BackupDoc {
  root: string;
  repository: boolean;
  automatic: boolean;
  /** What backup has not got, in the words of the command that would give it
   *  — no repository, or no remote. Empty where nothing is missing. */
  needs: string[];
  /** The documents that have moved since the last backup, by the names the
   *  store gives them. */
  outstanding: string[];
  backups: Backup[];
  ok?: boolean;
  said?: string;
}

export async function readBackup(): Promise<BackupDoc> {
  return await ask<BackupDoc>("GET", "/backup");
}

export async function switchBackup(automatic: boolean): Promise<BackupDoc> {
  return await ask<BackupDoc>("PUT", "/backup", { automatic });
}

export async function backUpNow(): Promise<BackupDoc> {
  return await ask<BackupDoc>("POST", "/backup/commit", {});
}

export async function restoreBackup(commit: string): Promise<BackupDoc> {
  return await ask<BackupDoc>("POST", "/backup/restore", { commit });
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
