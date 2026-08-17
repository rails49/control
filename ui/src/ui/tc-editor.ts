/**
 * The editor: a drawing, the palette, the canvas, and what the store says the
 * drawing means.
 *
 * Every edit re-asks `/review`, because the front end knows no topology
 * (EDITOR.md): red pins, junction membership and the derived layout are the
 * store's answers, not a second implementation here that could disagree with
 * the first inside the tool whose job is to be believed.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, state } from "lit/decorators.js";
import "@shoelace-style/shoelace/dist/components/button/button.js";
import "@shoelace-style/shoelace/dist/components/select/select.js";
import "@shoelace-style/shoelace/dist/components/option/option.js";
import "@shoelace-style/shoelace/dist/themes/light.css";

import type { Kind } from "../symbols.generated.js";
import { emptyDrawing, type SymbolSpec } from "../model/drawing.js";
import { Editor } from "../model/editor.js";
import { clashes, type Chosen, type Clash } from "../model/inspect.js";
import {
  listDrawings,
  readDrawing,
  review,
  saveDrawing,
  type Review,
} from "../model/store.js";
import { FIT, REDO, UNDO, ZOOM_IN, ZOOM_OUT } from "./icons.js";
import { appStyles } from "./styles.js";
import "./tc-canvas.js";
import "./tc-menu.js";
import "./tc-netlist.js";
import "./tc-palette.js";
import "./tc-properties.js";
import type { TcCanvas } from "./tc-canvas.js";
import type { MenuAction, MenuAt } from "./tc-menu.js";
import type { Properties } from "./tc-properties.js";

/** One press of the zoom-out button, and the reciprocal for zoom in. A quarter
 *  again is about what the wheel gives for a comfortable turn of it. */
const OUT = 1.25;

@customElement("tc-editor")
export class TcEditor extends LitElement {
  static override styles = appStyles;

  private editor = new Editor(emptyDrawing("untitled"));

  @state() private drawings: string[] = [];
  @state() private opened = "";
  @state() private reviewed: Review | null = null;
  @state() private trouble: string | null = null;
  @state() private saved = true;
  @state() private menu: MenuAt | null = null;
  @state() private editing: { name: string; spec: SymbolSpec } | null = null;
  @state() private chosen: Chosen | null = null;

  override connectedCallback(): void {
    super.connectedCallback();
    window.addEventListener("keydown", this.key);
    void this.load();
  }

  override disconnectedCallback(): void {
    window.removeEventListener("keydown", this.key);
    super.disconnectedCallback();
  }

  override render() {
    return html`
      <header>
        <span class="drawing">${this.opened || "no drawing"}</span>
        <sl-select
          size="small"
          value=${this.opened}
          placeholder="open a railroad"
          @sl-change=${this.open}
        >
          ${this.drawings.map(
            (name) => html`<sl-option value=${name}>${name}</sl-option>`,
          )}
        </sl-select>
        <span class="spacer"></span>
        ${this.tool(ZOOM_OUT, "Zoom out  −", () => this.zoom(OUT))}
        ${this.tool(ZOOM_IN, "Zoom in  +", () => this.zoom(1 / OUT))}
        ${this.tool(FIT, "Fit  0", () => this.fit())}
        ${this.tool(UNDO, "Undo  ⌘Z", () => this.act((e) => e.undo()))}
        ${this.tool(REDO, "Redo  ⇧⌘Z", () => this.act((e) => e.redo()))}
        <sl-button
          size="small"
          variant="primary"
          ?disabled=${this.saved || this.opened === ""}
          @click=${this.save}
        >
          Save
        </sl-button>
      </header>

      <tc-palette @take=${this.take}></tc-palette>

      <tc-canvas
        .editor=${this.editor}
        .review=${this.reviewed}
        .chosen=${this.chosen}
        @edit=${this.edited}
        @picked=${() => this.requestUpdate()}
        @canvas-menu=${(event: CustomEvent<MenuAt>) => {
          this.menu = event.detail;
        }}
      ></tc-canvas>

      <div class="side">
        ${this.findings()}
        <tc-netlist
          .review=${this.reviewed}
          .chosen=${this.chosen}
          .symbol=${this.inspecting}
          @transit-chosen=${(event: CustomEvent<Chosen | null>) => {
            this.chosen = event.detail;
            this.redraw();
          }}
        ></tc-netlist>
      </div>

      <tc-menu .at=${this.menu} @menu-action=${this.chose}
        @menu-dismissed=${() => {
          this.menu = null;
        }}
      ></tc-menu>

      <tc-properties
        .editing=${this.editing}
        @properties=${this.applied}
        @properties-closed=${() => {
          this.editing = null;
        }}
      ></tc-properties>
    `;
  }

