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
import { Unanswered, type Review } from "../src/model/store.js";
import { CLEAN } from "./support/shell.js";

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

describe("the drawings there are to open", () => {
  it("takes what the store lists", async () => {
    const { filing } = made(["reversing-loops", "otira"]);

    await filing.load();

    expect(filing.drawings).toEqual(["reversing-loops", "otira"]);
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
    const { filing, told } = made(["reversing-loops"]);

    await filing.load();

    expect(told.times).toBe(1);
  });
});

describe("opening a drawing", () => {
  it("reads it into the editor and names it as open", async () => {
    const { filing, editor } = made(["reversing-loops"]);

    const arrived = await filing.open("reversing-loops", editor);

    expect(arrived).toBe("opened");
    expect(filing.opened).toBe("reversing-loops");
    expect(Object.keys(editor.drawing.symbols).sort()).toEqual(["b1", "sw1"]);
  });

  it("holds what the store said the drawing means", async () => {
    const { filing, store, editor } = made(["reversing-loops"]);
    store.answer = () => Promise.resolve(REFUSED);

    await filing.open("reversing-loops", editor);

    expect(filing.reviewed).toEqual(REFUSED);
  });

  /** Every symbol in the file is already placed, so there is nothing to
   *  stage and nothing to save. */
  it("opens a placed railroad with nothing to save", async () => {
    const { filing, editor } = made(["reversing-loops"]);

    await filing.open("reversing-loops", editor);

    expect(filing.saved).toBe(true);
  });

  /** Staging is an edit, so a railroad written without placement opens with
   *  something to save rather than something already saved. */
  it("opens an unplaced railroad with edits to save", async () => {
    const { filing, store, editor } = made(["reversing-loops"]);
    store.stored["reversing-loops"] = {
      drawing: "reversing-loops",
      symbols: { sw1: { kind: "turnout" }, b1: { kind: "block" } },
      wires: [],
    };

    await filing.open("reversing-loops", editor);

    expect(filing.saved).toBe(false);
  });

  it("says so where the store will not give it, and opens nothing", async () => {
    const { filing, editor } = made(["reversing-loops"]);

    const arrived = await filing.open("otira", editor);

    expect(arrived).toBe("refused");
    expect(filing.opened).toBe("");
    expect(filing.trouble).toContain("no drawing 'otira'");
  });

  /** A store that did not answer is one to ask again, and a refusal is not:
   *  the caller reading again is told which it was (#758). */
  it("answers unanswered where nothing came back from the store", async () => {
    const { filing, store, editor } = made(["reversing-loops"]);
    store.broken = new Unanswered("the store is not answering");

    const arrived = await filing.open("reversing-loops", editor);

    expect(arrived).toBe("unanswered");
    expect(filing.opened).toBe("");
    expect(filing.trouble).toContain("the store is not answering");
  });
});

/**
 * Nothing open: the row the layout interface publishes names no railroad
 * (#727), so the editor holds nothing and nothing is left to save (ADR-0072,
 * decision 3).
 */
describe("closing the drawing", () => {
  it("empties the editor and reads as saved, with no trouble and no review", async () => {
    const { filing, store, editor } = made(["reversing-loops"]);
    store.answer = () => Promise.resolve(REFUSED);
    await filing.open("reversing-loops", editor);
    editor.place("block", [20, 20]);
    await filing.edited(editor);

    filing.close(editor);

    expect(filing.opened).toBe("");
    expect(filing.saved).toBe(true);
    expect(filing.edits).toBe(false);
    expect(filing.trouble).toBeNull();
    expect(filing.reviewed).toBeNull();
    expect(editor.drawing).toEqual(emptyDrawing(""));
  });

  it("tells the shell to redraw", async () => {
    const { filing, editor, told } = made(["reversing-loops"]);
    await filing.open("reversing-loops", editor);
    const before = told.times;

    filing.close(editor);

    expect(told.times).toBe(before + 1);
  });

  /** Save needs a drawing to save into, and `""` is not one. */
  it("leaves nothing a save would write", async () => {
    const { filing, store, editor } = made(["reversing-loops"]);
    await filing.open("reversing-loops", editor);
    filing.close(editor);

    await filing.save(editor);

    expect(store.written).toEqual([]);
  });
});

