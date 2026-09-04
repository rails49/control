/**
 * The stock view (ui/STOCK.md): what can go in a train on the left — cars
 * above, models below — and the trains on the right. You compose right from
 * left.
 *
 * The railroad it is editing is not its own: the app holds which one is loaded
 * and hands the name down, exactly as it hands the drawing to the editor
 * ([ADR-0038](../../../docs/adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md)).
 * **No session**, like the editor: this is a document view, and what it reads
 * and writes are the store's two stock routes (#388, #392).
 *
 * It works nothing out. Every length, kind and function shown is
 * `model/stock.ts`'s answer, and so is every refusal: what promotes an entry
 * to a car, what a minted name is, what holds a thing somebody asked to
 * remove, and why a length may not be corrected are rules, and a rule lives
 * where it can be driven from plain values (ui/README.md).
 *
 * **Composing a train and placing it are two actions**
 * ([ADR-0039](../../../docs/adr/0039-a-train-may-be-off-the-layout.md)): a
 * rake is durable and lives in the roster, and where it stands belongs to the
 * run. It is made up here and put on the layout in the run view.
 *
 * The run state comes down from the app because the app is the only thing on
 * the page that has any: the length guard reads it, and a second browser
 * editing stock during a run is not covered (ui/STOCK.md#the-length-guard,
 * [#390](https://github.com/rails49/control/issues/390)).
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import "@shoelace-style/shoelace/dist/components/button/button.js";
import "@shoelace-style/shoelace/dist/components/dialog/dialog.js";

import {
  KINDS,
  Stock,
  type CarRow,
  type EntryRow,
  type ModelRow,
  type TrainRow,
} from "../model/stock.js";
import {
  readCatalogue,
  readRoster,
  RETRY_MS,
  said,
  saveModel,
  saveRoster,
  Unanswered,
  type ModelDoc,
  type ModelFn,
} from "../model/store.js";
import { stockStyles } from "./tc-stock.styles.js";

/**
 * A model being written in the dialog, before it is a document.
 *
 * A product that does not exist yet is created in the same dialog rather than
 * on a screen of its own: the catalogue is a real document with its own route
 * underneath, and never a place a person navigates to for its own sake
 * (ui/STOCK.md).
 */
export interface Draft {
  model: string;
  kind: string;
  /** As typed: a field mid-edit is not a number yet, and the refusal for one
   *  that never becomes one is the same refusal a length gets anywhere else. */
  length: string;
  /** What each DCC function does, keyed by the number as typed — the number is
   *  the model's business and no view shows it again (ADR-0045). */
  functions: { number: string; name: string }[];
}

/** An empty dialog: a freight wagon, which is what most of a catalogue is. */
function draft(): Draft {
  return { model: "", kind: "freight", length: "", functions: [] };
}

@customElement("tc-stock")
export class TcStock extends LitElement {
  static override styles = stockStyles;

  /** The loaded railroad, whose roster this edits. `null` while none is
   *  loaded, which is a screen with nothing to edit and not a fault. */
  @property({ attribute: false }) railroad: string | null = null;

  /** Whether this view is the current one. The documents are read when the
   *  railroad changes and not on every switch, so edits survive a look at the
   *  run and come back as they were left. */
  @property({ type: Boolean }) current = false;

  /** The trains the run has on the layout, as the run view says. The length
   *  guard is the only thing that reads it. */
  @property({ attribute: false }) placed: readonly string[] = [];

  /** The roster and the catalogue, and every edit to either
   *  (`model/stock.ts`). `null` until the store has answered. */
  @state() private stock: Stock | null = null;

  /** The railroad the documents were read for, so they are read again when
   *  the app loads another and kept when anything else changes. */
  @state() private held: string | null = null;

  /** The train a press on the left is about. Composing right from left needs
   *  somewhere for the left to go, and one train is current at a time. */
  @state() private train: string | null = null;

  /** What was refused — by this screen before the store had to see it, or by
   *  the store — in the words of whichever refused it. */
  @state() private trouble: string | null = null;

  /** The model being written, `null` while the dialog is shut. */
  @state() private making: Draft | null = null;

  /** Bumped after each edit: `Stock` keeps its identity across one, so
   *  rendering is asked for rather than observed. */
  @state() private beat = 0;

  /** The read waiting to be made again, `null` while none is. */
  private waiting: ReturnType<typeof setTimeout> | null = null;

  override disconnectedCallback(): void {
    this.drop();
    super.disconnectedCallback();
  }

