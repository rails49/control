/**
 * The loaded railroad's documents, read and held in one place (#758): the
 * drawing (through the `Filing`), the roster with the catalogue it is read
 * against (the `Stock`), and the trains the store derives from them.
 *
 * Every view holds the loaded railroad and no other (ADR-0072, decision 3),
 * built or not: a railroad whose drawing is not a valid drawing is named with
 * `built: false` and its drawing held all the same, to be fixed (ADR-0085,
 * decision 4, #885). The row the layout interface publishes names it, and
 * `named` is the one way in: the shell hands over what the row says and does nothing else about
 * documents. When the row names another railroad, nothing of the last one
 * stays — the editor is emptied, the `Stock` and the trains go — before
 * anything of the next is read, so no view paints one railroad's drawing
 * under another's name.
 *
 * **A read the store did not answer is made again; a refusal is not.** The
 * store is not on the bus, so nothing republishes a document (ADR-0010), and
 * a page with a railroad on it wants to be on that railroad whatever was not
 * answering when it came up (`RETRY_MS`). One timer serves all three reads:
 * when it fires it reads whichever has not landed, for the railroad last
 * named. A refusal is the store answering, and would be answered the same
 * again (`Unanswered`, model/store.ts).
 *
 * The roster's Save is here too, so a Save in flight when the row names
 * another railroad writes its answer onto nothing the new railroad shows.
 * So is the drawing's save, made where one is owed (ADR-0085, decision 1).
 *
 * **A save that lands names the railroad again**, on `railroad_wanted`
 * through `name`, so every app builds what was written and keeps the trains
 * that fit (ADR-0071): a drawing that reached the store, and a roster Save
 * that moved a length. Each save names it once, and one that landed after the
 * row named another railroad names nothing — what it wrote is not what is
 * loaded (#798).
 *
 * No DOM, as nothing under `model/` has (docs/ARCHITECTURE.md). The store is a
 * dependency, as `Filing`'s is, and the `Editor` is taken when a read lands
 * and never held, for the reason `filing.ts` gives.
 */

import type { Editor } from "./editor.js";
import type { Filing } from "./filing.js";
import { Stock } from "./stock.js";
import {
  readCatalogue,
  readRoster,
  readTrains,
  RETRY_MS,
  said,
  saveModel,
  savePhoto,
  saveRoster,
  Unanswered,
  type ModelDoc,
  type RosterDoc,
  type TrainDoc,
  type TrainsDoc,
} from "./store.js";
import type { Power } from "./trace.js";

/** The store's stock routes, as the loaded railroad uses them. */
export interface StockStore {
  readTrains(railroad: string): Promise<TrainsDoc>;
  readRoster(railroad: string): Promise<RosterDoc>;
  readCatalogue(): Promise<Record<string, ModelDoc>>;
  saveRoster(roster: RosterDoc): Promise<void>;
  saveModel(model: ModelDoc): Promise<void>;
  savePhoto(model: string, jpeg: Uint8Array<ArrayBuffer>): Promise<void>;
}

/** The store as it is over HTTP. */
const live: StockStore = {
  readTrains,
  readRoster,
  readCatalogue,
  saveRoster,
  saveModel,
  savePhoto,
};

/** The three reads a railroad arriving makes, each landing on its own. */
type Read = "drawing" | "stock" | "trains";

export class Railroad {
  /** The railroad the row last named, `""` for none. */
  private last = "";
  /** Bumped whenever the row names another railroad, so a read or a Save that
   *  answers afterwards can tell it is about one that has gone. */
  private turn = 0;
  private held: Stock | null = null;
  private owned: Record<string, TrainDoc> = {};
  private wrong: string | null = null;
  private stockWrong: string | null = null;
  /** The documents whose Save is in flight, `null` where none is. */
  private writing: Stock | null = null;
  /** The drawing's save in flight, `null` while none is. */
  private drawing: Promise<boolean> | null = null;
  /** The reads the store did not answer, to be made again. */
  private due = new Set<Read>();
  private timer: ReturnType<typeof setTimeout> | null = null;

  /** Names a railroad on the bus: the session's `pressRailroad`. */
  private readonly naming: (railroad: string) => void;

