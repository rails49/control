/**
 * The stock screen's documents and the rules over them (ui/STOCK.md): a
 * railroad's roster, the installation's catalogue, and everything the screen
 * reads off the pair.
 *
 * Three levels, exactly as
 * [ADR-0045](../../../docs/adr/0045-the-railroad-owns-cars-and-a-train-is-an-ordered-list-of-them.md)
 * has them — a **model** is what a product is, a **car** is one item a
 * railroad owns, and a **train** is an ordered list of entries — with
 * [ADR-0061](../../../docs/adr/0061-stock-with-nothing-of-its-own-is-named-by-its-model.md)'s
 * amendment on top: an entry names **either a car or a model**, and an item
 * with nothing of its own is named by its model where it is used.
 *
 * **Length, kind and functions are derived and never authored.** They are
 * computed here for the same reason the store computes them for
 * `/rosters/<railroad>/trains`: a train being made up in the browser has not
 * been saved, so there is no derived answer to read, and a screen that showed
 * one only after a round trip would be showing the last train rather than
 * this one. The two derivations agree by saying the same thing
 * (`tc49.lib.roster.Train`), which is what the tests pin.
 *
 * It is a module in `model/` with a test because none of it is the DOM
 * (ui/README.md): what a model put in a train goes in as, what a name is
 * minted as, what holds a thing that somebody asked to remove, and why a
 * length may not be corrected are all rules, and a rule belongs where it can be driven from
 * plain values.
 */

import { lengthTrouble } from "./rules.js";
import { trackLive, type Power } from "./trace.js";
import type {
  CarDoc,
  Coupled,
  Fn,
  ModelDoc,
  ModelFn,
  Picture,
  RosterDoc,
  RosterTrain,
} from "./store.js";

/** What a model may be. A train's kind is derived and is never one of these:
 *  the two lists differ (GLOSSARY.md, **Kind**). */
export const KINDS = ["locomotive", "passenger", "freight", "special"] as const;

const LOCOMOTIVE = "locomotive";

/** The two kinds only a train has: several sorts hauled, and none at all. */
export const MIXED = "mixed";
export const LIGHT_ENGINE = "light engine";

export const FORWARD = "forward";
export const REVERSE = "reverse";

/** What a model's scale may be, strings all, `0` and `1` among them
 *  (`tc49.lib.roster.SCALES`). */
export const SCALES = ["Z", "N", "TT", "H0", "S", "0", "1", "G"] as const;

/** How a function answers its button: on at one press and off at the next,
 *  or on only while it is held (GLOSSARY.md, **Function**). The stock view
 *  calls them *toggle* and *hold*. Absent reads as latching. */
export const LATCHING = "latching";
export const MOMENTARY = "momentary";

/** The highest function number a decoder has: F0 to F68. */
export const TOP_FUNCTION = 68;

/** The highest DCC address, the top of the long addresses; the lowest is 1. */
export const TOP_ADDRESS = 10239;

/** What a person reads a model as: its `name`, and its key where the
 *  document states none (#975). */
export function modelName(model: ModelDoc): string {
  return model.name ?? model.model;
}

/** Whether a model has a decoder: as it says, and where it does not say,
 *  whether it lists functions (`tc49.lib.stock.validate_model`). */
export function hasDecoder(model: ModelDoc): boolean {
  return model.decoder ?? Object.keys(model.functions ?? {}).length > 0;
}

/**
 * The key a model is filed under, minted from its name at its first write
 * and never changed afterwards: lower-cased, accents dropped, every run of
 * anything but `a–z0–9` one `-`, `-` trimmed from both ends, `model` where
 * nothing is left, then `-2`, `-3` … until nothing has it. `Ae 6/6` is
 * `ae-6-6`. The key is never shown — the name is what a person reads — so it
 * only has to be a file's name the store takes (`check_name`) and nobody
 * else's.
 */
export function keyFor(name: string, taken: Iterable<string>): string {
  const base =
    name
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "model";
  const already = new Set(taken);
  if (!already.has(base)) return base;
  for (let n = 2; ; n++) {
    if (!already.has(`${base}-${n}`)) return `${base}-${n}`;
  }
}

/** A name nothing has taken, from `base`: itself, then `base (2)`, `base (3)`
 *  … — what New model and New car call what they make, a name being any
 *  characters and the person's to change at once. */
export function untaken(base: string, taken: Iterable<string>): string {
  const already = new Set(taken);
  if (!already.has(base)) return base;
  for (let n = 2; ; n++) {
    if (!already.has(`${base} (${n})`)) return `${base} (${n})`;
  }
}

/** One function row as the model editor holds it: the number as typed, so a
 *  number listed twice can stand on the screen while it is said to be wrong —
 *  a document keyed by number cannot hold two of one. */
export interface FnRow {
  number: string;
  name: string;
  mode: string;
}

/** Whose function rows: a model's, by key, or a car's own, by name. */
export type FnOwner = string | { car: string };

/** Where a model made on this page is held until Save writes it: a key no
 *  document has, `/` being what no file's name may hold (`check_name`). */
const FRESH = "new/";

/**
 * One item as it stands in a train: its model's every field, with anything
 * the car said instead.
 *
 * The merged result, so an entry is complete however it was written and one
 * rule reads it — which is what makes an anonymous entry and a car entry the
 * same thing to everything downstream (ADR-0061).
 */
export interface Merged {
  model: string;
  kind: string;
  length: number;
  /** The number programmed into its decoder, `null` where it has none. */
  addr: string | null;
  functions: Record<string, ModelFn>;
}

/** A model with nothing said over it: what an entry naming a model is. */
export function anonymous(model: ModelDoc): Merged {
  return {
    model: model.model,
    kind: model.kind,
    length: model.length,
    addr: null,
    functions: model.functions ?? {},
  };
}

/**
 * One car, merged onto its model. `null` where the installation has no such
 * model, which is a car nothing can say the length of.
 *
 * **A written key is a correction**, which is what `tc49.lib.stock._car`
 * reads: the branch is on the key being there and not on its value being
 * something. A car written `functions:` with a YAML null is a correction
 * somebody typed wrong, and the store refuses the document rather than
 * inheriting the product's — so a browser that read the null as "nothing
 * said" would draw a train the store will not take.
 *
 * `addr` is the exception at both ends: Python reads it with `spec.get`, an
 * item with no decoder having none rather than its product's.
 */
export function merged(
  car: CarDoc,
  catalogue: Record<string, ModelDoc>,
): Merged | null {
  const model = catalogue[car.model];
  if (model === undefined) return null;
  return {
    model: model.model,
    kind: "kind" in car ? car.kind : model.kind,
    length: "length" in car ? car.length : model.length,
    addr: car.addr ?? null,
    functions: "functions" in car ? car.functions : (model.functions ?? {}),
  };
}

