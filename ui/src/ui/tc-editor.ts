/**
 * The editor: a drawing, the palette, the canvas, and what the store says the
 * drawing means.
 *
 * Every edit re-asks `/review`, because the front end knows no topology
 * (EDITOR.md): red pins, junction membership and the derived layout are the
 * store's answers, not a second implementation here that could disagree with
 * the first inside the tool whose job is to be believed.
 *
 * What that answer says is wrong is not listed here. The canvas marks each
 * fault where it is and the band says coarsely whether the drawing derives
 * (ADR-0024), so the review goes to those two and the shell keeps none of it.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import "@shoelace-style/shoelace/dist/components/button/button.js";
import "@shoelace-style/shoelace/dist/components/dialog/dialog.js";
import "@shoelace-style/shoelace/dist/themes/light.css";

import type { Kind } from "../symbols.generated.js";
import { COMMANDS, type CommandId, type Standing } from "../model/commands.js";
import { emptyDrawing, type SymbolSpec } from "../model/drawing.js";
import { Editor } from "../model/editor.js";
import { Filing } from "../model/filing.js";
import type { Chosen } from "../model/inspect.js";
import { appStyles } from "./tc-editor.styles.js";
import "./tc-canvas.js";
import "./tc-header.js";
import "./tc-menu.js";
import "./tc-menubar.js";
import "./tc-netlist.js";
import "./tc-palette.js";
import "./tc-properties.js";
import type { TcCanvas } from "./tc-canvas.js";
import type { MenuAction, MenuAt } from "./tc-menu.js";
import type { TcMenubar } from "./tc-menubar.js";
import { editable, type Properties } from "./tc-properties.js";

/** One press of the zoom-out button, and the reciprocal for zoom in. A quarter
 *  again is about what the wheel gives for a comfortable turn of it. */
const OUT = 1.25;

/** What a keystroke belongs to rather than to the canvas: the controls the
 *  editor puts on screen, and the native ones they are built from. */
const CONTROLS = "sl-input, sl-select, input, textarea";

@customElement("tc-editor")
export class TcEditor extends LitElement {
  static override styles = appStyles;

  private editor = new Editor(emptyDrawing("untitled"));

  /** Everything the store is asked and everything it says back
   *  (`model/filing.ts`). None of it is `@state`, so it says when it has
   *  moved and the shell redraws. */
  private filing = new Filing(() => this.redraw());

  @state() private menu: MenuAt | null = null;
  /** Whether a menu on the bar is down. While one is, the keyboard is the
   *  menu's and nothing reaches the canvas. */
  @state() private barMenu = false;
  @state() private editing: { name: string; spec: SymbolSpec } | null = null;
  /** What is waiting on the operator's word before the open drawing is thrown
   *  away: the drawing wanted, or `null` for a new one, `null` being a choice
   *  and not the absence of one. `discarding` itself is `null` while nothing
   *  is waiting, which is the ordinary state. */
  @state() private discarding: { wanted: string | null } | null = null;
  @state() private chosen: Chosen | null = null;
  /** Whether the netlist pane is open. Shut on load and shut again whenever a
   *  drawing is opened, the netlist being a debugging view consulted when
   *  something looks wrong rather than what the editor is for (ADR-0024).
   *  Reflected onto the host because the shell's grid drops the column with
   *  the pane, and an attribute is what `tc-editor.styles.ts` can read. */
  @property({ type: Boolean, reflect: true }) netlist = false;

  override connectedCallback(): void {
    super.connectedCallback();
    window.addEventListener("keydown", this.key);
    void this.filing.load();
  }

  override disconnectedCallback(): void {
    window.removeEventListener("keydown", this.key);
    super.disconnectedCallback();
  }

