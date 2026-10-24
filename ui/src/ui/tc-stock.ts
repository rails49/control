/**
 * The stock view (ui/STOCK.md), as
 * [stock-mockup.html](../../../docs/ui/images/stock-mockup.html) lays it out:
 * a bar across the top with the one Save, and below it two columns — the list
 * of trains, cars or models, and the editor of the item chosen in it (#978).
 *
 * The railroad it is editing is not its own: the app holds the loaded railroad
 * and hands it down, exactly as it hands the drawing to the editor
 * ([ADR-0038](../../../docs/adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md)).
 * **No session**, like the editor: this is a document view. **It reads no
 * document either**: the roster and the catalogue are the loaded railroad's to
 * read, to read again where the store did not answer, and to drop when the row
 * names another railroad, and the one Save is its too (`model/railroad.ts`,
 * #758). What this sends itself is a model's `DELETE` and a picture asked of
 * the camera (#976, #629).
 *
 * It works nothing out. Every length, kind and function shown is
 * `model/stock.ts`'s answer, and so is every refusal and every key minted: a
 * rule lives where it can be driven from plain values (ui/README.md).
 *
 * **No press is answered with silence.** A press either does what it says or
 * says why it cannot. The presses that write are dead with `unwritable()` on
 * them until the documents are read
 * ([#565](https://github.com/rails49/control/issues/565)).
 *
 * **Composing a train and placing it are two actions**
 * ([ADR-0039](../../../docs/adr/0039-a-train-may-be-off-the-layout.md)): a
 * rake is durable and lives in the roster, and where it stands belongs to the
 * run. It is made up here and put on the layout in the run view.
 *
 * The run state comes down from the app because the app is the only thing on
 * the page that has any: the length guard reads its power and whether the
 * row naming the railroad is heard, and the trains read which are placed
 * (ui/STOCK.md#the-length-guard,
 * [ADR-0071](../../../docs/adr/0071-a-rebuild-under-the-same-name-keeps-the-placements.md)).
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { lookTheme } from "@rails49/look";
import { live } from "lit/directives/live.js";
import "@shoelace-style/shoelace/dist/components/button/button.js";

import { isPicture, NOT_A_PICTURE, toJpeg } from "../model/photo.js";
import {
  hasDecoder,
  KINDS,
  LATCHING,
  modelName,
  MOMENTARY,
  SCALES,
  Stock,
  type CarRow,
  type FnOwner,
  type ModelRow,
  type TrainRow,
} from "../model/stock.js";
import type { Railroad } from "../model/railroad.js";
import { deleteModel, photoUrl, said, takePicture } from "../model/store.js";
import type { Power } from "../model/trace.js";
import { stockStyles } from "./tc-stock.styles.js";

/** The three lists, in the order their tabs stand. */
type Tab = "trains" | "cars" | "models";

const TABS: [Tab, string][] = [
  ["trains", "Trains"],
  ["cars", "Cars"],
  ["models", "Models"],
];

/** What each list's New button says. */
const NEW: Record<Tab, string> = {
  trains: "New train",
  cars: "New car",
  models: "New model",
};

/** What each list says under its tabs. */
const LEAD: Record<Tab, string> = {
  trains: "Cars in order, head first.",
  cars: "What you own, with addresses.",
  models: "Products, shared by every railroad.",
};

/** A kind as the editor's buttons and the cards say it. */
const KIND: Record<string, string> = {
  locomotive: "Locomotive",
  passenger: "Passenger",
  freight: "Freight",
  special: "Special",
};

/** How long *Saved* stands in the bar once a Save lands, and how long what
 *  the picker did stands at the foot of the view. */
const SAVED_MS = 2500;
const TOLD_MS = 4000;

/** What a press that writes is dead with where no railroad is loaded: this
 *  view is one of the app's views of the loaded railroad (ADR-0038), so
 *  without one there is no roster and no catalogue to write into
 *  ([#565](https://github.com/rails49/control/issues/565)). */
const UNLOADED = "load a railroad first";

/** What it is dead with where a railroad is loaded and its documents have not
 *  arrived: which of the three ways the read failed is the bar's to say
 *  (#411), and a read still in flight is a moment. */
const UNREAD = "the roster and the catalogue are not read yet";

@customElement("tc-stock")
export class TcStock extends LitElement {
  static override styles = [lookTheme, stockStyles];

  /** The loaded railroad, whose roster this edits: the app's one instance,
   *  which reads the documents, holds them and saves them
   *  (`model/railroad.ts`). It holds them across a look at another view, so
   *  edits come back as they were left. `undefined` only before the app has
   *  handed it down. */
  @property({ attribute: false }) railroad: Railroad | undefined = undefined;

  /** The trains the run has on the layout, as the session says
   *  (`RunStatus.placed`). */
  @property({ attribute: false }) placed: readonly string[] = [];

  /** The run's track power, as the session says (`RunStatus.power`), `null`
   *  with no session. The length guard and the Save read it (ADR-0071). */
  @property({ attribute: false }) power: Power | null = null;

  /** The railroad the broker's row names (`RunStatus.railroad`), `null` while
   *  it has not been heard — a page that has lost the broker among them. The
   *  length guard holds lengths while it lasts (#804). */
  @property({ attribute: false }) loaded: string | null = null;

  /** The documents this view last drew, so what was about them — what is
   *  chosen, what an edit was refused with — goes when the loaded railroad
   *  holds others. */
  private held: Stock | null = null;

  /** Which list is shown: the trains, first, until a tab says another. */
  @state() private tab: Tab = "trains";

  /** Whether the editor stands in place of the list, which is what a press on
   *  a card does where the view is one column wide; the back button undoes
   *  it. Two columns wide, both stand and this changes nothing. */
  @state() private editing = false;

  /** The train chosen, which is the train the picker puts something in, as a
   *  **name**. Read through `pointed()` and never directly: a name is not a
   *  hold on the train, and the roster can stop having it (#445). */
  @state() private train: string | null = null;

  /** The car chosen, by name; the first there is where it names none. */
  @state() private car: string | null = null;

  /** The model chosen, by key; the first there is where it names none. A
   *  model made here is held under a key Save replaces, and `Stock.keyOf`
   *  finds it under the new one. */
  @state() private model: string | null = null;

  /** What an edit was refused with, by this screen before the store had to
   *  see it. What the store said about reading the documents or the last
   *  Save is the loaded railroad's `stockTrouble`, said in the same place. */
  @state() private trouble: string | null = null;

  /** Whether *Saved* is standing in the bar: for a moment after a Save
   *  lands. */
  @state() private landed = false;

  /** The model the camera is being waited on for, `null` where none is. */
  @state() private taking: string | null = null;

  /** Why the last picture for a model did not become its photo — not an
   *  image, one the browser cannot read, or the camera's answer — and the
   *  model it was for. */
  @state() private shot: { model: string; words: string } | null = null;

  /** The model whose frame a file is being dragged over. */
  @state() private hot: string | null = null;

  /** The model whose Delete is being asked about, `null` while none is. */
  @state() private asking: string | null = null;

  /** What the store refused a model's `DELETE` with, in its words, and the
   *  model it was for (#976). */
  @state() private kept: { model: string; words: string } | null = null;

  /** Whether the New car chooser on the Cars list is open. */
  @state() private choosing = false;

  /** The car whose address is being asked for, made just now of a model with
   *  a decoder, and what the answer was refused with. */
  @state() private asked: string | null = null;
  @state() private refusal: string | null = null;

