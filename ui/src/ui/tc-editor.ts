/**
 * The editing view: a drawing, the palette, the canvas, and what the store
 * says the drawing means.
 *
 * The railroad it is editing is not its own — the app holds it and hands over
 * the `Editor` and the review
 * ([ADR-0038](../../../docs/adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md)).
 * What is this view's is what only editing has: the selection's dialogs, the
 * right-click menu, and which transit the netlist pane has lit. An edit goes
 * up as an `edit` event, and the app asks the store what the drawing now
 * means.
 *
 * Every edit re-asks `/review`, because the front end knows no topology
 * (EDITOR.md): red pins, junction membership and the derived layout are the
 * store's answers, not a second implementation here that could disagree with
 * the first inside the tool whose job is to be believed.
 *
 * What that answer says is wrong is not listed here. The canvas marks each
 * fault where it is and the band says coarsely whether the drawing derives
 * (ADR-0024), so the review goes to those two and neither this nor the app
 * keeps any of it.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import type { Kind } from "../symbols.generated.js";
import { emptyDrawing, type SymbolSpec } from "../model/drawing.js";
import { Editor } from "../model/editor.js";
import { editingMachine, Gesture } from "../model/gesture.js";
import type { Chosen } from "../model/inspect.js";
import { UNREVIEWED, type Review } from "../model/store.js";
import type { Under } from "../model/under.js";
import { editorStyles } from "./tc-editor.styles.js";
import "./tc-canvas.js";
import "./tc-menu.js";
import "./tc-netlist.js";
import "./tc-palette.js";
import "./tc-properties.js";
import type { TcCanvas } from "./tc-canvas.js";
import type { MenuItem } from "./tc-menu.js";
import { editable, type Properties } from "./tc-properties.js";

export type MenuAction =
  | "properties"
  | "rotate"
  | "flip"
  | "delete"
  | "delete-wire";

/** Where the pointer was, and what was under it. The canvas works out the
 *  second half (model/under.ts) and the editor only asks what applies to it. */
export type MenuAt = Under & { x: number; y: number };

/**
 * What the right-click menu offers for what was clicked.
 *
 * A symbol offers its properties, where it has any, and the transforms the key
 * bindings also do; and a wire offers to be cut, this being the only way to
 * delete one — a wire has no symbol to select and so no keystroke to take it.
 *
 * A junction and a joint offer nothing, so a right-click on one draws no menu
 * at all. Their names are the editor's own: it mints them, `settle` keeps them
 * settled through splits and merges, and the netlist pane is where one is read
 * (EDITOR.md#junctions).
 */
export function editorMenu(at: MenuAt): MenuItem[] {
  const items: MenuItem[] = [];
  if (at.wire !== null) items.push({ label: "Delete wire", action: "delete-wire" });
  if (at.symbol !== null) {
    if (at.kind !== null && editable(at.kind)) {
      items.push({ label: "Properties…", action: "properties" });
    }
    items.push(
      { label: "Rotate", action: "rotate", key: "R" },
      { label: "Flip", action: "flip", key: "F" },
      { label: "Delete", action: "delete", key: "⌫" },
    );
  }
  return items;
}

@customElement("tc-editor")
export class TcEditor extends LitElement {
  static override styles = editorStyles;

  /** The editing session over the loaded railroad, the app's own instance. */
  @property({ attribute: false }) editor = new Editor(emptyDrawing("untitled"));

  /** What the store last said the drawing means, `null` before it has been
   *  asked. */
  @property({ attribute: false }) review: Review | null = null;

  /** Whether the netlist pane is open. Shut on load and shut again whenever a
   *  railroad is loaded, the netlist being a debugging view consulted when
   *  something looks wrong rather than what the editor is for (ADR-0024). The
   *  app owns it, `View ▸ Netlist` being a bar command; it is reflected onto
   *  the host because the grid drops the column with the pane, and an
   *  attribute is what `tc-editor.styles.ts` can read. */
  @property({ type: Boolean, reflect: true }) netlist = false;

  /** What a press on the canvas means here (model/gesture.ts), bound to the
   *  document it is about. The canvas drives it and decides none of it. */
  private readonly machine = editingMachine(
    new Gesture(),
    () => this.editor,
    () => this.review ?? UNREVIEWED,
  );

  @state() private menu: MenuAt | null = null;
  @state() private editing: { name: string; spec: SymbolSpec } | null = null;
  @state() private chosen: Chosen | null = null;

  override willUpdate(changed: Map<string, unknown>): void {
    // Shutting the pane unlights whatever transit was chosen in it: the pane
    // is the only thing that lights a way and the only thing that could
    // unlight one, so a way left lit with the pane gone would stay lit with
    // nothing to clear it.
    if (changed.has("netlist") && !this.netlist) this.chosen = null;
  }