/** What stands at one place in a train, whichever way the entry named it.
 *  `null` where the roster has no such car or the catalogue no such model. */
export function stands(
  entry: Coupled,
  roster: RosterDoc,
  catalogue: Record<string, ModelDoc>,
): Merged | null {
  if (entry.car !== undefined) {
    const car = roster.cars?.[entry.car];
    return car === undefined ? null : merged(car, catalogue);
  }
  const model = entry.model === undefined ? undefined : catalogue[entry.model];
  return model === undefined ? null : anonymous(model);
}

/**
 * The sum of a train's parts, `null` where any entry names something the
 * documents do not have: a length that left one item out would be a wrong
 * number rather than a missing one.
 *
 * A train that names no cars answers its **stated length**, which is what a
 * roster written before #223 has and what `tc49.lib.roster.Train.length`
 * answers for the same document. `null` where it states none, a train being
 * made up having no length yet.
 */
export function trainLength(
  train: RosterTrain,
  roster: RosterDoc,
  catalogue: Record<string, ModelDoc>,
): number | null {
  const made = train.cars ?? [];
  if (made.length === 0) return train.length ?? null;
  let total = 0;
  for (const entry of made) {
    const one = stands(entry, roster, catalogue);
    if (one === null) return null;
    total += one.length;
  }
  return total;
}

/**
 * What the train is, from **the cars it hauls, ignoring locomotives**: every
 * hauled train has one, so counting them would make every train *mixed*.
 * Exactly one sort hauled gives that sort, more than one gives `mixed`, and
 * nothing but locomotives is a `light engine` (GLOSSARY.md, **Kind**).
 *
 * A train that names nothing the documents have has no kind to derive, the
 * same answer as a train that names nothing at all — and as one that states
 * its length and names no cars, there being no car to read a kind off
 * (`tc49.lib.roster.Train.kind`).
 */
export function trainKind(
  train: RosterTrain,
  roster: RosterDoc,
  catalogue: Record<string, ModelDoc>,
): string | null {
  const made = train.cars ?? [];
  if (made.length === 0) return null;
  const hauled = new Set<string>();
  for (const entry of made) {
    const one = stands(entry, roster, catalogue);
    if (one === null) return null;
    if (one.kind !== LOCOMOTIVE) hauled.add(one.kind);
  }
  if (hauled.size === 0) return LIGHT_ENGINE;
  return hauled.size === 1 ? [...hauled][0]! : MIXED;
}

/**
 * What a person driving this train can switch: the functions its cars
 * declare, **by name**, first car first and each name once.
 *
 * In the train's frame like everything else a throttle works in: a set with a
 * locomotive at each end has one headlight to press, not two. No number —
 * which DCC function a name sits on is a decoder detail no view shows
 * (ADR-0045).
 */
export function trainFunctions(
  train: RosterTrain,
  roster: RosterDoc,
  catalogue: Record<string, ModelDoc>,
): Fn[] {
  const byName = new Map<string, Fn>();
  for (const entry of train.cars ?? []) {
    const one = stands(entry, roster, catalogue);
    if (one === null) continue;
    for (const fn of Object.values(one.functions)) {
      if (!byName.has(fn.name)) {
        byName.set(fn.name, { name: fn.name, mode: fn.mode ?? LATCHING });
      }
    }
  }
  return [...byName.values()];
}

/** What names a car, in words: the trains whose entries do. Empty where
 *  nothing holds it. */
export function carHolders(name: string, roster: RosterDoc): string[] {
  return carTrains(name, roster).map((train) => `train '${train}'`);
}

/** The trains whose entries name a car, by name. */
export function carTrains(name: string, roster: RosterDoc): string[] {
  return Object.entries(roster.trains)
    .filter(([, train]) => (train.cars ?? []).some((entry) => entry.car === name))
    .map(([train]) => train);
}

/** What names a model, in words: the cars that are one, then the trains whose
 *  entries name it directly. A car naming it is listed even where no train is
 *  made up of that car — a locomotive you own and have not made a rake for is
 *  still a thing that holds its model (ADR-0061). */
export function modelHolders(name: string, roster: RosterDoc): string[] {
  const cars = Object.entries(roster.cars ?? {})
    .filter(([, car]) => car.model === name)
    .map(([car]) => `car '${car}'`);
  const trains = Object.entries(roster.trains)
    .filter(([, train]) => (train.cars ?? []).some((entry) => entry.model === name))
    .map(([train]) => `train '${train}'`);
  return [...cars, ...trains];
}

/** A refusal that names what holds the thing, which is the whole point of
 *  refusing rather than removing: a person is told where to go and undo it. */
export function heldBy(what: string, holders: string[]): string {
  return `${what} is held by ${holders.join(", ")}`;
}

/**
 * Why no length may be corrected, or `null` where one may.
 *
 * A length lives on the model as well as the car, and correcting either moves
 * a train the dispatcher fits into blocks. So it is off while track power is
 * on or draining: the run is moving trains over what the dispatcher built, and
 * a correction could only be built with power off, the layout answering
 * `railroad_wanted` only then. With power off, or no session (`null`) on a
 * page that holds no roster from one, it is on, placed trains or not: the
 * roster's Save names the railroad again and the rebuild keeps the trains
 * that still fit
 * ([ADR-0071](../../../docs/adr/0071-a-rebuild-under-the-same-name-keeps-the-placements.md),
 * ui/STOCK.md#the-length-guard).
 *
 * It is off as well where the row naming the railroad is not `heard`: a page
 * that has lost the broker still holds the roster, and cannot know whether
 * the track has power — the broker, `layout` and the dispatcher may well be
 * running without it (#804). It keys on the row and not on `power === null`,
 * which a joined page whose drawing is invalid also reads, and whose
 * lengths stay editable. Nothing is latched: the row heard again with power
 * off, a length can be corrected.
 *
 * **A guard in one browser.** The run's power comes down from the app, which
 * is the only thing on this page that has any; a second browser editing stock
 * during a run is not covered, and the store enforces none of it (ADR-0071).
 */
export function lengthHeld(power: Power | null, heard: boolean = true): string | null {
  if (trackLive(power)) return "track power is on — turn it off to correct a length";
  return heard
    ? null
    : "the layout has not said whether the track has power, so a length cannot be corrected";
}

/** What the roster's Save says while a length edit waits for power off. */
export const LENGTH_WAITS = "a length has changed — turn track power off to save";

