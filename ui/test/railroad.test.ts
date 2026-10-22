/**
 * The loaded railroad's documents, read and held in one place (#758).
 *
 * No DOM. `Railroad` takes both stores as dependencies, as `Filing` does, so
 * these drive it against fakes that answer in documents and fail in the two
 * ways the store can — not answering, and refusing — rather than forging HTTP
 * to reach rules that are not about HTTP. The retry is on fake timers.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { emptyDrawing, type Drawing } from "../src/model/drawing.js";
import { Editor } from "../src/model/editor.js";
import { Filing, type Store } from "../src/model/filing.js";
import { Railroad, type StockStore } from "../src/model/railroad.js";
import { LENGTH_UNHEARD } from "../src/model/stock.js";
import {
  RETRY_MS,
  Unanswered,
  type ModelDoc,
  type Review,
  type RosterDoc,
  type TrainDoc,
  type TrainsDoc,
} from "../src/model/store.js";
import { CLEAN } from "./support/shell.js";

const HOPPER: ModelDoc = { model: "hopper", kind: "freight", length: 100 };

/** How a route fails, where it does: nothing answering, or the store's own
 *  refusal in its own words. */
type Failing = "unanswered" | "refused" | null;

function failure(how: Failing, path: string): Error {
  return how === "unanswered"
    ? new Unanswered("the store is not answering — run `tc49 serve`")
    : new Error(`no such thing as ${path}`);
}

/** Every route the loaded railroad asks, counted by path, each failing as a
 *  test says. Writes are recorded in order, and one route — a read, a write
 *  or a review — can be held in flight. */
class Fake implements Store, StockStore {
  asked: string[] = [];
  saved: string[] = [];
  failing: Record<string, Failing> = {};
  /** What the store refuses each drawing with on review, by name, so a late
   *  review is told apart from the one that should stand. */
  refusing: Record<string, string> = {};
  /** The next route on a path starting with `prefix` — a review's being
   *  `/review/<drawing>` — held in flight until the test lets it answer. How
   *  it answers is decided on release, so a test can fail it in between. */
  private held: { prefix: string; gate: Promise<void> } | null = null;

  hold(prefix: string): () => void {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => (release = resolve));
    this.held = { prefix, gate };
    return release;
  }

  count(path: string): number {
    return this.asked.filter((one) => one === path).length;
  }

  /** `done` answered now, or once the held route on this path is let go. */
  private gated<T>(path: string, done: () => Promise<T>): Promise<T> {
    const held = this.held;
    if (held !== null && path.startsWith(held.prefix)) {
      this.held = null;
      return held.gate.then(done);
    }
    return done();
  }

  private ask<T>(path: string, answer: () => T): Promise<T> {
    this.asked.push(path);
    return this.gated(path, () => {
      const how = this.failing[path] ?? null;
      return how === null ? Promise.resolve(answer()) : Promise.reject(failure(how, path));
    });
  }

  private write(path: string): Promise<void> {
    return this.gated(path, () => {
      const how = this.failing[path] ?? null;
      if (how !== null) return Promise.reject(failure(how, path));
      this.saved.push(path);
      return Promise.resolve();
    });
  }

  listDrawings(): Promise<string[]> {
    return Promise.resolve([]);
  }

  readDrawing(name: string): Promise<Drawing> {
    return this.ask(`/drawings/${name}`, () => ({
      drawing: name,
      symbols: { b1: { kind: "block", at: [0, 0] } },
      wires: [],
    }));
  }

  saveDrawing(drawing: Drawing): Promise<void> {
    return this.write(`/drawings/${drawing.drawing}`);
  }

  review(drawing: Drawing): Promise<Review> {
    const name = drawing.drawing;
    return this.gated(`/review/${name}`, () =>
      Promise.resolve({ ...CLEAN, refused: this.refusing[name] ?? null }),
    );
  }

  readTrains(railroad: string): Promise<TrainsDoc> {
    const trains: Record<string, TrainDoc> = { [`${railroad}-goods`]: { length: 400 } };
    return this.ask(`/rosters/${railroad}/trains`, () => ({ roster: railroad, trains }));
  }

  readRoster(railroad: string): Promise<RosterDoc> {
    return this.ask(`/rosters/${railroad}`, () => ({
      roster: railroad,
      cars: { "hopper-1": { model: "hopper" } },
      trains: { ore: { cars: [{ car: "hopper-1" }] } },
    }));
  }

  readCatalogue(): Promise<Record<string, ModelDoc>> {
    return this.ask("/catalogue", () => ({ hopper: HOPPER }));
  }

  saveRoster(roster: RosterDoc): Promise<void> {
    return this.write(`/rosters/${roster.roster}`);
  }

  saveModel(model: ModelDoc): Promise<void> {
    return this.write(`/catalogue/${model.model}`);
  }
}