  /** Everything wrong with the drawing, in one panel: the pins short of a
   *  wire, the names two connections cannot both wear, and the refusal
   *  derivation came back with. A name collision is listed even where
   *  derivation did not refuse, since two junctions wearing one name derive as
   *  one connection — a wrong netlist rather than a refused one. */
  private findings() {
    if (this.trouble !== null) {
      return html`<div class="findings"><p>${this.trouble}</p></div>`;
    }
    const red = this.reviewed?.red_pins ?? [];
    const refused = this.reviewed?.refused ?? null;
    const clashing = this.reviewed === null ? [] : clashes(this.reviewed);
    const stacked = this.stacked();
    if (
      red.length === 0 &&
      refused === null &&
      clashing.length === 0 &&
      stacked.length === 0
    ) {
      return html`
        <div class="findings clean">
          <p>Every pin holds its wires.</p>
        </div>
      `;
    }
    return html`
      <div class="findings">
        ${stacked.map((where) => html`<p>${where} overlap</p>`)}
        ${red.length === 0
          ? nothing
          : html`<p>${red.length} pin(s) short of a wire: ${red.join(", ")}</p>`}
        ${clashing.map((clash) => html`<p>${said(clash)}</p>`)}
        ${refused === null ? nothing : html`<p>${refused}</p>`}
      </div>
    `;
  }

  /** The symbols sharing a square, named once however many squares they share.
   *  Read off the drawing rather than raised by the rotate or flip that made
   *  the overlap, so it stays true through an undo (EDITOR.md#canvas). */
  private stacked(): string[] {
    const shared = this.editor.overlaps();
    return [...new Set(shared.map(({ symbols }) => symbols.join(" and ")))];
  }

  /** The one symbol the netlist pane inspects, where exactly one is selected.
   *  A group selection is a move about to happen, not a question about a
   *  frog. */
  private get inspecting(): string | null {
    const selected = [...this.editor.selection];
    return selected.length === 1 ? selected[0]! : null;
  }

  // --- talking to the store -----------------------------------------------

  private async load(): Promise<void> {
    try {
      this.drawings = await listDrawings();
      this.trouble = null;
    } catch (failure) {
      this.trouble = `the store is not answering: ${String(failure)}`;
    }
  }

  private async open(event: Event): Promise<void> {
    const name = (event.target as HTMLInputElement).value;
    if (name === "") return;
    try {
      this.editor.reset(await readDrawing(name));
      this.opened = name;
      // Staging is an edit, so a railroad that arrives without placement
      // opens with something to save rather than something already saved.
      this.saved = !this.editor.stage();
      this.trouble = null;
      await this.updateComplete;
      this.fit();
      await this.reviewNow();
    } catch (failure) {
      this.trouble = String(failure);
    }
  }

  /** Saving needs a drawing to save into. Nothing is open until a railroad
   *  is chosen, and `untitled` is not a file anyone asked for. */
  private async save(): Promise<void> {
    if (this.opened === "") return;
    try {
      await saveDrawing(this.editor.drawing);
      this.saved = true;
      this.trouble = null;
    } catch (failure) {
      this.trouble = String(failure);
    }
  }

  /** A drawing mid-edit is normally not derivable, so a refusal comes back
   *  inside a 200 and is shown; only a document that will not load at all is
   *  an error worth reporting as one. */
  private async reviewNow(): Promise<void> {
    try {
      const at = this.editor.revision;
      this.reviewed = await review(this.editor.drawing);
      this.trouble = null;
      // A junction always has a valid name, so the names the drawing has not
      // settled are minted the moment the store says which junctions exist.
      // The write folds into the edit that caused it, and asking again with
      // the names in place is what makes the pane agree with the drawing.
      if (this.editor.settle(this.reviewed, at)) {
        this.saved = false;
        this.reviewed = await review(this.editor.drawing);
      }
      this.redraw();
    } catch (failure) {
      this.trouble = String(failure);
    }
  }

  // --- edits ---------------------------------------------------------------

  private edited(): void {
    this.saved = false;
    this.redraw();
    void this.reviewNow();
  }

  /** The canvas holds the same `Editor` across an edit, so Lit sees no
   *  changed property and would not re-render it. Asking it directly is what
   *  makes a toolbar button show its effect without waiting for `/review`. */
  private redraw(): void {
    this.requestUpdate();
    this.renderRoot.querySelector<TcCanvas>("tc-canvas")?.requestUpdate();
  }

  private act(change: (editor: Editor) => void): void {
    change(this.editor);
    this.edited();
  }

  // --- the right-click menu, and what it opens -----------------------------

  private chose(event: CustomEvent<MenuAction>): void {
    const at = this.menu;
    this.menu = null;
    if (at === null) return;
    switch (event.detail) {
      case "properties": {
        const spec = at.symbol === null ? undefined : this.editor.drawing.symbols[at.symbol];
        if (at.symbol !== null && spec !== undefined) {
          this.editing = { name: at.symbol, spec };
        }
        return;
      }
      case "rename-junction":
        if (at.junction !== null) {
          const name = this.ask("Junction name", at.junction.name ?? "");
          if (name !== null) {
            this.act((editor) => editor.nameJunction(at.junction!.symbols, name));
          }
        }
        return;
      case "rename-joint":
        if (at.joint !== null) {
          const name = this.ask("Connection name", at.joint.name ?? "");
          if (name !== null) this.act((editor) => editor.nameJoint(at.joint!, name));
        }
        return;
      case "rotate":
        this.act((editor) => editor.rotate());
        return;
      case "flip":
        this.act((editor) => editor.flip());
        return;
      case "delete":
        this.act((editor) => editor.remove());
        return;
    }
  }

