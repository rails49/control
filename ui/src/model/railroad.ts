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
 * The roster's save is here too, so a save in flight when the row names
 * another railroad writes its answer onto nothing the new railroad shows.
 * So is the drawing's. Both are made at the same moments — a view left, the
 * page hidden, ON, a pick in the settings dialog — where one is owed
 * (ADR-0085, decision 1; #1233).
 *
 * **A save that lands names the railroad again**, on `railroad_wanted`
 * through `name`, so every app builds what was written and keeps the trains
 * that fit (ADR-0071): a drawing that reached the store, and a roster save
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
import type { Landing } from "./session.js";
import type { Power } from "./trace.js";

/** The store's stock routes, as the loaded railroad uses them. */
export interface StockStore {
  readTrains(railroad: string): Promise<TrainsDoc>;
  readRoster(railroad: string): Promise<RosterDoc>;
  readCatalogue(): Promise<Record<string, ModelDoc>>;
  saveRoster(roster: RosterDoc, leaving?: boolean): Promise<void>;
  saveModel(model: ModelDoc, leaving?: boolean): Promise<void>;
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
  /** Bumped whenever the row names another railroad, so a read or a save that
   *  answers afterwards can tell it is about one that has gone. */
  private turn = 0;
  private held: Stock | null = null;
  private owned: Record<string, TrainDoc> = {};
  private wrong: string | null = null;
  private stockWrong: string | null = null;
  /** The documents whose save is in flight, and what it will answer, `null`
   *  where none is. */
  private writing: { stock: Stock; landing: Promise<Landing> } | null = null;
  /** How many roster saves have landed, so the stock view can say *Saved*. */
  private kept = 0;
  /** Whether a save landing during `beforeOn` named the loaded railroad,
   *  held to be named once when it ends; `null` outside one. */
  private deferred: boolean | null = null;
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

  /** Why the roster or the catalogue could not be read, or what the last save
   *  was refused with. The stock view shows it in its bar. */
  get stockTrouble(): string | null {
    return this.stockWrong;
  }

  /** How many roster saves have landed: the stock view says *Saved* for a
   *  moment where this moves while it is on screen. */
  get landings(): number {
    return this.kept;
  }

  /**
   * Whether the roster holds edits that could not be saved, which the band
   * marks *unsaved* (#1233): the last save did not land, a save would be
   * refused (`Stock.stopsSaving`), or a length edit waits on power
   * (`Stock.waitsForPower`). Edits a leave would save say nothing, as the
   * drawing's do (`stranded`, model/commands.ts).
   */
  stranded(power: Power | null, heard: boolean): boolean {
    const stock = this.held;
    if (stock === null || !stock.edits) return false;
    return (
      this.stockWrong !== null ||
      stock.stopsSaving() !== null ||
      stock.waitsForPower(power, heard) !== null
    );
  }

  /** What changing the railroad would discard — the drawing, the roster, or
   *  both — `null` while nothing is unsaved. A restore is refused over it
   *  (#703), and a load that could not save it first says it (#1233): naming
   *  the document at stake tells a person who spent the evening composing a
   *  rake that it is the rake rather than a drawing they have not touched. */
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

  /** An edit was made to the stock, so what the last save was refused with is
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
   * save where it happened, what was written staying written and the rest
   * waiting for the next save. Nothing is written where the roster holds no
   * edits.
   *
   * It answers how it came out (`Landing`): `named` where a length reached
   * the store, the railroad it saved for named again before answering so the
   * dispatcher fits trains by it (ADR-0071); `landed` where the save landed
   * and moved no length, or there was nothing to write; `null` where it wrote
   * nothing or did not land. A model written and the roster then refused
   * names the railroad all the same, and answers `null`.
   *
   * One save at a time per `Stock` (#723): one asked for while one is in
   * flight is that one. Where the row names another railroad while it is in
   * flight, nothing the new railroad shows is touched and it answers `null`.
   * A save that landed reads the trains again, the lengths they derive having
   * moved. What `Stock.stopsSaving` returns writes nothing and stands as
   * `stockTrouble`. A length edit waits while power is on or stopped, or while
   * the row naming the railroad is not `heard` (#804): every edit waits with
   * it, and the stock view says why from `Stock.waitsForPower`. `leaving` is
   * the page being hidden or closed: the models and the roster go with
   * `keepalive`, the photos not, `keepalive` capping bodies at 64 KiB.
   */
  save(power: Power | null, heard: boolean = true, leaving = false): Promise<Landing> {
    const stock = this.held;
    if (stock === null || !stock.edits) return Promise.resolve("landed");
    if (this.writing?.stock === stock) return this.writing.landing;
    // Asked before the `PUT` so the words are this screen's own and the saved
    // roster is untouched: a train with nothing in it is one the store
    // refuses whole, and the refusal names the row to go and fill (#412).
    const stopped = stock.stopsSaving();
    if (stopped !== null) {
      this.stockWrong = stopped;
      this.notify();
      return Promise.resolve(null);
    }
    if (stock.waitsForPower(power, heard) !== null) return Promise.resolve(null);
    const landing = this.writeStock(stock, leaving);
    this.writing = { stock, landing };
    this.notify();
    return landing;
  }

  /** `save`'s writes, for `stock` as it stands. */
  private async writeStock(stock: Stock, leaving: boolean): Promise<Landing> {
    const railroad = this.last;
    const turn = this.turn;
    const lengths = stock.lengthEdits;
    stock.mintKeys();
    const written = stock.roster;
    let reached = false;
    let landed = false;
    let trouble: string | null = null;
    try {
      for (const model of stock.corrections) {
        await this.store.saveModel(model, leaving);
        stock.landed(model);
        // A model written moves a train's length only where one was
        // corrected; a name or a note is nothing the dispatcher fits.
        if (lengths) reached = true;
      }
      for (const [model, picture] of stock.photos) {
        await this.store.savePhoto(model, picture.jpeg);
        stock.photoLanded(model, picture);
      }
      await this.store.saveRoster(written, leaving);
      stock.kept(written);
      if (lengths) reached = true;
      landed = true;
    } catch (failure) {
      trouble = said(failure);
    }
    if (turn !== this.turn) return null;
    if (this.writing?.stock === stock) this.writing = null;
    this.stockWrong = trouble;
    if (landed) this.kept += 1;
    this.notify();
    if (landed) void this.reread();
    if (reached) this.nameAgain(railroad);
    if (!landed) return null;
    return reached ? "named" : "landed";
  }

  /**
   * What ON saves first, `null` where nothing is owed (ADR-0085, decision 2;
   * #1233): the drawing where `drawing` says a save is owed (`owed`,
   * model/commands.ts), and the roster where it holds edits that are not
   * waiting on power. Both are written
   * together, and the railroad is named again once, after both have
   * answered, so the power comes on over one build of both. It answers
   * `named` where either named the railroad and neither failed, `landed`
   * where all that was owed landed and named nothing, and `null` where one
   * did not land — what `pressOnSaved` (model/session.ts) waits on.
   */
  beforeOn(power: Power | null, heard: boolean, drawing: boolean): Promise<Landing> | null {
    const stock = this.held;
    const roster =
      stock !== null && stock.edits && stock.waitsForPower(power, heard) === null;
    if (!drawing && !roster) return null;
    const owner = this.deferred === null;
    if (owner) this.deferred = false;
    return Promise.all([
      drawing ? this.saveDrawing(power).then((named) => (named ? "named" : null)) : "landed",
      roster ? this.save(power, heard) : "landed",
    ]).then((both) => {
      if (owner) {
        const named = this.deferred === true;
        this.deferred = null;
        if (named) this.naming(this.last);
      }
      if (both.includes(null)) return null;
      return both.includes("named") ? "named" : "landed";
    });
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
        this.nameAgain(railroad);
        return true;
      })
      .finally(() => {
        this.drawing = null;
      });
    return this.drawing;
  }

  /** `railroad` named again on the bus, or held while `beforeOn` waits for
   *  the other save. */
  private nameAgain(railroad: string): void {
    if (this.deferred === null) this.naming(railroad);
    else if (railroad === this.last) this.deferred = true;
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