describe("saving", () => {
  it("gives the store the drawing as it stands", async () => {
    const { filing, store, editor } = made(["reversing-loops"]);
    await filing.open("reversing-loops", editor);
    editor.place("block", [20, 20]);
    await filing.edited(editor);

    await filing.save(editor);

    expect(filing.saved).toBe(true);
    expect(Object.keys(store.written[0]!.symbols)).toContain("b2");
  });

  /** A name the list lacks is one another page made since the list was
   *  asked for; the list learns it on the save all the same. */
  it("learns a name the drawings there are lacked", async () => {
    const { filing, store, editor } = made(["otira"]);
    await filing.load();
    store.stored["arth-goldau"] = drawn("arth-goldau");
    await filing.open("arth-goldau", editor);
    await filing.edited(editor);

    await filing.save(editor);

    expect(filing.drawings).toEqual(["arth-goldau", "otira"]);
  });

  /** Saving needs a drawing to save into: nothing is open until the row names
   *  a railroad. */
  it("writes nothing with no drawing open", async () => {
    const { filing, store, editor } = made();

    await filing.save(editor);

    expect(store.written).toEqual([]);
  });

  it("says so where the save did not land", async () => {
    const { filing, store, editor } = made(["reversing-loops"]);
    await filing.open("reversing-loops", editor);
    await filing.edited(editor);
    store.broken = new Error("disk full");

    await filing.save(editor);

    expect(filing.saved).toBe(false);
    expect(filing.trouble).toContain("disk full");
  });
});

describe("an edit", () => {
  it("leaves the drawing with something to save, and re-asks the store", async () => {
    const { filing, store, editor } = made(["reversing-loops"]);
    await filing.open("reversing-loops", editor);
    store.answer = () => Promise.resolve(REFUSED);

    await filing.edited(editor);

    expect(filing.saved).toBe(false);
    expect(filing.reviewed).toEqual(REFUSED);
  });

  /** A refusal does not outlive what caused it: the next accepted edit
   *  reviews, and a review that answers clears the band. */
  it("clears a refusal the band was carrying", async () => {
    const { filing, store, editor } = made(["reversing-loops"]);
    await filing.open("reversing-loops", editor);
    store.broken = new Error("disk full");
    await filing.save(editor);
    expect(filing.trouble).not.toBeNull();
    store.broken = null;

    await filing.edited(editor);

    expect(filing.trouble).toBeNull();
  });

  /** What `edited` answers with is the review itself, not a turn of the queue.
   *  The store is held open and let go from a timer, which the microtask queue
   *  cannot reach: a `void` return, or one resolved before the store answered,
   *  comes back with the previous answer still standing. The other waits in
   *  this file would merely race and mostly still pass, so this is the one
   *  that says what they are waiting on. */
  it("answers with a review that lands only where the store has", async () => {
    const { filing, store, editor } = made(["reversing-loops"]);
    await filing.open("reversing-loops", editor);
    let answer!: (review: Review) => void;
    store.answer = () => new Promise<Review>((held) => (answer = held));

    const reviewing = filing.edited(editor);

    expect(filing.reviewed).toEqual(CLEAN);
    setTimeout(() => answer(REFUSED));
    await reviewing;
    expect(filing.reviewed).toEqual(REFUSED);
  });
});

/**
 * Whether changing the railroad would lose anything, which a restore and a
 * load are refused over (#703, #733). It follows `saved`: the only drawing
 * open is one the store gave, so there is nothing unsaved that is not an
 * edit.
 */
