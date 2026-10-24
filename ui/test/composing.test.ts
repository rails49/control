/**
 * Composing stock: what the screen holds and every rule over it
 * (`model/stock.ts`, ui/STOCK.md, #393).
 *
 * No DOM. What is under test is the third kind of thing the app has — neither
 * the document nor the DOM (ui/README.md): what a model put in a train goes
 * in as, what a train's length and kind derive to, what holds a thing
 * somebody asked to remove, and why a length may not be corrected.
 *
 * The derivations are pinned against `tc49.lib.roster.Train`'s, which is the
 * other implementation of the same three rules: the browser derives a train
 * that has not been saved, and the store derives one that has.
 */

import { describe, expect, it } from "vitest";

import {
  LENGTH_UNHEARD,
  LIGHT_ENGINE,
  lengthHeld,
  MIXED,
  keyFor,
  merged,
  Stock,
  trainFunctions,
  trainKind,
  trainLength,
} from "../src/model/stock.js";
import type { CarDoc, ModelDoc, RosterDoc } from "../src/model/store.js";

const CATALOGUE: Record<string, ModelDoc> = {
  "arnold-ce68": {
    model: "arnold-ce68",
    kind: "locomotive",
    length: 122,
    functions: { "0": { name: "headlights" } },
  },
  hopper: { model: "hopper", kind: "freight", length: 100 },
  coach: { model: "coach", kind: "passenger", length: 200 },
  van: {
    model: "van",
    kind: "freight",
    length: 90,
    functions: { "3": { name: "vacuum" } },
  },
};

/** The ore train of ADR-0061: a Krokodil with something to say about it, and
 *  three hoppers with nothing. */
const OVAL: RosterDoc = {
  roster: "oval",
  cars: { "krokodil-a": { model: "arnold-ce68", addr: "3" } },
  trains: {
    ore: {
      cars: [
        { car: "krokodil-a" },
        { model: "hopper" },
        { model: "hopper" },
        { model: "hopper" },
      ],
    },
  },
};

/** A fresh screen over a copy, so one test's edits are not the next's. */
function stock(roster: RosterDoc = OVAL): Stock {
  return new Stock(JSON.parse(JSON.stringify(roster)) as RosterDoc, CATALOGUE);
}

const EMPTY: RosterDoc = { roster: "oval", trains: {} };

/** The shape a roster written before #223 has: a train stating its length and
 *  naming no cars, which the store keeps legal for an older file and answers
 *  as written (`store/stock.py`, #414). */
const OLDER: RosterDoc = { roster: "oval", trains: { goods: { length: 400 } } };

describe("what a train derives to", () => {
  it("is the sum of every entry, car and model alike", () => {
    expect(trainLength(OVAL.trains.ore!, OVAL, CATALOGUE)).toBe(122 + 100 * 3);
  });

  it("has no length where an entry names something the documents have not", () => {
    const roster: RosterDoc = { roster: "oval", trains: { ore: { cars: [{ model: "flat" }] } } };
    expect(trainLength(roster.trains.ore!, roster, CATALOGUE)).toBeNull();
  });

  /** Every hauled train has a locomotive, so counting them would make every
   *  train mixed (GLOSSARY.md, **Kind**). */
  it("takes its kind from what it hauls, ignoring locomotives", () => {
    expect(trainKind(OVAL.trains.ore!, OVAL, CATALOGUE)).toBe("freight");
  });

  it("is mixed where it hauls more than one sort", () => {
    const roster: RosterDoc = {
      roster: "oval",
      trains: { mail: { cars: [{ model: "hopper" }, { model: "coach" }] } },
    };
    expect(trainKind(roster.trains.mail!, roster, CATALOGUE)).toBe(MIXED);
  });

  it("has no kind where it names nothing at all", () => {
    const bare: RosterDoc = { roster: "oval", trains: { new: { cars: [] } } };
    expect(trainKind(bare.trains.new!, bare, CATALOGUE)).toBeNull();
  });

  it("is a light engine where it hauls nothing", () => {
    const roster: RosterDoc = {
      roster: "oval",
      cars: { "krokodil-a": { model: "arnold-ce68", addr: "3" } },
      trains: { light: { cars: [{ car: "krokodil-a" }] } },
    };
    expect(trainKind(roster.trains.light!, roster, CATALOGUE)).toBe(LIGHT_ENGINE);
  });

  /** In the train's frame: a set with a locomotive at each end has one
   *  headlight to press, not two, and no number is shown. */
  it("collects its functions by name, first entry first and each name once", () => {
    const roster: RosterDoc = {
      roster: "oval",
      cars: {
        a: { model: "arnold-ce68", addr: "3" },
        b: { model: "arnold-ce68", addr: "4" },
      },
      trains: {
        topped: { cars: [{ car: "a" }, { model: "van" }, { car: "b" }] },
      },
    };
    expect(trainFunctions(roster.trains.topped!, roster, CATALOGUE)).toEqual([
      { name: "headlights", mode: "latching" },
      { name: "vacuum", mode: "latching" },
    ]);
  });
});

/** A roster written before #223 states a train's length and names no cars.
 *  The store keeps it legal and answers the file as written, so the screen
 *  reads one: the derivations answer for what is not there, and the first
 *  entry converts the train (#414). */