  override willUpdate(changed: Map<string, unknown>): void {
    if (!changed.has("railroad") && !changed.has("current")) return;
    // A try waiting is a try on the railroad that was showing, in the view
    // that was showing: neither is what to read when either changes.
    this.drop();
    if (!this.current || this.railroad === null || this.railroad === this.held) return;
    void this.load(this.railroad);
  }

  /**
   * The railroad's roster and the installation's catalogue.
   *
   * Both, because a car is only complete against its model: a roster answers
   * names, and what a length is comes from the catalogue (ADR-0045). A
   * railroad with no roster and an installation with no `catalogue/` are
   * answered the empty documents, which is what a fresh box is and what the
   * screen writing the first car draws itself from.
   */
  private async load(railroad: string): Promise<void> {
    this.held = railroad;
    try {
      const [roster, catalogue] = await Promise.all([
        readRoster(railroad),
        readCatalogue(),
      ]);
      if (this.held !== railroad) return;
      this.stock = new Stock(roster, catalogue);
      this.train = Object.keys(roster.trains).sort()[0] ?? null;
      this.trouble = null;
    } catch (failure) {
      if (this.held !== railroad) return;
      // Which of the three it was is the store helper's to say
      // (model/store.ts, #411). A fixed string here named `tc49 serve` for
      // every one of them, and a proxy answering `GET /catalogue` with its own
      // 404 page sent a person after a store that was up and answering (#405).
      this.stock = null;
      this.held = null;
      this.trouble = said(failure);
      // Nothing came back, so there is something to wait for: the store
      // starting, or whatever is in front of it learning where it is. A
      // refusal is the store answering and would be refused again the same.
      if (failure instanceof Unanswered) this.retry(railroad);
    }
  }

  /**
   * Read again in a moment, unless a read is already waiting.
   *
   * There is nothing on this screen to press — the railroad is loaded and the
   * documents are read when it arrives — so a person who kept looking at a
   * message until they reloaded the page is what the run view's retry already
   * spares an operator (PANEL.md). What runs is the same `load` the railroad
   * arriving runs, and a screen that has read by the time it comes round is
   * one it leaves alone.
   */
  private retry(railroad: string): void {
    if (this.waiting !== null) return;
    this.waiting = setTimeout(() => {
      this.waiting = null;
      if (this.current && this.railroad === railroad && this.stock === null) {
        void this.load(railroad);
      }
    }, RETRY_MS);
  }

  /** Drop the try that is waiting, where there is one. */
  private drop(): void {
    if (this.waiting !== null) clearTimeout(this.waiting);
    this.waiting = null;
  }

  override render() {
    const stock = this.stock;
    return html`
      <section class="parts">
        ${this.carList(stock?.cars(this.placed) ?? [])}
        ${this.modelList(stock?.modelRows(this.placed) ?? [])}
      </section>
      ${this.trainList(stock?.trains(this.placed) ?? [])}
      ${this.dialog()}
    `;
  }

  // --- the cars a railroad owns --------------------------------------------

  /** The identified stock: an item with an address, or with a field corrected
   *  on that item (ADR-0061). A car may stand in no train — a locomotive you
   *  own and have not made a rake for is an ordinary thing to have. */
  private carList(cars: CarRow[]) {
    return html`
      <section class="cars">
        <header class="head"><h2>Cars</h2></header>
        ${cars.length === 0
          ? html`<p class="hint">
              no cars yet — a model entry becomes one when you give it an
              address
            </p>`
          : html`<ul>
              ${cars.map((car) => this.car(car))}
            </ul>`}
      </section>
    `;
  }

  private car(car: CarRow) {
    return html`
      <li class="car">
        <span class="what">
          <input
            class="name"
            .value=${car.name}
            aria-label="car name"
            @change=${(event: Event) =>
              this.did(this.stock?.renameCar(car.name, value(event)))}
          />
          <span class="of">${car.model}${car.kind === null ? " — no such model" : ""}</span>
        </span>
        <input
          class="addr"
          .value=${car.addr ?? ""}
          placeholder="address"
          aria-label="address"
          @change=${(event: Event) =>
            this.did(this.stock?.carAddress(car.name, value(event)))}
        />
        <input
          class="length"
          .value=${car.own ? String(car.length) : ""}
          placeholder=${car.length === null ? "" : String(car.length)}
          aria-label="length"
          title=${car.held ?? "millimetres over buffers, where this item is not its model's length"}
          ?disabled=${car.held !== null}
          @change=${(event: Event) =>
            this.did(this.stock?.carLength(car.name, millimetres(event), this.placed))}
        />
        <button
          class="add"
          title=${this.train === null ? "make a train up first" : `add to '${this.train}'`}
          ?disabled=${this.train === null}
          @click=${() => this.coupled({ car: car.name })}
        >
          +
        </button>
        <button
          class="remove"
          title="remove from the roster"
          @click=${() => this.did(this.stock?.removeCar(car.name))}
        >
          ×
        </button>
        ${car.held === null ? nothing : html`<span class="why">${car.held}</span>`}
      </li>
    `;
  }