  override render() {
    return html`
      <tc-header
        mode="editor"
        .drawing=${this.filing.opened === "" ? null : this.filing.opened}
        .unsaved=${!this.filing.saved}
        .derives=${this.filing.derives}
        .trouble=${this.filing.trouble}
      ></tc-header>

      <tc-menubar
        .standing=${this.standing}
        .drawings=${this.filing.drawings}
        @command=${(event: CustomEvent<CommandId>) => this.run(event.detail)}
        @open-drawing=${(event: CustomEvent<string>) => this.discard(event.detail)}
        @menu-open=${(event: CustomEvent<boolean>) => {
          this.barMenu = event.detail;
        }}
      ></tc-menubar>

      <tc-palette @take=${this.take}></tc-palette>

      <tc-canvas
        .editor=${this.editor}
        .review=${this.filing.reviewed}
        .chosen=${this.chosen}
        @edit=${this.edited}
        @picked=${() => this.requestUpdate()}
        @canvas-menu=${(event: CustomEvent<MenuAt>) => {
          this.menu = event.detail;
        }}
      ></tc-canvas>

      ${this.netlist
        ? html`
            <tc-netlist
              .review=${this.filing.reviewed}
              .chosen=${this.chosen}
              .symbol=${this.inspecting}
              @transit-chosen=${(event: CustomEvent<Chosen | null>) => {
                this.chosen = event.detail;
                this.redraw();
              }}
            ></tc-netlist>
          `
        : nothing}

      <tc-menu .at=${this.menu} @menu-action=${this.chose}
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

      ${this.discarding === null
        ? nothing
        : this.question(this.discarding.wanted)}
    `;
  }

  /** The one thing the editor asks rather than does. Edits the store has not
   *  been given are the operator's, and a menu click is a thin thing to lose
   *  an evening's drawing to (#101), so what would discard them says so and
   *  waits. It is the dialog the properties are edited in, not a native
   *  `confirm`, which the page cannot style and a browser may suppress. */
  private question(wanted: string | null) {
    // Nothing is open until a drawing is chosen, and what is drawn on the
    // canvas before that is still an evening's work.
    const losing =
      this.filing.opened === "" ? "The canvas" : `'${this.filing.opened}'`;
    const instead =
      wanted === null ? "Starting a new drawing" : `Opening '${wanted}'`;
    return html`
      <sl-dialog open label="Discard unsaved edits?" @sl-after-hide=${this.kept}>
        <p>
          ${losing} has edits that have not been saved. ${instead} discards
          them.
        </p>
        <sl-button slot="footer" @click=${this.kept}>Cancel</sl-button>
        <sl-button slot="footer" variant="danger" @click=${this.discarded}>
          Discard
        </sl-button>
      </sl-dialog>
    `;
  }

  /** The one symbol the netlist pane inspects, where exactly one is selected.
   *  A group selection is a move about to happen, not a question about a
   *  frog. */
  private get inspecting(): string | null {
    const selected = [...this.editor.selection];
    return selected.length === 1 ? selected[0]! : null;
  }

  /** Where the editor stands, as far as a command needs to know
   *  (model/commands.ts). Nothing here decides what is dead; that module
   *  does, and it is what both the bar and the keyboard ask. */
  private get standing(): Standing {
    const one = this.inspecting;
    const spec = one === null ? undefined : this.editor.drawing.symbols[one];
    return {
      opened: this.filing.opened,
      saved: this.filing.saved,
      drawings: this.filing.drawings.length,
      selection: this.editor.selection.size,
      editable: spec !== undefined && editable(spec.kind),
      undo: this.editor.canUndo,
      redo: this.editor.canRedo,
    };
  }