describe("a train that states its length and names no cars", () => {
  it("is as long as it says, having no cars to sum", () => {
    expect(trainLength(OLDER.trains.goods!, OLDER, CATALOGUE)).toBe(400);
  });

  /** The same answer `tc49.lib.roster.Train` gives the same document: there
   *  is no car to read a kind or a function off. */
  it("has no kind and no functions", () => {
    expect(trainKind(OLDER.trains.goods!, OLDER, CATALOGUE)).toBeNull();
    expect(trainFunctions(OLDER.trains.goods!, OLDER, CATALOGUE)).toEqual([]);
  });

  it("draws as a row with its stated length and nothing in it", () => {
    const [row] = stock(OLDER).trains();
    expect(row).toMatchObject({
      train: "goods",
      length: 400,
      kind: null,
      stated: true,
    });
    expect(row!.entries).toEqual([]);
    expect(row!.functions).toEqual([]);
  });

  it("is not a train with nothing in it, and stops no save", () => {
    const screen = stock(OLDER);
    expect(screen.stopsSaving()).toBeNull();
    expect(screen.edits).toBe(false);
    expect(screen.roster.trains.goods).toEqual({ length: 400 });
  });

  /** A train says one or the other and never both, and the store refuses one
   *  that says both: the first entry drops the stated number, and the length
   *  is derived from then on. */
  it("becomes the ordinary shape when something is put in it", () => {
    const screen = stock(OLDER);
    screen.append("goods", { model: "hopper" });
    expect(screen.roster.trains.goods).toEqual({ cars: [{ model: "hopper" }] });
    expect(screen.trains()[0]).toMatchObject({ length: 100, kind: "freight", stated: false });
  });

  it("keeps its stated length through a rename of a car", () => {
    const screen = stock({
      ...OLDER,
      cars: { "krokodil-a": { model: "arnold-ce68", addr: "3" } },
    });
    expect(screen.renameCar("krokodil-a", "krokodil")).toBeNull();
    expect(screen.roster.trains.goods).toEqual({ length: 400 });
  });
});

describe("making up a train", () => {
  it("starts with a name and nothing in it", () => {
    const screen = stock(EMPTY);
    expect(screen.addTrain("ore")).toBeNull();
    expect(screen.roster.trains.ore).toEqual({ cars: [] });
    expect(screen.edits).toBe(true);
  });

  it("takes a name of any characters, and refuses a second train of one name", () => {
    const screen = stock();
    expect(screen.addTrain("S 1/S 2")).toBeNull();
    expect(screen.addTrain("ore")).toBe("There is already a train 'ore'.");
    expect(Object.keys(screen.roster.trains)).toEqual(["ore", "S 1/S 2"]);
  });

  it("adds a model entry as an anonymous item", () => {
    const screen = stock(EMPTY);
    screen.addTrain("ore");
    screen.append("ore", { model: "hopper" });
    expect(screen.roster.trains.ore!.cars).toEqual([{ model: "hopper" }]);
  });

  it("is New train, then New train (2), with nothing in it", () => {
    const screen = stock(EMPTY);
    expect(screen.newTrain()).toBe("New train");
    expect(screen.newTrain()).toBe("New train (2)");
    expect(screen.roster.trains["New train (2)"]).toEqual({ cars: [] });
  });

  /** One item cannot stand in a train twice. */
  it("refuses a car the train already has", () => {
    const screen = stock();
    expect(screen.append("ore", { car: "krokodil-a" })).toBe(
      "krokodil-a is already in ore. One item cannot stand in a train twice.",
    );
    expect(screen.roster.trains.ore!.cars).toHaveLength(4);
    expect(screen.edits).toBe(false);
  });

  it("moves an entry to where it is dropped", () => {
    const screen = stock();
    screen.moveEntry("ore", 0, 3);
    expect(screen.roster.trains.ore!.cars!.map((one) => one.car ?? one.model)).toEqual([
      "hopper",
      "hopper",
      "hopper",
      "krokodil-a",
    ]);
    screen.moveEntry("ore", 3, 0);
    expect(screen.roster.trains.ore!.cars![0]).toEqual({ car: "krokodil-a" });
  });

  it("sets a priority, takes it off when emptied, and refuses one that is none", () => {
    const screen = stock();
    expect(screen.trainPriority("ore", "2")).toBeNull();
    expect(screen.roster.trains.ore!.priority).toBe(2);
    expect(screen.trainPriority("ore", "0")).toBe(
      "'0' is not a priority. Use a whole number: 1 is highest.",
    );
    expect(screen.trainPriority("ore", "")).toBeNull();
    expect(screen.roster.trains.ore!.priority).toBeUndefined();
  });

  it("turns an item round, and back by taking the key off", () => {
    const screen = stock();
    screen.turn("ore", 0);
    expect(screen.roster.trains.ore!.cars![0]).toEqual({
      car: "krokodil-a",
      orientation: "reverse",
    });
    screen.turn("ore", 0);
    expect(screen.roster.trains.ore!.cars![0]).toEqual({ car: "krokodil-a" });
  });

  /** The store refuses an empty `cars` list, so the screen refuses the save
   *  first and the words name the row to go and fill (#412). */
  it("stops the save while a train has nothing in it, and names the train", () => {
    const screen = stock(EMPTY);
    screen.addTrain("ore");
    expect(screen.stopsSaving()).toBe(
      "train 'ore' has nothing in it — press Add to put a car or a model in it, or unmake it",
    );
    expect(screen.edits).toBe(true);
    screen.append("ore", { model: "hopper" });
    expect(screen.stopsSaving()).toBeNull();
  });

  /** The same rule from a **hand-edited file**, which is a supported way to
   *  work: a train naming neither `cars` nor a length is the same train with
   *  nothing in it, and the store refuses it in the same words as an empty
   *  `cars` list (`lib/stock.py`, *names no cars*). Composing cannot make it
   *  — `addTrain` writes an empty list — so the guard reads the shape rather
   *  than the key, and the words stay the screen's about the row (#447). */
  it("stops the save for a train naming neither cars nor a length", () => {
    const words =
      "train 'goods' has nothing in it — press Add to put a car or a model in it, or unmake it";
    expect(stock({ roster: "oval", trains: { goods: {} } }).stopsSaving()).toBe(words);
    expect(stock({ roster: "oval", trains: { goods: { cars: [] } } }).stopsSaving()).toBe(
      words,
    );
    // The older shape states its length and names no cars, and goes on saving.
    expect(stock(OLDER).stopsSaving()).toBeNull();
  });

  it("stops nothing where every train has something in it", () => {
    expect(stock().stopsSaving()).toBeNull();
    expect(stock(EMPTY).stopsSaving()).toBeNull();
  });

  it("unmakes a rake without taking its cars off the roster", () => {
    const screen = stock();
    screen.removeTrain("ore");
    expect(screen.roster.trains).toEqual({});
    expect(screen.roster.cars).toEqual({ "krokodil-a": { model: "arnold-ce68", addr: "3" } });
  });
});

