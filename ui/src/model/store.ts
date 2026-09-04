/**
 * The store's routes (EDITOR.md, PANEL.md), the shapes they answer with, and
 * nothing else.
 *
 * A railroad's documents — its drawing, its roster — and the installation's
 * catalogue beside them: a model is shared between railroads, so reading one
 * takes no railroad's name (ADR-0045). A document's route answers the document
 * as written and takes it back the same way, so `GET` and `PUT` on one path
 * are inverses; what a run view reads instead is *derived* and hangs below it,
 * `/rosters/<railroad>/trains` being the one there is (#388).
 *
 * `review` is the whole of the editor's view of topology: red pins, the portal
 * labels that pair with nothing, the junctions as symbol groups, the derived
 * layout, its explanation, the refusal where there is one, and the way that
 * refusal is about where it is about one. A drawing with a red pin is the
 * normal state mid-edit, so a refusal arrives inside a 200 and is read rather
 * than caught.
 */

import type { Drawing } from "./drawing.js";

/** How long a view waits before asking the store again.
 *
 *  The run view's retry after a session it lost, and the stock view's after a
 *  read that got no document: both begin by asking the store, so the wait is
 *  one number and lives beside the routes rather than in either view.
 *
 *  The loaded railroad **is** the session (#171), so a page with a railroad on
 *  it wants to be joined to that railroad and there is no choice left for a
 *  person to make: the band's picker says nothing about a name it is already
 *  showing, and a session that went is not a reason to make somebody reload.
 *  Three seconds is long enough not to hammer a port nothing is listening on,
 *  and short enough that restarting `tc49 live` under an open tab reconnects
 *  while the operator is still looking at it. */
