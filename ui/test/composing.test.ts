/**
 * Composing stock: what the screen holds and every rule over it
 * (`model/stock.ts`, ui/STOCK.md, #393).
 *
 * No DOM. What is under test is the third kind of thing the app has — neither
 * the document nor the DOM (ui/README.md): what promotes an entry to a car,
 * what a minted name is, what a train's length and kind derive to, what holds
 * a thing somebody asked to remove, and why a length may not be corrected.
 *
 * The derivations are pinned against `tc49.lib.roster.Train`'s, which is the
 * other implementation of the same three rules: the browser derives a train
 * that has not been saved, and the store derives one that has.
 */

import { describe, expect, it } from "vitest";

import {
  LIGHT_ENGINE,
  MIXED,
  mint,
  Stock,
  trainFunctions,
  trainKind,
  trainLength,
} from "../src/model/stock.js";
import type { ModelDoc, RosterDoc } from "../src/model/store.js";

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
    functions: { "3": { name: "vacuum", values: ["off", "half", "full"] } },
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

describe("what a train derives to", () => {
  it("is the sum of every entry, car and model alike", () => {
    expect(trainLength(OVAL.trains.ore!, OVAL, CATALOGUE)).toBe(122 + 100 * 3);
  });

  it("has no length where an entry names something the documents have not", () => {
    const roster: RosterDoc = { roster: "oval", trains: { ore: { cars: [{ model: "flat" }] } } };
    expect(trainLength(roster.trains.ore!, roster, CATALOGUE)).toBeNull();
  });

  /** Every hauled train has a locomotive, so counting them would make every
   *  train mixed (CONTEXT.md, **Kind**). */
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
      { name: "headlights", values: ["off", "on"] },
      { name: "vacuum", values: ["off", "half", "full"] },
    ]);
  });
});

describe("a name minted for a promoted item", () => {
  it("is the model with the lowest suffix nothing has taken", () => {
    expect(mint("arnold-ce68", [])).toBe("arnold-ce68-1");
    expect(mint("arnold-ce68", ["arnold-ce68-1", "arnold-ce68-2"])).toBe("arnold-ce68-3");
  });

  it("steps over a name a person typed", () => {
    expect(mint("hopper", ["hopper-1", "krokodil-a"])).toBe("hopper-2");
  });
});