/** A model put in a train goes in as a model entry where it has no decoder,
 *  and as a car where it has one: an address belongs to one item (#980). */
describe("a model put in a train", () => {
  it("goes in as a model entry where it has no decoder", () => {
    const screen = stock();
    expect(screen.addModel("ore", "hopper")).toEqual({ as: "model" });
    expect(screen.roster.trains.ore!.cars!.at(-1)).toEqual({ model: "hopper" });
  });

  it("makes a car of a decoder model the railroad has none of to spare", () => {
    const screen = stock();
    expect(screen.addModel("ore", "arnold-ce68")).toEqual({ as: "made", car: "arnold-ce68" });
    expect(screen.roster.cars!["arnold-ce68"]).toEqual({ model: "arnold-ce68" });
    expect(screen.roster.trains.ore!.cars!.at(-1)).toEqual({ car: "arnold-ce68" });
  });

  it("puts in the one car of it the railroad has", () => {
    const screen = stock(EMPTY);
    screen.addTrain("light");
    screen.newCar("arnold-ce68");
    expect(screen.addModel("light", "arnold-ce68")).toEqual({ as: "only", car: "arnold-ce68" });
    expect(screen.roster.trains.light!.cars).toEqual([{ car: "arnold-ce68" }]);
  });

  it("puts in nothing yet where there are several, and lists them", () => {
    const screen = stock();
    screen.newCar("arnold-ce68");
    expect(screen.addModel("ore", "arnold-ce68")).toEqual({ as: "which" });
    expect(screen.roster.trains.ore!.cars).toHaveLength(4);
    expect(screen.carsOf("ore", "arnold-ce68")).toEqual([
      { car: "arnold-ce68", inTrain: false },
      { car: "krokodil-a", inTrain: true },
    ]);
  });
});

describe("filling in a camera", () => {
  it("sets a car's camera, trimmed", () => {
    const screen = stock();
    expect(screen.carCamera("krokodil-a", " cam-1.local ")).toBeNull();
    expect(screen.roster.cars!["krokodil-a"]).toEqual({
      model: "arnold-ce68",
      addr: "3",
      camera: "cam-1.local",
    });
    expect(screen.edits).toBe(true);
  });

  it("clears a camera without taking the car off the roster", () => {
    const screen = stock({
      ...OVAL,
      cars: { "krokodil-a": { model: "arnold-ce68", addr: "3", camera: "192.168.178.58" } },
    });
    expect(screen.carCamera("krokodil-a", "  ")).toBeNull();
    expect(screen.roster.cars!["krokodil-a"]).toEqual({ model: "arnold-ce68", addr: "3" });
  });

  /** How the camera is spoken to is the `camera` app's (ADR-0082): the
   *  roster holds where it answers and nothing else, as `lib/stock.py` has. */
  it.each(["http://cam", "cam:8080", "cam/stream", "admin@cam", "-cam", "cam.", "two words"])(
    "refuses %j, which is not a camera address",
    (typed) => {
      const screen = stock();
      expect(screen.carCamera("krokodil-a", typed)).toBe(
        `'${typed}' is not a camera address — write the camera's host name or IP address`,
      );
      expect(screen.roster.cars!["krokodil-a"]).toEqual({ model: "arnold-ce68", addr: "3" });
      expect(screen.edits).toBe(false);
    },
  );

  /** One camera rides in one car: two naming it would put one picture on two
   *  trains. The store refuses it; this says which car has it. */
  it("refuses a camera another car already carries, and names it", () => {
    const screen = stock({
      ...OVAL,
      cars: {
        "krokodil-a": { model: "arnold-ce68", addr: "3", camera: "cam-1" },
        "van-1": { model: "van" },
      },
    });
    expect(screen.carCamera("van-1", "cam-1")).toBe(
      "car 'krokodil-a' already carries camera 'cam-1'",
    );
    expect(screen.roster.cars!["van-1"]).toEqual({ model: "van" });
    expect(screen.carCamera("krokodil-a", "cam-1")).toBeNull();
  });



});

