/**
 * The app: one railroad, a list of views of it, and the two rows of chrome
 * they share
 * ([ADR-0038](../../../docs/adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md)).
 *
 * It holds the loaded railroad — its name, the document, and what the store
 * says the document means — and hands it to whichever view is current. The
 * views hold what is theirs: the editor its selection and its dialogs, the run
 * view its session and what the bus has shown it. Which railroad they are
 * about is not one of those things, which is why it is here.
 *
 * It also holds everything the two rows need. The band is the system's, so the
 * picker that loads a railroad and the toggle that switches view report here;
 * the bar is the current view's document's, so a command comes here and is
 * either run against the document this holds or passed to the view that owns
 * the surface. The keyboard is the same single path — `model/commands.ts`
 * decides what is dead, and an item and the key printed beside it cannot come
 * to mean different things.
 *
 * Which railroad is loaded is set by whichever happened last: the band's
 * picker, or a session joined in the run view. That is interim — a session is
 * named by a scenario until [#171](https://github.com/rails49/control/issues/171),
 * after which the picker is the only setter — and it needs no mechanism beyond
 * the question this already asks before edits are thrown away.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, state } from "lit/decorators.js";
import "@shoelace-style/shoelace/dist/components/button/button.js";
import "@shoelace-style/shoelace/dist/components/dialog/dialog.js";
import "@shoelace-style/shoelace/dist/themes/light.css";

import { COMMANDS, type CommandId, type Standing } from "../model/commands.js";
import { emptyDrawing } from "../model/drawing.js";
import { Editor } from "../model/editor.js";
import { Filing } from "../model/filing.js";
import type { Run } from "../model/trace.js";
import { hashOf, viewOf, VIEWS, type ViewId } from "../model/views.js";
import { appStyles } from "./tc-app.styles.js";
import "./tc-editor.js";
import "./tc-header.js";
import "./tc-menubar.js";
import "./tc-panel.js";
import type { TcEditor } from "./tc-editor.js";
import type { TcMenubar } from "./tc-menubar.js";
import type { RunStatus, TcPanel } from "./tc-panel.js";
import { editable } from "./tc-properties.js";

/** One press of the zoom-out button, and the reciprocal for zoom in. A quarter
 *  again is about what the wheel gives for a comfortable turn of it. */
const OUT = 1.25;

/** What a keystroke belongs to rather than to the canvas: the controls the app
 *  puts on screen, and the native ones they are built from. */
const CONTROLS = "sl-input, sl-select, input, textarea";

/** What the run view says about itself before it has said anything. */
const QUIET: RunStatus = {
  joined: false,
  linked: false,
  boundary: null,
  run: null,
  trouble: null,
};

@customElement("tc-app")
export class TcApp extends LitElement {
  static override styles = appStyles;

  /** The loaded railroad's document, and the editing session over it. */
  private editor = new Editor(emptyDrawing("untitled"));

  /** Everything the store is asked and everything it says back
   *  (`model/filing.ts`): the railroad's name, whether it is saved, and what
   *  the store last said it means. None of it is `@state`, so it says when it
   *  has moved and the app redraws. */
  private filing = new Filing(() => this.redraw());

  /** The view that is current. The app opens in the run view: it is a control
   *  surface, and the editor is the setup tool you go to deliberately. */
  @state() private view: ViewId = VIEWS[0]!.id;

  /** Whether a menu on the bar is down. While one is, the keyboard is the
   *  menu's and nothing reaches the view. */
  @state() private barMenu = false;

  /** Whether the netlist pane is open in the editor. It is the bar's `View ▸
   *  Netlist` that opens it, so the flag is the bar's side of the app rather
   *  than the view's. */
  @state() private netlist = false;

  /** What is waiting on the operator's word before the loaded railroad is
   *  thrown away: the railroad wanted, or `null` for a new one, `null` being a
   *  choice and not the absence of one. `discarding` itself is `null` while
   *  nothing is waiting, which is the ordinary state. */
  @state() private discarding: { wanted: string | null } | null = null;

  /** What the run view says about itself: the bridge, how far the run has got,
   *  and what a session refused. The band reads it, and the run view is the
   *  only thing that knows any of it. */
  @state() private status: RunStatus = QUIET;

  override connectedCallback(): void {
    super.connectedCallback();
    window.addEventListener("keydown", this.key);
    window.addEventListener("hashchange", this.hashed);
    this.view = viewOf(location.hash);
    void this.filing.load();
  }