  /** The car whose address field *Fitted one to this car?* has shown though
   *  its model has no decoder. */
  @state() private fitting: string | null = null;

  /** The picker, open on a train: which tab it shows, and the model whose
   *  cars *Which <model>?* lists where it is asking that. */
  @state() private picking: {
    train: string;
    tab: "cars" | "models";
    model: string | null;
  } | null = null;

  /** What the picker did that is worth a word — *Added <car>, your only
   *  <model>.* — standing at the foot of the view for a moment. */
  @state() private told: string | null = null;

  /** The place of the tile being dragged along the strip, and of the tile
   *  it is over. */
  @state() private dragged: number | null = null;
  @state() private over: number | null = null;

  /** The photo version at which each model's photo did not load, by key:
   *  the route answering anything but 200, which is the whole of how this
   *  screen learns there is none (docs/SYSTEM.md). A photo written since is
   *  a newer version and is asked for again. Not `@state`: read on the
   *  render the `error` event asks for with `beat`. */
  private absent = new Map<string, number>();

  /** Bumped after each edit: `Stock` keeps its identity across one, so
   *  rendering is asked for rather than observed. */
  @state() private beat = 0;

  /** The field an edit was just typed into, while the render that edit asked
   *  for is outstanding, and `null` on every other render (#444). */
  private back: string | null = null;

  private timer: ReturnType<typeof setTimeout> | null = null;
  private telling: ReturnType<typeof setTimeout> | null = null;

  /** The roster and the catalogue, and every edit to either
   *  (`model/stock.ts`), as the loaded railroad holds them: `null` until the
   *  store has answered for both. */
  private get stock(): Stock | null {
    return this.railroad?.stock ?? null;
  }

  /** Whether the row naming the railroad is heard, which the length guard
   *  reads beside power (#804). */
  private get heard(): boolean {
    return this.loaded !== null;
  }

  override willUpdate(): void {
    // The loaded railroad holds other documents — another railroad, or none —
    // so what was chosen and said belongs to the ones that went.
    if (this.stock === this.held) return;
    this.held = this.stock;
    this.train = null;
    this.car = null;
    this.model = null;
    this.trouble = null;
    this.shot = null;
    this.kept = null;
    this.asking = null;
    this.choosing = false;
    this.asked = null;
    this.refusal = null;
    this.fitting = null;
    this.picking = null;
    this.told = null;
  }