describe("a car of one's own", () => {
  it("can stand in no train at all", () => {
    const screen = stock(EMPTY);
    screen.addTrain("ore");
    screen.addModel("ore", "arnold-ce68");
    screen.removeTrain("ore");
    expect(screen.cars().map((car) => car.name)).toEqual(["arnold-ce68"]);
  });

  it("is renamed everywhere a train names it", () => {
    const screen = stock();
    expect(screen.renameCar("krokodil-a", "krokodil")).toBeNull();
    expect(Object.keys(screen.roster.cars!)).toEqual(["krokodil"]);
    expect(screen.roster.trains.ore!.cars![0]).toEqual({ car: "krokodil" });
  });

  it("draws its model's length until it corrects one", () => {
    const screen = stock();
    expect(screen.cars()[0]).toMatchObject({ length: 122, own: false });
    expect(screen.carLength("krokodil-a", 130)).toBeNull();
    expect(screen.cars()[0]).toMatchObject({ length: 130, own: true });
    expect(screen.carLength("krokodil-a", null)).toBeNull();
    expect(screen.cars()[0]).toMatchObject({ length: 122, own: false });
  });

  it("refuses a length that is not a positive whole number of millimetres", () => {
    const screen = stock();
    expect(screen.carLength("krokodil-a", 0)).toMatch("positive whole number");
  });

  it("refuses a name another car has, in the editor's words", () => {
    const screen = stock();
    screen.newCar("hopper");
    expect(screen.renameCar("hopper", "krokodil-a")).toBe("There is already a car 'krokodil-a'.");
  });

  /** A DCC address is 1 to 10239, the long addresses' top; anything else is
   *  no address a decoder can be programmed with (#979). */
  it("refuses an address that is no DCC address, and changes nothing", () => {
    const screen = stock();
    const refused = "'abc' is not a DCC address. Use a number from 1 to 10239.";
    expect(screen.carAddress("krokodil-a", "abc")).toBe(refused);
    expect(screen.carAddress("krokodil-a", "0")).toMatch("'0' is not a DCC address");
    expect(screen.carAddress("krokodil-a", "10240")).toMatch("'10240' is not a DCC address");
    expect(screen.roster.cars!["krokodil-a"]!.addr).toBe("3");
    expect(screen.edits).toBe(false);
  });

  it("refuses an address another car has, naming that car", () => {
    const screen = stock();
    const name = screen.newCar("arnold-ce68")!;
    expect(screen.carAddress(name, "3")).toBe("Car krokodil-a already has address 3.");
    expect(screen.carAddress(name, "10239")).toBeNull();
    expect(screen.roster.cars![name]!.addr).toBe("10239");
  });

  it("writes its own notes, and takes the key off where they are emptied", () => {
    const screen = stock();
    screen.carNotes("krokodil-a", "repainted");
    expect(screen.roster.cars!["krokodil-a"]!.notes).toBe("repainted");
    expect(screen.cars()[0]).toMatchObject({ notes: "repainted" });
    screen.carNotes("krokodil-a", "");
    expect("notes" in screen.roster.cars!["krokodil-a"]!).toBe(false);
  });

  it("draws what the editor shows of it: its model's decoder, notes and the trains holding it", () => {
    const screen = stock();
    expect(screen.cars()[0]).toMatchObject({
      decoder: true,
      modelLength: 122,
      modelNotes: null,
      notes: null,
      ownFunctions: false,
      trains: ["ore"],
    });
  });
});

/** A car whose decoder is not its model's: the model's functions copied onto
 *  it as rows to edit, and taken off again to read the model's (#979). */
describe("a car's own functions", () => {
  it("starts as a copy of the model's, written on the car", () => {
    const screen = stock();
    screen.ownFunctions("krokodil-a");
    expect(screen.functionRows({ car: "krokodil-a" })).toEqual([
      { number: "0", name: "headlights", mode: "latching" },
    ]);
    expect(screen.roster.cars!["krokodil-a"]!.functions).toEqual({ "0": { name: "headlights" } });
    expect(screen.cars()[0]!.ownFunctions).toBe(true);
  });

  it("is edited as the model's rows are, and leaves the model alone", () => {
    const screen = stock();
    const krokodil = { car: "krokodil-a" };
    screen.ownFunctions("krokodil-a");
    screen.addFunction(krokodil);
    screen.functionName(krokodil, 1, "Horn");
    screen.functionMode(krokodil, 1, "momentary");
    expect(screen.roster.cars!["krokodil-a"]!.functions).toEqual({
      "0": { name: "headlights" },
      "1": { name: "Horn", mode: "momentary" },
    });
    expect(screen.model("arnold-ce68")!.functions).toEqual({ "0": { name: "headlights" } });
    expect(screen.corrections).toEqual([]);
  });

  it("stops Save while one of its rows has no name", () => {
    const screen = stock();
    screen.ownFunctions("krokodil-a");
    screen.addFunction({ car: "krokodil-a" });
    expect(screen.stopsSaving()).toBe("F1 needs a name.");
  });

  it("goes with Use the model's functions again", () => {
    const screen = stock();
    screen.ownFunctions("krokodil-a");
    screen.addFunction({ car: "krokodil-a" });
    screen.modelFunctions("krokodil-a");
    expect("functions" in screen.roster.cars!["krokodil-a"]!).toBe(false);
    expect(screen.stopsSaving()).toBeNull();
    expect(screen.functionRows({ car: "krokodil-a" })).toEqual([]);
  });

  it("follows the car through a rename", () => {
    const screen = stock();
    screen.ownFunctions("krokodil-a");
    screen.addFunction({ car: "krokodil-a" });
    screen.renameCar("krokodil-a", "krokodil");
    expect(screen.stopsSaving()).toBe("F1 needs a name.");
    expect(screen.functionRows({ car: "krokodil" })).toHaveLength(2);
  });
});