  constructor(
    private readonly filing: Filing,
    private readonly editor: () => Editor,
    private readonly notify: () => void,
    name: (railroad: string) => void,
    private readonly store: StockStore = live,
  ) {
    this.naming = name;
  }

  /** The railroad the row last named, `""` while it names none. */
  get name(): string {
    return this.last;
  }

  /** The roster and the catalogue, and every edit to either
   *  (`model/stock.ts`); `null` until the store has answered for both. */
  get stock(): Stock | null {
    return this.held;
  }

  /** The trains the railroad owns, as the store derives them (#388): `{}`
   *  until read. */
  get trains(): Record<string, TrainDoc> {
    return this.owned;
  }

  /** Why the trains could not be read, `null` where nothing is wrong. The band
   *  shows it. */
  get trouble(): string | null {
    return this.wrong;
  }

  /** Why the roster or the catalogue could not be read, or what the last Save
   *  was refused with. The stock view shows it under the trains. */
  get stockTrouble(): string | null {
    return this.stockWrong;
  }

  /** Whether a Save is in flight for the documents held. */
  get saving(): boolean {
    return this.held !== null && this.writing === this.held;
  }

  /** What changing the railroad would discard — the drawing, the roster, or
   *  both — `null` while nothing is unsaved. A restore and a load are both
   *  refused over it (#415, #703, #733), and naming the document at stake
   *  tells a person who spent the evening composing a rake that it is the
   *  rake rather than a drawing they have not touched. */
  get unsaved(): string | null {
    const roster = this.held?.edits ?? false;
    const drawing = this.filing.edits;
    if (!roster) return drawing ? "the drawing" : null;
    return drawing ? "the drawing and the roster" : "the roster";
  }

  /**
   * The railroad the row names. The same name as last time does nothing: the
   * row is retained and republished whenever a page resubscribes, and edits
   * are not thrown away for it. `""` holds nothing. Any other name clears
   * everything the last railroad left and reads the next one's three
   * documents, each on its own.
   */
  named(railroad: string): void {
    if (railroad === this.last) return;
    this.last = railroad;
    this.turn += 1;
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
    this.due.clear();
    this.held = null;
    this.owned = {};
    this.wrong = null;
    this.stockWrong = null;
    this.writing = null;
    // Empties the editor and tells the shell, so what was on screen goes now
    // rather than when the next railroad's drawing lands.
    this.filing.close(this.editor());
    if (railroad === "") return;
    for (const read of ["drawing", "stock", "trains"] as const) void this.reading(read);
  }

  /**
   * The trains read again over a railroad already held: the store is not on
   * the bus, so a train made up on the stock screen reaches the run view by
   * being read when that view becomes current (ui/STOCK.md). A failure keeps
   * what is held — the trains it had are a better answer than none.
   */
  async reread(): Promise<void> {
    const railroad = this.last;
    if (railroad === "") return;
    const turn = this.turn;
    try {
      const trains = await this.store.readTrains(railroad);
      if (turn !== this.turn) return;
      this.owned = trains.trains;
      this.wrong = null;
      this.due.delete("trains");
    } catch {
      return;
    }
    this.notify();
  }

  /** An edit was made to the stock, so what the last Save was refused with is
   *  about a document that has since changed, and goes; and whatever reads
   *  `unsaved` is told. A read that failed holds no stock to edit, so its
   *  words stay. */
  edited(): void {
    if (this.held !== null) this.stockWrong = null;
    this.notify();
  }