/** What the roster's Save says while a length edit waits for the row naming
 *  the railroad to be heard again, and with it whether the track has power. */
export const LENGTH_UNHEARD =
  "a length has changed — the layout has not said whether the track has power";

// --- the screen's session -------------------------------------------------

/** One car as the list above draws it: what it is, what is its own, and why
 *  its length may not be corrected. */
export interface CarRow {
  name: string;
  /** The model's key, and the name a person reads it by. */
  model: string;
  modelName: string;
  addr: string | null;
  /** Where the camera it carries answers, `null` where it carries none. */
  camera: string | null;
  /** Merged, so `null` only where the catalogue has no such model. */
  length: number | null;
  kind: string | null;
  /** Whether that length is the car's own rather than the model's. */
  own: boolean;
  /** The model's length, which an empty length field reads as; `null` where
   *  the catalogue has no such model. */
  modelLength: number | null;
  held: string | null;
  /** Whether its model has a decoder, which is where the car is asked for an
   *  address. */
  decoder: boolean;
  /** Whether it lists functions of its own rather than reading its model's. */
  ownFunctions: boolean;
  /** Its own notes, and its model's, kept apart (#975). */
  notes: string | null;
  modelNotes: string | null;
  /** The trains whose entries name it, by name. */
  trains: string[];
}

/** One model as the list below draws it, with what names it: ten identical
 *  hoppers are this one row (ADR-0061). */
export interface ModelRow {
  /** The key, which is never shown. */
  model: string;
  name: string;
  kind: string;
  scale: string | null;
  length: number;
  decoder: boolean;
  holders: string[];
  held: string | null;
}

/** One place in a train: what stands there and which way round, and what
 *  its tile says of it. */
export interface EntryRow {
  /** The car it names, `null` where the entry is anonymous. */
  car: string | null;
  /** What it is, however it was named; `null` where the documents have not
   *  got it. */
  model: string | null;
  /** What a person reads it as: the car's name, or for a model entry the
   *  model's. */
  name: string;
  addr: string | null;
  /** The camera of the car it names; an anonymous entry carries none. */
  camera: string | null;
  length: number | null;
  reverse: boolean;
}

/** One train: its entries, and the three things derived from them. */
export interface TrainRow {
  train: string;
  entries: EntryRow[];
  length: number | null;
  kind: string | null;
  functions: Fn[];
  /** The model of its first locomotive, head first, whose photo is the
   *  train's on its card; `null` where it has none. */
  locomotive: string | null;
  priority: number | null;
  placed: boolean;
  /** Whether it **states its length and names no cars**, which is the shape a
   *  roster written before #223 has: the length is that stated number rather
   *  than a sum, there is no kind and no function to read off a car, and the
   *  first entry converts it (#414). */
  stated: boolean;
}

/** What a model put in a train went in as (`Stock.addModel`): a model
 *  entry, a car made for it whose address is to be asked, the one car of it
 *  the railroad has, or nothing yet, the railroad having several to choose
 *  from — or nothing at all, where there is no such train or model. */
export type Added =
  | { as: "model" }
  | { as: "made"; car: string }
  | { as: "only"; car: string }
  | { as: "which" }
  | { as: "nothing" };

/**
 * The stock screen's session: the roster being edited, the catalogue it is
 * read against, and every edit either of them takes.
 *
 * It holds the documents rather than a projection of them, so what is saved is
 * what was read with the edits on it and nothing is reassembled — `GET` and
 * `PUT` on `/rosters/<railroad>` are inverses, and a car left out is a car
 * removed (#388).
 *
 * **One Save writes everything**: each changed model's document, then each
 * changed photo, then the roster (#718, #978). They are documents on three
 * routes, and the order is the store's: a roster naming a model the
 * installation has not got is refused whole, and so is a photo of a model it
 * has not got (#392, #630). A model made here is held under a key no document
 * has until that Save mints its own from its name (`keyFor`).
 *
 * Every method that can refuse answers with the words to show and changes
 * nothing, rather than throwing: a refusal here is an ordinary answer about a
 * document being edited, exactly as `/review`'s is
 * ([ADR-0021](../../../docs/adr/0021-a-bad-request-is-answered-not-raised.md)).
 */
export class Stock {
  private doc: RosterDoc;
  private models: Record<string, ModelDoc>;
  /** Edits made to the roster, counted, and the count each document was made
   *  at, so `kept` can tell which edits the written one held. */
  private edited = 0;
  private countOf = new WeakMap<RosterDoc, number>();
  /** The count the store holds, and the count at the latest length edit. */
  private stored = 0;
  private lengthAt = 0;
  /** The models changed and not yet written, by key. */
  private changed = new Set<string>();
  /** The models made on this page that the store has not got, by key: under
   *  a `FRESH` key until Save mints theirs, and under it until the write
   *  lands. */
  private fresh = new Set<string>();
  /** How many models this page has made, which the `FRESH` keys count. */
  private made = 0;
  /** The key a `FRESH` key was minted as, so a screen holding the old one
   *  still finds the model. */
  private minted = new Map<string, string>();
  /** The function rows of each model the editor has drawn, by key: what the
   *  model's `functions` are written from (`FnRow`). */
  private rows = new Map<string, FnRow[]>();
  /** The function rows of each car given its own, by name: what the car's
   *  `functions` are written from, as `rows` is for a model's. */
  private carRows = new Map<string, FnRow[]>();
  /** A photo chosen, dropped or taken and not yet written, by key. */
  private pending = new Map<string, Picture>();
  /** How many times a model's photo has been written from this page, by key:
   *  the `?v=<n>` its thumbnail asks for, the bytes at the route having
   *  changed under what the browser holds (#630). */
  private written = new Map<string, number>();

  constructor(roster: RosterDoc, catalogue: Record<string, ModelDoc>) {
    this.doc = roster;
    this.models = catalogue;
    this.countOf.set(roster, 0);
  }

  /** The roster as it stands, which is what `PUT` is given. */
  get roster(): RosterDoc {
    return this.doc;
  }

  get catalogue(): Record<string, ModelDoc> {
    return this.models;
  }

  /** Whether the roster, a model or a photo holds edits the store has not
   *  been given. */
  get edits(): boolean {
    return this.edited > this.stored;
  }

  /** How many edits the store has not been given, which the bar counts. */
  get unsaved(): number {
    return Math.max(0, this.edited - this.stored);
  }

  /** Whether those edits change a length, which is what makes the roster's
   *  Save wait for power off and, once it lands, name the railroad again so
   *  the dispatcher fits trains with the new length (ADR-0071). */
  get lengthEdits(): boolean {
    return this.lengthAt > this.stored;
  }