/**
 * What a car says over its model, and what counts as saying it.
 *
 * The two bindings have to agree, `tc49.lib.stock._car` being the other one:
 * it branches on the key being written, so a car that wrote `functions:` with
 * a YAML null is a correction typed wrong and the store refuses the whole
 * document. A browser that read that null as "nothing said" would draw a
 * train off the product's functions and hand the store a roster it will not
 * take.
 */
describe("a car merged onto its model", () => {
  it("inherits what it says nothing about", () => {
    expect(merged({ model: "van" }, CATALOGUE)).toEqual({
      model: "van",
      kind: "freight",
      length: 90,
      addr: null,
      functions: { "3": { name: "vacuum" } },
    });
  });

  it("takes what it corrects", () => {
    expect(merged({ model: "van", kind: "special", length: 95 }, CATALOGUE)).toMatchObject({
      kind: "special",
      length: 95,
    });
  });

  /** A null the store refuses reaches no fallback: what is written is the
   *  correction, whatever was written. The cast is the point — the shape is
   *  one no document may have, and it arrives from a file all the same. */
  it("does not read a written null as nothing said", () => {
    const wrong = { model: "van", functions: null } as unknown as CarDoc;
    expect(merged(wrong, CATALOGUE)!.functions).toBeNull();
  });

  /** An item with no decoder has no address rather than its product's, which
   *  is `spec.get("addr")` at the other end. */
  it("has no address of its own until one is programmed", () => {
    expect(merged({ model: "van" }, CATALOGUE)!.addr).toBeNull();
    expect(merged({ model: "van", addr: "7" }, CATALOGUE)!.addr).toBe("7");
  });

  it("is nothing at all where the catalogue has no such model", () => {
    expect(merged({ model: "nothing-like-it" }, CATALOGUE)).toBeNull();
  });
});

describe("a refusal names what holds the thing", () => {
  it("keeps a car a train is made of, and says which train", () => {
    const screen = stock();
    expect(screen.removeCar("krokodil-a")).toBe("car 'krokodil-a' is held by train 'ore'");
    expect(screen.roster.cars!["krokodil-a"]).toBeDefined();
  });

  it("removes a car no train is made of", () => {
    const screen = stock();
    screen.removeTrain("ore");
    expect(screen.removeCar("krokodil-a")).toBeNull();
    expect(screen.roster.cars).toEqual({});
  });

  /** A model is held by a car that is one and by an entry that names it, and
   *  the row says both — the catalogue has no delete verb, so what holds a
   *  model is read rather than run into. */
  it("says what names a model: the cars that are one, then the trains", () => {
    const screen = stock();
    const rows = Object.fromEntries(screen.modelRows().map((row) => [row.model, row.holders]));
    expect(rows["arnold-ce68"]).toEqual(["car 'krokodil-a'"]);
    expect(rows["hopper"]).toEqual(["train 'ore'"]);
    expect(rows["coach"]).toEqual([]);
  });
});

/**
 * The length guard reads track power (ADR-0071, decision 5): with power on the
 * run moves trains over what the dispatcher built, and only a build with power
 * off can bring it a new length. Placed trains no longer hold it.
 */
describe("the length guard", () => {
  const WORDS = "track power is on — turn it off to correct a length";

  it("is off while power is on or draining, and moves no length", () => {
    for (const power of ["on", "draining"] as const) {
      const screen = stock();
      expect(screen.cars(power)[0]!.held).toBe(WORDS);
      expect(screen.modelRows(power).every((row) => row.held === WORDS)).toBe(true);
      expect(screen.carLength("krokodil-a", 130, power)).toBe(WORDS);
      expect(screen.modelLength("hopper", 110, power)).toBe(WORDS);
      expect(screen.roster.cars!["krokodil-a"]!.length).toBeUndefined();
      expect(screen.catalogue["hopper"]!.length).toBe(100);
      expect(screen.edits).toBe(false);
      expect(screen.lengthEdits).toBe(false);
    }
  });

  /** A train placed with power off holds nothing: the save names the railroad
   *  again and the rebuild keeps it where it still fits. */
  it("is on with power off, or with no session", () => {
    for (const power of ["off", null] as const) {
      const screen = stock();
      expect(screen.cars(power)[0]!.held).toBeNull();
      expect(screen.modelRows(power).every((row) => row.held === null)).toBe(true);
      expect(screen.modelLength("hopper", 110, power)).toBeNull();
      expect(screen.catalogue["hopper"]!.length).toBe(110);
    }
  });

  /** A page that has lost the broker still holds the roster, and cannot know
   *  whether the track has power (#804). Power on keeps its own words. */
  describe("with the row naming the railroad not heard", () => {
    const UNHEARD =
      "the layout has not said whether the track has power, so a length cannot be corrected";

    it("answers why, whatever power last read", () => {
      expect(lengthHeld(null, false)).toBe(UNHEARD);
      expect(lengthHeld("off", false)).toBe(UNHEARD);
      expect(lengthHeld("on", false)).toBe(WORDS);
      expect(lengthHeld("draining", false)).toBe(WORDS);
      expect(lengthHeld(null)).toBeNull();
    });

    it("is off, and moves no length", () => {
      for (const power of ["off", null] as const) {
        const screen = stock();
        expect(screen.cars(power, false)[0]!.held).toBe(UNHEARD);
        expect(screen.modelRows(power, false).every((row) => row.held === UNHEARD)).toBe(
          true,
        );
        expect(screen.carLength("krokodil-a", 130, power, false)).toBe(UNHEARD);
        expect(screen.modelLength("hopper", 110, power, false)).toBe(UNHEARD);
        expect(screen.roster.cars!["krokodil-a"]!.length).toBeUndefined();
        expect(screen.catalogue["hopper"]!.length).toBe(100);
        expect(screen.edits).toBe(false);
      }
    });
  });
});