describe("whether there are edits to lose", () => {
  it("has nothing to lose on a drawing as the store gave it", async () => {
    const { filing, editor } = made(["reversing-loops"]);

    await filing.open("reversing-loops", editor);

    expect(filing.edits).toBe(false);
  });

  it("has edits to lose on one edited since it was read", async () => {
    const { filing, editor } = made(["reversing-loops"]);
    await filing.open("reversing-loops", editor);

    editor.place("block", [20, 20]);
    await filing.edited(editor);

    expect(filing.edits).toBe(true);
  });

  /** Staging is an edit, so a railroad that arrives without placement has
   *  changes to save and something to lose with them (#105). */
  it("counts the staging an unplaced railroad needed", async () => {
    const { filing, store, editor } = made(["reversing-loops"]);
    store.stored["reversing-loops"] = {
      drawing: "reversing-loops",
      symbols: { sw1: { kind: "turnout" }, b1: { kind: "block" } },
      wires: [],
    };

    await filing.open("reversing-loops", editor);

    expect(filing.edits).toBe(true);
  });

  /**
   * Every place that records an edit puts the dot up: `edited`, `open`, and
   * the review that mints names the drawing did not hold. The store cannot
   * say this about a drawing it gave with every name in place, so the fake
   * says it, and what is guarded is the invariant rather than the reachable
   * path to it (#147).
   */
  it("has edits to lose once a review named a junction for it", async () => {
    const { filing, store, editor } = made(["reversing-loops"]);
    store.answer = () =>
      Promise.resolve({
        ...CLEAN,
        junctions: [{ name: null, names: [], symbols: ["sw1"] }],
      });

    await filing.open("reversing-loops", editor);

    expect(filing.edits).toBe(true);
  });

  it("has nothing to lose again once the drawing is saved", async () => {
    const { filing, editor } = made(["reversing-loops"]);
    await filing.open("reversing-loops", editor);
    editor.place("block", [20, 20]);
    await filing.edited(editor);

    await filing.save(editor);

    expect(filing.edits).toBe(false);
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
    const { filing, store, editor } = made(["reversing-loops"]);
    await filing.open("reversing-loops", editor);

    store.answer = () => Promise.resolve(REFUSED);
    await filing.edited(editor);

    expect(filing.derives).toBe(false);
  });

  it("clears as soon as an edit derives again", async () => {
    const { filing, store, editor } = made(["reversing-loops"]);
    await filing.open("reversing-loops", editor);
    store.answer = () => Promise.resolve(REFUSED);
    await filing.edited(editor);

    store.answer = () => Promise.resolve(CLEAN);
    await filing.edited(editor);

    expect(filing.derives).toBe(true);
  });

  /** An overlap is cosmetic and derives fine, and so does a turnout with no
   *  address: a valid layout nobody can drive yet. Both are marked on the
   *  canvas in a quieter weight (#92, #96) and leave the band clean. */
  it("stays clean over faults the store still derives through", async () => {
    const { filing, editor } = made(["reversing-loops"]);
    await filing.open("reversing-loops", editor);

    editor.place("turnout", [0, 0]);
    await filing.edited(editor);

    expect(filing.derives).toBe(true);
  });

  /** One is the author's to fix and the other is not, so the store going quiet
   *  neither raises the mark nor takes it down. */
  it("stands where the store stops answering", async () => {
    const { filing, store, editor } = made(["reversing-loops"]);
    await filing.open("reversing-loops", editor);
    store.answer = () => Promise.resolve(REFUSED);
    await filing.edited(editor);

    store.broken = new Error("no store");
    await filing.edited(editor);

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
    store.drawings = ["reversing-loops"];
    store.stored["reversing-loops"] = {
      drawing: "reversing-loops",
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
    const { filing, editor } = typed("station_a");

    await filing.open("reversing-loops", editor);

    expect(editor.drawing.symbols.sw1!.connection).toBe("j1");
    expect(editor.drawing.symbols.sw2!.connection).toBe("j1");
  });

  /** It has edits to save, because the names it now holds are not the ones the
   *  file was written with. */
  it("says the drawing has edits the store has not been given", async () => {
    const { filing, editor } = typed("station_a");

    await filing.open("reversing-loops", editor);

    expect(filing.saved).toBe(false);
  });

  /** A drawing already wearing minted names is the one already saved, so
   *  opening one does not offer to write it back unchanged. */
  it("writes nothing where every name is already minted", async () => {
    const { filing, editor } = typed("j1");

    await filing.open("reversing-loops", editor);

    expect(filing.saved).toBe(true);
  });
});