  /** The models changed and not yet written, as Save is to write them: each
   *  once, as it stands, its function rows written into it. */
  get corrections(): ModelDoc[] {
    return [...this.changed]
      .filter((key) => this.models[key] !== undefined)
      .map((key) => this.models[key]!);
  }

  /** The store took one changed model, as `corrections` gave it. A model
   *  changed again since is still pending, as it now stands. */
  landed(model: ModelDoc): void {
    if (this.models[model.model] !== model) return;
    this.changed.delete(model.model);
    this.fresh.delete(model.model);
  }

  /** The photos chosen, dropped or taken and not yet written, as Save is to
   *  write them: after the models, the store refusing a photo for a model it
   *  has not got (#630). */
  get photos(): [string, Picture][] {
    return [...this.pending].filter(([key]) => this.models[key] !== undefined);
  }

  /** The store took one photo, as `photos` gave it. One chosen since is
   *  still pending. */
  photoLanded(key: string, picture: Picture): void {
    if (this.pending.get(key) !== picture) return;
    this.pending.delete(key);
    this.written.set(key, (this.written.get(key) ?? 0) + 1);
  }

  /** The store took the roster, as `roster` gave it. An edit made since is
   *  still to write, and so is a model still in `corrections` (#723). */
  kept(written: RosterDoc): void {
    this.stored = this.countOf.get(written)!;
  }

  /** Why the roster's Save waits, or `null` where it does not: a length edit
   *  with track power on or draining, or with the row not `heard` (#804). Any
   *  other edit saves as ever — it moves nothing the dispatcher fits. */
  waitsForPower(power: Power | null, heard: boolean = true): string | null {
    if (!this.lengthEdits) return null;
    if (trackLive(power)) return LENGTH_WAITS;
    return heard ? null : LENGTH_UNHEARD;
  }

  /**
   * What stops the roster being saved, or `null` where nothing does.
   *
   * A train with nothing in it is the one thing: the store refuses an empty
   * `cars` list (`store/stock.py`), and a train that reached it would come
   * back a refusal about a document rather than about the row on the screen.
   * Refused here, the words are this screen's own and the saved roster is
   * unchanged. `edits` stays true — there is still something to give the
   * store once the train is filled — so Save stays enabled (#412).
   *
   * A train that **states its length and names no cars** is not that train:
   * it names no `cars` list at all, which is the shape the store keeps legal
   * for an older file, and saving the roster back keeps it as it was (#414).
   *
   * A train naming **neither** key is that train again, said another way: the
   * store refuses it in the same words as the empty list (`lib/stock.py`,
   * *names no cars*). Composing cannot write it — `addTrain` makes an empty
   * list — but a hand-edited roster file can, and is answered as written, so
   * the guard reads the shape rather than the key (#447).
   */
  stopsSaving(): string | null {
    const empty = Object.entries(this.doc.trains)
      .sort(([one], [other]) => (one < other ? -1 : 1))
      .find(
        ([, train]) => train.length === undefined && (train.cars ?? []).length === 0,
      );
    if (empty !== undefined) {
      return (
        `train '${empty[0]}' has nothing in it — press Add to put a car or a` +
        ` model in it, or unmake it`
      );
    }
    for (const key of this.rows.keys()) {
      const trouble = this.functionTrouble(key);
      if (trouble !== null) return trouble;
    }
    for (const car of this.carRows.keys()) {
      const trouble = this.functionTrouble({ car });
      if (trouble !== null) return trouble;
    }
    return null;
  }

  // --- what the three lists draw -------------------------------------------

  cars(power: Power | null = null, heard: boolean = true): CarRow[] {
    return Object.entries(this.doc.cars ?? {})
      .sort(([one], [other]) => (one < other ? -1 : 1))
      .map(([name, car]) => {
        const whole = merged(car, this.models);
        const product = this.models[car.model];
        return {
          name,
          model: car.model,
          modelName:
            this.models[car.model] === undefined
              ? car.model
              : modelName(this.models[car.model]!),
          addr: car.addr ?? null,
          camera: car.camera ?? null,
          length: whole?.length ?? null,
          kind: whole?.kind ?? null,
          own: car.length !== undefined,
          modelLength: product?.length ?? null,
          held: lengthHeld(power, heard),
          decoder: product !== undefined && hasDecoder(product),
          ownFunctions: "functions" in car,
          notes: car.notes ?? null,
          modelNotes: product?.notes ?? null,
          trains: carTrains(name, this.doc),
        };
      });
  }

  modelRows(power: Power | null = null, heard: boolean = true): ModelRow[] {
    return Object.values(this.models)
      .sort((one, other) => byName(modelName(one), modelName(other)))
      .map((model) => ({
        model: model.model,
        name: modelName(model),
        kind: model.kind,
        scale: model.scale ?? null,
        length: model.length,
        decoder: hasDecoder(model),
        holders: modelHolders(model.model, this.doc),
        held: this.fresh.has(model.model) ? null : lengthHeld(power, heard),
      }));
  }

  trains(placed: readonly string[] = []): TrainRow[] {
    const onLayout = new Set(placed);
    return Object.entries(this.doc.trains)
      .sort(([one], [other]) => (one < other ? -1 : 1))
      .map(([train, made]) => ({
        train,
        entries: (made.cars ?? []).map((entry) => this.entry(entry)),
        length: trainLength(made, this.doc, this.models),
        kind: trainKind(made, this.doc, this.models),
        functions: trainFunctions(made, this.doc, this.models),
        locomotive: this.locomotive(made),
        priority: made.priority ?? null,
        placed: onLayout.has(train),
        stated: made.length !== undefined,
      }));
  }

  private locomotive(train: RosterTrain): string | null {
    for (const entry of train.cars ?? []) {
      const one = stands(entry, this.doc, this.models);
      if (one?.kind === LOCOMOTIVE) return one.model;
    }
    return null;
  }

  private entry(entry: Coupled): EntryRow {
    const whole = stands(entry, this.doc, this.models);
    const product = entry.model === undefined ? undefined : this.models[entry.model];
    return {
      car: entry.car ?? null,
      model: whole?.model ?? entry.model ?? null,
      addr: whole?.addr ?? null,
      name: entry.car ?? (product === undefined ? (entry.model ?? "—") : modelName(product)),
      camera: entry.car === undefined ? null : (this.doc.cars?.[entry.car]?.camera ?? null),
      length: whole?.length ?? null,
      reverse: entry.orientation === REVERSE,
    };
  }

  // --- trains ---------------------------------------------------------------

