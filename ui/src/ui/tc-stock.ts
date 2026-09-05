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
import { live } from "lit/directives/live.js";
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

  /** The train a press on the left is about, as a **name**. Composing right
   *  from left needs somewhere for the left to go, and one train is current
   *  at a time. Read through `pointed()` and never directly: a name is not a
   *  hold on the train, and the roster can stop having it (#445). */
  @state() private train: string | null = null;

  /** What was refused — by this screen before the store had to see it, or by
   *  the store — in the words of whichever refused it. */
  @state() private trouble: string | null = null;

  /** The model being written, `null` while the dialog is shut. */
  @state() private making: Draft | null = null;

  /** What the New-model dialog was refused with, in the words of whichever
   *  refused it, and `null` where nothing was. The dialog's own rather than
   *  the screen's `trouble`: the two are unrelated surfaces, so sharing one
   *  state said a refusal about the dialog under the Trains heading as well,
   *  and left it standing there once the dialog was gone (#446). */
  @state() private refusal: string | null = null;

  /** Bumped after each edit: `Stock` keeps its identity across one, so
   *  rendering is asked for rather than observed. */
  @state() private beat = 0;

  /** The field an edit was just typed into, while the render that edit asked
   *  for is outstanding, and `null` on every other render. Not `@state`: the
   *  edit bumps `beat`, so the render it names is already asked for. */
  private back: string | null = null;

  /** The read waiting to be made again, `null` while none is. */
  private waiting: ReturnType<typeof setTimeout> | null = null;

  /** Whether the roster held edits the store had not been given when this view
   *  last said so. `null` before it has said anything, so the first answer is
   *  reported whatever it is. */
  private told: boolean | null = null;

  override disconnectedCallback(): void {
    this.drop();
    super.disconnectedCallback();
  }

  override willUpdate(changed: Map<string, unknown>): void {
    if (!changed.has("railroad") && !changed.has("current")) return;
    // A try waiting is a try on the railroad that was showing, in the view
    // that was showing: neither is what to read when either changes.
    this.drop();
    // The app has loaded another railroad, so what is being composed belongs
    // to the one that was open. It goes now rather than the next time this
    // view is looked at: the app asked about it before the railroad moved
    // (#415), and edits kept past that answer would be asked about again.
    if (changed.has("railroad") && this.railroad !== this.held) this.forget();
    if (!this.current || this.railroad === null || this.railroad === this.held) return;
    void this.load(this.railroad);
  }

  /** Everything that was about the railroad that was loaded. */
  private forget(): void {
    this.stock = null;
    this.held = null;
    this.train = null;
    this.trouble = null;
  }

  /**
   * What this view holds that the store has not been given, told to the app.
   *
   * The app guards the loaded railroad and this view holds the second document
   * a person can lose with it, so what would discard the roster asks first the
   * way it does for the drawing (#101, #415). Told rather than asked, which is
   * the way the run view says what its session is doing: this view is a Lit
   * child, and the app holds nothing of its own to read.
   */
  override updated(): void {
    // The render the field was named for has happened, so the name goes: a
    // frame about the railroad draws this view again and is not news about
    // what somebody is typing (#444).
    this.back = null;
    const now = this.stock?.edits ?? false;
    if (now === this.told) return;
    this.told = now;
    this.dispatchEvent(
      new CustomEvent<boolean>("roster-edits", {
        detail: now,
        bubbles: true,
        composed: true,
      }),
    );
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
      this.train = this.first();
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
            .value=${this.putting(`car:${car.name}:name`, car.name)}
            aria-label="car name"
            @change=${(event: Event) =>
              this.did(
                this.stock?.renameCar(car.name, value(event)),
                `car:${car.name}:name`,
              )}
          />
          <span class="of">${car.model}${car.kind === null ? " — no such model" : ""}</span>
        </span>
        <input
          class="addr"
          .value=${this.putting(`car:${car.name}:addr`, car.addr ?? "")}
          placeholder="address"
          aria-label="address"
          @change=${(event: Event) =>
            this.did(
              this.stock?.carAddress(car.name, value(event)),
              `car:${car.name}:addr`,
            )}
        />
        <input
          class="length"
          .value=${this.putting(
            `car:${car.name}:length`,
            car.own ? String(car.length) : "",
          )}
          placeholder=${car.length === null ? "" : String(car.length)}
          aria-label="length"
          title=${car.held ?? "millimetres over buffers, where this item is not its model's length"}
          ?disabled=${car.held !== null}
          @change=${(event: Event) =>
            this.did(
              this.stock?.carLength(car.name, millimetres(event), this.placed),
              `car:${car.name}:length`,
            )}
        />
        <button
          class="add"
          title=${this.pointed() === null
            ? "make a train up first"
            : `add to '${this.pointed()}'`}
          ?disabled=${this.pointed() === null}
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
          .value=${this.putting(`model:${model.model}:length`, String(model.length))}
          aria-label="length"
          title=${model.held ?? "millimetres over buffers, on every item of this product"}
          ?disabled=${model.held !== null}
          @change=${(event: Event) =>
            this.did(
              this.stock?.modelLength(model.model, millimetres(event) ?? 0, this.placed),
              `model:${model.model}:length`,
            )}
        />
        <button
          class="add"
          title=${this.pointed() === null
            ? "make a train up first"
            : `add to '${this.pointed()}'`}
          ?disabled=${this.pointed() === null}
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
   *  it converts it to the ordinary shape (#414). The note names the stated
   *  number and says that filling the train in takes it: the stated length is
   *  a property of the older shape that the conversion consumes, and emptying
   *  the train again does not bring it back, so the screen owes the price
   *  before the press rather than the number afterwards (#448). */
  private trainRow(train: TrainRow) {
    return html`
      <li
        class=${`train ${this.pointed() === train.train ? "current" : ""}`}
        @click=${() => {
          this.train = train.train;
        }}
      >
        <header>
          <input
            class="name"
            .value=${this.putting(`train:${train.train}:name`, train.train)}
            aria-label="train name"
            @change=${(event: Event) => this.renamed(train.train, value(event))}
          />
          ${train.placed ? html`<span class="of">on the layout</span>` : nothing}
          <button
            class="remove"
            title="unmake this train"
            @click=${(event: Event) => this.unmade(event, train.train)}
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
                ? `states its length and names no cars — press + beside a car` +
                  ` or a model to fill it in, and the stated ${train.length} mm` +
                  ` goes`
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
          .value=${this.putting(`entry:${train}:${at}:addr`, entry.addr ?? "")}
          placeholder="address"
          aria-label="address"
          @change=${(event: Event) =>
            this.did(
              this.stock?.address(train, at, value(event)),
              `entry:${train}:${at}:addr`,
            )}
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

  /**
   * Unmake a train. All it does is unmake it: `×` sits inside the row and the
   * row's click is what makes a train current, so the press is stopped from
   * being a press on the row as well (#416).
   *
   * It moves nothing. Whatever was current, a train that is gone is not, and
   * `pointed()` is what says so — the first train left, and `null` where the
   * roster has none, which is the `+` disabled with no target as it is before
   * any train is made up. Moving `this.train` here as well would be the same
   * rule written twice, and it was written here alone that let the rename
   * road into the same defect stay open (#445).
   */
  private unmade(event: Event, train: string): void {
    event.stopPropagation();
    this.changed((stock) => stock.removeTrain(train));
  }

  /**
   * A train renamed.
   *
   * The current train is a name and `renameTrain` rebuilds `trains` under the
   * new key, so renaming the current one would leave the name naming nothing.
   * It is carried: the person renamed the train they were composing, not
   * another one, and falling back to the first train the roster has would
   * hand them a different train to compose (#445).
   *
   * A refusal changes the document not at all, so there is nothing to carry,
   * and renaming any other train says nothing about which one is current.
   */
  private renamed(was: string, name: string): void {
    if (this.stock === null) return;
    const refused = this.stock.renameTrain(was, name);
    if (refused === null && this.train === was) this.train = name;
    // The old name, because a refused rename is the row still drawn under it:
    // the field to write back is the one the edit was typed into (#444).
    this.did(refused, `train:${was}:name`);
  }

  /**
   * The train every `+` names: the one that is current.
   *
   * `this.train` where the roster has that train, and the first train it has
   * where it has not — `null` where it has none at all. The current train is
   * a name, and what a roster has is the view's to keep up with rather than
   * the name's: unmaking a train takes one away, and every read going through
   * here is what makes *the `+` buttons name one train, and it is always a
   * train there is* (ui/STOCK.md) hold for whatever else does (#416, #445).
   */
  private pointed(): string | null {
    const trains = this.stock?.roster.trains ?? {};
    return this.train !== null && this.train in trains ? this.train : this.first();
  }

  /** The train the left points at when nothing has said which: the first the
   *  roster has, and `null` where it has none. */
  private first(): string | null {
    return Object.keys(this.stock?.roster.trains ?? {}).sort()[0] ?? null;
  }

  /** A car or a model put at the tail of the current train: the whole of
   *  composing right from left. Named for what it does to the train rather
   *  than for the list press, `append` being `HTMLElement`'s. */
  private coupled(what: { car: string } | { model: string }): void {
    const train = this.pointed();
    if (train === null) return;
    this.stock?.append(train, what);
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

  /** What an edit answered: nothing, or the words to show, and the field it
   *  was typed into where it was typed into one. Either way the screen
   *  redraws — `Stock` keeps its identity across an edit, so Lit sees no
   *  changed property.
   *
   *  A redraw is not by itself the field going back. A refusal changes the
   *  document by construction not at all, so what a field is bound to is what
   *  it was last rendered with and Lit's property part skips the write: a car
   *  renamed to `a/b` was refused and went on showing `a/b`, a value the
   *  roster has not got (#416). The field is named here so that the render
   *  this edit asks for is the one that writes it back, and no other. */
  private did(refused: string | null | undefined, field: string | null = null): void {
    this.trouble = refused ?? null;
    this.back = field;
    this.beat++;
  }

  /**
   * What a document-backed field is bound to: the document's value, and on
   * the render an edit typed into *that* field asked for, the document's
   * value written over the DOM.
   *
   * `live` compares against the DOM rather than against the last binding, so
   * it writes a refused edit back where an ordinary binding skips it. Binding
   * every field with it did that on **every** render, and this view redraws
   * for reasons that have nothing to do with the field being typed in: the
   * app hands it `placed`, and every `run-status` the run view fires replaces
   * the run state whole. Power going off then wrote the document's `122` over
   * the `12` somebody was half way through typing (#444). So `live` is
   * reached for by name: the field the edit was typed into, on the render
   * that edit asked for.
   */
  private putting(field: string, held: string) {
    return this.back === field ? live(held) : held;
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
      <sl-dialog open label="New model" @sl-after-hide=${this.shut}>
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
        ${this.refusal === null ? nothing : html`<p class="trouble">${this.refusal}</p>`}
        <sl-button slot="footer" @click=${this.shut}>Cancel</sl-button>
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

  /** The dialog put away, and what it was refused with put away in the same
   *  breath: a sentence about a dialog that is gone is about nothing (#446). */
  private shut(): void {
    this.making = null;
    this.refusal = null;
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
    const refused = this.wrong(making, stock);
    if (refused !== null) {
      this.refusal = refused;
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
      this.shut();
      // The catalogue has a row it had not got, so this is an edit that cannot
      // refuse: the screen redraws and what it last said is taken down.
      this.did(null);
    } catch (trouble) {
      this.refusal = said(trouble);
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