  override disconnectedCallback(): void {
    window.removeEventListener("keydown", this.key);
    window.removeEventListener("hashchange", this.hashed);
    super.disconnectedCallback();
  }

  override render() {
    const name = this.filing.opened === "" ? null : this.filing.opened;
    return html`
      <tc-header
        .drawing=${name}
        .drawings=${this.filing.drawings}
        .unsaved=${!this.filing.saved}
        .derives=${this.filing.derives}
        .trouble=${this.filing.trouble ?? this.status.trouble}
        .joined=${this.status.joined}
        .linked=${this.status.linked}
        .boundary=${this.status.boundary}
        .view=${this.view}
        @railroad-wanted=${(event: CustomEvent<string>) => this.discard(event.detail)}
        @view-wanted=${(event: CustomEvent<ViewId>) => this.showing(event.detail)}
        @picker-open=${(event: CustomEvent<boolean>) => {
          if (event.detail) this.renderRoot.querySelector<TcMenubar>("tc-menubar")?.close();
        }}
      ></tc-header>

      <tc-menubar
        .view=${this.view}
        .standing=${this.standing}
        .run=${this.status.run}
        @command=${(event: CustomEvent<CommandId>) => this.run(event.detail)}
        @run-wanted=${(event: CustomEvent<Run>) => this.held(event.detail)}
        @menu-open=${(event: CustomEvent<boolean>) => {
          this.barMenu = event.detail;
        }}
      ></tc-menubar>

      <tc-panel
        class=${this.view === "run" ? "" : "off"}
        .drawing=${this.editor.drawing}
        .review=${this.filing.reviewed}
        @railroad-wanted=${(event: CustomEvent<string>) => this.discard(event.detail)}
        @run-status=${(event: CustomEvent<RunStatus>) => {
          this.status = event.detail;
        }}
      ></tc-panel>

      <tc-editor
        class=${this.view === "edit" ? "" : "off"}
        .editor=${this.editor}
        .review=${this.filing.reviewed}
        .netlist=${this.netlist}
        @edit=${this.edited}
        @picked=${() => this.redraw()}
      ></tc-editor>

      ${this.discarding === null
        ? nothing
        : this.question(this.discarding.wanted)}
    `;
  }

  // --- the views ------------------------------------------------------------

  /** Switch view, and say so in the hash so a reload and a bookmark keep it.
   *  Nothing about the loaded railroad moves: the two views are of it, and it
   *  is this that holds it. */
  private showing(view: ViewId): void {
    if (this.view === view) return;
    this.view = view;
    location.hash = hashOf(view);
  }

  /** The hash changed under the app — a bookmark opened, a back button
   *  pressed — which is the same choice by another route. */
  private hashed = (): void => {
    this.view = viewOf(location.hash);
  };

  private get edit(): TcEditor | null {
    return this.renderRoot.querySelector<TcEditor>("tc-editor");
  }

  /** HOLD or GO, pressed on the bar. The socket is the run view's, so the
   *  press goes there: the bar draws the run's word and this carries it, and
   *  neither decides anything about the run. */
  private held(run: Run): void {
    this.renderRoot.querySelector<TcPanel>("tc-panel")?.press(run);
  }

  // --- the bar and the keyboard --------------------------------------------

  /** Where the app stands, as far as a command needs to know
   *  (model/commands.ts). Nothing here decides what is dead; that module
   *  does, and it is what both the bar and the keyboard ask. */
  private get standing(): Standing {
    const one = this.inspecting;
    const spec = one === null ? undefined : this.editor.drawing.symbols[one];
    return {
      opened: this.filing.opened,
      saved: this.filing.saved,
      selection: this.editor.selection.size,
      editable: spec !== undefined && editable(spec.kind),
      undo: this.editor.canUndo,
      redo: this.editor.canRedo,
      // The editor's canvas has a viewport; the run view's picture is fitted
      // to the sheet and gains one with the canvas merge (#168).
      zoomable: this.view === "edit",
    };
  }