  // --- the catalogue --------------------------------------------------------

  /** What anything is made of. No remove: the store's catalogue face has no
   *  DELETE for any document and an unused model costs nothing
   *  (`store/server.py`), so what holds a model is read on the row rather
   *  than run into. */
  private modelList(models: ModelRow[]) {
    return html`
      <section class="models">
        <header class="head">
          <h2>Models</h2>
          <button class="new-model" @click=${() => (this.making = draft())}>
            New model…
          </button>
        </header>
        ${models.length === 0
          ? html`<p class="hint">
              no models yet — a train is made of them, so write the first one
            </p>`
          : html`<ul>
              ${models.map((model) => this.model(model))}
            </ul>`}
      </section>
    `;
  }

  private model(model: ModelRow) {
    return html`
      <li class="product">
        <span class="what">
          ${model.model}
          <span class="of">
            ${model.kind}${model.holders.length === 0
              ? ""
              : ` — ${model.holders.join(", ")}`}
          </span>
        </span>
        <span></span>
        <input
          class="length"
          .value=${String(model.length)}
          aria-label="length"
          title=${model.held ?? "millimetres over buffers, on every item of this product"}
          ?disabled=${model.held !== null}
          @change=${(event: Event) =>
            this.did(this.stock?.modelLength(model.model, millimetres(event) ?? 0, this.placed))}
        />
        <button
          class="add"
          title=${this.train === null ? "make a train up first" : `add to '${this.train}'`}
          ?disabled=${this.train === null}
          @click=${() => this.coupled({ model: model.model })}
        >
          +
        </button>
        <span></span>
        ${model.held === null ? nothing : html`<span class="why">${model.held}</span>`}
      </li>
    `;
  }

  // --- the trains -----------------------------------------------------------

  private trainList(trains: TrainRow[]) {
    return html`
      <section class="trains">
        <header class="head">
          <h2>Trains</h2>
          <button class="new-train" @click=${this.newTrain}>New train…</button>
          <sl-button
            class="save"
            size="small"
            variant="primary"
            ?disabled=${this.stock === null || !this.stock.edits}
            @click=${this.save}
            >Save</sl-button
          >
        </header>
        ${this.trouble === null
          ? nothing
          : html`<p class="trouble">${this.trouble}</p>`}
        ${trains.length === 0
          ? html`<p class="hint">
              no trains yet — make one up, then press + beside a car or a model
            </p>`
          : html`<ul>
              ${trains.map((train) => this.trainRow(train))}
            </ul>`}
      </section>
    `;
  }

  /** One train: its name, what it derives to, and the ordered list it is made
   *  of. Length, kind and functions are shown and never offered for editing
   *  (ADR-0045).
   *
   *  A train written before #223 states its length and names no cars: it is
   *  drawn with that length and a note saying so, and the first thing put in
   *  it converts it to the ordinary shape (#414). */
  private trainRow(train: TrainRow) {
    return html`
      <li
        class=${`train ${this.train === train.train ? "current" : ""}`}
        @click=${() => {
          this.train = train.train;
        }}
      >
        <header>
          <input
            class="name"
            .value=${train.train}
            aria-label="train name"
            @change=${(event: Event) =>
              this.did(this.stock?.renameTrain(train.train, value(event)))}
          />
          ${train.placed ? html`<span class="of">on the layout</span>` : nothing}
          <button
            class="remove"
            title="unmake this train"
            @click=${() => this.changed((stock) => stock.removeTrain(train.train))}
          >
            ×
          </button>
          <span class="derived">
            ${train.length === null ? "—" : `${train.length} mm`} ·
            ${train.kind ?? "—"}${train.functions.length === 0
              ? ""
              : ` · ${train.functions.map((fn) => fn.name).join(", ")}`}
          </span>
        </header>
        ${train.entries.length === 0
          ? html`<p class="hint">
              ${train.stated
                ? "states its length and names no cars — press + beside a car" +
                  " or a model to fill it in"
                : "nothing in it yet"}
            </p>`
          : html`<ol>
              ${train.entries.map((entry, at) => this.entry(train.train, entry, at))}
            </ol>`}
      </li>
    `;
  }