/** A railroad over a fake store, the editor the shell would own, how
 *  often it asked to be redrawn, and every railroad it named on the bus. */
function made() {
  const store = new Fake();
  const told = { times: 0 };
  const notify = (): void => {
    told.times++;
  };
  const names: string[] = [];
  const editor = new Editor(emptyDrawing("untitled"));
  const filing = new Filing(notify, store);
  const railroad = new Railroad(filing, () => editor, notify, (one) => names.push(one), store);
  return { railroad, filing, editor, store, told, names };
}

/** Every answer in flight delivered, and every answer those set off. */
async function flushed(): Promise<void> {
  for (let turn = 0; turn < 20; turn++) await Promise.resolve();
}

/** The interval passed, and what the retry asked answered. */
async function waited(): Promise<void> {
  await vi.advanceTimersByTimeAsync(RETRY_MS);
  await flushed();
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("a railroad the row names", () => {
  it("reads the drawing, the roster with the catalogue, and the trains", async () => {
    const { railroad, filing, editor, store } = made();

    railroad.named("toy");
    await flushed();

    expect(filing.opened).toBe("toy");
    expect(editor.drawing.drawing).toBe("toy");
    expect(railroad.name).toBe("toy");
    expect(railroad.stock?.roster.roster).toBe("toy");
    expect(Object.keys(railroad.trains)).toEqual(["toy-goods"]);
    expect(store.asked.sort()).toEqual([
      "/catalogue",
      "/drawings/toy",
      "/rosters/toy",
      "/rosters/toy/trains",
    ]);
  });

  for (const path of ["/drawings/toy", "/rosters/toy", "/catalogue", "/rosters/toy/trains"]) {
    it(`reads ${path} again after the interval where the store did not answer`, async () => {
      const { railroad, filing, store } = made();
      store.failing[path] = "unanswered";

      railroad.named("toy");
      await flushed();
      expect(store.count(path)).toBe(1);

      store.failing = {};
      await waited();

      expect(store.count(path)).toBe(2);
      expect(filing.opened).toBe("toy");
      expect(railroad.stock).not.toBeNull();
      expect(Object.keys(railroad.trains)).toEqual(["toy-goods"]);
      expect(filing.trouble).toBeNull();
      expect(railroad.trouble).toBeNull();
      expect(railroad.stockTrouble).toBeNull();
    });
  }

  it("says why the trains and the roster could not be read", async () => {
    const { railroad, store } = made();
    store.failing["/rosters/toy/trains"] = "unanswered";
    store.failing["/catalogue"] = "refused";

    railroad.named("toy");
    await flushed();

    expect(railroad.trouble).toBe("the store is not answering — run `tc49 serve`");
    expect(railroad.stockTrouble).toBe("no such thing as /catalogue");
  });

  it("keeps one timer whatever fails, and reads each failed one once per interval", async () => {
    const { railroad, store } = made();
    store.failing = {
      "/drawings/toy": "unanswered",
      "/rosters/toy": "unanswered",
      "/rosters/toy/trains": "unanswered",
    };

    railroad.named("toy");
    await flushed();
    expect(vi.getTimerCount()).toBe(1);

    await waited();

    expect(vi.getTimerCount()).toBe(1);
    expect(store.count("/drawings/toy")).toBe(2);
    expect(store.count("/rosters/toy")).toBe(2);
    expect(store.count("/rosters/toy/trains")).toBe(2);
  });

  it("reads nothing more once all three have landed", async () => {
    const { railroad, store } = made();
    store.failing["/rosters/toy/trains"] = "unanswered";
    railroad.named("toy");
    await flushed();
    store.failing = {};
    await waited();
    const asked = store.asked.length;

    await waited();
    await waited();

    expect(store.asked.length).toBe(asked);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("makes a read the store refused once, and shows the refusal", async () => {
    const { railroad, filing, store } = made();
    store.failing = {
      "/drawings/toy": "refused",
      "/rosters/toy": "refused",
      "/rosters/toy/trains": "refused",
    };

    railroad.named("toy");
    await flushed();
    await waited();

    expect(store.count("/drawings/toy")).toBe(1);
    expect(store.count("/rosters/toy")).toBe(1);
    expect(store.count("/rosters/toy/trains")).toBe(1);
    expect(vi.getTimerCount()).toBe(0);
    expect(filing.trouble).toContain("no such thing as /drawings/toy");
    expect(railroad.trouble).toBe("no such thing as /rosters/toy/trains");
    expect(railroad.stockTrouble).toBe("no such thing as /rosters/toy");
  });
});

describe("the row naming another railroad", () => {
  it("holds nothing of the first while the second's reads fail, and retries only the second", async () => {
    const { railroad, filing, editor, store } = made();
    railroad.named("toy");
    await flushed();
    store.failing = {
      "/drawings/otira": "unanswered",
      "/rosters/otira": "unanswered",
      "/rosters/otira/trains": "unanswered",
    };

    railroad.named("otira");
    await flushed();

    expect(filing.opened).toBe("");
    expect(editor.drawing).toEqual(emptyDrawing(""));
    expect(railroad.stock).toBeNull();
    expect(railroad.trains).toEqual({});
    expect(railroad.name).toBe("otira");

    store.asked = [];
    store.failing = {};
    await waited();

    expect(store.asked.every((path) => !path.includes("toy"))).toBe(true);
    expect(filing.opened).toBe("otira");
    expect(railroad.stock?.roster.roster).toBe("otira");
    expect(Object.keys(railroad.trains)).toEqual(["otira-goods"]);
  });

  it("retries nothing of the first while its reads were failing", async () => {
    const { railroad, store } = made();
    store.failing["/rosters/toy/trains"] = "unanswered";
    railroad.named("toy");
    await flushed();

    railroad.named("otira");
    await flushed();
    store.asked = [];
    await waited();

    expect(store.asked).toEqual([]);
    expect(Object.keys(railroad.trains)).toEqual(["otira-goods"]);
  });

  it("cancels the retry and holds nothing for a row naming none", async () => {
    const { railroad, filing, editor, store } = made();
    store.failing["/rosters/toy/trains"] = "unanswered";
    store.failing["/rosters/toy"] = "unanswered";
    railroad.named("toy");
    await flushed();

    railroad.named("");
    store.asked = [];
    await waited();

    expect(vi.getTimerCount()).toBe(0);
    expect(store.asked).toEqual([]);
    expect(filing.opened).toBe("");
    expect(editor.drawing).toEqual(emptyDrawing(""));
    expect(railroad.stock).toBeNull();
    expect(railroad.trains).toEqual({});
    expect(railroad.trouble).toBeNull();
    expect(railroad.stockTrouble).toBeNull();
  });

  it("reads nothing and keeps the edits for the same name again", async () => {
    const { railroad, filing, editor, store } = made();
    railroad.named("toy");
    await flushed();
    railroad.stock!.carAddress("hopper-1", "7");
    editor.reset({ ...editor.drawing, symbols: {} });
    void filing.edited(editor);
    await flushed();
    const asked = store.asked.length;

    railroad.named("toy");
    await flushed();

    expect(store.asked.length).toBe(asked);
    expect(railroad.unsaved).toBe("the drawing and the roster");
  });

  it("drops the first's drawing where it arrives after the second's", async () => {
    const { railroad, filing, editor, store } = made();
    const answer = store.hold("/drawings/toy");
    railroad.named("toy");
    await flushed();

    railroad.named("otira");
    await flushed();
    answer();
    await flushed();

    expect(filing.opened).toBe("otira");
    expect(editor.drawing.drawing).toBe("otira");
    expect(filing.trouble).toBeNull();
  });

  it("drops the first's drawing failing after the second's arrived, and retries nothing of it", async () => {
    const { railroad, filing, store } = made();
    const answer = store.hold("/drawings/toy");
    railroad.named("toy");
    await flushed();

    railroad.named("otira");
    await flushed();
    store.failing["/drawings/toy"] = "unanswered";
    answer();
    await flushed();

    expect(filing.trouble).toBeNull();
    await waited();
    expect(store.count("/drawings/toy")).toBe(1);
  });

  it("keeps the edits to the same name named again after another, whatever the first read brings", async () => {
    const { railroad, filing, editor, store } = made();
    const answer = store.hold("/drawings/toy");
    railroad.named("toy");
    await flushed();
    railroad.named("otira");
    await flushed();
    railroad.named("toy");
    await flushed();
    const edit = { ...editor.drawing, symbols: {} };
    editor.reset(edit);
    void filing.edited(editor);
    await flushed();

    answer();
    await flushed();

    expect(editor.drawing).toEqual(edit);
    expect(railroad.unsaved).toBe("the drawing");
  });

  it("drops the first's review where it arrives after the second opened", async () => {
    const { railroad, filing, store } = made();
    store.refusing.toy = "toy is an invalid drawing";
    const answer = store.hold("/review/toy");
    railroad.named("toy");
    await flushed();

    railroad.named("otira");
    await flushed();
    answer();
    await flushed();

    expect(filing.reviewed?.refused).toBeNull();
    expect(filing.valid).toBe(true);
  });

  it("drops the first's Save where it lands after the second was edited, and answers false", async () => {
    const { railroad, filing, editor, store } = made();
    railroad.named("toy");
    await flushed();
    editor.reset({ ...editor.drawing, symbols: {} });
    void filing.edited(editor);
    await flushed();
    const answer = store.hold("/drawings/toy");
    const saving = filing.save(editor);

    railroad.named("otira");
    await flushed();
    editor.reset({ ...editor.drawing, symbols: {} });
    void filing.edited(editor);
    await flushed();
    answer();

    expect(await saving).toBe(false);
    expect(filing.saved).toBe(false);
    expect(railroad.unsaved).toBe("the drawing");
  });
});

describe("what changing the railroad would discard", () => {
  it("names the roster, the drawing, or both", async () => {
    const { railroad, filing, editor } = made();
    railroad.named("toy");
    await flushed();
    expect(railroad.unsaved).toBeNull();

    railroad.stock!.carAddress("hopper-1", "7");
    expect(railroad.unsaved).toBe("the roster");

    void filing.edited(editor);
    expect(railroad.unsaved).toBe("the drawing and the roster");
  });
});

describe("the roster's Save", () => {
  /** `toy` loaded, with a model's length corrected and a car's address
   *  given: two documents to write. */
  async function edited() {
    const made_ = made();
    made_.railroad.named("toy");
    await flushed();
    made_.railroad.stock!.modelLength("hopper", 110, "off");
    made_.railroad.stock!.carAddress("hopper-1", "7");
    return made_;
  }

  it("writes the corrected models before the roster, and answers that a length reached the store", async () => {
    const { railroad, store, names } = await edited();

    const reached = await railroad.save("off");

    expect(reached).toBe(true);
    expect(names).toEqual(["toy"]);
    expect(store.saved).toEqual(["/catalogue/hopper", "/rosters/toy"]);
    expect(railroad.unsaved).toBeNull();
    expect(railroad.stockTrouble).toBeNull();
  });

  it("answers false and names nothing where no length moved", async () => {
    const { railroad, store, names } = made();
    railroad.named("toy");
    await flushed();
    railroad.stock!.carAddress("hopper-1", "7");

    expect(await railroad.save("off")).toBe(false);
    expect(store.saved).toEqual(["/rosters/toy"]);
    expect(names).toEqual([]);
  });

  /** A Save that did not land changed nothing any app could build. */
  it("names nothing where the store refused the length", async () => {
    const { railroad, store, names } = await edited();
    store.failing["/catalogue/hopper"] = "refused";

    expect(await railroad.save("off")).toBe(false);

    expect(names).toEqual([]);
  });

  it("is saving until the write answers, and writes once per press", async () => {
    const { railroad, store } = await edited();
    const answer = store.hold("/rosters/");

    const first = railroad.save("off");
    await flushed();
    expect(railroad.saving).toBe(true);
    expect(await railroad.save("off")).toBe(false);

    answer();
    await first;

    expect(railroad.saving).toBe(false);
    expect(store.saved.filter((path) => path.startsWith("/rosters/"))).toEqual([
      "/rosters/toy",
    ]);
  });

  it("leaves what was written where a refusal stops it partway", async () => {
    const { railroad, store } = await edited();
    store.failing["/rosters/toy"] = "refused";

    const reached = await railroad.save("off");

    expect(reached).toBe(true);
    expect(store.saved).toEqual(["/catalogue/hopper"]);
    expect(railroad.stock!.corrections).toEqual([]);
    expect(railroad.unsaved).toBe("the roster");
    expect(railroad.stockTrouble).toBe("no such thing as /rosters/toy");
    expect(railroad.saving).toBe(false);
  });

  it("writes nothing with a length edit while the rails have power, and says why", async () => {
    const { railroad, store } = await edited();

    expect(await railroad.save("on")).toBe(false);

    expect(store.saved).toEqual([]);
    expect(railroad.stockTrouble).not.toBeNull();
  });

  /** A page that has lost the broker cannot know whether the track has power
   *  (#804). */
  it("writes nothing with a length edit while the row is not heard, and says why", async () => {
    const { railroad, store } = await edited();

    expect(await railroad.save(null, false)).toBe(false);

    expect(store.saved).toEqual([]);
    expect(railroad.stockTrouble).toBe(LENGTH_UNHEARD);
  });

  it("writes nothing with a train that has nothing in it, and says why", async () => {
    const { railroad, store } = made();
    railroad.named("toy");
    await flushed();
    railroad.stock!.addTrain("empty");

    expect(await railroad.save("off")).toBe(false);

    expect(store.saved).toEqual([]);
    expect(railroad.stockTrouble).toContain("train 'empty' has nothing in it");
  });

  it("changes nothing the next railroad shows where the row moved while it was in flight", async () => {
    const { railroad, store } = await edited();
    const answer = store.hold("/rosters/");
    store.failing["/rosters/toy"] = "refused";
    const saving = railroad.save("off");
    await flushed();

    railroad.named("otira");
    await flushed();
    answer();

    expect(await saving).toBe(false);
    expect(railroad.stockTrouble).toBeNull();
    expect(railroad.saving).toBe(false);
    expect(railroad.stock?.roster.roster).toBe("otira");
  });

  it("reads the trains again once it has landed", async () => {
    const { railroad, store } = await edited();
    const before = store.count("/rosters/toy/trains");

    await railroad.save("off");
    await flushed();

    expect(store.count("/rosters/toy/trains")).toBe(before + 1);
  });

  it("takes a refusal down with the next edit", async () => {
    const { railroad, store } = await edited();
    store.failing["/rosters/toy"] = "refused";
    await railroad.save("off");

    railroad.edited();

    expect(railroad.stockTrouble).toBeNull();
  });
});

describe("the drawing's save", () => {
  /** `toy` loaded, with an edit to its drawing. */
  async function edited() {
    const made_ = made();
    made_.railroad.named("toy");
    await flushed();
    await made_.filing.edited(made_.editor);
    made_.store.saved.length = 0;
    return made_;
  }

  it("writes the drawing and names the railroad once", async () => {
    const { railroad, filing, store, names } = await edited();

    expect(await railroad.saveDrawing("off")).toBe(true);

    expect(store.saved).toEqual(["/drawings/toy"]);
    expect(filing.saved).toBe(true);
    expect(names).toEqual(["toy"]);
  });

  it("writes nothing without edits", async () => {
    const { railroad, store, names } = made();
    railroad.named("toy");
    await flushed();
    await railroad.saveDrawing("off");
    store.saved.length = 0;

    expect(await railroad.saveDrawing("off")).toBe(false);

    expect(store.saved).toEqual([]);
    expect(names).toEqual([]);
  });

  for (const power of ["on", "draining", null] as const) {
    it(`writes nothing with power ${power}`, async () => {
      const { railroad, filing, store, names } = await edited();

      expect(await railroad.saveDrawing(power)).toBe(false);

      expect(store.saved).toEqual([]);
      expect(filing.saved).toBe(false);
      expect(names).toEqual([]);
    });
  }

  it("writes nothing and names nothing where another railroad was named before it answered", async () => {
    const { railroad, store, names } = await edited();
    const answer = store.hold("/drawings/toy");

    const saved = railroad.saveDrawing("off");
    await flushed();
    railroad.named("yard");
    answer();

    expect(await saved).toBe(false);
    expect(names).toEqual([]);
  });

  it("writes once and names once for a second call during the write", async () => {
    const { railroad, store, names } = await edited();
    const answer = store.hold("/drawings/toy");

    const first = railroad.saveDrawing("off", true);
    const second = railroad.saveDrawing("off");
    expect(second).toBe(first);
    answer();

    expect(await first).toBe(true);
    expect(await second).toBe(true);
    expect(store.saved).toEqual(["/drawings/toy"]);
    expect(names).toEqual(["toy"]);
  });

  it("names nothing where the write fails", async () => {
    const { railroad, filing, store, names } = await edited();
    store.failing["/drawings/toy"] = "refused";

    expect(await railroad.saveDrawing("off")).toBe(false);

    expect(filing.saved).toBe(false);
    expect(names).toEqual([]);
  });
});

describe("the trains read again", () => {
  it("reads them for the railroad held, and keeps them where the read fails", async () => {
    const { railroad, store } = made();
    railroad.named("toy");
    await flushed();
    store.failing["/rosters/toy/trains"] = "unanswered";

    await railroad.reread();

    expect(store.count("/rosters/toy/trains")).toBe(2);
    expect(Object.keys(railroad.trains)).toEqual(["toy-goods"]);
    expect(railroad.trouble).toBeNull();
  });

  it("reads nothing with no railroad named", async () => {
    const { railroad, store } = made();

    await railroad.reread();

    expect(store.asked).toEqual([]);
  });
});