  /**
   * The roster, whole, with each changed model written first and then each
   * changed photo, each in turn (#718, #978): the store refuses a roster
   * naming a model it has not got, and a photo of one. A model made on the
   * page is given its key first (`Stock.mintKeys`). A `PUT` is the whole
   * document, so a car left out is a car removed (#388); a refusal stops the
   * Save where it happened, what was written staying written and the rest
   * waiting for the next Save.
   *
   * It answers whether a length reached the store, and where one did names
   * the railroad it saved for again, before answering, so the dispatcher fits
   * trains by it (ADR-0071) — a model written and the roster then refused
   * included. One
   * Save at a time per `Stock` (#723). Where the row names another railroad
   * while it is in flight, nothing the new railroad shows is touched and it
   * answers `false`. A Save that landed reads the trains again, the lengths
   * they derive having moved. A length edit waits while power is on or
   * stopped, or while the row naming the railroad is not `heard` (#804).
   */
  async save(power: Power | null, heard: boolean = true): Promise<boolean> {
    const stock = this.held;
    if (stock === null || this.writing === stock) return false;
    // Asked before the `PUT` so the words are this screen's own and the saved
    // roster is untouched: a train with nothing in it is one the store
    // refuses whole, and the refusal names the row to go and fill (#412).
    const stopped = stock.stopsSaving() ?? stock.waitsForPower(power, heard);
    if (stopped !== null) {
      this.stockWrong = stopped;
      this.notify();
      return false;
    }
    const railroad = this.last;
    const turn = this.turn;
    const lengths = stock.lengthEdits;
    stock.mintKeys();
    const written = stock.roster;
    let reached = false;
    let landed = false;
    this.writing = stock;
    this.notify();
    let trouble: string | null = null;
    try {
      for (const model of stock.corrections) {
        await this.store.saveModel(model);
        stock.landed(model);
        // A model written moves a train's length only where one was
        // corrected; a name or a note is nothing the dispatcher fits.
        if (lengths) reached = true;
      }
      for (const [model, picture] of stock.photos) {
        await this.store.savePhoto(model, picture.jpeg);
        stock.photoLanded(model, picture);
      }
      await this.store.saveRoster(written);
      stock.kept(written);
      if (lengths) reached = true;
      landed = true;
    } catch (failure) {
      trouble = said(failure);
    }
    if (turn !== this.turn) return false;
    if (this.writing === stock) this.writing = null;
    this.stockWrong = trouble;
    this.notify();
    if (landed) void this.reread();
    if (reached) this.naming(railroad);
    return reached;
  }

  /**
   * The drawing given to the store where a save is owed: the drawing open is
   * the loaded railroad's, it holds edits, and `power` is `off` (ADR-0085,
   * decision 1). Anything else writes nothing and answers `false`. It answers
   * whether the drawing reached the store with the same railroad still open,
   * and where it did names that railroad again, once, before answering.
   * `leaving` is the page being hidden or closed, whose write must outlive
   * it. A save asked for while one is in flight — the page hidden and then
   * gone, or ON pressed while leaving the Edit view writes — is that one,
   * and names the railroad once.
   */
  saveDrawing(power: Power | null, leaving = false): Promise<boolean> {
    if (this.drawing !== null) return this.drawing;
    const railroad = this.filing.opened;
    if (railroad === "" || railroad !== this.last) return Promise.resolve(false);
    if (this.filing.saved || power !== "off") return Promise.resolve(false);
    const turn = this.turn;
    this.drawing = this.filing
      .save(this.editor(), leaving)
      .then((reached) => {
        if (!reached || turn !== this.turn) return false;
        this.naming(railroad);
        return true;
      })
      .finally(() => {
        this.drawing = null;
      });
    return this.drawing;
  }

  /** One of the three reads, for the railroad last named. */
  private async reading(read: Read): Promise<void> {
    const railroad = this.last;
    const turn = this.turn;
    if (read === "drawing") {
      const opened = await this.filing.open(railroad, this.editor());
      if (turn === this.turn && opened === "unanswered") this.again(read);
      return;
    }
    try {
      if (read === "stock") {
        const [roster, catalogue] = await Promise.all([
          this.store.readRoster(railroad),
          this.store.readCatalogue(),
        ]);
        if (turn !== this.turn) return;
        this.held = new Stock(roster, catalogue);
        this.stockWrong = null;
      } else {
        const trains = await this.store.readTrains(railroad);
        if (turn !== this.turn) return;
        this.owned = trains.trains;
        this.wrong = null;
      }
    } catch (failure) {
      if (turn !== this.turn) return;
      // Which of the three ways it failed is the store helper's to say
      // (model/store.ts, #411).
      if (read === "stock") this.stockWrong = said(failure);
      else this.wrong = said(failure);
      if (failure instanceof Unanswered) this.again(read);
    }
    this.notify();
  }

  /** A read to make again when the one timer fires, which it is set going for
   *  where it is not already. */
  private again(read: Read): void {
    this.due.add(read);
    if (this.timer !== null) return;
    this.timer = setTimeout(() => {
      this.timer = null;
      const due = [...this.due];
      this.due.clear();
      for (const one of due) void this.reading(one);
    }, RETRY_MS);
  }
}