  /** One command, however it was asked for. A menu item and the key printed
   *  beside it come through here, so the two cannot diverge, and a command
   *  that is dead does nothing whichever way it was reached. */
  private run(id: CommandId): void {
    if (!COMMANDS[id].enabled(this.standing)) return;
    switch (id) {
      case "new":
        this.discard(null);
        return;
      // The drawings are the submenu's own items, so `Open` itself is only
      // ever the thing they hang off.
      case "open":
        return;
      case "save":
        void this.filing.save(this.editor);
        return;
      case "save-as": {
        const said = this.ask("Save as", this.filing.opened);
        void this.filing.saveAs(said, this.editor);
        return;
      }
      case "export-svg":
        this.exportSvg();
        return;
      case "undo":
        this.act((editor) => editor.undo());
        return;
      case "redo":
        this.act((editor) => editor.redo());
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
      case "properties":
        this.editSelected();
        return;
      case "zoom-in":
        this.zoom(1 / OUT);
        return;
      case "zoom-out":
        this.zoom(OUT);
        return;
      case "fit":
        this.fit();
        return;
      case "netlist":
        this.folding();
        return;
      // A command with no arm above narrows to something other than `never`
      // here and fails to typecheck, so adding one to `CommandId` cannot leave
      // a live menu item that does nothing. The same guarantee `GLYPHS` gives
      // over the same union, for the verb rather than the glyph.
      default: {
        const unhandled: never = id;
        return unhandled;
      }
    }
  }

  /** The netlist pane, put beside the canvas or taken away again. Shutting it
   *  unlights whatever transit was chosen in it: the pane is the only thing
   *  that lights a way and the only thing that could unlight one, so a way
   *  left lit with the pane gone would stay lit with nothing to clear it. */
  private folding(): void {
    this.netlist = !this.netlist;
    if (!this.netlist) this.chosen = null;
    this.redraw();
  }