/** A length correction waits for power off to be saved, and the roster records
 *  that it holds one until the store takes it (ADR-0071, decision 6). */
describe("a length edit in the roster", () => {
  const WAITS = "a length has changed — turn track power off to save";

  it("is recorded by a car's length, set or taken off, and cleared by kept", () => {
    const screen = stock();
    expect(screen.carLength("krokodil-a", 130, "off")).toBeNull();
    expect(screen.lengthEdits).toBe(true);
    screen.kept(screen.roster);
    expect(screen.lengthEdits).toBe(false);
    expect(screen.carLength("krokodil-a", null, "off")).toBeNull();
    expect(screen.lengthEdits).toBe(true);
  });

  it("is recorded by a model's length", () => {
    const screen = stock();
    screen.modelLength("hopper", 110, "off");
    expect(screen.lengthEdits).toBe(true);
  });

  /** A corrected model is written on the roster's Save, so it is an edit the
   *  page holds like any other (#718). */
  it("marks the roster as holding edits for a model's length", () => {
    const screen = stock();
    screen.modelLength("hopper", 110, "off");
    expect(screen.edits).toBe(true);
    expect(screen.corrections).toEqual([{ ...screen.catalogue["hopper"]!, length: 110 }]);
  });

  it("holds one correction per model, with the latest length", () => {
    const screen = stock();
    screen.modelLength("hopper", 110, "off");
    screen.modelLength("hopper", 120, "off");
    expect(screen.corrections.map((model) => [model.model, model.length])).toEqual([
      ["hopper", 120],
    ]);
  });

  it("drops a correction once it is written, and keeps the roster's edits", () => {
    const screen = stock();
    screen.modelLength("hopper", 110, "off");
    screen.landed(screen.corrections[0]!);
    expect(screen.corrections).toEqual([]);
    expect(screen.edits).toBe(true);
  });

  /** A length typed while the older one is being written is still to write. */
  it("keeps a correction made again while the older one was written", () => {
    const screen = stock();
    screen.modelLength("hopper", 110, "off");
    const writing = screen.corrections[0]!;
    screen.modelLength("hopper", 120, "off");
    screen.landed(writing);
    expect(screen.corrections.map((model) => model.length)).toEqual([120]);
  });

  it("is clear once each correction has landed and the roster is kept", () => {
    const screen = stock();
    screen.modelLength("hopper", 110, "off");
    screen.landed(screen.corrections[0]!);
    screen.kept(screen.roster);
    expect(screen.corrections).toEqual([]);
    expect(screen.edits).toBe(false);
    expect(screen.lengthEdits).toBe(false);
  });

  it("is not recorded by any other edit, or by a refused length", () => {
    const screen = stock();
    screen.carAddress("krokodil-a", "7");
    expect(screen.carLength("krokodil-a", 0, "off")).toMatch("positive whole number");
    expect(screen.edits).toBe(true);
    expect(screen.lengthEdits).toBe(false);
  });

  it("holds the Save while power is on or draining, and only then", () => {
    const screen = stock();
    screen.carLength("krokodil-a", 130, "off");
    expect(screen.waitsForPower("on")).toBe(WAITS);
    expect(screen.waitsForPower("draining")).toBe(WAITS);
    expect(screen.waitsForPower("off")).toBeNull();
    expect(screen.waitsForPower(null)).toBeNull();
  });

  /** The row not heard, a length edit waits for it: the page cannot know
   *  whether the track has power (#804). */
  it("holds the Save while the row is not heard, in its own words", () => {
    const screen = stock();
    screen.carLength("krokodil-a", 130, "off");
    expect(LENGTH_UNHEARD).toBe(
      "a length has changed — the layout has not said whether the track has power",
    );
    expect(screen.waitsForPower(null, false)).toBe(LENGTH_UNHEARD);
    expect(screen.waitsForPower("off", false)).toBe(LENGTH_UNHEARD);
    expect(screen.waitsForPower("on", false)).toBe(WAITS);
  });

  it("holds nothing for another edit with the row not heard", () => {
    const screen = stock();
    screen.carAddress("krokodil-a", "7");
    expect(screen.waitsForPower(null, false)).toBeNull();
  });

  it("holds nothing for another edit with power on", () => {
    const screen = stock();
    screen.carAddress("krokodil-a", "7");
    expect(screen.waitsForPower("on")).toBeNull();
  });
});

/** Save writes the corrected models and then the roster, and the page stays
 *  editable while it does: what the store took is cleared and nothing else, so
 *  an edit made during the write is written by the next Save (#723). */