  /** Make up a train: a name and nothing in it yet, which is what composing
   *  right from left starts with. */
  addTrain(name: string): string | null {
    if (name.trim() === "") return "A train needs a name.";
    if (this.doc.trains[name] !== undefined) return `There is already a train '${name}'.`;
    this.write({ trains: { ...this.doc.trains, [name]: { cars: [] } } });
    return null;
  }

  /** New train: *New train*, or *New train (2)* where that is taken, with
   *  nothing in it yet. The name it was made under. */
  newTrain(): string {
    const name = untaken("New train", Object.keys(this.doc.trains));
    this.addTrain(name);
    return name;
  }

  renameTrain(was: string, name: string): string | null {
    if (name === was) return null;
    if (name.trim() === "") return "A train needs a name.";
    if (this.doc.trains[name] !== undefined) return `There is already a train '${name}'.`;
    const train = this.doc.trains[was];
    if (train === undefined) return null;
    const trains: Record<string, RosterTrain> = {};
    for (const [key, one] of Object.entries(this.doc.trains)) {
      trains[key === was ? name : key] = one;
    }
    this.write({ trains });
    return null;
  }

  /** A train's priority, 1 the highest; empty takes the key off, which is
   *  the lowest. Anything but a whole number from 1 is refused. */
  trainPriority(train: string, typed: string): string | null {
    const made = this.doc.trains[train];
    if (made === undefined) return null;
    const wanted = typed.trim();
    const { priority: _was, ...rest } = made;
    if (wanted === "") {
      if (made.priority !== undefined) this.write({ trains: { ...this.doc.trains, [train]: rest } });
      return null;
    }
    if (!/^\d+$/.test(wanted) || Number(wanted) < 1) {
      return `'${wanted}' is not a priority. Use a whole number: 1 is highest.`;
    }
    if (made.priority === Number(wanted)) return null;
    this.write({ trains: { ...this.doc.trains, [train]: { ...rest, priority: Number(wanted) } } });
    return null;
  }

  /** Unmake a rake. The cars it was made of stay on the roster: composing a
   *  train and owning the stock are two things (ADR-0045). */
  removeTrain(name: string): void {
    const trains = { ...this.doc.trains };
    delete trains[name];
    this.write({ trains });
  }

  /**
   * Put something at the tail of a train: a car, or a model, which gives an
   * anonymous item. **One item cannot stand in a train twice**, so a car the
   * train already has is refused.
   *
   * The first entry on a train that **states its length** converts it: the
   * stated number goes and the length is derived from then on (#414).
   */
  append(train: string, what: { car: string } | { model: string }): string | null {
    const made = this.doc.trains[train];
    if (made === undefined) return null;
    if ("car" in what && (made.cars ?? []).some((entry) => entry.car === what.car)) {
      return `${what.car} is already in ${train}. One item cannot stand in a train twice.`;
    }
    this.inTrain(train, (cars) => [...cars, what]);
    return null;
  }

  /**
   * A model put in a train, as the picker puts one (#980).
   *
   * **A model without a decoder goes in as a model entry** (ADR-0061). **One
   * with a decoder goes in as a car**, its address belonging to one item:
   * where the railroad has no car of it the train does not already hold, one
   * is made (`newCar`) and its address is the next thing to ask; where it has
   * exactly one car of it, that car goes in; where it has more, nothing goes
   * in yet and the cars are the person's to choose from (`carsOf`).
   */
  addModel(train: string, key: string): Added {
    const at = this.keyOf(key);
    const model = this.models[at];
    if (model === undefined || this.doc.trains[train] === undefined) return { as: "nothing" };
    if (!hasDecoder(model)) {
      this.append(train, { model: at });
      return { as: "model" };
    }
    const cars = this.carsOf(train, at);
    const free = cars.filter((one) => !one.inTrain);
    if (free.length === 0) {
      const car = this.newCar(at)!;
      this.append(train, { car });
      return { as: "made", car };
    }
    if (cars.length === 1) {
      this.append(train, { car: free[0]!.car });
      return { as: "only", car: free[0]!.car };
    }
    return { as: "which" };
  }

  /** Every car of a model, by name, and whether the train already holds it:
   *  what *Which <model>?* lists. */
  carsOf(train: string, key: string): { car: string; inTrain: boolean }[] {
    const at = this.keyOf(key);
    const held = new Set(
      (this.doc.trains[train]?.cars ?? []).flatMap((entry) =>
        entry.car === undefined ? [] : [entry.car],
      ),
    );
    return Object.entries(this.doc.cars ?? {})
      .filter(([, car]) => car.model === at)
      .map(([car]) => car)
      .sort(byName)
      .map((car) => ({ car, inTrain: held.has(car) }));
  }

  removeEntry(train: string, index: number): void {
    this.inTrain(train, (cars) => cars.filter((_, at) => at !== index));
  }

  /** The entry at `from` taken out and put back at `to`, which is where a
   *  tile dragged along the strip is dropped. */
  moveEntry(train: string, from: number, to: number): void {
    const cars = this.doc.trains[train]?.cars ?? [];
    if (from === to || cars[from] === undefined || to < 0 || to >= cars.length) return;
    this.inTrain(train, (all) => {
      const moved = [...all];
      const [one] = moved.splice(from, 1);
      moved.splice(to, 0, one!);
      return moved;
    });
  }

  /** Which way round the item at one place is coupled. `forward` is the
   *  unstated value, so turning back to it takes the key off rather than
   *  writing a default into the document. */
  turn(train: string, index: number): void {
    this.inTrain(train, (cars) =>
      cars.map((entry, at) => {
        if (at !== index) return entry;
        const { orientation: _was, ...rest } = entry;
        return entry.orientation === REVERSE ? rest : { ...rest, orientation: REVERSE };
      }),
    );
  }

  // --- cars -----------------------------------------------------------------

  renameCar(was: string, name: string): string | null {
    if (name === was) return null;
    if (name.trim() === "") return "A car needs a name.";
    if (this.doc.cars?.[name] !== undefined) return `There is already a car '${name}'.`;
    const car = this.doc.cars?.[was];
    if (car === undefined) return null;
    const cars: Record<string, CarDoc> = {};
    for (const [key, one] of Object.entries(this.doc.cars ?? {})) {
      cars[key === was ? name : key] = one;
    }
    const rows = this.carRows.get(was);
    if (rows !== undefined) {
      this.carRows.delete(was);
      this.carRows.set(name, rows);
    }
    this.write({ cars, trains: this.renamed(was, name) });
    return null;
  }