  /** The one symbol the netlist pane inspects, where exactly one is selected.
   *  A group selection is a move about to happen, not a question about a
   *  frog. */
  private get inspecting(): string | null {
    const selected = [...this.editor.selection];
    return selected.length === 1 ? selected[0]! : null;
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
        this.edit?.editSelected();
        return;
      case "zoom-in":
        this.edit?.zoom(1 / OUT);
        return;
      case "zoom-out":
        this.edit?.zoom(OUT);
        return;
      case "fit":
        this.edit?.fit();
        return;
      case "netlist":
        this.netlist = !this.netlist;
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
   * The loaded railroad, written to a file the browser downloads.
   *
   * A Blob behind an `<a download>` and nothing else: the file is the user's
   * and not the repo's, so there is no store round trip and no new endpoint.
   * What is in it is the canvas's; the name is the railroad's.
   */
  private exportSvg(): void {
    const drawn = this.edit?.exported();
    if (drawn === undefined) return;
    const blob = new Blob([drawn], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${this.filing.opened}.svg`;
    link.click();
    // The click starts the download, which reads the url after this turn ends.
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  // --- the loaded railroad --------------------------------------------------

  /** The one thing the app asks rather than does. Edits the store has not been
   *  given are the operator's, and a click is a thin thing to lose an
   *  evening's drawing to (#101), so what would discard them says so and
   *  waits. It is a dialog of the app's own, not a native `confirm`, which the
   *  page cannot style and a browser may suppress. */
  private question(wanted: string | null) {
    // Nothing is loaded until a railroad is chosen, and what is drawn on the
    // canvas before that is still an evening's work.
    const losing =
      this.filing.opened === "" ? "The canvas" : `'${this.filing.opened}'`;
    const instead =
      wanted === null ? "Starting a new railroad" : `Opening '${wanted}'`;
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

  /** Throw the loaded railroad away for another, or for a new one — the two
   *  things that discard whatever has been drawn since the last save. Edits an
   *  operator would recognise as lost are asked about first; with nothing to
   *  lose there is nothing to ask, and the railroad opens as it always did
   *  (#101). What is asked about is `edits` and not `saved`: a canvas just
   *  started is unsaved and has nothing on it (#136).
   *
   *  It guards the band's picker and a session joined in the run view alike,
   *  both being ways the loaded railroad changes. */
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
   *  the dialog's own close. Nothing has been read or reset by this point, the
   *  question having come first. */
  private kept(): void {
    this.discarding = null;
  }

  /**
   * What was asked for, once there is nothing in the way of it. A railroad
   * arrives with the netlist shut, whatever the last one left open: it belongs
   * to the railroad being replaced, and the netlist is opened when something
   * looks wrong rather than kept up (ADR-0024).
   *
   * A new railroad is named here, after the question and not before it: a
   * prompt answered and then a discard declined would have asked for nothing.
   * Fitting the canvas is what is left over for the app — the two DOM touches
   * `Filing` cannot take with it, and it says whether a railroad arrived to
   * fit to.
   */
  private async opening(wanted: string | null): Promise<void> {
    this.netlist = false;
    const arrived =
      wanted === null
        ? await this.filing.create(this.ask("New railroad", ""), this.editor)
        : await this.filing.open(wanted, this.editor);
    if (!arrived) return;
    await this.updateComplete;
    this.edit?.fit();
  }

  /** A one-field prompt. A dialog for a single word would be more of the app
   *  than naming a railroad is worth (EDITOR.md's simplicity). */
  private ask(what: string, was: string): string | null {
    const said = window.prompt(what, was);
    return said === null || said.trim() === "" ? null : said.trim();
  }

  // --- edits ---------------------------------------------------------------

  private edited(): void {
    void this.filing.edited(this.editor);
  }

  private act(change: (editor: Editor) => void): void {
    change(this.editor);
    this.edited();
  }

  /** The views hold the same `Editor` across an edit, so Lit sees no changed
   *  property and would not re-render them. Asking directly is what makes a
   *  bar button show its effect without waiting for `/review`. */
  private redraw(): void {
    this.requestUpdate();
    this.edit?.redraw();
    this.renderRoot.querySelector<TcPanel>("tc-panel")?.requestUpdate();
  }

  // --- the keyboard ---------------------------------------------------------

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
    // The question about to discard the railroad is up, so the keyboard is the
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
    // The view's own commands, and then its verbs. Zoom is every view's, and
    // is asked for first so that it keeps working wherever there is a viewport
    // to move; the rest are the editor's document, and a bare `r` in the run
    // view must not turn a symbol nobody can see.
    switch (event.key) {
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
    }
    if (this.view !== "edit") return;
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
    // either — `r` with nothing selected does not mark the railroad unsaved
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
    "tc-app": TcApp;
  }
}
