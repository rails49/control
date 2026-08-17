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
import { emptyDrawing } from "../model/drawing.js";
import { Editor } from "../model/editor.js";
import {
  listDrawings,
  readDrawing,
  review,
  saveDrawing,
  type Review,
} from "../model/store.js";
import { appStyles } from "./styles.js";
import "./tc-canvas.js";
import "./tc-palette.js";
import type { TcCanvas } from "./tc-canvas.js";

@customElement("tc-editor")
export class TcEditor extends LitElement {
  static override styles = appStyles;

  private editor = new Editor(emptyDrawing("untitled"));

  @state() private drawings: string[] = [];
  @state() private opened = "";
  @state() private armed: Kind | null = null;
  @state() private reviewed: Review | null = null;
  @state() private trouble: string | null = null;
  @state() private saved = true;

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
        <sl-button size="small" @click=${() => this.act((e) => e.rotate())}>
          Rotate
        </sl-button>
        <sl-button size="small" @click=${() => this.act((e) => e.flip())}>
          Flip
        </sl-button>
        <sl-button size="small" @click=${() => this.act((e) => e.remove())}>
          Delete
        </sl-button>
        <sl-button size="small" @click=${() => this.act((e) => e.undo())}>
          Undo
        </sl-button>
        <sl-button size="small" @click=${() => this.act((e) => e.redo())}>
          Redo
        </sl-button>
        <sl-button size="small" @click=${this.fit}>Fit</sl-button>
        <sl-button
          size="small"
          variant="primary"
          ?disabled=${this.saved || this.opened === ""}
          @click=${this.save}
        >
          Save
        </sl-button>
      </header>

      <tc-palette .armed=${this.armed} @arm=${this.arm}></tc-palette>

      <tc-canvas
        .editor=${this.editor}
        .review=${this.reviewed}
        .placing=${this.armed}
        @edit=${this.edited}
      ></tc-canvas>

      <div class="side">${this.findings()}</div>
    `;
  }

  private findings() {
    if (this.trouble !== null) {
      return html`<div class="findings"><p>${this.trouble}</p></div>`;
    }
    const red = this.reviewed?.red_pins ?? [];
    const refused = this.reviewed?.refused ?? null;
    if (red.length === 0 && refused === null) {
      return html`
        <div class="findings clean">
          <p>Every pin holds its wires.</p>
        </div>
      `;
    }
    return html`
      <div class="findings">
        ${red.length === 0
          ? nothing
          : html`<p>${red.length} pin(s) short of a wire: ${red.join(", ")}</p>`}
        ${refused === null ? nothing : html`<p>${refused}</p>`}
      </div>
    `;
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
      this.reviewed = await review(this.editor.drawing);
      this.trouble = null;
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

  private arm(event: CustomEvent<Kind | null>): void {
    this.armed = event.detail;
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
    switch (event.key) {
      case "Escape":
        this.armed = null;
        this.editor.cancelWire();
        this.editor.clearSelection();
        this.redraw();
        return;
      case "r":
      case "R":
        this.act((editor) => editor.rotate());
        return;
      case "f":
      case "F":
        this.act((editor) => editor.flip());
        return;
      case "Delete":
      case "Backspace":
        event.preventDefault();
        this.act((editor) => editor.remove());
        return;
      default:
        return;
    }
  };
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-editor": TcEditor;
  }
}
