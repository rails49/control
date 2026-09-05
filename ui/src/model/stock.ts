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
 * (ui/README.md): what promotes an entry to a car, what a name is minted as,
 * what holds a thing that somebody asked to remove, and why a length may not
 * be corrected are all rules, and a rule belongs where it can be driven from
 * plain values.
 */

import type {
  CarDoc,
  Coupled,
  Fn,
  ModelDoc,
  ModelFn,
  RosterDoc,
  RosterTrain,
} from "./store.js";

/** What a model may be. A train's kind is derived and is never one of these:
 *  the two lists differ (CONTEXT.md, **Kind**). */
export const KINDS = ["locomotive", "passenger", "freight", "special"] as const;

const LOCOMOTIVE = "locomotive";

/** The two kinds only a train has: several sorts hauled, and none at all. */
export const MIXED = "mixed";
export const LIGHT_ENGINE = "light engine";

export const FORWARD = "forward";
export const REVERSE = "reverse";

/** What a function is in where the model states no values: a plain switch,
 *  off to begin with (`tc49.lib.roster.OFF_ON`). */
export const OFF_ON = ["off", "on"];

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

/** One car, merged onto its model. `null` where the installation has no such
 *  model, which is a car nothing can say the length of. */
export function merged(
  car: CarDoc,
  catalogue: Record<string, ModelDoc>,
): Merged | null {
  const model = catalogue[car.model];
  if (model === undefined) return null;
  return {
    model: model.model,
    kind: car.kind ?? model.kind,
    length: car.length ?? model.length,
    addr: car.addr ?? null,
    functions: car.functions ?? model.functions ?? {},
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
 * nothing but locomotives is a `light engine` (CONTEXT.md, **Kind**).
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
        byName.set(fn.name, { name: fn.name, values: fn.values ?? OFF_ON });
      }
    }
  }
  return [...byName.values()];
}

/**
 * The name a promoted entry is filed under: the model's, with the lowest
 * suffix nothing has taken — `arnold-ce68-1` until a person calls it
 * `krokodil-a`.
 *
 * Minted rather than asked for, because nothing should have to classify an
 * item before adding it: filling in an address is the whole gesture, and the
 * name is what the roster then needs to refer to it by.
 */
export function mint(model: string, taken: Iterable<string>): string {
  const already = new Set(taken);
  for (let n = 1; ; n++) {
    const name = `${model}-${n}`;
    if (!already.has(name)) return name;
  }
}

/** Whether a name is one a document may be filed under: the store refuses a
 *  `.` or a `/` in one, and an empty name names nothing
 *  (`tc49.lib.layout.check_name`). */
export function nameable(name: string): boolean {
  return name !== "" && !name.includes(".") && !name.includes("/");
}

/** What names a car, in words: the trains whose entries do. Empty where
 *  nothing holds it. */