  override updated(): void {
    // The render the field was named for has happened, so the name goes: a
    // frame about the railroad draws this view again and is not news about
    // what somebody is typing (#444).
    this.back = null;
  }

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    if (this.timer !== null) clearTimeout(this.timer);
    if (this.telling !== null) clearTimeout(this.telling);
  }

  override render() {
    return html`
      ${this.bar()}
      <div class=${`cols ${this.editing ? "editing" : ""}`}>
        <section class="list" aria-label="Stock">${this.list()}</section>
        <section class="editor" aria-label="Editor">${this.editor()}</section>
      </div>
      ${this.deleting()} ${this.chooser()} ${this.picker()} ${this.addressing()}
      ${this.told === null ? nothing : html`<p class="toast" role="status">${this.told}</p>`}
    `;
  }

  // --- the bar --------------------------------------------------------------

  /** *Stock*, the railroad's name, what is unsaved, and the one Save. */
  private bar() {
    const stock = this.stock;
    const said = this.said();
    const waits = stock?.waitsForPower(this.power, this.heard) ?? null;
    return html`
      <header class="bar">
        <h1>Stock</h1>
        <span class="railroad">${this.railroad?.name ?? ""}</span>
        <span class=${`said ${said.tone}`}>${said.words}</span>
        <button
          class="save"
          title=${waits ?? this.unwritable() ?? nothing}
          ?disabled=${
            stock === null ||
            this.railroad?.saving === true ||
            !stock.edits ||
            waits !== null
          }
          @click=${this.save}
        >
          Save
        </button>
      </header>
    `;
  }

  /** What the bar says, and in which tone: what was refused, why nothing can
   *  be written, why Save waits, how much is unsaved — or that nothing is. */
  private said(): { words: string; tone: string } {
    const stock = this.stock;
    const trouble = this.trouble ?? this.railroad?.stockTrouble ?? null;
    if (trouble !== null) return { words: trouble, tone: "trouble" };
    if (stock === null)
      return { words: this.unwritable() ?? "", tone: "trouble" };
    const waits = stock.waitsForPower(this.power, this.heard);
    if (waits !== null) return { words: waits, tone: "waits" };
    const unsaved = stock.unsaved;
    if (unsaved > 0) {
      return {
        words: `${unsaved} unsaved ${unsaved === 1 ? "change" : "changes"}`,
        tone: "",
      };
    }
    if (this.landed) return { words: "Saved", tone: "landed" };
    return { words: "Everything is saved", tone: "" };
  }

  // --- the list -------------------------------------------------------------

  private list() {
    const stock = this.stock;
    const counts: Record<Tab, number> = {
      trains: Object.keys(stock?.roster.trains ?? {}).length,
      cars: Object.keys(stock?.roster.cars ?? {}).length,
      models: Object.keys(stock?.catalogue ?? {}).length,
    };
    return html`
      <div class="tabs" role="tablist">
        ${TABS.map(
          ([tab, label]) => html`
            <button
              class="tab"
              role="tab"
              data-tab=${tab}
              aria-selected=${this.tab === tab ? "true" : "false"}
              @click=${() => {
                this.tab = tab;
              }}
            >
              ${label}<span class="count">${counts[tab]}</span>
            </button>
          `,
        )}
      </div>
      <div class="head">
        <p>${LEAD[this.tab]}</p>
        <button
          class="new"
          title=${this.unwritable() ?? nothing}
          ?disabled=${stock === null}
          @click=${this.made}
        >
          ${NEW[this.tab]}
        </button>
      </div>
      <div class="cards">${this.cards()}</div>
    `;
  }

  private cards() {
    const stock = this.stock;
    if (this.tab === "models") {
      const models = stock?.modelRows(this.power, this.heard) ?? [];
      if (models.length === 0)
        return this.none("no models yet — a train is made of them");
      const chosen = this.chosenModel();
      return models.map((model) =>
        this.modelCard(model, model.model === chosen),
      );
    }
    if (this.tab === "cars") {
      const cars = stock?.cars(this.power, this.heard) ?? [];
      if (cars.length === 0) {
        return this.none("no cars yet — press New car on a model to make one");
      }
      const chosen = this.chosenCar();
      return cars.map((car) => this.carCard(car, car.name === chosen));
    }
    const trains = stock?.trains(this.placed) ?? [];
    if (trains.length === 0) {
      return this.none(
        "no trains yet — press New train, then Add to put cars in it",
      );
    }
    const chosen = this.pointed();
    return trains.map((train) => this.trainCard(train, train.train === chosen));
  }

  private none(words: string) {
    return html`<p class="hint">${words}</p>`;
  }

  /** One card: a photo frame 10:3 wide, the name, and a line of facts. A
   *  card that is `dead` is greyed and does nothing, its title saying why:
   *  what the picker draws a car already in the train as. */
  private card(
    which: string,
    photo: string | null,
    name: string,
    facts: unknown,
    chosen: boolean,
    press: () => void,
    dead: string | null = null,
  ) {
    return html`
      <button
        class=${`card ${which}`}
        aria-current=${chosen ? "true" : "false"}
        title=${dead ?? nothing}
        ?disabled=${dead !== null}
        @click=${press}
      >
        <span class="frame">${this.photo(photo)}</span>
        <span class="text">
          <span class="name">${name}</span>
          <span class="facts">${facts}</span>
        </span>
      </button>
    `;
  }

  /** A model's facts: kind, scale, length, and *decoder* where it has one. */
  private modelFacts(model: ModelRow) {
    return html`<span>${KIND[model.kind] ?? model.kind}</span>${
        model.scale === null ? nothing : html`<span>${model.scale}</span>`
      }<span>${model.length} mm</span>${
        model.decoder ? html`<span class="pill">decoder</span>` : nothing
      }`;
  }

  private modelCard(model: ModelRow, chosen: boolean) {
    return this.card(
      "model",
      model.model,
      model.name,
      this.modelFacts(model),
      chosen,
      () => this.chose("models", model.model),
    );
  }

  /** A car's facts: its model's name, its address, *camera*. Its photo is its
   *  model's: ten identical hoppers have one picture between them
   *  (ADR-0061). */
  private carCard(car: CarRow, chosen: boolean) {
    return this.card(
      "car",
      car.kind === null ? null : car.model,
      car.name,
      this.carFacts(car),
      chosen,
      () => this.chose("cars", car.name),
    );
  }

  private carFacts(car: CarRow) {
    return html`<span
        >${car.modelName}${car.kind === null ? " — no such model" : ""}</span
      >${
        car.addr === null
          ? nothing
          : html`<span class="pill">${car.addr}</span>`
      }${
        car.camera === null ? nothing : html`<span class="pill">camera</span>`
      }`;
  }

  /** A train's facts: how many cars, its length, its kind, its priority. Its
   *  photo is its first locomotive's. */
  private trainCard(train: TrainRow, chosen: boolean) {
    const count = train.entries.length;
    return this.card(
      "train",
      train.locomotive,
      train.train,
      html`<span>${count} ${count === 1 ? "car" : "cars"}</span
        ><span>${train.length === null ? "—" : `${train.length} mm`}</span
        ><span>${train.kind ?? "—"}</span>${
          train.priority === null
            ? nothing
            : html`<span class="pill">P${train.priority}</span>`
        }${train.placed ? html`<span>on the layout</span>` : nothing}`,
      chosen,
      () => this.chose("trains", train.train),
    );
  }

  /** A card pressed: its item chosen, and the editor shown in place of the
   *  list where there is room for only one. */
  private chose(tab: Tab, key: string): void {
    if (tab === "trains") this.train = key;
    if (tab === "cars") this.car = key;
    if (tab === "models") this.model = key;
    this.editing = true;
  }

  /**
   * A model's photo, shown whole: the picture chosen and not yet saved, the
   * one the store has, or *No photo*. Nothing on a model's document says
   * whether there is one, so an `<img>` on the route that did not load is the
   * whole of how this screen learns there is none (#630). A model made here
   * has none the store could have.
   */
  private photo(model: string | null) {
    const stock = this.stock;
    if (model === null || stock === null) return this.noPhoto();
    const pending = stock.photo(model);
    if (pending !== null) return html`<img src=${pending.shown} alt="" />`;
    const key = stock.keyOf(model);
    const version = stock.photoVersion(key);
    if (stock.isFresh(key) || this.absent.get(key) === version)
      return this.noPhoto();
    return html`<img
      src=${photoUrl(key, version)}
      alt=""
      @error=${() => this.missing(key, version)}
    />`;
  }

  private noPhoto() {
    return html`<span class="no-photo">No photo</span>`;
  }

  private missing(model: string, version: number): void {
    if (this.absent.get(model) === version) return;
    this.absent.set(model, version);
    this.beat++;
  }

  /** Whether a model has a photo to show, the store's or one waiting. */
  private hasPhoto(model: string): boolean {
    const stock = this.stock;
    if (stock === null) return false;
    if (stock.photo(model) !== null) return true;
    const key = stock.keyOf(model);
    return (
      !stock.isFresh(key) && this.absent.get(key) !== stock.photoVersion(key)
    );
  }

  // --- the editor -----------------------------------------------------------

  private editor() {
    const stock = this.stock;
    if (this.tab === "models") {
      const model = this.chosenModel();
      return model === null || stock === null
        ? this.nothingHere()
        : this.modelEditor(model);
    }
    if (this.tab === "cars") {
      const name = this.chosenCar();
      const car = stock
        ?.cars(this.power, this.heard)
        .find((one) => one.name === name);
      return car === undefined ? this.nothingHere() : this.carEditor(car);
    }
    const name = this.pointed();
    const train = stock?.trains(this.placed).find((one) => one.train === name);
    return train === undefined ? this.nothingHere() : this.trainEditor(train);
  }

  private nothingHere() {
    return html`<div class="empty">
      Nothing here yet. Press ${NEW[this.tab]}.
    </div>`;
  }

  /** The editor's head: the back button where the list is not beside it,
   *  what kind of item it edits, and its own press at the right. The name is
   *  in the Name field below and nowhere else. */
  private head(eyebrow: string, press: unknown = nothing) {
    return html`
      <header class="ed-head">
        <button
          class="back"
          aria-label="Back to the list"
          @click=${() => {
            this.editing = false;
          }}
        >
          ‹
        </button>
        <div class="title">
          <p class="eyebrow">${eyebrow}</p>
        </div>
        ${press}
      </header>
    `;
  }

  /** The model chosen, by its key now, or the first model there is. */
  private chosenModel(): string | null {
    const stock = this.stock;
    if (stock === null) return null;
    if (this.model !== null && stock.model(this.model) !== null)
      return stock.keyOf(this.model);
    return stock.modelRows()[0]?.model ?? null;
  }

  private chosenCar(): string | null {
    const cars = this.stock?.roster.cars ?? {};
    if (this.car !== null && this.car in cars) return this.car;
    return this.stock?.cars()[0]?.name ?? null;
  }

  /**
   * The model editor, from the top as the mockup draws it: the photo, name,
   * kind, scale, length, notes, the decoder and its functions, and what uses
   * the model with the Delete beside it. Every edit is the document's to
   * hold and Save's to write; only Delete goes to the store at once.
   */
  private modelEditor(key: string) {
    const stock = this.stock!;
    const model = stock.model(key)!;
    const row = stock
      .modelRows(this.power, this.heard)
      .find((one) => one.model === key)!;
    return html`
      ${this.head(
        "Model",
        html`<button class="new-car" @click=${() => this.carOf(key)}>
          New car
        </button>`,
      )}
      <div class="body model-editor">
        ${this.photoFrame(key)}
        <div class="grid">
          <label class="field wide">
            <span class="label">Name</span>
            <input
              class="name"
              .value=${this.putting(`model:${key}:name`, row.name)}
              placeholder="Ae 6/6"
              @change=${(event: Event) =>
                this.did(
                  stock.renameModel(key, value(event)),
                  `model:${key}:name`,
                )}
            />
          </label>
          <div class="field wide">
            <span class="label">Kind</span>
            <div class="seg kind" role="group" aria-label="Kind">
              ${KINDS.map(
                (kind) => html`
                  <button
                    data-kind=${kind}
                    aria-pressed=${model.kind === kind ? "true" : "false"}
                    @click=${() => this.changed((one) => one.modelKind(key, kind))}
                  >
                    ${KIND[kind]}
                  </button>
                `,
              )}
            </div>
          </div>
          <label class="field">
            <span class="label">Scale</span>
            <select
              class="scale"
              @change=${(event: Event) =>
                this.changed((one) => one.modelScale(key, value(event)))}
            >
              ${
                model.scale === undefined
                  ? html`<option value="" selected>—</option>`
                  : nothing
              }
              ${SCALES.map(
                (scale) =>
                  html`<option
                    value=${scale}
                    ?selected=${model.scale === scale}
                  >
                    ${scale}
                  </option>`,
              )}
            </select>
          </label>
          <label class="field">
            <span class="label">Length over buffers, mm</span>
            <input
              class="length"
              inputmode="numeric"
              .value=${this.putting(`model:${key}:length`, String(row.length))}
              title=${row.held ?? "millimetres over buffers, on every item of this product"}
              ?disabled=${row.held !== null}
              @change=${(event: Event) =>
                this.did(
                  stock.modelLength(
                    key,
                    millimetres(event) ?? 0,
                    this.power,
                    this.heard,
                  ),
                  `model:${key}:length`,
                )}
            />
            ${row.held === null ? nothing : html`<span class="why">${row.held}</span>`}
          </label>
        </div>
        <label class="field">
          <span class="label">Notes</span>
          <textarea
            class="notes"
            rows="4"
            placeholder="Manufacturer, catalogue number, colour, when you bought it…"
            .value=${this.putting(`model:${key}:notes`, model.notes ?? "")}
            @change=${(event: Event) =>
              this.changed(
                (one) => one.modelNotes(key, value(event)),
                `model:${key}:notes`,
              )}
          ></textarea>
        </label>
        ${this.decoder(key, row.decoder)} ${this.usedBy(key, row)}
      </div>
    `;
  }

  /**
   * The photo frame and its two presses. A file dropped on the frame at any
   * time, or chosen, is the model's photo from then on; the camera's picture
   * is too, its bytes kept as they are. Either is written by Save, after the
   * model's document (#630).
   */
  private photoFrame(key: string) {
    const has = this.hasPhoto(key);
    const taking = this.taking === key;
    return html`
      <div
        class=${`photo-frame ${has ? "" : "empty"} ${this.hot === key ? "hot" : ""}`}
        @dragover=${(event: DragEvent) => {
          event.preventDefault();
          this.hot = key;
        }}
        @dragleave=${() => {
          this.hot = null;
        }}
        @drop=${(event: DragEvent) => {
          event.preventDefault();
          this.hot = null;
          const file = event.dataTransfer?.files[0];
          if (file !== undefined) void this.picked(key, file);
        }}
      >
        ${
          has
            ? this.photo(key)
            : html`<div class="drop">
                <b>Drop a picture here</b>
                <span>or choose a file, or take one with the photo camera</span>
              </div>`
        }
        ${taking ? html`<span class="wait">Taking a picture…</span>` : nothing}
      </div>
      <div class="photo-tools">
        <label class="choose">
          Choose file…
          <input
            class="file"
            type="file"
            accept="image/*"
            @change=${(event: Event) => {
              const input = event.target as HTMLInputElement;
              const file = input.files?.[0];
              if (file !== undefined) void this.picked(key, file);
            }}
          />
        </label>
        <button
          class="take"
          ?disabled=${taking}
          @click=${() => void this.takes(key)}
        >
          ${has ? "Retake photo" : "Take photo"}
        </button>
      </div>
      ${
        this.shot?.model === key
          ? html`<p class="trouble photo-trouble">${this.shot.words}</p>`
          : nothing
      }
    `;
  }

  /** A file dropped or chosen: refused where it is not an image, and
   *  otherwise decoded and written again as the JPEG the store keeps
   *  (`model/photo.ts`), refused where the browser cannot read it. */
  private async picked(key: string, file: File): Promise<void> {
    const stock = this.stock;
    if (stock === null) return;
    if (!isPicture(file)) {
      this.shot = { model: key, words: NOT_A_PICTURE };
      return;
    }
    try {
      const picture = await toJpeg(file);
      if (this.stock !== stock) return;
      stock.setPhoto(key, picture);
      this.shot = null;
      this.did(null);
    } catch (trouble) {
      if (this.stock === stock)
        this.shot = { model: key, words: said(trouble) };
    }
  }

  /**
   * A picture from the photo camera, now: `GET /camera/snapshot`, its bytes
   * kept as they are. While it is waited on the frame says so and the press
   * is dead. Any answer but 200 is no picture, said under the frame, and the
   * press is live again — a camera plugged in a minute later is a picture a
   * minute later (#629).
   */
  private takes = async (key: string): Promise<void> => {
    const stock = this.stock;
    if (stock === null || this.taking !== null) return;
    this.taking = key;
    this.shot = null;
    try {
      const picture = await takePicture();
      if (this.stock === stock) {
        stock.setPhoto(key, picture);
        this.did(null);
      }
    } catch (trouble) {
      if (this.stock === stock)
        this.shot = { model: key, words: `no picture: ${said(trouble)}` };
    } finally {
      this.taking = null;
    }
  };

  /** The decoder switch, and the function rows while it is on. */
  private decoder(key: string, on: boolean) {
    return html`
      <section class="sec decoder">
        <div class="sec-head">
          <div>
            <h3>Decoder</h3>
            <p class="hint">
              ${
                on
                  ? "Each car of this model gets its own address."
                  : "This product has no decoder."
              }
            </p>
          </div>
          <button
            class="switch"
            role="switch"
            aria-checked=${on ? "true" : "false"}
            aria-label="Has a decoder"
            @click=${() => this.changed((one) => one.modelDecoder(key, !on))}
          >
            <i></i>
          </button>
        </div>
        ${on ? this.functions(key) : nothing}
      </section>
    `;
  }

  /** One row per function: its number, its name, Toggle or Hold, and a
   *  remove. A number listed twice is said under the rows while it stands.
   *  A model's, or a car's own, which are edited the same way. */
  private functions(key: FnOwner) {
    const stock = this.stock!;
    const id = typeof key === "string" ? key : `car:${key.car}`;
    const rows = stock.functionRows(key);
    const twice = stock.listedTwice(key);
    return html`
      <ul class="functions">
        ${rows.map(
          (row, at) => html`
            <li class="function">
              <span class="number">
                <i>F</i>
                <input
                  class="number"
                  inputmode="numeric"
                  aria-label="function number"
                  .value=${this.putting(`fn:${id}:${at}:number`, row.number)}
                  @change=${(event: Event) =>
                    this.did(
                      stock.functionNumber(key, at, value(event)),
                      `fn:${id}:${at}:number`,
                    )}
                />
              </span>
              <input
                class="fn-name"
                aria-label="function name"
                placeholder="Horn, Headlights…"
                .value=${this.putting(`fn:${id}:${at}:name`, row.name)}
                @change=${(event: Event) =>
                  this.changed(
                    (one) => one.functionName(key, at, value(event)),
                    `fn:${id}:${at}:name`,
                  )}
              />
              <div class="seg mode" role="group" aria-label="Toggle or hold">
                ${[LATCHING, MOMENTARY].map(
                  (mode) => html`
                    <button
                      data-mode=${mode}
                      aria-pressed=${row.mode === mode ? "true" : "false"}
                      @click=${() => this.changed((one) => one.functionMode(key, at, mode))}
                    >
                      ${mode === LATCHING ? "Toggle" : "Hold"}
                    </button>
                  `,
                )}
              </div>
              <button
                class="remove"
                aria-label=${`Remove F${row.number}`}
                @click=${() => this.changed((one) => one.removeFunction(key, at))}
              >
                ×
              </button>
            </li>
          `,
        )}
      </ul>
      ${twice === null ? nothing : html`<p class="trouble twice">${twice}</p>`}
      <div class="row-end">
        <button
          class="add-function"
          @click=${() => this.changed((one) => one.addFunction(key))}
        >
          Add a function
        </button>
        <span class="hint">
          Toggle: one press on, the next off, like lights. Hold: on only while
          the button is held down, like a horn.
        </span>
      </div>
    `;
  }

  /** What uses the model on the loaded railroad — its cars, then its trains
   *  with entries naming it — and Delete, dead while anything does. The
   *  store's refusal, for a railroad that is not loaded, is said under it in
   *  the store's words (#976). */
  private usedBy(key: string, row: ModelRow) {
    const used = row.holders.length > 0;
    return html`
      <section class="sec used">
        <h3>Used by</h3>
        ${
          used
            ? html`<ul class="uses">
                ${row.holders.map((holder) => html`<li>${holder}</li>`)}
              </ul>`
            : html`<p class="hint">Nothing uses this model.</p>`
        }
        <div class="row-end">
          <button
            class="delete"
            ?disabled=${used}
            @click=${() => {
              this.asking = key;
              this.kept = null;
            }}
          >
            Delete model
          </button>
          <span class="hint">
            ${
              used
                ? "A model in use cannot be deleted. Take it out of everything above first."
                : "Its photo goes with it."
            }
          </span>
        </div>
        ${
          this.kept?.model === key
            ? html`<p class="trouble delete-trouble">${this.kept.words}</p>`
            : nothing
        }
      </section>
    `;
  }

  /** The question Delete asks before it sends anything. */
  private deleting() {
    const stock = this.stock;
    const key = this.asking;
    if (key === null || stock === null) return nothing;
    const row = stock.modelRows().find((one) => one.model === stock.keyOf(key));
    if (row === undefined) return nothing;
    return html`
      <look-dialog
        open
        class="delete"
        label=${`Delete ${row.name}?`}
        @sl-after-hide=${() => {
          this.asking = null;
        }}
      >
        <p>Its photo goes with it. A backup can bring it back.</p>
        <sl-button
          slot="footer"
          class="cancel"
          @click=${() => (this.asking = null)}
        >
          Cancel
        </sl-button>
        <sl-button
          slot="footer"
          variant="danger"
          class="confirm"
          @click=${() => void this.deletes(key)}
        >
          Delete
        </sl-button>
      </look-dialog>
    `;
  }

  /**
   * The model deleted at once: `DELETE /catalogue/<model>`, its photo going
   * with it (#976). A model made here and never written is the store's
   * business not at all, and goes from this page alone. A refusal — another
   * railroad's roster uses it — is said under the button in the store's
   * words, and the model stays.
   */
  private deletes = async (key: string): Promise<void> => {
    const stock = this.stock;
    this.asking = null;
    if (stock === null) return;
    const at = stock.keyOf(key);
    if (!stock.isFresh(at)) {
      try {
        await deleteModel(at);
      } catch (trouble) {
        if (this.stock === stock)
          this.kept = { model: at, words: said(trouble) };
        return;
      }
    }
    if (this.stock !== stock) return;
    stock.dropModel(at);
    if (this.model !== null && stock.keyOf(this.model) === at)
      this.model = null;
    this.did(null);
  };

  /** A car of this model, chosen in the Cars list, and asked for its
   *  address at once where the model has a decoder. */
  private carOf(key: string): void {
    const stock = this.stock;
    const name = stock?.newCar(key) ?? null;
    if (stock === null || name === null) return;
    this.choosing = false;
    this.tab = "cars";
    this.car = name;
    this.editing = true;
    this.refusal = null;
    this.asked = stock.cars().find((one) => one.name === name)?.decoder
      ? name
      : null;
    this.did(null);
  }

  /** The New car chooser on the Cars list: which model the car is one of. */
  private chooser() {
    const stock = this.stock;
    if (!this.choosing || stock === null) return nothing;
    const models = stock.modelRows(this.power, this.heard);
    return html`
      <look-dialog
        open
        class="which-model"
        label="New car of which model?"
        @sl-after-hide=${() => {
          this.choosing = false;
        }}
      >
        <div class="cards">
          ${
            models.length === 0
              ? this.none("no models yet — make one in the Models list first")
              : models.map((model) =>
                  this.card(
                    "model",
                    model.model,
                    model.name,
                    this.modelFacts(model),
                    false,
                    () => this.carOf(model.model),
                  ),
                )
          }
        </div>
      </look-dialog>
    `;
  }

  // --- the car's editor -----------------------------------------------------

  /**
   * The car editor, from the top as the mockup draws it: its model's photo,
   * its name, its model, its address and camera, what is different from the
   * model — length, functions, notes — and the trains holding it, with Remove
   * at the top right, dead while a train does. Every edit is the roster's to
   * hold and Save's to write.
   */
  private carEditor(car: CarRow) {
    const name = car.name;
    const inTrain = car.trains[0];
    return html`
      ${this.head(
        "Car",
        html`<button
          class="remove-car"
          title=${
            inTrain === undefined
              ? "Take this car off the roster"
              : `In train ${inTrain}. Take it out of the train first.`
          }
          ?disabled=${inTrain !== undefined}
          @click=${() => this.did(this.stock?.removeCar(name))}
        >
          Remove
        </button>`,
      )}
      <div class="body car-editor">
        <div class="photo-frame">
          ${this.photo(car.kind === null ? null : car.model)}
          <span class="chip">Photo of the model</span>
        </div>
        <div class="grid">
          <label class="field wide">
            <span class="label">Name</span>
            <input
              class="name"
              .value=${this.putting(`car:${name}:name`, name)}
              @change=${(event: Event) => this.renamedCar(name, value(event))}
            />
          </label>
          <div class="field">
            <span class="label">Model</span>
            <button
              class="open-model"
              @click=${() => this.opened("models", car.model)}
            >
              ${car.modelName}${car.kind === null ? " — no such model" : ""}
            </button>
          </div>
          ${this.address(car)}
          <label class="field wide">
            <span class="label">Camera address</span>
            <input
              class="camera"
              .value=${this.putting(`car:${name}:camera`, car.camera ?? "")}
              placeholder="cam-1.local or 192.168.1.40"
              @change=${(event: Event) =>
                this.did(
                  this.stock?.carCamera(name, value(event)),
                  `car:${name}:camera`,
                )}
            />
            <span class="hint">
              Host name or IP address of the camera riding in this car. Empty if
              it carries none.
            </span>
          </label>
        </div>
        <section class="sec different">
          <div>
            <h3>Different from the model</h3>
            <p class="hint">
              Leave a field empty and the car takes the model's.
            </p>
          </div>
          <label class="field">
            <span class="label">Length over buffers, mm</span>
            <input
              class="length"
              inputmode="numeric"
              .value=${this.putting(`car:${name}:length`, car.own ? String(car.length) : "")}
              placeholder=${car.modelLength === null ? "" : String(car.modelLength)}
              title=${car.held ?? "millimetres over buffers, where this car is not its model's length"}
              ?disabled=${car.held !== null}
              @change=${(event: Event) =>
                this.did(
                  this.stock?.carLength(
                    name,
                    millimetres(event),
                    this.power,
                    this.heard,
                  ),
                  `car:${name}:length`,
                )}
            />
            ${
              car.held === null
                ? html`<span class="hint">
                    ${
                      car.modelLength === null
                        ? ""
                        : car.own
                          ? `The model says ${car.modelLength} mm.`
                          : `The model's ${car.modelLength} mm.`
                    }
                  </span>`
                : html`<span class="why">${car.held}</span>`
            }
          </label>
          ${car.decoder || car.addr !== null ? this.carFunctions(car) : nothing}
          <div class="field">
            <span class="label">Notes</span>
            ${
              car.modelNotes === null
                ? nothing
                : html`<p class="quote model-notes">${car.modelNotes}</p>`
            }
            <textarea
              class="notes"
              rows="3"
              placeholder="What is particular to this car…"
              .value=${this.putting(`car:${name}:notes`, car.notes ?? "")}
              @change=${(event: Event) =>
                this.changed(
                  (one) => one.carNotes(name, value(event)),
                  `car:${name}:notes`,
                )}
            ></textarea>
          </div>
        </section>
        <section class="sec in-trains">
          <h3>In trains</h3>
          ${
            car.trains.length === 0
              ? html`<p class="hint">In no train yet.</p>`
              : html`<ul class="uses">
                  ${car.trains.map(
                    (train) =>
                      html`<li>
                        <button
                          class="link train"
                          @click=${() => this.opened("trains", train)}
                        >
                          ${train}
                        </button>
                      </li>`,
                  )}
                </ul>`
          }
        </section>
      </div>
    `;
  }

  /** The DCC address, where the model has a decoder, the car has an address
   *  or the person has said one was fitted; otherwise that the model has none
   *  and the link that shows the field. Committed when the field is left. */
  private address(car: CarRow) {
    const name = car.name;
    if (!car.decoder && car.addr === null && this.fitting !== name) {
      return html`
        <div class="field">
          <span class="label">DCC address</span>
          <p class="hint">${car.modelName} has no decoder.</p>
          <button class="link fitted" @click=${() => void this.fitted(name)}>
            Fitted one to this car? Give it an address
          </button>
        </div>
      `;
    }
    return html`
      <label class="field">
        <span class="label">DCC address</span>
        <input
          class="addr"
          inputmode="numeric"
          .value=${this.putting(`car:${name}:addr`, car.addr ?? "")}
          placeholder="the number in its decoder"
          @change=${(event: Event) =>
            this.did(
              this.stock?.carAddress(name, value(event)),
              `car:${name}:addr`,
            )}
        />
        <span class="hint">
          ${
            car.decoder
              ? "The number programmed into this car's decoder. No two cars share one."
              : `${car.modelName} has no decoder; this car has one fitted.`
          }
        </span>
      </label>
    `;
  }

  /** *Fitted one to this car?*: the address field shown, and focused. */
  private async fitted(name: string): Promise<void> {
    this.fitting = name;
    await this.updateComplete;
    this.renderRoot
      .querySelector<HTMLInputElement>(".car-editor input.addr")
      ?.focus();
  }

  /** The model's functions as chips, and the press that gives the car its
   *  own; or the car's own as function rows, and the press that takes them
   *  off. */
  private carFunctions(car: CarRow) {
    const stock = this.stock!;
    const name = car.name;
    if (car.ownFunctions) {
      return html`
        <div class="field own-functions">
          <span class="label">Functions, this car's own</span>
          ${this.functions({ car: name })}
          <button
            class="link model-functions"
            @click=${() => this.changed((one) => one.modelFunctions(name))}
          >
            Use the model's functions again
          </button>
        </div>
      `;
    }
    const rows =
      stock.model(car.model) === null ? [] : stock.functionRows(car.model);
    return html`
      <div class="field">
        <span class="label">Functions, from the model</span>
        <div class="chips">
          ${
            rows.length === 0
              ? html`<span class="hint">None</span>`
              : rows.map(
                  (row) =>
                    html`<span
                      class=${`fchip ${row.mode === MOMENTARY ? "hold" : ""}`}
                      ><code>F${row.number}</code>${row.name}${
                        row.mode === MOMENTARY ? html`<em>hold</em>` : nothing
                      }</span
                    >`,
                )
          }
        </div>
        <button
          class="link own-functions"
          @click=${() => this.changed((one) => one.ownFunctions(name))}
        >
          This car's decoder is different: give it its own functions
        </button>
      </div>
    `;
  }

  /**
   * The question a new car of a decoder model asks at once: the address
   * programmed into its decoder, refused as the field refuses it. *Later*
   * leaves the car with none.
   */
  private addressing() {
    const stock = this.stock;
    const name = this.asked;
    const car =
      name === null
        ? undefined
        : stock?.cars().find((one) => one.name === name);
    if (stock === null || name === null || car === undefined) return nothing;
    return html`
      <look-dialog
        open
        class="address"
        label=${`Address for ${name}`}
        @sl-after-hide=${() => {
          this.asked = null;
          this.refusal = null;
        }}
      >
        <p>
          ${car.modelName} has a decoder. Type the address programmed into this
          car's decoder.
        </p>
        <input class="ask-addr" inputmode="numeric" placeholder="e.g. 460" />
        ${this.refusal === null ? nothing : html`<p class="trouble">${this.refusal}</p>`}
        <sl-button
          slot="footer"
          class="later"
          @click=${() => {
            this.asked = null;
            this.refusal = null;
          }}
        >
          Later
        </sl-button>
        <sl-button
          slot="footer"
          variant="primary"
          class="set"
          @click=${() => this.setAddress(name)}
        >
          Set address
        </sl-button>
      </look-dialog>
    `;
  }

  /** *Set address*: the one typed, or nothing where none was, and the
   *  question gone; a refusal stays in the question. */
  private setAddress(name: string): void {
    const field = this.renderRoot.querySelector<HTMLInputElement>(
      "look-dialog.address input",
    );
    const typed = field?.value.trim() ?? "";
    const refused =
      typed === "" ? null : (this.stock?.carAddress(name, typed) ?? null);
    if (refused !== null) {
      this.refusal = refused;
      return;
    }
    this.asked = null;
    this.refusal = null;
    this.did(null);
  }

  /** A car renamed, carrying the choice and what was asked about it. */
  private renamedCar(was: string, name: string): void {
    const refused = this.stock?.renameCar(was, name) ?? null;
    if (refused === null && this.car === was) this.car = name;
    if (refused === null && this.fitting === was) this.fitting = name;
    this.did(refused, `car:${was}:name`);
  }

  /** A model or a train the car editor links to, opened in its own list. */
  private opened(tab: Tab, key: string): void {
    this.tab = tab;
    this.chose(tab, key);
  }

  // --- the train's editor --------------------------------------------------

  /**
   * The train editor, from the top as the mockup draws it (#980): the first
   * locomotive's photo, the name, the priority, the cars as a strip of
   * tiles head first with Add at its end, and what follows from them, with
   * Unmake at the top right. Every edit is the roster's to hold and Save's to
   * write. Placing the train is the run view's (ADR-0039).
   */
  private trainEditor(train: TrainRow) {
    const name = train.train;
    const pictured =
      train.locomotive !== null && this.hasPhoto(train.locomotive);
    return html`
      ${this.head(
        "Train",
        html`${train.placed ? html`<span class="pill placed">on the layout</span>` : nothing}
          <button
            class="unmake"
            title="The cars stay on the roster."
            @click=${() => this.changed((one) => one.removeTrain(name))}
          >
            Unmake
          </button>`,
      )}
      <div class="body train-editor">
        <div class="photo-frame">
          ${pictured ? this.photo(train.locomotive) : this.noPhoto()}
          <span class="chip">
            ${pictured ? "Photo of the first locomotive" : "No locomotive with a photo"}
          </span>
        </div>
        <div class="grid">
          <label class="field">
            <span class="label">Name</span>
            <input
              class="name"
              .value=${this.putting(`train:${name}:name`, name)}
              @change=${(event: Event) => this.renamed(name, value(event))}
            />
          </label>
          <label class="field">
            <span class="label">Priority</span>
            <input
              class="priority"
              inputmode="numeric"
              placeholder="lowest"
              .value=${this.putting(`train:${name}:priority`, String(train.priority ?? ""))}
              @change=${(event: Event) =>
                this.did(
                  this.stock?.trainPriority(name, value(event)),
                  `train:${name}:priority`,
                )}
            />
            <span class="hint">1 is highest. Empty is lowest.</span>
          </label>
        </div>
        <section class="sec cars">
          <div class="sec-head">
            <h3>Cars</h3>
            <span class="hint">Drag to reorder.</span>
          </div>
          ${
            train.stated
              ? html`<p class="hint stated">
                  states its length and names no cars — press Add to fill it in,
                  and the stated ${train.length} mm goes
                </p>`
              : nothing
          }
          <div class="ends"><span>← Head</span><span>Tail</span></div>
          <div class="strip">
            ${train.entries.map((entry, at) => this.tile(name, entry, at))}
            <button
              class="add-tile"
              @click=${() => {
                this.picking = { train: name, tab: "cars", model: null };
              }}
            >
              <span aria-hidden="true">+</span>Add
            </button>
          </div>
        </section>
        <section class="sec follows">
          <h3>What follows from the cars</h3>
          <dl class="derived">
            <dt>Length</dt>
            <dd class="length">
              ${train.length === null ? "—" : `${train.length} mm`}
            </dd>
            <dt>Kind</dt>
            <dd class="kind">${train.kind ?? "—"}</dd>
            <dt>Functions</dt>
            <dd class="functions">
              ${
                train.functions.length === 0
                  ? html`<span class="hint">None</span>`
                  : html`<span class="chips">
                      ${train.functions.map(
                        (fn) =>
                          html`<span
                            class=${`fchip ${fn.mode === MOMENTARY ? "hold" : ""}`}
                            >${fn.name}${
                              fn.mode === MOMENTARY
                                ? html`<em>hold</em>`
                                : nothing
                            }</span
                          >`,
                      )}
                    </span>`
              }
            </dd>
          </dl>
        </section>
      </div>
    `;
  }

  /**
   * One entry as a tile: its model's photo, mirrored where the entry is
   * reversed; the car's name or the model's; its address, *no address* or
   * *by model*, *camera*, and its length; Forward / Reversed and the ×, and
   * *Give it an address* on a model entry of a model with a decoder, which
   * cannot be driven without one (#993). Dragged along the strip with HTML drag and drop, which iPadOS has.
   */
  private tile(train: string, entry: TrainRow["entries"][number], at: number) {
    const facts = [
      entry.car === null
        ? "by model"
        : entry.addr === null
          ? "no address"
          : `address ${entry.addr}`,
      ...(entry.camera === null ? [] : ["camera"]),
      entry.length === null ? "—" : `${entry.length} mm`,
    ].join(" · ");
    const classes = [
      "tile",
      entry.reverse ? "rev" : "",
      this.dragged === at ? "dragging" : "",
      this.over === at && this.dragged !== at ? "over" : "",
    ].join(" ");
    const model =
      entry.car === null && entry.model !== null
        ? this.stock?.model(entry.model)
        : null;
    const addressable =
      model !== null && model !== undefined && hasDecoder(model);
    return html`
      <div
        class=${classes}
        draggable="true"
        data-at=${at}
        @dragstart=${(event: DragEvent) => {
          this.dragged = at;
          // A drag dispatched as a plain event carries no data transfer.
          if (event.dataTransfer) {
            event.dataTransfer.effectAllowed = "move";
            event.dataTransfer.setData("text/plain", String(at));
          }
        }}
        @dragover=${(event: DragEvent) => {
          if (this.dragged === null) return;
          event.preventDefault();
          this.over = at;
        }}
        @drop=${(event: DragEvent) => {
          event.preventDefault();
          const from = this.dragged;
          this.dragged = null;
          this.over = null;
          if (from !== null && from !== at) {
            this.changed((one) => one.moveEntry(train, from, at));
          }
        }}
        @dragend=${() => {
          this.dragged = null;
          this.over = null;
        }}
      >
        <span class="tph"
          >${entry.model === null ? this.noPhoto() : this.photo(entry.model)}</span
        >
        <span class="tb">
          <span class="tn">${entry.name}</span>
          <span class="tm">${facts}</span>
        </span>
        <span class="ta">
          <button
            class="flip"
            aria-pressed=${entry.reverse ? "true" : "false"}
            @click=${() => this.changed((one) => one.turn(train, at))}
          >
            ${entry.reverse ? "Reversed" : "Forward"}
          </button>
          ${
            addressable
              ? html`<button
                  class="address"
                  @click=${() => this.addressed(train, at)}
                >
                  Give it an address
                </button>`
              : nothing
          }
          <button
            class="out"
            aria-label=${`Take ${entry.name} out`}
            @click=${() => this.changed((one) => one.removeEntry(train, at))}
          >
            ×
          </button>
        </span>
      </div>
    `;
  }

  /** *Give it an address* on a tile: a car of the entry's model in its
   *  place, asked for its address at once as New car asks it. */
  private addressed(train: string, at: number): void {
    const car = this.stock?.carFor(train, at) ?? null;
    if (car === null) return;
    this.asked = car;
    this.refusal = null;
    this.did(null);
  }

  /**
   * *Add to <train>*, with a Cars tab and a Models tab, or *Which <model>?*
   * where a model with a decoder has several cars. A car already in the
   * train is greyed: one item cannot stand in a train twice.
   */
  private picker() {
    const stock = this.stock;
    const picking = this.picking;
    if (
      stock === null ||
      picking === null ||
      stock.roster.trains[picking.train] === undefined
    ) {
      return nothing;
    }
    const train = picking.train;
    const held = new Set(
      (stock.roster.trains[train]!.cars ?? []).flatMap((entry) =>
        entry.car === undefined ? [] : [entry.car],
      ),
    );
    const cars = stock.cars(this.power, this.heard);
    const car = (one: CarRow) =>
      this.card(
        "car",
        one.kind === null ? null : one.model,
        one.name,
        this.carFacts(one),
        false,
        () => this.pickedCar(one.name),
        held.has(one.name) ? `${one.name} is already in ${train}.` : null,
      );
    const which = picking.model === null ? null : stock.model(picking.model);
    if (which !== null && picking.model !== null) {
      const named = new Set(
        stock.carsOf(train, picking.model).map((one) => one.car),
      );
      return html`
        <look-dialog
          open
          class="picker which"
          label=${`Which ${modelName(which)}?`}
          @sl-after-hide=${() => this.closePicker()}
        >
          <p class="hint">
            You own more than one. A car already in this train is greyed.
          </p>
          <div class="cards offered">
            ${cars.filter((one) => named.has(one.name)).map(car)}
          </div>
        </look-dialog>
      `;
    }
    const models = stock.modelRows(this.power, this.heard);
    return html`
      <look-dialog
        open
        class="picker"
        label=${`Add to ${train}`}
        @sl-after-hide=${() => this.closePicker()}
      >
        <div class="tabs two" role="tablist">
          ${(
            [
              ["cars", "Cars"],
              ["models", "Models"],
            ] as const
          ).map(
            ([tab, label]) => html`
              <button
                class="tab"
                role="tab"
                data-tab=${tab}
                aria-selected=${picking.tab === tab ? "true" : "false"}
                @click=${() => {
                  this.picking = { ...picking, tab };
                }}
              >
                ${label}
              </button>
            `,
          )}
        </div>
        <p class="hint">
          ${
            picking.tab === "cars"
              ? "A car already in this train is greyed."
              : "A model with a decoder goes in as its car, made for it if there is none."
          }
        </p>
        <div class="cards offered">
          ${
            picking.tab === "cars"
              ? cars.length === 0
                ? this.none(
                    "no cars yet — a model with a decoder becomes one when it is added",
                  )
                : cars.map(car)
              : models.length === 0
                ? this.none("no models yet — make one in the Models list first")
                : models.map((model) =>
                    this.card(
                      "model",
                      model.model,
                      model.name,
                      this.modelFacts(model),
                      false,
                      () => this.pickedModel(model.model),
                    ),
                  )
          }
        </div>
      </look-dialog>
    `;
  }

  private closePicker(): void {
    this.picking = null;
  }

  /** A car pressed in the picker: at the tail of the train, as itself. */
  private pickedCar(car: string): void {
    const picking = this.picking;
    if (picking === null || this.stock === null) return;
    const refused = this.stock.append(picking.train, { car });
    if (refused === null) this.picking = null;
    this.did(refused);
  }

  /**
   * A model pressed in the picker: a model entry where it has no decoder;
   * otherwise its car — made, and asked for its address at once as New car
   * does; the only one, said; or chosen from several (`Stock.addModel`).
   */
  private pickedModel(key: string): void {
    const picking = this.picking;
    const stock = this.stock;
    if (picking === null || stock === null) return;
    const added = stock.addModel(picking.train, key);
    if (added.as === "which") {
      this.picking = { ...picking, model: stock.keyOf(key) };
      return;
    }
    this.picking = null;
    if (added.as === "made") {
      this.asked = added.car;
      this.refusal = null;
    }
    this.did(null);
    if (added.as === "only") {
      const model = stock.model(key);
      this.tell(
        `Added ${added.car}, your only ${model === null ? key : modelName(model)}.`,
      );
    }
  }

  /** Words at the foot of the view, for a moment. */
  private tell(words: string): void {
    this.told = words;
    if (this.telling !== null) clearTimeout(this.telling);
    this.telling = setTimeout(() => {
      this.told = null;
    }, TOLD_MS);
  }

  // --- the presses ----------------------------------------------------------

  /**
   * Why there is nothing here to write into, or `null` where there is. The
   * two documents are what a press that writes writes into, and until they
   * are read there are none: the New buttons and Save are dead with this on
   * them (#565).
   */
  private unwritable(): string | null {
    if (this.stock !== null) return null;
    return (this.railroad?.name ?? "") === "" ? UNLOADED : UNREAD;
  }

  /** The New button of the list shown. */
  private made = (): void => {
    const stock = this.stock;
    if (stock === null) {
      this.did(this.unwritable());
      return;
    }
    if (this.tab === "models") void this.newModel(stock);
    else if (this.tab === "cars") this.choosing = true;
    else this.newTrain(stock);
  };

  /** *New model* in the list, chosen, with its name selected to be typed
   *  over. It is written by Save, which mints its key from its name. */
  private async newModel(stock: Stock): Promise<void> {
    this.model = stock.newModel();
    this.editing = true;
    this.did(null);
    await this.updateComplete;
    this.renderRoot
      .querySelector<HTMLInputElement>(".model-editor input.name")
      ?.select();
  }

  /** *New train* in the list, chosen, with the picker open on it. */
  private newTrain(stock: Stock): void {
    this.train = stock.newTrain();
    this.editing = true;
    this.picking = { train: this.train, tab: "cars", model: null };
    this.did(null);
  }

  /**
   * A train renamed. The chosen train is a name, so renaming it carries the
   * choice with it: the person renamed the train they were composing, not
   * another one (#445). A refusal changes the document not at all.
   */
  private renamed(was: string, name: string): void {
    if (this.stock === null) return;
    const chosen = this.pointed() === was;
    const refused = this.stock.renameTrain(was, name);
    if (refused === null && chosen) this.train = name;
    // The old name, because a refused rename is the row still drawn under it:
    // the field to write back is the one the edit was typed into (#444).
    this.did(refused, `train:${was}:name`);
  }

  /**
   * The train the editor shows and the picker fills: the one chosen, where
   * the roster has it, and
   * the first train it has where it has not — `null` where it has none at
   * all (#416, #445).
   */
  private pointed(): string | null {
    const trains = this.stock?.roster.trains ?? {};
    if (this.train !== null && this.train in trains) return this.train;
    return Object.keys(trains).sort()[0] ?? null;
  }

  /**
   * The one Save, which is the loaded railroad's (`model/railroad.ts`): each
   * changed model, each changed photo, then the roster, and what the store
   * said in the bar. *Saved* stands there for a moment once it has landed.
   */
  private save = async (): Promise<void> => {
    const railroad = this.railroad;
    if (railroad === undefined) return;
    this.trouble = null;
    await railroad.save(this.power, this.heard);
    const stock = railroad.stock;
    if (stock === null || stock.edits || railroad.stockTrouble !== null) return;
    this.landed = true;
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.landed = false;
    }, SAVED_MS);
  };

  /** An edit that cannot refuse, through `did` all the same so the screen
   *  redraws and the last refusal is taken down. */
  private changed(
    edit: (stock: Stock) => void,
    field: string | null = null,
  ): void {
    if (this.stock === null) return;
    edit(this.stock);
    this.did(null, field);
  }

  /** What an edit answered: nothing, or the words to show, and the field it
   *  was typed into where it was typed into one. A refusal changes the
   *  document not at all, so the field is named here so that the render this
   *  edit asks for writes the document's value back over it (#416). */
  private did(
    refused: string | null | undefined,
    field: string | null = null,
  ): void {
    this.trouble = refused ?? null;
    this.back = field;
    this.beat++;
    this.landed = false;
    // What the last Save was refused with is about a roster that has moved
    // since, and the app reads what is unsaved off the railroad.
    this.railroad?.edited();
  }

  /** What a document-backed field is bound to: the document's value, written
   *  over the DOM on the render an edit typed into *that* field asked for,
   *  and on no other — a frame about the railroad is not news about what
   *  somebody is typing (#444). */
  private putting(field: string, held: string) {
    return this.back === field ? live(held) : held;
  }
}

/** What was typed into a control, whichever kind it is. */
function value(event: Event): string {
  return (
    event.target as HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement
  ).value;
}

/** A length as typed, `null` for a field left empty — which is a car reading
 *  its model's length again rather than a number this could not parse. */
function millimetres(event: Event): number | null {
  const typed = value(event).trim();
  return typed === "" ? null : Number(typed);
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-stock": TcStock;
  }
}