export const RETRY_MS = 3000;

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
 * A railroad's trains: every one it owns, whether on the layout or off it
 * ([ADR-0039](../../../docs/adr/0039-a-train-may-be-off-the-layout.md)).
 *
 * An asset of the railroad rather than a fact about the run, which is the line
 * [ADR-0010](../../../docs/adr/0010-asset-store-serves-coarse-read-only-documents.md)
 * draws: the store says what stock there is and how long each train is, the
 * bus says where it stands.
 *
 * **Derived, which is why it is a path below the roster**: what the run views
 * read is worked out from the cars a train is made of, and the document those
 * cars are written in is `/rosters/<railroad>` itself
 * ([#388](https://github.com/rails49/control/issues/388)).
 */
export interface TrainsDoc {
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

export async function readTrains(railroad: string): Promise<TrainsDoc> {
  return await ask<TrainsDoc>(
    "GET",
    `/rosters/${encodeURIComponent(railroad)}/trains`,
  );
}

/**
 * A railroad's roster **as the document it is**: the cars it owns, and the
 * trains made up from them
 * ([ADR-0045](../../../docs/adr/0045-the-railroad-owns-cars-and-a-train-is-an-ordered-list-of-them.md)).
 *
 * What the stock screen edits, which is why it is this and not `TrainsDoc`:
 * the derived answer withholds the cars, the addresses and the function
 * numbers on purpose, and those are exactly what there is to edit. `GET` and
 * `PUT` on the same path are inverses, and a `PUT` is the whole document — a
 * roster saved without a car is that car removed
 * ([#388](https://github.com/rails49/control/issues/388)).
 */
export interface RosterDoc {
  /** The railroad that owns it, which is the name in the path. */
  roster: string;
  /** The **identified stock**: an item with an address, or with a field
   *  corrected on that item. A railroad that owns nothing yet has none, which
   *  is a drawing saved this morning and not a fault. */
  cars?: Record<string, CarDoc>;
  trains: Record<string, RosterTrain>;
}

/** One item the railroad owns: its model, with anything true of this item and
 *  not of the product said over the top of it. Every field but `model` is
 *  optional, and stating none is legal — a name is worth having wherever a
 *  person wants one. */
export interface CarDoc {
  model: string;
  /** The number programmed into its decoder, **as a string** and bare — no
   *  system prefix, unlike a point's. Absent where it has no decoder, and no
   *  two cars on one railroad may wear the same one. */
  addr?: string;
  kind?: string;
  length?: number;
  functions?: Record<string, ModelFn>;
}

/** A train the railroad has made up: an ordered list, head first. Its length
 *  and its kind are derived from those cars and are never written down, which
 *  is what `/rosters/<railroad>/trains` answers with. */
export interface RosterTrain {
  cars: Coupled[];
  /** Lowest number highest, and absent is lowest of all. No default number is
   *  written into a document. */
  priority?: number;
}

/** One place in a train: what stands there, and which way round it is
 *  coupled. It names **either a car or a model** — a car where the railroad
 *  has something to say about that item, and otherwise the model, ten
 *  identical hoppers having nothing to tell one from another
 *  ([ADR-0061](../../../docs/adr/0061-stock-with-nothing-of-its-own-is-named-by-its-model.md)). */
export interface Coupled {
  car?: string;
  model?: string;
  /** `forward` or `reverse`, and `forward` where unstated: `reverse` says the
   *  car's nose points toward the tail. */
  orientation?: string;
}

/** The roster document, whole. A railroad with no roster file answers the
 *  empty one — owning nothing is an ordinary state, and it is what the screen
 *  writing the first car draws itself from. */
export async function readRoster(railroad: string): Promise<RosterDoc> {
  return await ask<RosterDoc>("GET", `/rosters/${encodeURIComponent(railroad)}`);
}

/** Create or replace one railroad's roster. Strict, unlike a drawing: the
 *  store validates it against the installation's catalogue and writes nothing
 *  where it does not validate, so a refusal arrives as a thrown error carrying
 *  the validator's words. */
export async function saveRoster(roster: RosterDoc): Promise<void> {
  await ask("PUT", `/rosters/${encodeURIComponent(roster.roster)}`, roster);
}

/**
 * One model: what a product *is*, independent of any railroad that owns one
 * ([ADR-0045](../../../docs/adr/0045-the-railroad-owns-cars-and-a-train-is-an-ordered-list-of-them.md)).
 *
 * The **document as written**, and not the merged model a car reads: this is
 * what the catalogue screen edits, so every field comes back as it is on disk
 * — including the ones nothing branches on, the shelf a locomotive lives on
 * among them. `model` is the name it is filed under and the key every car
 * refers to it by, so it is what the path says.
 */
export interface ModelDoc {
  model: string;
  /** `locomotive`, `passenger`, `freight` or `special`. A train's kind is
   *  derived and is never one a document states (CONTEXT.md, **Kind**). */
  kind: string;
  /** Millimetres of actual model track, measured over buffers on the item,
   *  whatever the scale (`catalogue/README.md`). */
  length: number;
  manufacturer?: string;
  scale?: string;
  description?: string;
  /** What each DCC function does on this product, keyed by the function
   *  number **written as a string**: YAML integer keys and JSON object keys
   *  do not agree, so the number is quoted at both ends. */
  functions?: Record<string, ModelFn>;
}

/** One function on a model: what it is called, and what it can be in. Absent
 *  `values` is the plain switch, `["off", "on"]`, off to begin with. */
export interface ModelFn {
  name: string;
  values?: string[];
}

/**
 * The installation's catalogue: every model it knows, by name.
 *
 * One catalogue for the box rather than one per railroad — a product does not
 * become a different product on another layout (CONTEXT.md, **Catalogue**) —
 * so this takes no railroad. An installation that has written no model yet
 * answers an empty map, which is what a fresh box is and not a fault.
 */
export async function readCatalogue(): Promise<Record<string, ModelDoc>> {
  return (await ask<{ models: Record<string, ModelDoc> }>("GET", "/catalogue"))
    .models;
}

export async function readModel(name: string): Promise<ModelDoc> {
  return await ask<ModelDoc>("GET", `/catalogue/${encodeURIComponent(name)}`);
}

/** Create or replace one model. The store validates it and writes nothing
 *  where it does not validate, so a refusal arrives as a thrown error
 *  carrying the validator's words. */
export async function saveModel(model: ModelDoc): Promise<void> {
  await ask("PUT", `/catalogue/${encodeURIComponent(model.model)}`, model);
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
  /** Where the copy off this machine goes, `null` where nowhere. */
  remote: string | null;
  /** The public half of the store's own deploy key, for the person to paste
   *  into the repository's deploy keys; `null` where the store has none
   *  (#355). */
  key: string | null;
  automatic: boolean;
  /** What backup has not got, in the words of the command that would give it
   *  — no repository, or no remote. Empty where nothing is missing. */
  needs: string[];
  /** The documents that have moved since the last backup, by the names the
   *  store gives them. */
  outstanding: string[];
  backups: Backup[];
  /** How the copy on the other machine stands (#321). */
  copy: Copy;
  ok?: boolean;
  said?: string;
}

/**
 * The copy off this machine: what the remote has not been given, and how the
 * last attempt to give it went.
 *
 * The commit is the backup and this is the copy of it, so a failure here never
 * interrupts anybody at the moment it happens. What it does instead is
 * accumulate: `stale` is the store saying it has been carrying a backup nobody
 * else has for longer than a day.
 */
export interface Copy {
  /** Backups made here that the remote has not been given. */
  waiting: number;
  /** Seconds since the oldest of them was made, `null` where none is waiting
   *  or there is no remote to measure against. */
  since: number | null;
  /** Whether that is longer than the store is willing to stay quiet about. */
  stale: boolean;
  /** How the last attempt went, `null` where there has not been one this
   *  session. */
  ok: boolean | null;
  /** What git said about it, in git's words. */
  said: string;
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

export async function adoptRepository(url: string): Promise<BackupDoc> {
  return await ask<BackupDoc>("POST", "/backup/repository", { url });
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