  /** The number programmed into a car's decoder, 1 to 10239, written without
   *  leading zeros so `0460` and `460` are one address. Two cars on one
   *  address both answer the same packet, which is what the store refuses; it
   *  is refused here so the words name the other car rather than arriving on
   *  a save. */
  carAddress(name: string, addr: string): string | null {
    const car = this.doc.cars?.[name];
    if (car === undefined) return null;
    const wanted = addr.trim();
    if (wanted === "") {
      const { addr: _was, ...rest } = car;
      this.write({ cars: { ...this.doc.cars, [name]: rest } });
      return null;
    }
    const trouble = this.addressTrouble(wanted, name);
    if (trouble !== null) return trouble;
    this.write({ cars: { ...this.doc.cars, [name]: { ...car, addr: String(Number(wanted)) } } });
    return null;
  }

  /** Where the camera a car carries answers. Empty takes it off and keeps the
   *  car. Checked here as `lib/stock.py` checks it, so the words name the
   *  value or the other car rather than arriving on a save. */
  carCamera(name: string, camera: string): string | null {
    const car = this.doc.cars?.[name];
    if (car === undefined) return null;
    const wanted = camera.trim();
    if (wanted === "") {
      const { camera: _was, ...rest } = car;
      this.write({ cars: { ...this.doc.cars, [name]: rest } });
      return null;
    }
    const trouble = this.cameraTrouble(wanted, name);
    if (trouble !== null) return trouble;
    this.write({ cars: { ...this.doc.cars, [name]: { ...car, camera: wanted } } });
    return null;
  }

  /**
   * A length corrected on this item and not on the product. `null` takes the
   * override off, and the car reads its model's length again.
   *
   * Refused while track power is on or draining: the dispatcher is fitting
   * trains into blocks on the length this answers, and only a build with
   * power off brings it up to date (ui/STOCK.md#the-length-guard).
   */
  carLength(
    name: string,
    mm: number | null,
    power: Power | null = null,
    heard: boolean = true,
  ): string | null {
    const car = this.doc.cars?.[name];
    if (car === undefined) return null;
    const held = lengthHeld(power, heard);
    if (held !== null) return held;
    if (mm === null) {
      const { length: _was, ...rest } = car;
      this.write({ cars: { ...this.doc.cars, [name]: rest } });
      this.lengthAt = this.edited;
      return null;
    }
    const trouble = lengthTrouble(mm);
    if (trouble !== null) return trouble;
    this.write({ cars: { ...this.doc.cars, [name]: { ...car, length: mm } } });
    this.lengthAt = this.edited;
    return null;
  }

  /** Take a car off the roster. Refused while a train is made of it, and the
   *  refusal says which. */
  removeCar(name: string): string | null {
    const holders = carHolders(name, this.doc);
    if (holders.length > 0) return heldBy(`car '${name}'`, holders);
    const cars = { ...this.doc.cars };
    delete cars[name];
    this.carRows.delete(name);
    this.write({ cars });
    return null;
  }

  /** A car's own notes, beside its model's rather than over them (#975);
   *  empty takes the key off rather than writing `""`. */
  carNotes(name: string, notes: string): void {
    const car = this.doc.cars?.[name];
    if (car === undefined || (car.notes ?? "") === notes) return;
    const { notes: _was, ...rest } = car;
    this.write({ cars: { ...this.doc.cars, [name]: notes === "" ? rest : { ...rest, notes } } });
  }

  /** *This car's decoder is different*: its model's functions copied onto the
   *  car as rows of its own, edited from then on as a model's are. */
  ownFunctions(name: string): void {
    const car = this.doc.cars?.[name];
    if (car === undefined || "functions" in car) return;
    this.setRows({ car: name }, this.functionRows(car.model).map((row) => ({ ...row })));
  }

  /** *Use the model's functions again*: the car's own taken off. */
  modelFunctions(name: string): void {
    const car = this.doc.cars?.[name];
    if (car === undefined) return;
    this.carRows.delete(name);
    if (!("functions" in car)) return;
    const { functions: _was, ...rest } = car;
    this.write({ cars: { ...this.doc.cars, [name]: rest } });
  }

  // --- models ---------------------------------------------------------------

  /** One model by key, `null` where the catalogue has none. A `FRESH` key
   *  Save has minted another for still finds it. */
  model(key: string): ModelDoc | null {
    return this.models[this.keyOf(key)] ?? null;
  }

  /** The key a model is filed under now: `key`, or what Save minted for it. */
  keyOf(key: string): string {
    return this.minted.get(key) ?? key;
  }

  /** Whether the store has not got this model yet: it was made on this page
   *  and no Save has written it. Deleting one is dropping it here. */
  isFresh(key: string): boolean {
    return this.fresh.has(this.keyOf(key));
  }

  /** The photo chosen, dropped or taken for a model and not yet written. */
  photo(key: string): Picture | null {
    return this.pending.get(this.keyOf(key)) ?? null;
  }

  /** How many times this page has written the model's photo (`written`). */
  photoVersion(key: string): number {
    return this.written.get(this.keyOf(key)) ?? 0;
  }

  /** A photo for the model, written by the next Save. */
  setPhoto(key: string, picture: Picture): void {
    const at = this.keyOf(key);
    if (this.models[at] === undefined) return;
    this.pending.set(at, picture);
    this.write({});
  }

  /**
   * A model made here: *New model*, or *New model (2)* where that is taken,
   * and nothing else said — a passenger car in H0 with no decoder, which is
   * what the person is about to change. It is written by Save, ahead of the
   * roster, so the roster never names a model the store lacks (#978).
   */
  newModel(): string {
    this.made += 1;
    const key = `${FRESH}${this.made}`;
    const name = untaken(
      "New model",
      Object.values(this.models).map((model) => modelName(model)),
    );
    this.models = {
      ...this.models,
      [key]: { model: key, name, kind: "passenger", scale: "H0", length: 200, decoder: false },
    };
    this.fresh.add(key);
    this.changed.add(key);
    this.write({});
    return key;
  }

  /** A model's name: any characters, refused empty or where another model
   *  has it — the store refuses that too (`AssetStore.put_model`). */
  renameModel(key: string, name: string): string | null {
    const at = this.keyOf(key);
    const model = this.models[at];
    if (model === undefined) return null;
    const wanted = name.trim();
    if (wanted === modelName(model)) return null;
    if (wanted === "") return "A model needs a name.";
    for (const other of Object.values(this.models)) {
      if (other.model !== at && modelName(other) === wanted) {
        return `There is already a model '${wanted}'.`;
      }
    }
    this.change(at, { name: wanted });
    return null;
  }

  modelKind(key: string, kind: string): void {
    this.change(this.keyOf(key), { kind });
  }

  modelScale(key: string, scale: string): void {
    this.change(this.keyOf(key), { scale });
  }