  /** One place in a train. The address is offered whatever the item's kind —
   *  a powered van is a real thing, so kind never implies an address
   *  (ADR-0061) — and typing one is what promotes an anonymous item to a car
   *  in the list above. */
  private entry(train: string, entry: EntryRow, at: number) {
    return html`
      <li class="entry">
        <span class=${`what ${entry.car === null ? "anonymous" : ""}`}>
          ${entry.car ?? entry.model ?? "—"}
          ${entry.car === null
            ? nothing
            : html`<span class="of">${entry.model ?? "no such model"}</span>`}
        </span>
        <input
          class="addr"
          .value=${entry.addr ?? ""}
          placeholder="address"
          aria-label="address"
          @change=${(event: Event) =>
            this.did(this.stock?.address(train, at, value(event)))}
        />
        <button
          class="turn"
          title="which way round it is coupled"
          aria-pressed=${entry.reverse ? "true" : "false"}
          @click=${() => this.changed((stock) => stock.turn(train, at))}
        >
          ${entry.reverse ? "↰" : "↱"}
        </button>
        <button
          class="remove"
          title="take it out of the train"
          @click=${() => this.changed((stock) => stock.removeEntry(train, at))}
        >
          ×
        </button>
      </li>
    `;
  }

  // --- the presses ----------------------------------------------------------

  /** A one-field prompt, as the app names a railroad with: a dialog for a
   *  single word would be more of the app than naming a train is worth. */
  private newTrain = (): void => {
    const said = window.prompt("New train", "");
    const name = said === null ? "" : said.trim();
    if (name === "" || this.stock === null) return;
    const refused = this.stock.addTrain(name);
    this.did(refused);
    if (refused === null) this.train = name;
  };

  /** A car or a model put at the tail of the current train: the whole of
   *  composing right from left. Named for what it does to the train rather
   *  than for the list press, `append` being `HTMLElement`'s. */
  private coupled(what: { car: string } | { model: string }): void {
    if (this.train === null) return;
    this.stock?.append(this.train, what);
    this.did(null);
  }

  /**
   * The roster, whole. A `PUT` is the whole document, so a car left out is a
   * car removed (#388), and the store validates it against the catalogue and
   * writes nothing where it does not validate — which is why a refusal is
   * shown here rather than left to be discovered later.
   */
  private save = async (): Promise<void> => {
    const stock = this.stock;
    if (stock === null) return;
    // Asked before the `PUT` so the words are this screen's own and the saved
    // roster is untouched: a train with nothing in it is one the store
    // refuses whole, and the refusal names the row to go and fill (#412).
    const stopped = stock.stopsSaving();
    if (stopped !== null) {
      this.did(stopped);
      return;
    }
    try {
      await saveRoster(stock.roster);
      stock.kept();
      this.trouble = null;
      this.beat++;
    } catch (trouble) {
      this.trouble = said(trouble);
    }
  };

  /** An edit that cannot refuse. It still goes through `did`, so the screen
   *  redraws and whatever the last refusal said is taken down. */
  private changed(edit: (stock: Stock) => void): void {
    if (this.stock === null) return;
    edit(this.stock);
    this.did(null);
  }

  /** What an edit answered: nothing, or the words to show. Either way the
   *  screen redraws — `Stock` keeps its identity across an edit, so Lit sees
   *  no changed property. */
  private did(refused: string | null | undefined): void {
    this.trouble = refused ?? null;
    this.beat++;
  }

  // --- writing a model ------------------------------------------------------