  /**
   * The open drawing, written to a file the browser downloads.
   *
   * A Blob behind an `<a download>` and nothing else: the file is the user's
   * and not the repo's, so there is no store round trip and no new endpoint.
   * What is in it is the canvas's (`exported`); the name is the drawing's.
   */
  private exportSvg(): void {
    const canvas = this.renderRoot.querySelector<TcCanvas>("tc-canvas");
    if (canvas === null) return;
    const blob = new Blob([canvas.exported()], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${this.filing.opened}.svg`;
    link.click();
    // The click starts the download, which reads the url after this turn ends.
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  /** The properties of the one selected symbol. The right-click menu asks the
   *  same dialog about whatever is under the pointer instead. */
  private editSelected(): void {
    const name = this.inspecting;
    if (name === null) return;
    const spec = this.editor.drawing.symbols[name];
    if (spec !== undefined) this.editing = { name, spec };
  }

  // --- talking to the store -----------------------------------------------

  /** Throw the open drawing away for another, or for a new one — the two
   *  things that discard whatever has been drawn since the last save. Edits an
   *  operator would recognise as lost are asked about first; with nothing to
   *  lose there is nothing to ask, and the drawing opens as it always did
   *  (#101). What is asked about is `edits` and not `saved`: a canvas just
   *  started is unsaved and has nothing on it, and there is nothing to ask
   *  about (#136). */
  private discard(wanted: string | null): void {
    if (this.filing.edits) this.discarding = { wanted };
    else void this.opening(wanted);
  }

  /** The operator said the edits can go. */
  private discarded(): void {
    const pending = this.discarding;
    this.discarding = null;
    if (pending !== null) void this.opening(pending.wanted);
  }

  /** The operator said they cannot — by the Cancel button, by Escape, or by
   *  the dialog's own close. The editor is left exactly as it was: nothing has
   *  been read or reset by this point, the question having come first. */
  private kept(): void {
    this.discarding = null;
  }

  /**
   * What was asked for, once there is nothing in the way of it. A drawing
   * arrives with the netlist shut, whatever the last one left open, and with
   * no way lit: both belong to the railroad being replaced, and the netlist
   * is opened when something looks wrong rather than kept up (ADR-0024).
   *
   * A new drawing is named here, after the question and not before it: a
   * prompt answered and then a discard declined would have asked for nothing.
   * Fitting the canvas is what is left over for the shell — the two DOM
   * touches `Filing` cannot take with it, and it says whether a drawing
   * arrived to fit to.
   */
  private async opening(wanted: string | null): Promise<void> {
    this.netlist = false;
    this.chosen = null;
    const arrived =
      wanted === null
        ? await this.filing.create(this.ask("New railroad", ""), this.editor)
        : await this.filing.open(wanted, this.editor);
    if (!arrived) return;
    await this.updateComplete;
    this.fit();
  }

  // --- edits ---------------------------------------------------------------

  private edited(): void {
    this.filing.edited(this.editor);
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

  /** A one-field prompt. A dialog for a single word would be more of the
   *  editor than naming a drawing is worth (EDITOR.md's simplicity). */
  private ask(what: string, was: string): string | null {
    const said = window.prompt(what, was);
    return said === null || said.trim() === "" ? null : said.trim();
  }

  /** What the dialog handed back, which it only does for a name the drawing
   *  can take: it asks `symbolTrouble` before it closes, so the document's own
   *  guard has nothing left to catch here. */
  private applied(event: CustomEvent<Properties>): void {
    const { was, name, spec } = event.detail;
    this.editing = null;
    if (this.editor.edit(was, name, spec)) this.edited();
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
    //
    // A Shoelace control keeps a native input in its own shadow root, so the
    // path starts there and `closest` stops at the boundary without ever
    // reaching the host. Walking the path is what crosses it.
    if (
      event
        .composedPath()
        .some((node) => node instanceof HTMLElement && node.matches(CONTROLS))
    ) {
      return;
    }
    // The question about to discard the drawing is up, so the keyboard is the
    // dialog's: Escape answers it and nothing else reaches anything. `r`
    // rotating the selection behind a modal, or Escape clearing it while
    // taking the question down, is the same bug the open menu has below.
    if (this.discarding !== null) {
      if (event.key === "Escape") {
        event.preventDefault();
        this.kept();
      }
      return;
    }
    const meta = event.metaKey || event.ctrlKey;
    // A menu on the bar is down, so the keyboard is the menu's: `r` would
    // typeahead in the menu and rotate the selection behind it at once, and
    // Escape would close the menu and clear the selection. Escape closes the
    // menu, and closing it is all it does.
    //
    // A shortcut is not a bare key. The open menu prints `⌘S` beside Save, so
    // pressing it has to be that item (#85) — otherwise the key it just
    // taught does nothing while Chrome offers to save the page over the top.
    // It takes the menu up, the command having been chosen, and falls through
    // to the handlers below, which are the ones the item itself reaches.
    if (this.barMenu) {
      if (event.key === "Escape") {
        event.preventDefault();
        this.renderRoot.querySelector<TcMenubar>("tc-menubar")?.close();
        return;
      }
      if (!meta) return;
      this.renderRoot.querySelector<TcMenubar>("tc-menubar")?.close();
    }
    if (meta && event.key.toLowerCase() === "z") {
      event.preventDefault();
      this.run(event.shiftKey ? "redo" : "undo");
      return;
    }
    if (meta && event.key.toLowerCase() === "s") {
      event.preventDefault();
      this.run(event.shiftKey ? "save-as" : "save");
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

    // Every one of these is a command the bar also names, so the two cannot
    // come to mean different things, and one that is dead does nothing here
    // either — `r` with nothing selected does not mark the drawing unsaved
    // and ask `/review` again.
    switch (event.key) {
      case "Escape":
        this.editor.cancelWire();
        this.editor.clearSelection();
        this.redraw();
        return;
      case "r":
      case "R":
        this.run("rotate");
        return;
      case "f":
      case "F":
        this.run("flip");
        return;
      case "Delete":
      case "Backspace":
        event.preventDefault();
        this.run("delete");
        return;
      case "+":
      case "=":
        this.run("zoom-in");
        return;
      case "-":
        this.run("zoom-out");
        return;
      case "0":
        this.run("fit");
        return;
      case "n":
      case "N":
        this.run("netlist");
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