  /** A model's notes; empty takes the key off rather than writing `""`. */
  modelNotes(key: string, notes: string): void {
    const at = this.keyOf(key);
    const model = this.models[at];
    if (model === undefined || (model.notes ?? "") === notes) return;
    const { notes: _was, ...rest } = model;
    this.put(at, notes === "" ? rest : { ...rest, notes });
  }

  /** Correcting a product's length changes every item of that product, which
   *  is the whole reason the length lives here as well as on the car. Refused
   *  while track power is on or draining. Written on the roster's Save.
   *
   *  A model made here and not yet written is none of that: no train the
   *  dispatcher fits is made of it, so its length is neither held nor a
   *  length edit — only typed. */
  modelLength(
    name: string,
    mm: number,
    power: Power | null = null,
    heard: boolean = true,
  ): string | null {
    const at = this.keyOf(name);
    const model = this.models[at];
    if (model === undefined) return null;
    const fresh = this.fresh.has(at);
    const held = fresh ? null : lengthHeld(power, heard);
    if (held !== null) return held;
    const trouble = lengthTrouble(mm);
    if (trouble !== null) return trouble;
    this.change(at, { length: mm });
    if (!fresh) this.lengthAt = this.edited;
    return null;
  }

  /**
   * Whether the product has a decoder. Turned on with no functions it gets
   * F0 *Headlights*, which nearly every decoder has; turned off it loses its
   * functions, a function being a bit on a decoder (`lib/stock.py`).
   */
  modelDecoder(key: string, on: boolean): void {
    const at = this.keyOf(key);
    const model = this.models[at];
    if (model === undefined) return;
    const rows = on ? this.functionRows(at) : [];
    this.putModel({ ...model, decoder: on });
    this.setRows(
      at,
      on && rows.length === 0 ? [{ number: "0", name: "Headlights", mode: LATCHING }] : rows,
    );
  }

  /** The function rows of a model, or of a car with its own, as the editor
   *  draws them: the ones it is holding, or the document's, by number. A car
   *  reading its model's has none. */
  functionRows(of: FnOwner): FnRow[] {
    let held: FnRow[] | undefined;
    let functions: Record<string, ModelFn>;
    if (typeof of === "string") {
      const at = this.keyOf(of);
      held = this.rows.get(at);
      functions = this.models[at]?.functions ?? {};
    } else {
      held = this.carRows.get(of.car);
      functions = this.doc.cars?.[of.car]?.functions ?? {};
    }
    if (held !== undefined) return held;
    return Object.entries(functions)
      .sort(([one], [other]) => Number(one) - Number(other))
      .map(([number, fn]) => ({ number, name: fn.name, mode: fn.mode ?? LATCHING }));
  }

  /** A function row added, on the lowest number not in use. */
  addFunction(key: FnOwner): void {
    const rows = this.functionRows(key);
    const used = new Set(rows.map((row) => row.number));
    let number = 0;
    while (used.has(String(number))) number++;
    this.setRows(key, [...rows, { number: String(number), name: "", mode: LATCHING }]);
  }

  removeFunction(key: FnOwner, at: number): void {
    this.setRows(
      key,
      this.functionRows(key).filter((_, index) => index !== at),
    );
  }

  /** A function's number, F0 to F68. One listed twice stands, said to be
   *  wrong, and stops Save while it does (`functionTrouble`). */
  functionNumber(key: FnOwner, at: number, typed: string): string | null {
    const number = typed.trim().replace(/^[Ff]/, "");
    if (!/^\d+$/.test(number) || Number(number) > TOP_FUNCTION) {
      return `A function number is 0 to ${TOP_FUNCTION}.`;
    }
    this.setRow(key, at, { number: String(Number(number)) });
    return null;
  }

  functionName(key: FnOwner, at: number, name: string): void {
    this.setRow(key, at, { name: name.trim() });
  }

  functionMode(key: FnOwner, at: number, mode: string): void {
    this.setRow(key, at, { mode });
  }

  /** What is wrong with a model's function rows, or `null` where nothing is:
   *  a number listed twice, or a function with no name. Either stops Save —
   *  the store would refuse the document (`lib/stock.py`). */
  functionTrouble(key: FnOwner): string | null {
    const twice = this.listedTwice(key);
    if (twice !== null) return twice;
    const unnamed = this.functionRows(key).find((row) => row.name === "");
    return unnamed === undefined ? null : `F${unnamed.number} needs a name.`;
  }

  /** A function number listed twice on a model, said as the editor says it
   *  under the rows while it stands, or `null` where none is. */
  listedTwice(key: FnOwner): string | null {
    const seen = new Set<string>();
    for (const row of this.functionRows(key)) {
      if (seen.has(row.number)) {
        return `F${row.number} is listed twice. One number names one function.`;
      }
      seen.add(row.number);
    }
    return null;
  }

  /** A car of this model, named after it as New model names a model: no
   *  address yet, which is a car's to be given. */
  newCar(key: string): string | null {
    const at = this.keyOf(key);
    const model = this.models[at];
    if (model === undefined) return null;
    const name = untaken(modelName(model), Object.keys(this.doc.cars ?? {}));
    this.write({ cars: { ...this.doc.cars, [name]: { model: at } } });
    return name;
  }

  /** A model gone from the catalogue: the store deleted it, or it was made
   *  here and never written. Nothing on this railroad names it, the delete
   *  being refused while anything does. */
  dropModel(key: string): void {
    const at = this.keyOf(key);
    const models = { ...this.models };
    delete models[at];
    this.models = models;
    this.changed.delete(at);
    this.fresh.delete(at);
    this.rows.delete(at);
    this.pending.delete(at);
  }

  /**
   * Every model made here given the key it is filed under, minted from its
   * name (`keyFor`) — what Save does first, so what it writes names keys the
   * store will have. The roster's references move with it, and that is no
   * edit: the document says what it said, under the key it will be read by.
   */
  mintKeys(): void {
    for (const was of [...this.fresh]) {
      if (!was.startsWith(FRESH)) continue;
      const model = this.models[was]!;
      const key = keyFor(
        modelName(model),
        Object.keys(this.models).filter((one) => one !== was),
      );
      this.rekey(was, key);
    }
  }

  /** A model a train is made of, put in the catalogue the store answered: a
   *  model `PUT` replaces the document, so this holds what the store now has. */
  putModel(model: ModelDoc): void {
    this.models = { ...this.models, [model.model]: model };
  }

  /** One model changed: the fields given set, and the model owed a write. */
  private change(key: string, part: Partial<ModelDoc>): void {
    const model = this.models[key];
    if (model === undefined) return;
    this.put(key, { ...model, ...part });
  }