describe("an edit made during a Save", () => {
  const WAITS = "a length has changed — turn track power off to save";

  it("leaves the roster holding edits", () => {
    const screen = stock();
    screen.carAddress("krokodil-a", "7");
    const written = screen.roster;
    screen.carAddress("krokodil-a", "8");
    screen.kept(written);
    expect(screen.edits).toBe(true);
    expect(screen.lengthEdits).toBe(false);
  });

  it("is nothing to clear when there was none", () => {
    const screen = stock();
    screen.carAddress("krokodil-a", "7");
    screen.kept(screen.roster);
    expect(screen.edits).toBe(false);
  });

  it("keeps a car's length waiting for power off", () => {
    const screen = stock();
    screen.carAddress("krokodil-a", "7");
    const written = screen.roster;
    expect(screen.carLength("krokodil-a", 130, "off")).toBeNull();
    screen.kept(written);
    expect(screen.lengthEdits).toBe(true);
    expect(screen.waitsForPower("on")).toBe(WAITS);
  });

  it("clears a car's length that was written, when the edit since is not one", () => {
    const screen = stock();
    screen.carLength("krokodil-a", 130, "off");
    const written = screen.roster;
    screen.carAddress("krokodil-a", "7");
    screen.kept(written);
    expect(screen.edits).toBe(true);
    expect(screen.lengthEdits).toBe(false);
  });

  it("keeps a model corrected for the first time to write", () => {
    const screen = stock();
    screen.modelLength("hopper", 110, "off");
    const writing = screen.corrections[0]!;
    const written = screen.roster;
    screen.modelLength("coach", 50, "off");
    screen.landed(writing);
    screen.kept(written);
    expect(screen.corrections.map((model) => model.model)).toEqual(["coach"]);
    expect(screen.edits).toBe(true);
    expect(screen.lengthEdits).toBe(true);
  });

  it("keeps a model corrected while only the roster is written", () => {
    const screen = stock();
    screen.carAddress("krokodil-a", "7");
    const written = screen.roster;
    screen.modelLength("coach", 50, "off");
    screen.kept(written);
    expect(screen.corrections.map((model) => model.model)).toEqual(["coach"]);
    expect(screen.edits).toBe(true);
    expect(screen.lengthEdits).toBe(true);
  });

  it("keeps a model corrected again with its newer length", () => {
    const screen = stock();
    screen.modelLength("hopper", 110, "off");
    const writing = screen.corrections[0]!;
    const written = screen.roster;
    screen.modelLength("hopper", 120, "off");
    screen.landed(writing);
    screen.kept(written);
    expect(screen.corrections.map((model) => model.length)).toEqual([120]);
    expect(screen.edits).toBe(true);
    expect(screen.lengthEdits).toBe(true);
  });
});

/** The model editor's rules: a model is made here and written by Save, under
 *  a key minted from its name at that write (#978). */
describe("making a model", () => {
  it("is New model, then New model (2), and owed a write", () => {
    const screen = stock();
    const one = screen.newModel();
    const two = screen.newModel();
    expect(screen.model(one)).toMatchObject({ name: "New model", decoder: false });
    expect(screen.model(two)!.name).toBe("New model (2)");
    expect(screen.isFresh(one)).toBe(true);
    expect(screen.corrections.map((model) => model.name)).toEqual([
      "New model",
      "New model (2)",
    ]);
    expect(screen.unsaved).toBe(2);
  });

  it("is filed under a key minted from its name, and keeps it", () => {
    const screen = stock();
    const made = screen.newModel();
    expect(screen.renameModel(made, "Ae 6/6")).toBeNull();
    screen.append("ore", { model: made });

    screen.mintKeys();

    expect(screen.keyOf(made)).toBe("ae-6-6");
    expect(screen.model(made)).toMatchObject({ model: "ae-6-6", name: "Ae 6/6" });
    expect(screen.roster.trains.ore!.cars!.at(-1)).toEqual({ model: "ae-6-6" });
    screen.renameModel(made, "Ae 6/6 II");
    screen.mintKeys();
    expect(screen.keyOf(made)).toBe("ae-6-6");
  });

  it("mints past a key another model has", () => {
    const screen = stock();
    const made = screen.newModel();
    screen.renameModel(made, "Hopper");
    screen.mintKeys();
    expect(screen.keyOf(made)).toBe("hopper-2");
  });

  /** No train the dispatcher fits is made of a model the store has not got,
   *  so its length is neither held under power nor a length edit. */
  it("takes a length with power on, and makes no length edit of it", () => {
    const screen = stock();
    const made = screen.newModel();
    expect(screen.modelLength(made, 230, "on")).toBeNull();
    expect(screen.lengthEdits).toBe(false);
    expect(screen.modelRows("on").find((row) => row.model === made)!.held).toBeNull();
  });

  it("is written once, and fresh no longer", () => {
    const screen = stock();
    const made = screen.newModel();
    screen.mintKeys();
    screen.landed(screen.corrections[0]!);
    expect(screen.isFresh(made)).toBe(false);
    expect(screen.corrections).toEqual([]);
  });
});

describe("a model's key", () => {
  it("drops accents, lower-cases and joins every other run with -", () => {
    expect(keyFor("Ae 6/6", [])).toBe("ae-6-6");
    expect(keyFor("  Ćrème Brûlée! ", [])).toBe("creme-brulee");
    expect(keyFor("/// ", [])).toBe("model");
    expect(keyFor("Ae 6/6", ["ae-6-6", "ae-6-6-2"])).toBe("ae-6-6-3");
  });
});

describe("a model's name", () => {
  it("is the key where the document states none", () => {
    expect(stock().model("hopper")!.name).toBeUndefined();
    expect(stock().modelRows().find((row) => row.model === "hopper")!.name).toBe("hopper");
  });

  it("refuses empty, and a name another model has", () => {
    const screen = stock();
    expect(screen.renameModel("coach", " ")).toBe("A model needs a name.");
    expect(screen.renameModel("coach", "hopper")).toBe("There is already a model 'hopper'.");
    expect(screen.edits).toBe(false);
  });

  it("takes any characters", () => {
    const screen = stock();
    expect(screen.renameModel("coach", "EW IV B/2")).toBeNull();
    expect(screen.corrections).toEqual([{ ...CATALOGUE["coach"]!, name: "EW IV B/2" }]);
  });
});