describe("making up a train", () => {
  it("starts with a name and nothing in it", () => {
    const screen = stock(EMPTY);
    expect(screen.addTrain("ore")).toBeNull();
    expect(screen.roster.trains.ore).toEqual({ cars: [] });
    expect(screen.edits).toBe(true);
  });

  it("refuses a name the store would refuse, and a second train of one name", () => {
    const screen = stock();
    expect(screen.addTrain("a/b")).toMatch("not a name");
    expect(screen.addTrain("ore")).toMatch("already a train");
    expect(Object.keys(screen.roster.trains)).toEqual(["ore"]);
  });

  it("adds a model entry as an anonymous item", () => {
    const screen = stock(EMPTY);
    screen.addTrain("ore");
    screen.append("ore", { model: "hopper" });
    expect(screen.roster.trains.ore!.cars).toEqual([{ model: "hopper" }]);
  });

  it("turns an item round, and back by taking the key off", () => {
    const screen = stock();
    screen.turn("ore", 0);
    expect(screen.roster.trains.ore!.cars[0]).toEqual({
      car: "krokodil-a",
      orientation: "reverse",
    });
    screen.turn("ore", 0);
    expect(screen.roster.trains.ore!.cars[0]).toEqual({ car: "krokodil-a" });
  });

  /** The store refuses an empty `cars` list, so the screen refuses the save
   *  first and the words name the row to go and fill (#412). */
  it("stops the save while a train has nothing in it, and names the train", () => {
    const screen = stock(EMPTY);
    screen.addTrain("ore");
    expect(screen.stopsSaving()).toBe(
      "train 'ore' has nothing in it — press + beside a car or a model, or remove it",
    );
    expect(screen.edits).toBe(true);
    screen.append("ore", { model: "hopper" });
    expect(screen.stopsSaving()).toBeNull();
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

describe("filling in an address", () => {
  /** Nothing asks a person to classify an item before they add it: the
   *  address is the whole gesture, and the name is minted (ADR-0061). */
  it("promotes an anonymous entry to a car named from its model", () => {
    const screen = stock(EMPTY);
    screen.addTrain("ore");
    screen.append("ore", { model: "arnold-ce68" });
    expect(screen.address("ore", 0, "3")).toBeNull();
    expect(screen.roster.cars).toEqual({
      "arnold-ce68-1": { model: "arnold-ce68", addr: "3" },
    });
    expect(screen.roster.trains.ore!.cars).toEqual([{ car: "arnold-ce68-1" }]);
  });

  it("keeps which way round the item was coupled", () => {
    const screen = stock(EMPTY);
    screen.addTrain("ore");
    screen.append("ore", { model: "arnold-ce68" });
    screen.turn("ore", 0);
    screen.address("ore", 0, "3");
    expect(screen.roster.trains.ore!.cars).toEqual([
      { car: "arnold-ce68-1", orientation: "reverse" },
    ]);
  });

  /** Two locomotives of one product keep their two addresses, written once,
   *  and neither is restated when a rake is made up (ADR-0061). */
  it("gives two items of one model two cars and two addresses", () => {
    const screen = stock(EMPTY);
    screen.addTrain("shed");
    screen.append("shed", { model: "arnold-ce68" });
    screen.append("shed", { model: "arnold-ce68" });
    screen.address("shed", 0, "3");
    screen.address("shed", 1, "4");
    expect(screen.roster.cars).toEqual({
      "arnold-ce68-1": { model: "arnold-ce68", addr: "3" },
      "arnold-ce68-2": { model: "arnold-ce68", addr: "4" },
    });
    expect(screen.roster.trains.shed!.cars).toEqual([
      { car: "arnold-ce68-1" },
      { car: "arnold-ce68-2" },
    ]);
  });

  it("sets the car's own address where the entry already names one", () => {
    const screen = stock();
    expect(screen.address("ore", 0, "7")).toBeNull();
    expect(screen.roster.cars!["krokodil-a"]).toEqual({ model: "arnold-ce68", addr: "7" });
  });

  /** Two cars on one address both answer the same packet, and no run can tell
   *  them apart. The store refuses it; this says which car has it. */
  it("refuses an address another car already wears, and names it", () => {
    const screen = stock();
    screen.addTrain("shunt");
    screen.append("shunt", { model: "arnold-ce68" });
    expect(screen.address("shunt", 0, "3")).toBe("car 'krokodil-a' already wears address '3'");
    expect(screen.roster.cars).toEqual({ "krokodil-a": { model: "arnold-ce68", addr: "3" } });
  });

  it("clears an address without taking the car off the roster", () => {
    const screen = stock();
    expect(screen.address("ore", 0, "")).toBeNull();
    expect(screen.roster.cars!["krokodil-a"]).toEqual({ model: "arnold-ce68" });
  });
});

describe("a car of one's own", () => {
  it("can stand in no train at all", () => {
    const screen = stock(EMPTY);
    screen.addTrain("ore");
    screen.append("ore", { model: "arnold-ce68" });
    screen.address("ore", 0, "3");
    screen.removeTrain("ore");
    expect(screen.cars().map((car) => car.name)).toEqual(["arnold-ce68-1"]);
  });

  it("is renamed everywhere a train names it", () => {
    const screen = stock();
    expect(screen.renameCar("krokodil-a", "krokodil")).toBeNull();
    expect(Object.keys(screen.roster.cars!)).toEqual(["krokodil"]);
    expect(screen.roster.trains.ore!.cars[0]).toEqual({ car: "krokodil" });
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

describe("the length guard", () => {
  it("is off while the run shows a train made of the item placed", () => {
    const screen = stock();
    expect(screen.cars(["ore"])[0]!.held).toBe(
      "'ore' is on the layout — take it off to correct a length",
    );
    expect(screen.carLength("krokodil-a", 130, ["ore"])).toMatch("on the layout");
    expect(screen.roster.cars!["krokodil-a"]!.length).toBeUndefined();
  });

  /** A length lives on the model as well, so correcting the product's changes
   *  every item of it — including the one under a train that is running. */
  it("is off for a model a placed train uses, through an entry or through a car", () => {
    const screen = stock();
    const held = Object.fromEntries(screen.modelRows(["ore"]).map((row) => [row.model, row.held]));
    expect(held["hopper"]).toMatch("on the layout");
    expect(held["arnold-ce68"]).toMatch("on the layout");
    expect(held["coach"]).toBeNull();
    expect(screen.modelLength("hopper", 110, ["ore"])).toMatch("on the layout");
  });

  it("is on for everything while nothing is placed", () => {
    const screen = stock();
    expect(screen.cars([])[0]!.held).toBeNull();
    expect(screen.modelLength("hopper", 110, [])).toBeNull();
    expect(screen.catalogue["hopper"]!.length).toBe(110);
  });
});

/** A dialog labelled New model with a Create button touches nothing that
 *  exists: `PUT /catalogue/<name>` replaces the document whole, so a name in
 *  use would rewrite that product for every railroad in the installation and
 *  step around the length guard its row keeps (#413). */
describe("writing a model", () => {
  it("stops a name the catalogue already has, and names it", () => {
    expect(stock().stopsMaking("hopper")).toBe("there is already a model 'hopper'");
  });

  it("stops nothing where the catalogue has no such name", () => {
    expect(stock().stopsMaking("flat")).toBeNull();
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