  /** A one-field rename. A dialog for a single word would be more of the
   *  editor than renaming a junction is worth (EDITOR.md's simplicity). */
  private ask(what: string, was: string): string | null {
    const said = window.prompt(what, was);
    return said === null || said.trim() === "" ? null : said.trim();
  }

  private applied(event: CustomEvent<Properties>): void {
    const { was, name, spec } = event.detail;
    this.editing = null;
    if (!this.editor.edit(was, name, spec)) {
      this.trouble = `'${name}' is not a name this drawing can take`;
      return;
    }
    this.edited();
  }

  // --- dragging a symbol off the palette -----------------------------------

  /**
   * A tile was pressed. The canvas draws the ghost and takes the drop, since
   * both are its coordinates; all that is left over is the release that happens
   * anywhere else, which abandons the symbol.
   *
   * The canvas's own handler runs first — a pointer event from inside its
   * shadow root reaches the window afterwards — so by the time this sees a
   * release over the canvas there is nothing pending left to cancel.
   */
  private take(event: CustomEvent<Kind>): void {
    this.editor.beginPlace(event.detail);
    this.redraw();
    window.addEventListener("pointerup", this.dropped);
  }

  private dropped = (): void => {
    window.removeEventListener("pointerup", this.dropped);
    if (this.editor.pending === null) return;
    this.editor.cancelPending();
    this.redraw();
  };

  private tool(icon: unknown, label: string, act: () => void) {
    return html`
      <sl-button size="small" title=${label} aria-label=${label} @click=${act}>
        ${icon}
      </sl-button>
    `;
  }

  private zoom(scale: number): void {
    this.renderRoot.querySelector<TcCanvas>("tc-canvas")?.zoom(scale);
  }

  private fit(): void {
    this.renderRoot.querySelector<TcCanvas>("tc-canvas")?.fit();
  }

  private key = (event: KeyboardEvent): void => {
    // The listener is on the window, so an event from inside a shadow root
    // arrives retargeted to this host. The composed path is what still says
    // where it started, and a key typed into a control is that control's.
    const from = event.composedPath()[0];
    if (from instanceof HTMLElement && from.closest("sl-input, sl-select")) {
      return;
    }
    const meta = event.metaKey || event.ctrlKey;
    if (meta && event.key.toLowerCase() === "z") {
      event.preventDefault();
      this.act((editor) => (event.shiftKey ? editor.redo() : editor.undo()));
      return;
    }
    if (meta && event.key.toLowerCase() === "s") {
      event.preventDefault();
      void this.save();
      return;
    }
    // A symbol on its way out of the palette takes the same two keys the
    // selection does, and any of the three ways out abandons it.
    if (this.editor.pending !== null) {
      switch (event.key) {
        case "r":
        case "R":
          this.editor.turnPending();
          break;
        case "f":
        case "F":
          this.editor.flipPending();
          break;
        case "Escape":
        case "Delete":
        case "Backspace":
          event.preventDefault();
          this.editor.cancelPending();
          break;
        default:
          return;
      }
      this.redraw();
      return;
    }

    switch (event.key) {
      case "Escape":
        this.editor.cancelWire();
        this.editor.clearSelection();
        this.redraw();
        return;
      case "r":
      case "R":
        this.selected((editor) => editor.rotate());
        return;
      case "f":
      case "F":
        this.selected((editor) => editor.flip());
        return;
      case "Delete":
      case "Backspace":
        event.preventDefault();
        this.selected((editor) => editor.remove());
        return;
      case "+":
      case "=":
        this.zoom(1 / OUT);
        return;
      case "-":
        this.zoom(OUT);
        return;
      case "0":
        this.fit();
        return;
      default:
        return;
    }
  };

  /** A verb that needs something to act on. With nothing selected it does
   *  nothing at all — not even mark the drawing unsaved and ask `/review`
   *  again, which is what routing it through `act` did. */
  private selected(change: (editor: Editor) => void): void {
    if (this.editor.selection.size === 0) return;
    this.act(change);
  }
}

/** A name collision as a sentence. Which half is Airolo is not the editor's
 *  decision to make (naming.ts), so the finding says where both are and stops
 *  there. */
function said(clash: Clash): string {
  const where = clash.where.map((one) => one.join(", ")).join(" and ");
  return clash.kind === "duplicate"
    ? `two connections are both named '${clash.names[0]}': ${where}`
    : `one connection is named ${clash.names
        .map((name) => `'${name}'`)
        .join(" and ")}: ${where}`;
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-editor": TcEditor;
  }
}