describe("a model's decoder and functions", () => {
  it("reads a decoder where functions are listed and none where none are", () => {
    const rows = Object.fromEntries(stock().modelRows().map((row) => [row.model, row.decoder]));
    expect(rows).toMatchObject({ "arnold-ce68": true, hopper: false });
  });

  it("gets F0 Headlights when the decoder goes on, and loses its functions off", () => {
    const screen = stock();
    screen.modelDecoder("hopper", true);
    expect(screen.model("hopper")).toMatchObject({
      decoder: true,
      functions: { "0": { name: "Headlights" } },
    });
    screen.modelDecoder("hopper", false);
    expect(screen.model("hopper")!.decoder).toBe(false);
    expect(screen.model("hopper")!.functions).toBeUndefined();
    expect(screen.functionRows("hopper")).toEqual([]);
  });

  it("adds a function on the lowest number not in use, latching", () => {
    const screen = stock();
    screen.addFunction("arnold-ce68");
    expect(screen.functionRows("arnold-ce68")).toEqual([
      { number: "0", name: "headlights", mode: "latching" },
      { number: "1", name: "", mode: "latching" },
    ]);
  });

  it("writes a momentary function's mode, and none for a latching one", () => {
    const screen = stock();
    screen.addFunction("arnold-ce68");
    screen.functionName("arnold-ce68", 1, " Horn ");
    screen.functionMode("arnold-ce68", 1, "momentary");
    expect(screen.model("arnold-ce68")!.functions).toEqual({
      "0": { name: "headlights" },
      "1": { name: "Horn", mode: "momentary" },
    });
  });

  it("stops Save while a number is listed twice, and says which", () => {
    const screen = stock();
    screen.addFunction("arnold-ce68");
    screen.functionName("arnold-ce68", 1, "Horn");
    expect(screen.functionNumber("arnold-ce68", 1, "0")).toBeNull();
    expect(screen.stopsSaving()).toBe("F0 is listed twice. One number names one function.");
    screen.functionNumber("arnold-ce68", 1, "2");
    expect(screen.stopsSaving()).toBeNull();
  });

  it("stops Save for a function with no name", () => {
    const screen = stock();
    screen.addFunction("arnold-ce68");
    expect(screen.stopsSaving()).toBe("F1 needs a name.");
  });

  it("refuses a number no decoder has", () => {
    const screen = stock();
    expect(screen.functionNumber("arnold-ce68", 0, "69")).toBe("A function number is 0 to 68.");
    expect(screen.functionNumber("arnold-ce68", 0, "x")).toBe("A function number is 0 to 68.");
    expect(screen.edits).toBe(false);
  });
});

describe("a model's photo and notes", () => {
  const PICTURE = { jpeg: new Uint8Array([1]), shown: "data:," };

  it("holds a photo for the next Save, and counts the write once landed", () => {
    const screen = stock();
    screen.setPhoto("hopper", PICTURE);
    expect(screen.photos).toEqual([["hopper", PICTURE]]);
    expect(screen.edits).toBe(true);
    screen.photoLanded("hopper", PICTURE);
    expect(screen.photos).toEqual([]);
    expect(screen.photoVersion("hopper")).toBe(1);
  });

  it("writes notes, and takes the key off where they are emptied", () => {
    const screen = stock();
    screen.modelNotes("hopper", "brown");
    expect(screen.model("hopper")!.notes).toBe("brown");
    screen.modelNotes("hopper", "");
    expect("notes" in screen.model("hopper")!).toBe(false);
  });
});

describe("a car made from a model", () => {
  it("is named after the model and has no address", () => {
    const screen = stock();
    expect(screen.newCar("hopper")).toBe("hopper");
    expect(screen.newCar("hopper")).toBe("hopper (2)");
    expect(screen.roster.cars!["hopper (2)"]).toEqual({ model: "hopper" });
  });
});

describe("a model dropped", () => {
  it("goes from the catalogue and owes no write", () => {
    const screen = stock();
    const made = screen.newModel();
    screen.dropModel(made);
    expect(screen.model(made)).toBeNull();
    expect(screen.corrections).toEqual([]);
  });
});

describe("what the lists draw", () => {
  it("orders cars, models and trains by name", () => {
    const screen = stock({
      roster: "oval",
      cars: { b: { model: "hopper" }, a: { model: "hopper" } },
      trains: { z: { cars: [{ model: "hopper" }] }, m: { cars: [{ model: "coach" }] } },
    });
    expect(screen.cars().map((one) => one.name)).toEqual(["a", "b"]);
    expect(screen.trains().map((one) => one.train)).toEqual(["m", "z"]);
    expect(screen.modelRows().map((one) => one.model)).toEqual([
      "arnold-ce68",
      "coach",
      "hopper",
      "van",
    ]);
  });

  it("draws a train with what it derives to and where the run has it", () => {
    const [row] = stock().trains(["ore"]);
    expect(row).toMatchObject({ train: "ore", length: 422, kind: "freight", placed: true });
    expect(row!.entries.map((one) => one.model)).toEqual([
      "arnold-ce68",
      "hopper",
      "hopper",
      "hopper",
    ]);
    expect(row!.entries[0]).toMatchObject({ car: "krokodil-a", addr: "3" });
    expect(row!.entries[1]).toMatchObject({ car: null, addr: null });
  });
});