  /** One model, as it now stands, owed a write and counted as an edit. */
  private put(key: string, model: ModelDoc): void {
    this.putModel(model);
    this.changed.add(key);
    // Counted as an edit to the roster, which Save writes after the models:
    // the change is outstanding until a roster written after it lands.
    this.write({});
  }

  private setRow(key: FnOwner, at: number, part: Partial<FnRow>): void {
    this.setRows(
      key,
      this.functionRows(key).map((row, index) => (index === at ? { ...row, ...part } : row)),
    );
  }

  /** A model's function rows, and the document's `functions` written from
   *  them: a number listed twice is the later row's in the document until it
   *  is put right, Save being refused meanwhile. A latching function says
   *  nothing about its mode, that being what absent reads as. */
  private setRows(key: FnOwner, rows: FnRow[]): void {
    const functions: Record<string, ModelFn> = {};
    for (const row of rows) {
      functions[row.number] =
        row.mode === LATCHING ? { name: row.name } : { name: row.name, mode: row.mode };
    }
    if (typeof key !== "string") {
      // A car's own stay its own with every row removed: `functions: {}` is a
      // decoder with none, where no key would be the model's.
      const car = this.doc.cars?.[key.car];
      if (car === undefined) return;
      this.carRows.set(key.car, rows);
      this.write({ cars: { ...this.doc.cars, [key.car]: { ...car, functions } } });
      return;
    }
    const at = this.keyOf(key);
    const model = this.models[at];
    if (model === undefined) return;
    this.rows.set(at, rows);
    const { functions: _was, ...rest } = model;
    this.put(at, rows.length === 0 ? rest : { ...rest, functions });
  }

  /** A model moved from one key to another, and everything that names it. */
  private rekey(was: string, key: string): void {
    const models: Record<string, ModelDoc> = {};
    for (const [at, model] of Object.entries(this.models)) {
      models[at === was ? key : at] = at === was ? { ...model, model: key } : model;
    }
    this.models = models;
    for (const held of [this.changed, this.fresh]) {
      if (held.delete(was)) held.add(key);
    }
    for (const held of [this.rows, this.pending, this.written] as Map<string, unknown>[]) {
      if (held.has(was)) {
        held.set(key, held.get(was));
        held.delete(was);
      }
    }
    this.minted.set(was, key);
    const cars: Record<string, CarDoc> = {};
    for (const [name, car] of Object.entries(this.doc.cars ?? {})) {
      cars[name] = car.model === was ? { ...car, model: key } : car;
    }
    const trains: Record<string, RosterTrain> = {};
    for (const [name, train] of Object.entries(this.doc.trains)) {
      trains[name] =
        train.cars === undefined
          ? train
          : {
              ...train,
              cars: train.cars.map((entry) =>
                entry.model === was ? { ...entry, model: key } : entry,
              ),
            };
    }
    // The same document under the key it will be read by, and no edit: it
    // counts as the document it replaces, so `kept` reads it as that one.
    const count = this.countOf.get(this.doc) ?? this.edited;
    this.doc = { ...this.doc, ...(this.doc.cars === undefined ? {} : { cars }), trains };
    this.countOf.set(this.doc, count);
  }

  // --- writing --------------------------------------------------------------

  /** One edit to the roster: a new document with the edit on it, and the
   *  screen marked as holding something the store has not been given. */
  private write(part: Partial<RosterDoc>): void {
    this.doc = { ...this.doc, ...part };
    this.edited += 1;
    this.countOf.set(this.doc, this.edited);
  }

  /**
   * One train's entries, changed.
   *
   * A train says **either** a stated length **or** cars and never both, the
   * store refusing one that says both, so the first entry on a train that
   * stated its length drops the stated number and the train becomes the
   * ordinary shape (#414). An edit that leaves such a train with no entries
   * leaves it as it was: there was nothing in it to change.
   */
  private inTrain(train: string, change: (cars: Coupled[]) => Coupled[]): void {
    const made = this.doc.trains[train];
    if (made === undefined) return;
    const cars = change(made.cars ?? []);
    if (made.length !== undefined) {
      if (cars.length === 0) return;
      const { length: _stated, ...rest } = made;
      this.write({ trains: { ...this.doc.trains, [train]: { ...rest, cars } } });
      return;
    }
    this.write({ trains: { ...this.doc.trains, [train]: { ...made, cars } } });
  }

  /** Every train's entries with one car's name changed, so a rename does not
   *  leave a train naming a car the railroad has not. A train that names no
   *  cars is left as written: giving it an empty list would state a length
   *  beside one, which the store refuses (#414). */
  private renamed(was: string, name: string): Record<string, RosterTrain> {
    const trains: Record<string, RosterTrain> = {};
    for (const [key, train] of Object.entries(this.doc.trains)) {
      trains[key] =
        train.cars === undefined
          ? train
          : {
              ...train,
              cars: train.cars.map((entry) =>
                entry.car === was ? { ...entry, car: name } : entry,
              ),
            };
    }
    return trains;
  }

  /** Why an address may not be written on a car, said as a refusal, or
   *  `null` where it may: no DCC address, or worn by another car already. */
  private addressTrouble(addr: string, but: string | null): string | null {
    const number = Number(addr);
    if (!/^\d+$/.test(addr) || number < 1 || number > TOP_ADDRESS) {
      return `'${addr}' is not a DCC address. Use a number from 1 to ${TOP_ADDRESS}.`;
    }
    for (const [name, car] of Object.entries(this.doc.cars ?? {})) {
      if (name !== but && car.addr === String(number)) {
        return `Car ${name} already has address ${number}.`;
      }
    }
    return null;
  }

  /** Why a camera may not be written on a car, said as a refusal, or `null`
   *  where it may: not a bare host name or IPv4 address, or carried by
   *  another car already. */
  private cameraTrouble(camera: string, but: string | null): string | null {
    if (!HOST.test(camera)) {
      return `'${camera}' is not a camera address — write the camera's host name or IP address`;
    }
    for (const [name, car] of Object.entries(this.doc.cars ?? {})) {
      if (name !== but && car.camera === camera) {
        return `car '${name}' already carries camera '${camera}'`;
      }
    }
    return null;
  }
}

/** A camera's address as `tc49.lib.stock._camera` takes it: letters, digits,
 *  dots and hyphens, starting and ending with a letter or digit — so no
 *  scheme, port, path or login, how the camera is spoken to being the
 *  `camera` app's (ADR-0082). */
const HOST = /^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$/;

/** Names in the order a person reads a list: case aside. */
function byName(one: string, other: string): number {
  return one.localeCompare(other, undefined, { sensitivity: "base" });
}