  override render() {
    return html`
      <tc-palette @take=${this.take}></tc-palette>

      <tc-canvas
        .editor=${this.editor}
        .review=${this.review}
        .chosen=${this.chosen}
        .machine=${this.machine}
        @canvas-menu=${(event: CustomEvent<MenuAt>) => {
          this.menu = event.detail;
        }}
      ></tc-canvas>

      ${this.netlist
        ? html`
            <tc-netlist
              .review=${this.review}
              .chosen=${this.chosen}
              .symbol=${this.inspecting}
              @transit-chosen=${(event: CustomEvent<Chosen | null>) => {
                this.chosen = event.detail;
                this.redraw();
              }}
            ></tc-netlist>
          `
        : nothing}

      <tc-menu
        .at=${this.menu}
        .items=${this.menu === null ? [] : editorMenu(this.menu)}
        @menu-action=${this.chose}
        @menu-dismissed=${() => {
          this.menu = null;
        }}
      ></tc-menu>

      <tc-properties
        .editing=${this.editing}
        .taken=${Object.keys(this.editor.drawing.symbols)}
        @properties=${this.applied}
        @properties-closed=${() => {
          this.editing = null;
        }}
      ></tc-properties>
    `;
  }

  // --- what the app asks of the view ---------------------------------------

  /** The properties of the one selected symbol. The right-click menu asks the
   *  same dialog about whatever is under the pointer instead. */
  editSelected(): void {
    const name = this.inspecting;
    if (name === null) return;
    const spec = this.editor.drawing.symbols[name];
    if (spec !== undefined) this.editing = { name, spec };
  }

  zoom(scale: number): void {
    this.canvas?.zoom(scale);
  }

  fit(): void {
    this.canvas?.fit();
  }

  /** The drawing as a standalone SVG, which is what `Export SVG…` writes. */
  exported(): string | undefined {
    return this.canvas?.exported();
  }

  /** The canvas holds the same `Editor` across an edit, so Lit sees no changed
   *  property and would not re-render it. Asking it directly is what makes a
   *  bar button show its effect without waiting for `/review`. */
  redraw(): void {
    this.requestUpdate();
    this.canvas?.requestUpdate();
  }

  private get canvas(): TcCanvas | null {
    return this.renderRoot.querySelector<TcCanvas>("tc-canvas");
  }

  /** The one symbol the netlist pane inspects, where exactly one is selected.
   *  A group selection is a move about to happen, not a question about a
   *  frog. */
  private get inspecting(): string | null {
    const selected = [...this.editor.selection];
    return selected.length === 1 ? selected[0]! : null;
  }

  // --- edits ---------------------------------------------------------------

  /** An edit happened here rather than on the canvas, which raises its own.
   *  The app hears both and asks the store what the drawing now means. */
  private edited(): void {
    this.dispatchEvent(new CustomEvent("edit", { bubbles: true, composed: true }));
  }

  private act(change: (editor: Editor) => void): void {
    change(this.editor);
    this.redraw();
    this.edited();
  }

  // --- the right-click menu, and what it opens -----------------------------

  private chose(event: CustomEvent<string>): void {
    const at = this.menu;
    this.menu = null;
    if (at === null) return;
    switch (event.detail as MenuAction) {
      case "properties": {
        const spec = at.symbol === null ? undefined : this.editor.drawing.symbols[at.symbol];
        if (at.symbol !== null && spec !== undefined) {
          this.editing = { name: at.symbol, spec };
        }
        return;
      }
      case "delete-wire":
        if (at.wire !== null) this.act((editor) => editor.unwire(at.wire!));
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

  /** What the dialog handed back, which it only does for a name the drawing
   *  can take: it asks `symbolTrouble` before it closes, so the document's own
   *  guard has nothing left to catch here. */
  private applied(event: CustomEvent<Properties>): void {
    const { was, name, spec } = event.detail;
    this.editing = null;
    if (!this.editor.edit(was, name, spec)) return;
    this.redraw();
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

  /**
   * The release that ends the drag, wherever it happened. A symbol still
   * pending here was dropped nowhere, so it is abandoned.
   *
   * Except a portal's mate: a drop over the canvas leaves it in flight and this
   * runs on the same release, which would abandon the pair's second half before
   * it could be placed (ADR-0020). It is dropped by a click of its own, and no
   * listener is waiting on that one.
   */
  private dropped = (): void => {
    window.removeEventListener("pointerup", this.dropped);
    if (this.editor.pending === null || this.editor.mating) return;
    this.editor.cancelPending();
    this.redraw();
  };
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-editor": TcEditor;
  }
}
