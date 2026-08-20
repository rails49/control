/**
 * The editor's dealings with the store (#105): what is open, whether it is
 * saved, what the store said, and what went wrong.
 *
 * No DOM. `Filing` takes the store as a dependency, so these drive it against
 * a fake that answers in Drawings and Reviews rather than mounting the shell
 * and forging HTTP answers to reach rules that are not about HTTP
 * (EDITOR.md#tests).
 */

import { describe, expect, it } from "vitest";

import { emptyDrawing, type Drawing } from "../src/model/drawing.js";
import { Editor } from "../src/model/editor.js";
import { Filing, type Store } from "../src/model/filing.js";
import type { Review } from "../src/model/store.js";

/** A drawing the store is happy with: nothing to report. */
const CLEAN: Review = {
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

/** What derivation came back with over a way it refused (#93). */
const REFUSED: Review = {
  ...CLEAN,
  refused: "the way out of 'b1' leads back into 'b1'",
  offending: [{ ends: ["b1.a", "b1.b"], way: [["sw1", "toe"]] }],
};

/** One turnout and one block, neither overlapping the other. */
function drawn(name: string): Drawing {
  return {
    drawing: name,
    symbols: {
      sw1: { kind: "turnout", at: [0, 0] },
      b1: { kind: "block", at: [4, 0] },
    },
    wires: [],
  };
}

/** A store the tests hand over instead of the HTTP one, with what it holds and
 *  what it answers set per test. `written` is what `saveDrawing` was given,
 *  which is the only way to see that a save happened at all. */
class Fake implements Store {
  drawings: string[] = [];
  stored: Record<string, Drawing> = {};
  answer: () => Promise<Review> = () => Promise.resolve(CLEAN);
  written: Drawing[] = [];
  /** Set to a failure a route should throw instead of answering. */
  broken: Error | null = null;

  listDrawings(): Promise<string[]> {
    return this.broken === null
      ? Promise.resolve([...this.drawings])
      : Promise.reject(this.broken);
  }

  readDrawing(name: string): Promise<Drawing> {
    if (this.broken !== null) return Promise.reject(this.broken);
    const found = this.stored[name];
    return found === undefined
      ? Promise.reject(new Error(`no drawing '${name}'`))
      : Promise.resolve(structuredClone(found));
  }

  saveDrawing(drawing: Drawing): Promise<void> {
    if (this.broken !== null) return Promise.reject(this.broken);
    this.written.push(structuredClone(drawing));
    this.stored[drawing.drawing] = structuredClone(drawing);
    return Promise.resolve();
  }

  review(): Promise<Review> {
    return this.broken === null ? this.answer() : Promise.reject(this.broken);
  }
}

/**
 * A filing over a store holding one drawing per name, the editor the shell
 * would own, and the count of how often the filing asked to be redrawn — the
 * one thing the shell wires to it.
 */
function made(names: string[] = []) {
  const store = new Fake();
  store.drawings = [...names];
  for (const name of names) store.stored[name] = drawn(name);
  const told = { times: 0 };
  const filing = new Filing(() => told.times++, store);
  const editor = new Editor(emptyDrawing("untitled"));
  return { filing, store, editor, told };
}

/** Let the review an edit set off settle. `edited` answers at once and asks
 *  the store afterwards, which is what the shell wants: the dot goes up on the
 *  keystroke rather than on the round trip. */
async function settled(): Promise<void> {
  for (let turn = 0; turn < 5; turn++) await Promise.resolve();
}

describe("the drawings there are to open", () => {
  it("takes what the store lists", async () => {
    const { filing } = made(["gotthard", "otira"]);

    await filing.load();

    expect(filing.drawings).toEqual(["gotthard", "otira"]);
    expect(filing.trouble).toBeNull();
  });

  it("says so where the store is not answering", async () => {
    const { filing, store } = made();
    store.broken = new Error("no store");

    await filing.load();

    expect(filing.drawings).toEqual([]);
    expect(filing.trouble).toContain("the store is not answering");
    expect(filing.trouble).toContain("no store");
  });

  it("tells the shell to redraw", async () => {
    const { filing, told } = made(["gotthard"]);

    await filing.load();

    expect(told.times).toBe(1);
  });
});

describe("opening a drawing", () => {
  it("reads it into the editor and names it as open", async () => {
    const { filing, editor } = made(["gotthard"]);

    const arrived = await filing.open("gotthard", editor);

    expect(arrived).toBe(true);
    expect(filing.opened).toBe("gotthard");
    expect(Object.keys(editor.drawing.symbols).sort()).toEqual(["b1", "sw1"]);
  });

  it("holds what the store said the drawing means", async () => {
    const { filing, store, editor } = made(["gotthard"]);
    store.answer = () => Promise.resolve(REFUSED);

    await filing.open("gotthard", editor);

    expect(filing.reviewed).toEqual(REFUSED);
  });

  /** Every symbol in the file is already placed, so there is nothing to
   *  stage and nothing to save. */
  it("opens a placed railroad with nothing to save", async () => {
    const { filing, editor } = made(["gotthard"]);

    await filing.open("gotthard", editor);

    expect(filing.saved).toBe(true);
  });

  /** Staging is an edit, so a railroad written without placement opens with
   *  something to save rather than something already saved. */
  it("opens an unplaced railroad with edits to save", async () => {
    const { filing, store, editor } = made(["gotthard"]);
    store.stored.gotthard = {
      drawing: "gotthard",
      symbols: { sw1: { kind: "turnout" }, b1: { kind: "block" } },
      wires: [],
    };

    await filing.open("gotthard", editor);

    expect(filing.saved).toBe(false);
  });

  it("says so where the store will not give it, and opens nothing", async () => {
    const { filing, editor } = made(["gotthard"]);

    const arrived = await filing.open("otira", editor);

    expect(arrived).toBe(false);
    expect(filing.opened).toBe("");
    expect(filing.trouble).toContain("no drawing 'otira'");
  });
});

describe("starting a drawing", () => {
  it("empties the canvas under the name, with edits to save", async () => {
    const { filing, editor } = made(["gotthard"]);
    await filing.load();

    const arrived = await filing.create("arth-goldau", editor);

    expect(arrived).toBe(true);
    expect(filing.opened).toBe("arth-goldau");
    expect(editor.drawing.symbols).toEqual({});
    expect(filing.saved).toBe(false);
  });

  /** The prompt is the shell's, and `null` is the operator closing it. */
  it("starts nothing where nothing was said", async () => {
    const { filing, editor } = made(["gotthard"]);
    await filing.load();

    const arrived = await filing.create(null, editor);

    expect(arrived).toBe(false);
    expect(filing.opened).toBe("");
    expect(filing.trouble).toBeNull();
  });

  it("refuses a name no file can wear", async () => {
    const { filing, editor } = made(["gotthard"]);
    await filing.load();

    const arrived = await filing.create("a/b", editor);

    expect(arrived).toBe(false);
    expect(filing.opened).toBe("");
    expect(filing.trouble).toBe("'a/b' cannot name a file");
  });

  /** A taken name is refused rather than overwritten: overwriting
   *  deliberately is open-and-save. */
  it("refuses a name a railroad already has", async () => {
    const { filing, editor } = made(["gotthard"]);
    await filing.load();

    await filing.create("gotthard", editor);

    expect(filing.trouble).toBe("'gotthard' is already a railroad");
  });
});

describe("saving", () => {
  it("gives the store the drawing as it stands", async () => {
    const { filing, store, editor } = made(["gotthard"]);
    await filing.open("gotthard", editor);
    editor.place("block", [20, 20]);
    filing.edited(editor);

    await filing.save(editor);

    expect(filing.saved).toBe(true);
    expect(Object.keys(store.written[0]!.symbols)).toContain("b2");
  });

  /** The first save of a new name is what creates the file, so the list that
   *  refuses taken names learns it here. */
  it("learns a new name into the drawings there are", async () => {
    const { filing, editor } = made(["otira"]);
    await filing.load();
    await filing.create("arth-goldau", editor);

    await filing.save(editor);

    expect(filing.drawings).toEqual(["arth-goldau", "otira"]);
  });

  /** Saving needs a drawing to save into: nothing is open until a railroad is
   *  chosen, and `untitled` is not a file anyone asked for. */
  it("writes nothing with no drawing open", async () => {
    const { filing, store, editor } = made();

    await filing.save(editor);

    expect(store.written).toEqual([]);
  });

  it("says so where the save did not land", async () => {
    const { filing, store, editor } = made(["gotthard"]);
    await filing.open("gotthard", editor);
    filing.edited(editor);
    await settled();
    store.broken = new Error("disk full");

    await filing.save(editor);

    expect(filing.saved).toBe(false);
    expect(filing.trouble).toContain("disk full");
  });
});

describe("saving under another name", () => {
  it("writes the open drawing, unsaved edits and all, under the new one", async () => {
    const { filing, store, editor } = made(["gotthard"]);
    await filing.load();
    await filing.open("gotthard", editor);
    editor.place("block", [20, 20]);
    filing.edited(editor);

    await filing.saveAs("otira", editor);

    expect(filing.opened).toBe("otira");
    expect(filing.saved).toBe(true);
    expect(store.written[0]!.drawing).toBe("otira");
    expect(Object.keys(store.stored.gotthard!.symbols).sort()).toEqual([
      "b1",
      "sw1",
    ]);
  });

  it("refuses a name no file can wear, and writes nothing", async () => {
    const { filing, store, editor } = made(["gotthard"]);
    await filing.load();
    await filing.open("gotthard", editor);

    await filing.saveAs("gotthard/2", editor);

    expect(filing.trouble).toBe("'gotthard/2' cannot name a file");
    expect(filing.opened).toBe("gotthard");
    expect(store.written).toEqual([]);
  });

  it("writes nothing with no drawing open", async () => {
    const { filing, store, editor } = made();

    await filing.saveAs("otira", editor);

    expect(store.written).toEqual([]);
  });
});

describe("an edit", () => {
  it("leaves the drawing with something to save, and re-asks the store", async () => {
    const { filing, store, editor } = made(["gotthard"]);
    await filing.open("gotthard", editor);
    store.answer = () => Promise.resolve(REFUSED);

    filing.edited(editor);
    await settled();

    expect(filing.saved).toBe(false);
    expect(filing.reviewed).toEqual(REFUSED);
  });

  /** A refusal does not outlive what caused it: the next accepted edit
   *  reviews, and a review that answers clears the band. */
  it("clears a refusal the band was carrying", async () => {
    const { filing, editor } = made(["gotthard"]);
    await filing.load();
    await filing.create("a/b", editor);
    expect(filing.trouble).not.toBeNull();

    filing.edited(editor);
    await settled();

    expect(filing.trouble).toBeNull();
  });
});

/**
 * What the band says about the drawing itself: it derives, or it does not
 * (#91, ADR-0024). The canvas is where you find out where, so the whole of
 * this is one fact off the store's refusal.
 */
describe("whether the drawing derives", () => {
  it("says nothing is against a drawing nothing has been asked about", () => {
    const { filing } = made();

    expect(filing.derives).toBe(true);
  });

  it("marks a drawing derivation refused", async () => {
    const { filing, store, editor } = made(["gotthard"]);
    await filing.open("gotthard", editor);

    store.answer = () => Promise.resolve(REFUSED);
    filing.edited(editor);
    await settled();

    expect(filing.derives).toBe(false);
  });

  it("clears as soon as an edit derives again", async () => {
    const { filing, store, editor } = made(["gotthard"]);
    await filing.open("gotthard", editor);
    store.answer = () => Promise.resolve(REFUSED);
    filing.edited(editor);
    await settled();

    store.answer = () => Promise.resolve(CLEAN);
    filing.edited(editor);
    await settled();

    expect(filing.derives).toBe(true);
  });

  /** An overlap is cosmetic and derives fine, and so does a turnout with no
   *  address: a valid layout nobody can drive yet. Both are marked on the
   *  canvas in a quieter weight (#92, #96) and leave the band clean. */
  it("stays clean over faults the store still derives through", async () => {
    const { filing, editor } = made(["gotthard"]);
    await filing.open("gotthard", editor);

    editor.place("turnout", [0, 0]);
    filing.edited(editor);
    await settled();

    expect(filing.derives).toBe(true);
  });

  /** One is the author's to fix and the other is not, so the store going quiet
   *  neither raises the mark nor takes it down. */
  it("stands where the store stops answering", async () => {
    const { filing, store, editor } = made(["gotthard"]);
    await filing.open("gotthard", editor);
    store.answer = () => Promise.resolve(REFUSED);
    filing.edited(editor);
    await settled();

    store.broken = new Error("no store");
    filing.edited(editor);
    await settled();

    expect(filing.derives).toBe(false);
    expect(filing.trouble).toContain("no store");
  });
});

/**
 * Opening a hand-written railroad replaces the connection names it carries
 * (ADR-0023). Three of the five committed drawings type theirs, so this is the
 * ordinary case rather than a corner of it.
 */
describe("opening a drawing that names its junctions", () => {
  /** A throat wearing one name, and the review saying the two turnouts are one
   *  junction. `wearing` is what the file was written with. */
  function typed(wearing: string) {
    const { filing, store, editor, told } = made();
    store.drawings = ["gotthard"];
    store.stored.gotthard = {
      drawing: "gotthard",
      symbols: {
        sw1: { kind: "turnout", at: [0, 0], connection: wearing },
        sw2: { kind: "turnout", at: [4, 0], connection: wearing },
      },
      wires: [],
    };
    store.answer = () =>
      Promise.resolve({
        ...CLEAN,
        junctions: [{ name: wearing, names: [wearing], symbols: ["sw1", "sw2"] }],
      });
    return { filing, store, editor, told };
  }

  it("replaces the name a person typed with a minted one", async () => {
    const { filing, editor } = typed("airolo");

    await filing.open("gotthard", editor);

    expect(editor.drawing.symbols.sw1!.connection).toBe("j1");
    expect(editor.drawing.symbols.sw2!.connection).toBe("j1");
  });

  /** It has edits to save, because the names it now holds are not the ones the
   *  file was written with. */
  it("says the drawing has edits the store has not been given", async () => {
    const { filing, editor } = typed("airolo");

    await filing.open("gotthard", editor);

    expect(filing.saved).toBe(false);
  });

  /** A drawing already wearing minted names is the one already saved, so
   *  opening one does not offer to write it back unchanged. */
  it("writes nothing where every name is already minted", async () => {
    const { filing, editor } = typed("j1");

    await filing.open("gotthard", editor);

    expect(filing.saved).toBe(true);
  });
});