  /**
   * The dialog a product that does not exist yet is made in: name, length over
   * buffers, kind, and what each DCC function does.
   *
   * It is a form, so it is Shoelace's the way the properties dialog is, where
   * the rows behind it are a table and are the browser's own controls.
   */
  private dialog() {
    const making = this.making;
    if (making === null) return nothing;
    return html`
      <sl-dialog open label="New model" @sl-after-hide=${() => (this.making = null)}>
        <div class="field">
          <label for="model">Name</label>
          <input
            id="model"
            .value=${making.model}
            @change=${(event: Event) => this.drafting({ model: value(event) })}
          />
        </div>
        <div class="field">
          <label for="kind">Kind</label>
          <select
            id="kind"
            .value=${making.kind}
            @change=${(event: Event) => this.drafting({ kind: value(event) })}
          >
            ${KINDS.map(
              (kind) =>
                html`<option value=${kind} ?selected=${kind === making.kind}>
                  ${kind}
                </option>`,
            )}
          </select>
        </div>
        <div class="field">
          <label for="length">Length over buffers, mm</label>
          <input
            id="length"
            class="length"
            .value=${making.length}
            @change=${(event: Event) => this.drafting({ length: value(event) })}
          />
        </div>
        <div class="field">
          <label>Functions</label>
          <ul>
            ${making.functions.map((fn, at) => this.functionRow(fn, at))}
          </ul>
          <button
            class="add-function"
            @click=${() =>
              this.drafting({
                functions: [...making.functions, { number: "", name: "" }],
              })}
          >
            Add a function
          </button>
        </div>
        ${this.trouble === null ? nothing : html`<p class="trouble">${this.trouble}</p>`}
        <sl-button slot="footer" @click=${() => (this.making = null)}>Cancel</sl-button>
        <sl-button slot="footer" variant="primary" class="create" @click=${this.create}>
          Create
        </sl-button>
      </sl-dialog>
    `;
  }

  private functionRow(fn: { number: string; name: string }, at: number) {
    const making = this.making!;
    const changed = (part: { number?: string; name?: string }): void => {
      this.drafting({
        functions: making.functions.map((one, index) =>
          index === at ? { ...one, ...part } : one,
        ),
      });
    };
    return html`
      <li class="function">
        <input
          class="number"
          .value=${fn.number}
          placeholder="0"
          aria-label="function number"
          @change=${(event: Event) => changed({ number: value(event) })}
        />
        <input
          class="name"
          .value=${fn.name}
          placeholder="headlights"
          aria-label="function name"
          @change=${(event: Event) => changed({ name: value(event) })}
        />
        <button
          class="remove"
          @click=${() =>
            this.drafting({
              functions: making.functions.filter((_, index) => index !== at),
            })}
        >
          ×
        </button>
      </li>
    `;
  }

  private drafting(part: Partial<Draft>): void {
    this.making = { ...this.making!, ...part };
  }

  /**
   * Write the model, then take it into the catalogue this roster is read
   * against.
   *
   * It goes to the store now rather than with the roster because they are two
   * documents on two routes: a roster naming a model the installation has not
   * got is refused whole, so the product has to exist before anything refers
   * to it (#392).
   */
  private create = async (): Promise<void> => {
    const making = this.making;
    const stock = this.stock;
    if (making === null || stock === null) return;
    const trouble = this.wrong(making, stock);
    if (trouble !== null) {
      this.trouble = trouble;
      return;
    }
    const functions: Record<string, ModelFn> = {};
    for (const fn of making.functions) functions[fn.number.trim()] = { name: fn.name.trim() };
    const model: ModelDoc = {
      model: making.model.trim(),
      kind: making.kind,
      length: Number(making.length),
      ...(making.functions.length === 0 ? {} : { functions }),
    };
    try {
      await saveModel(model);
      stock.putModel(model);
      this.making = null;
      this.trouble = null;
      this.beat++;
    } catch (refused) {
      this.trouble = said(refused);
    }
  };

  /** What is wrong with the dialog as it stands, in the words the store would
   *  use, or `null` where nothing is. Asked before the `PUT` so that a name
   *  with a slash in it is answered where it was typed, and so that a name the
   *  catalogue already has never reaches a route that replaces a document
   *  whole (#413). */
  private wrong(making: Draft, stock: Stock): string | null {
    const name = making.model.trim();
    if (name === "" || name.includes(".") || name.includes("/")) {
      return `'${name}' is not a name a model can have`;
    }
    const already = stock.stopsMaking(name);
    if (already !== null) return already;
    const mm = Number(making.length);
    if (!Number.isInteger(mm) || mm <= 0) {
      return "a length is a positive whole number of millimetres";
    }
    for (const fn of making.functions) {
      if (fn.number.trim() === "" || fn.name.trim() === "") {
        return "a function is a DCC number and what it does on this product";
      }
    }
    return null;
  }
}

/** What was typed into a control, whichever kind it is. */
function value(event: Event): string {
  return (event.target as HTMLInputElement | HTMLSelectElement).value;
}

/** A length as typed, `null` for a field left empty — which is a car reading
 *  its model's length again rather than a number this could not parse. */
function millimetres(event: Event): number | null {
  const said = value(event).trim();
  return said === "" ? null : Number(said);
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-stock": TcStock;
  }
}
