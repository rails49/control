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
import "@shoelace-style/shoelace/dist/components/dialog/dialog.js";
import "@shoelace-style/shoelace/dist/themes/light.css";

import type { Kind } from "../symbols.generated.js";
import { COMMANDS, type CommandId, type Standing } from "../model/commands.js";
import { emptyDrawing, nameTrouble, type SymbolSpec } from "../model/drawing.js";
import { Editor } from "../model/editor.js";
import type { Chosen } from "../model/inspect.js";
import {
  listDrawings,
  readDrawing,
  review,
  saveDrawing,
  type Review,
  type UnpairedPortal,
} from "../model/store.js";
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

  @state() private drawings: string[] = [];
  @state() private opened = "";
  @state() private reviewed: Review | null = null;
  /** What is wrong outside the drawing — the store not answering, a save that
   *  did not land. It reads in the band, not among the findings, which are the
   *  things the person drawing has to fix (#84). */
  @state() private trouble: string | null = null;
  /** A name no drawing can wear, said of the one asked for by `New…` or
   *  `Save As…`. That one *is* the author's, so it is a finding. It lives
   *  until the next accepted edit, the same lifetime it had when it shared
   *  `trouble`: a refusal outliving what caused it would still be listed
   *  against a drawing that no longer has the problem. A symbol name is
   *  refused in the properties dialog instead, where it was typed, and never
   *  reaches here (ADR-0023).  */
  @state() private naming: string | null = null;
  @state() private saved = true;
  @state() private menu: MenuAt | null = null;
  /** Whether a menu on the bar is down. While one is, the keyboard is the
   *  menu's and nothing reaches the canvas. */
  @state() private barMenu = false;
  @state() private editing: { name: string; spec: SymbolSpec } | null = null;
  /** What is waiting on the operator's word before the open drawing is thrown
   *  away: the drawing to open, or `null` for a new one. `null` while nothing
   *  is waiting, which is the ordinary state. */
  @state() private discarding: { open: string | null } | null = null;
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
      <tc-header
        mode="editor"
        .drawing=${this.opened === "" ? null : this.opened}
        .unsaved=${!this.saved}
        .derives=${this.derives}
        .trouble=${this.trouble}
      ></tc-header>

      <tc-menubar
        .standing=${this.standing}
        .drawings=${this.drawings}
        @command=${(event: CustomEvent<CommandId>) => this.run(event.detail)}
        @open-drawing=${(event: CustomEvent<string>) => this.discard(event.detail)}
        @menu-open=${(event: CustomEvent<boolean>) => {
          this.barMenu = event.detail;
        }}
      ></tc-menubar>

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
        .taken=${Object.keys(this.editor.drawing.symbols)}
        @properties=${this.applied}
        @properties-closed=${() => {
          this.editing = null;
        }}
      ></tc-properties>

      ${this.discarding === null ? nothing : this.question(this.discarding.open)}
    `;
  }

  /** The one thing the editor asks rather than does. Edits the store has not
   *  been given are the operator's, and a menu click is a thin thing to lose
   *  an evening's drawing to (#101), so what would discard them says so and
   *  waits. It is the dialog the properties are edited in, not a native
   *  `confirm`, which the page cannot style and a browser may suppress. */
  private question(open: string | null) {
    // Nothing is open until a drawing is chosen, and what is drawn on the
    // canvas before that is still an evening's work.
    const losing = this.opened === "" ? "The canvas" : `'${this.opened}'`;
    const instead =
      open === null ? "Starting a new drawing" : `Opening '${open}'`;
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

  /** Everything wrong with the drawing, in one panel: the pins short of a
   *  wire, the portal labels that pair with nothing, and the refusal
   *  derivation came back with. The refusal names one unpaired label and
   *  stops, so the lines above it are what say how many there are. */
  private findings() {
    const red = this.reviewed?.red_pins ?? [];
    const lone = this.reviewed?.unpaired_portals ?? [];
    const refused = this.reviewed?.refused ?? null;
    const stacked = this.stacked();
    if (
      red.length === 0 &&
      lone.length === 0 &&
      refused === null &&
      stacked.length === 0 &&
      this.naming === null
    ) {
      return html`
        <div class="findings clean">
          <p>Every pin holds its wires.</p>
        </div>
      `;
    }
    return html`
      <div class="findings">
        ${this.naming === null ? nothing : html`<p>${this.naming}</p>`}
        ${stacked.map((where) => html`<p>${where} overlap</p>`)}
        ${red.length === 0
          ? nothing
          : html`<p>${red.length} pin(s) short of a wire: ${red.join(", ")}</p>`}
        ${lone.map((one) => html`<p>${wearing(one)}</p>`)}
        ${refused === null ? nothing : html`<p>${refused}</p>`}
      </div>
    `;
  }

  /** Whether the drawing derives, which is the whole of what the band says
   *  about the drawing itself (ADR-0024). Off the store's refusal and nothing
   *  else: an overlap and a symbol still lacking an address derive, and a
   *  drawing nothing has been asked about yet has nothing against it. A store
   *  that stops answering leaves the last review standing, so the mark neither
   *  appears nor clears on a fault that is not the author's. */
  private get derives(): boolean {
    return this.reviewed === null || this.reviewed.refused === null;
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

  /** Where the editor stands, as far as a command needs to know
   *  (model/commands.ts). Nothing here decides what is dead; that module
   *  does, and it is what both the bar and the keyboard ask. */
  private get standing(): Standing {
    const one = this.inspecting;
    const spec = one === null ? undefined : this.editor.drawing.symbols[one];
    return {
      opened: this.opened,
      saved: this.saved,
      drawings: this.drawings.length,
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
        void this.save();
        return;
      case "save-as":
        void this.saveAs();
        return;
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
    link.download = `${this.opened}.svg`;
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

  private async load(): Promise<void> {
    try {
      this.drawings = await listDrawings();
      this.trouble = null;
    } catch (failure) {
      this.trouble = `the store is not answering: ${String(failure)}`;
    }
  }

  /** Throw the open drawing away for another, or for a new one — the two
   *  things that discard whatever has been drawn since the last save. Edits
   *  the store has not been given are asked about first; with nothing to lose
   *  there is nothing to ask, and the drawing opens as it always did (#101). */
  private discard(open: string | null): void {
    if (this.saved) void this.opening(open);
    else this.discarding = { open };
  }

  /** The operator said the edits can go. */
  private discarded(): void {
    const pending = this.discarding;
    this.discarding = null;
    if (pending !== null) void this.opening(pending.open);
  }

  /** The operator said they cannot — by the Cancel button, by Escape, or by
   *  the dialog's own close. The editor is left exactly as it was: nothing has
   *  been read or reset by this point, the question having come first. */
  private kept(): void {
    this.discarding = null;
  }

  /** What was asked for, once there is nothing in the way of it. */
  private opening(open: string | null): Promise<void> {
    return open === null ? this.newDrawing() : this.open(open);
  }

  private async open(name: string): Promise<void> {
    try {
      this.editor.reset(await readDrawing(name));
      this.opened = name;
      // Staging is an edit, so a railroad that arrives without placement
      // opens with something to save rather than something already saved.
      this.saved = !this.editor.stage();
      this.trouble = null;
      await this.updateComplete;
      this.fit();
      await this.reviewNow(true);
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
      // The first save of a new name is what creates the file, so the list
      // that refuses taken names learns it here.
      if (!this.drawings.includes(this.opened)) {
        this.drawings = [...this.drawings, this.opened].sort();
      }
    } catch (failure) {
      this.trouble = String(failure);
    }
  }

  /** A named empty canvas, asked for up front: `untitled` is not a file
   *  anyone asked for, and nothing is written until the first Save, so an
   *  abandoned start leaves no file behind. */
  private async newDrawing(): Promise<void> {
    const name = this.named("New railroad", "");
    if (name === null) return;
    this.editor.reset(emptyDrawing(name));
    this.opened = name;
    this.saved = false;
    await this.updateComplete;
    this.fit();
    await this.reviewNow();
  }

  /** The fork: the open drawing, unsaved edits and all, written at once under
   *  a new name. The file under the old name keeps its last-saved state. */
  private async saveAs(): Promise<void> {
    if (this.opened === "") return;
    const name = this.named("Save as", this.opened);
    if (name === null) return;
    this.editor.rename(name);
    this.opened = name;
    await this.save();
  }

  /** One drawing name, asked for and checked. A refusal lands in the findings
   *  panel rather than a re-prompt; asking again is one click away. */
  private named(what: string, was: string): string | null {
    this.naming = null;
    const said = this.ask(what, was);
    if (said === null) return null;
    const trouble = nameTrouble(said, this.drawings);
    if (trouble === null) return said;
    this.naming = trouble;
    return null;
  }

  /**
   * A drawing mid-edit is normally not derivable, so a refusal comes back
   * inside a 200 and is shown; only a document that will not load at all is
   * an error worth reporting as one.
   *
   * A junction always has a valid name, so the names the drawing has not
   * settled are minted the moment the store says which junctions exist. The
   * write folds into the edit that caused it, and asking again with the names
   * in place is what makes the pane agree with the drawing. `opening` is the
   * one review that also replaces the names a person typed (ADR-0023), which
   * happens once, before anything is drawn from the answer.
   */
  private async reviewNow(opening = false): Promise<void> {
    try {
      const at = this.editor.revision;
      const first = await review(this.editor.drawing);
      this.trouble = null;
      this.naming = null;
      const named = opening
        ? this.editor.remint(first, at)
        : this.editor.settle(first, at);
      if (named) {
        // Opening a hand-written railroad has edits to save, because the names
        // it was written with are not the ones it now holds.
        this.saved = false;
        this.reviewed = await review(this.editor.drawing);
      } else {
        this.reviewed = first;
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
      default:
        return;
    }
  };
}

/** A portal label that pairs with nothing, as a sentence. A label pairs
 *  exactly two portals, so worn once and worn three times are one finding and
 *  the count is what the line has to say; the portals wearing it are where to
 *  look, and each of them carries the same label on the canvas. */
function wearing({ label, portals }: UnpairedPortal): string {
  const worn = portals.length === 1 ? "1 portal" : `${portals.length} portals`;
  return `portal label '${label}' is worn by ${worn}, not two: ${portals.join(
    ", ",
  )}`;
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-editor": TcEditor;
  }
}