export function carHolders(name: string, roster: RosterDoc): string[] {
  return Object.entries(roster.trains)
    .filter(([, train]) => (train.cars ?? []).some((entry) => entry.car === name))
    .map(([train]) => `train '${train}'`);
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
 * Why a car's length may not be corrected, or `null` where it may.
 *
 * A length lives on the model as well as the car, and correcting either moves
 * a train the dispatcher is fitting into blocks right now. So it is off while
 * the run shows a train made of that item placed, and the reason names the
 * train (ui/STOCK.md#the-length-guard).
 *
 * **A guard in one browser.** The run state comes down from the app, which is
 * the only thing on this page that has any; a second browser editing stock
 * during a run is not covered, and closing that properly is #390's.
 */
export function carHeldByRun(
  name: string,
  roster: RosterDoc,
  placed: Iterable<string>,
): string | null {
  return onLayout(
    roster,
    placed,
    (entry) => entry.car === name,
  );
}

/** Why a model's length may not be corrected, or `null` where it may. A model
 *  is used by a placed train through an anonymous entry or through a car, so
 *  both are asked. */
export function modelHeldByRun(
  name: string,
  roster: RosterDoc,
  placed: Iterable<string>,
): string | null {
  const cars = new Set(
    Object.entries(roster.cars ?? {})
      .filter(([, car]) => car.model === name)
      .map(([car]) => car),
  );
  return onLayout(
    roster,
    placed,
    (entry) =>
      entry.model === name || (entry.car !== undefined && cars.has(entry.car)),
  );
}

/** The first placed train an entry of this description is in, said as the
 *  reason a control is dead. */
function onLayout(
  roster: RosterDoc,
  placed: Iterable<string>,
  names: (entry: Coupled) => boolean,
): string | null {
  for (const train of placed) {
    if (roster.trains[train]?.cars?.some(names) === true) {
      return `'${train}' is on the layout — take it off to correct a length`;
    }
  }
  return null;
}

// --- the screen's session -------------------------------------------------

/** One car as the list above draws it: what it is, what is its own, and why
 *  its length may not be corrected. */
export interface CarRow {
  name: string;
  model: string;
  addr: string | null;
  /** Merged, so `null` only where the catalogue has no such model. */
  length: number | null;
  kind: string | null;
  /** Whether that length is the car's own rather than the model's. */
  own: boolean;
  held: string | null;
}

/** One model as the list below draws it, with what names it: ten identical
 *  hoppers are this one row (ADR-0061). */
export interface ModelRow {
  model: string;
  kind: string;
  length: number;
  holders: string[];
  held: string | null;
}

/** One place in a train: what stands there and which way round, with the
 *  address offered whatever its kind — a powered van is a real thing, so the
 *  field is offered and never assumed (ADR-0061, `layout/interface.py`). */
export interface EntryRow {
  /** The car it names, `null` where the entry is anonymous. */
  car: string | null;
  /** What it is, however it was named; `null` where the documents have not
   *  got it. */
  model: string | null;
  addr: string | null;
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
  placed: boolean;
  /** Whether it **states its length and names no cars**, which is the shape a
   *  roster written before #223 has: the length is that stated number rather
   *  than a sum, there is no kind and no function to read off a car, and the
   *  first entry converts it (#414). */
  stated: boolean;
}

/**
 * The stock screen's session: the roster being edited, the catalogue it is
 * read against, and every edit either of them takes.
 *
 * It holds the documents rather than a projection of them, so what is saved is
 * what was read with the edits on it and nothing is reassembled — `GET` and
 * `PUT` on `/rosters/<railroad>` are inverses, and a car left out is a car
 * removed (#388).
 *
 * **A model is written the moment it is made and the roster when Save is
 * pressed.** They are two documents on two routes: a roster naming a model the
 * installation has not got is refused whole, so the product exists before
 * anything refers to it (#392).
 *
 * Every method that can refuse answers with the words to show and changes
 * nothing, rather than throwing: a refusal here is an ordinary answer about a
 * document being edited, exactly as `/review`'s is
 * ([ADR-0021](../../../docs/adr/0021-a-bad-request-is-answered-not-raised.md)).
 */
export class Stock {
  private doc: RosterDoc;
  private models: Record<string, ModelDoc>;
  private dirty = false;

  constructor(roster: RosterDoc, catalogue: Record<string, ModelDoc>) {
    this.doc = roster;
    this.models = catalogue;
  }

  /** The roster as it stands, which is what `PUT` is given. */
  get roster(): RosterDoc {
    return this.doc;
  }

  get catalogue(): Record<string, ModelDoc> {
    return this.models;
  }

  /** Whether the roster holds edits the store has not been given. A model is
   *  not counted: it was written when it was made. */
  get edits(): boolean {
    return this.dirty;
  }

  /** The store took the roster. */
  kept(): void {
    this.dirty = false;
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
    return empty === undefined
      ? null
      : `train '${empty[0]}' has nothing in it — press + beside a car or a` +
          ` model, or remove it`;
  }

  // --- what the three lists draw -------------------------------------------

  cars(placed: readonly string[] = []): CarRow[] {
    return Object.entries(this.doc.cars ?? {})
      .sort(([one], [other]) => (one < other ? -1 : 1))
      .map(([name, car]) => {
        const whole = merged(car, this.models);
        return {
          name,
          model: car.model,
          addr: car.addr ?? null,
          length: whole?.length ?? null,
          kind: whole?.kind ?? null,
          own: car.length !== undefined,
          held: carHeldByRun(name, this.doc, placed),
        };
      });
  }

  modelRows(placed: readonly string[] = []): ModelRow[] {
    return Object.values(this.models)
      .sort((one, other) => (one.model < other.model ? -1 : 1))
      .map((model) => ({
        model: model.model,
        kind: model.kind,
        length: model.length,
        holders: modelHolders(model.model, this.doc),
        held: modelHeldByRun(model.model, this.doc, placed),
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
        placed: onLayout.has(train),
        stated: made.length !== undefined,
      }));
  }

  private entry(entry: Coupled): EntryRow {
    const whole = stands(entry, this.doc, this.models);
    return {
      car: entry.car ?? null,
      model: whole?.model ?? entry.model ?? null,
      addr: whole?.addr ?? null,
      length: whole?.length ?? null,
      reverse: entry.orientation === REVERSE,
    };
  }

  // --- trains ---------------------------------------------------------------

  /** Make up a train: a name and nothing in it yet, which is what composing
   *  right from left starts with. */
  addTrain(name: string): string | null {
    if (!nameable(name)) return `'${name}' is not a name a train can have`;
    if (this.doc.trains[name] !== undefined) return `there is already a train '${name}'`;
    this.write({ trains: { ...this.doc.trains, [name]: { cars: [] } } });
    return null;
  }

  renameTrain(was: string, name: string): string | null {
    if (name === was) return null;
    if (!nameable(name)) return `'${name}' is not a name a train can have`;
    if (this.doc.trains[name] !== undefined) return `there is already a train '${name}'`;
    const train = this.doc.trains[was];
    if (train === undefined) return null;
    const trains: Record<string, RosterTrain> = {};
    for (const [key, one] of Object.entries(this.doc.trains)) {
      trains[key === was ? name : key] = one;
    }
    this.write({ trains });
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
   * Put something at the tail of a train: a car from the list above, or a
   * model from the list below, which gives an anonymous item.
   *
   * The first entry on a train that **states its length** converts it: the
   * stated number goes and the length is derived from then on (#414).
   */
  append(train: string, what: { car: string } | { model: string }): void {
    this.inTrain(train, (cars) => [...cars, what]);
  }

  removeEntry(train: string, index: number): void {
    this.inTrain(train, (cars) => cars.filter((_, at) => at !== index));
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

  /**
   * An address typed against one place in a train.
   *
   * **This is what promotes an anonymous entry to a car**: an address is the
   * physical identity, so having one is exactly what puts an item on `cars`
   * (ADR-0061). The name is minted from the model and is the person's to
   * change afterwards; nothing asked them to classify the item before they
   * added it.
   *
   * An entry that already names a car has that car's address set instead, and
   * clearing it leaves the car — a car with neither an address nor an override
   * is still legal, and a person who named one meant to.
   */
  address(train: string, index: number, addr: string): string | null {
    const entry = this.doc.trains[train]?.cars?.[index];
    if (entry === undefined) return null;
    const wanted = addr.trim();
    if (entry.car !== undefined) return this.carAddress(entry.car, wanted);
    if (wanted === "") return null;
    const clash = this.wearing(wanted, null);
    if (clash !== null) return clash;
    const model = entry.model;
    if (model === undefined) return null;
    const name = mint(model, Object.keys(this.doc.cars ?? {}));
    this.write({
      cars: { ...this.doc.cars, [name]: { model, addr: wanted } },
      trains: {
        ...this.doc.trains,
        [train]: {
          ...this.doc.trains[train]!,
          cars: this.doc.trains[train]!.cars!.map((one, at) =>
            at === index ? promoted(one, name) : one,
          ),
        },
      },
    });
    return null;
  }

  // --- cars -----------------------------------------------------------------

  renameCar(was: string, name: string): string | null {
    if (name === was) return null;
    if (!nameable(name)) return `'${name}' is not a name a car can have`;
    if (this.doc.cars?.[name] !== undefined) return `there is already a car '${name}'`;
    const car = this.doc.cars?.[was];
    if (car === undefined) return null;
    const cars: Record<string, CarDoc> = {};
    for (const [key, one] of Object.entries(this.doc.cars ?? {})) {
      cars[key === was ? name : key] = one;
    }
    this.write({ cars, trains: this.renamed(was, name) });
    return null;
  }

  /** The number programmed into a car's decoder. Two cars on one address both
   *  answer the same packet, which is what the store refuses; it is refused
   *  here so the words name the other car rather than arriving on a save. */
  carAddress(name: string, addr: string): string | null {
    const car = this.doc.cars?.[name];
    if (car === undefined) return null;
    const wanted = addr.trim();
    if (wanted === "") {
      const { addr: _was, ...rest } = car;
      this.write({ cars: { ...this.doc.cars, [name]: rest } });
      return null;
    }
    const clash = this.wearing(wanted, name);
    if (clash !== null) return clash;
    this.write({ cars: { ...this.doc.cars, [name]: { ...car, addr: wanted } } });
    return null;
  }

  /**
   * A length corrected on this item and not on the product. `null` takes the
   * override off, and the car reads its model's length again.
   *
   * Refused while the run shows a train made of the item placed: the
   * dispatcher is fitting that train into blocks on the length this answers
   * (ui/STOCK.md#the-length-guard).
   */
  carLength(name: string, mm: number | null, placed: readonly string[] = []): string | null {
    const car = this.doc.cars?.[name];
    if (car === undefined) return null;
    const held = carHeldByRun(name, this.doc, placed);
    if (held !== null) return held;
    if (mm === null) {
      const { length: _was, ...rest } = car;
      this.write({ cars: { ...this.doc.cars, [name]: rest } });
      return null;
    }
    if (!Number.isInteger(mm) || mm <= 0) return "a length is a positive whole number of millimetres";
    this.write({ cars: { ...this.doc.cars, [name]: { ...car, length: mm } } });
    return null;
  }

  /** Take a car off the roster. Refused while a train is made of it, and the
   *  refusal says which. */
  removeCar(name: string): string | null {
    const holders = carHolders(name, this.doc);
    if (holders.length > 0) return heldBy(`car '${name}'`, holders);
    const cars = { ...this.doc.cars };
    delete cars[name];
    this.write({ cars });
    return null;
  }

  // --- models ---------------------------------------------------------------

  /** A model the store has taken, in the catalogue this roster is read
   *  against. Written rather than merged: `PUT /catalogue/<name>` replaces the
   *  document, so this holds what the store now has. */
  putModel(model: ModelDoc): void {
    this.models = { ...this.models, [model.model]: model };
  }

  /**
   * What stops a model being made under this name, or `null` where nothing
   * does.
   *
   * A name the catalogue already has is the one thing. `PUT
   * /catalogue/<name>` replaces the document whole, so Create under a name in
   * use would rewrite that product's kind, length and functions for every
   * railroad in the installation — and step around the length guard the
   * product's own row keeps, a placed train's derived length moving under the
   * dispatcher with nothing said. A dialog labelled New model touches nothing
   * that exists, and correcting a product is done on its row (#413).
   */
  stopsMaking(name: string): string | null {
    return this.models[name] === undefined
      ? null
      : `there is already a model '${name}'`;
  }

  /** Correcting a product's length changes every item of that product, which
   *  is the whole reason the length lives here as well as on the car. Refused
   *  while a placed train uses one. */
  modelLength(name: string, mm: number, placed: readonly string[] = []): string | null {
    const model = this.models[name];
    if (model === undefined) return null;
    const held = modelHeldByRun(name, this.doc, placed);
    if (held !== null) return held;
    if (!Number.isInteger(mm) || mm <= 0) return "a length is a positive whole number of millimetres";
    this.putModel({ ...model, length: mm });
    return null;
  }

  // --- writing --------------------------------------------------------------

  /** One edit to the roster: a new document with the edit on it, and the
   *  screen marked as holding something the store has not been given. */
  private write(part: Partial<RosterDoc>): void {
    this.doc = { ...this.doc, ...part };
    this.dirty = true;
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

  /** The car already wearing an address, said as a refusal, or `null` where
   *  none is. */
  private wearing(addr: string, but: string | null): string | null {
    for (const [name, car] of Object.entries(this.doc.cars ?? {})) {
      if (name !== but && car.addr === addr) {
        return `car '${name}' already wears address '${addr}'`;
      }
    }
    return null;
  }
}

/** The promoted entry: the car it now names, keeping which way round it was
 *  coupled. Written out rather than spread over the old one, so the saved
 *  document never names both a car and a model — the store refuses one that
 *  does (`store/stock.py`). */
function promoted(entry: Coupled, car: string): Coupled {
  return entry.orientation === undefined
    ? { car }
    : { car, orientation: entry.orientation };
}
