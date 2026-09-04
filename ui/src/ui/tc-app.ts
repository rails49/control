/**
 * The app: one railroad, a list of views of it, and the two rows of chrome
 * they share
 * ([ADR-0038](../../../docs/adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md)).
 *
 * It holds the loaded railroad — its name, the document, and what the store
 * says the document means — and hands it to whichever view is current. The
 * views hold what is theirs: the editor its selection and its dialogs, the run
 * view its session and what the bus has shown it, the throttle the train a
 * person picked and where they have put the lever. Which railroad they are
 * about is not one of those things, which is why it is here.
 *
 * **One session, and it is the run view's.** The throttle is a view of this
 * app with nothing of its own to join, so what it draws comes down from the
 * view that holds the broker's client and its gestures go back the same way
 * the band's power presses do (ui/THROTTLE.md). The stock screen takes the same route for
 * what it needs of the run: which trains are placed, which is what its length
 * guard is (ui/STOCK.md).
 *
 * It also holds everything the two rows need. The band is the system's, so the
 * toggle that switches view reports here; the bar is the current view's
 * document's, so a command comes here and is either run against the document
 * this holds or passed to the view that owns the surface. The keyboard is the same single path — `model/commands.ts`
 * decides what is dead, and an item and the key printed beside it cannot come
 * to mean different things.
 *
 * **The broker is the only thing that loads a railroad**
 * ([#371](https://github.com/rails49/control/issues/371)). One broker runs one
 * railroad and the layout interface says which on a retained row
 * ([ADR-0059](../../../docs/adr/0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md),
 * decision 2), so the run view reads that row and hands the name up here; this
 * reads the documents off the store. There is no picker, switching railroads
 * being restarting the apps, and the run view and this cannot come to name
 * different ones.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, state } from "lit/decorators.js";
import "@shoelace-style/shoelace/dist/components/button/button.js";
import "@shoelace-style/shoelace/dist/components/dialog/dialog.js";
import "@shoelace-style/shoelace/dist/themes/light.css";

import {
  COMMANDS,
  frozen,
  type CommandId,
  type Standing,
} from "../model/commands.js";
import { Backing } from "../model/backup.js";
import { emptyDrawing } from "../model/drawing.js";
import { Editor } from "../model/editor.js";
import { Filing } from "../model/filing.js";
import type { Cab } from "../model/throttle.js";
import type { Power, Run } from "../model/trace.js";
import { hashOf, viewOf, VIEWS, type ViewId } from "../model/views.js";
import { appStyles } from "./tc-app.styles.js";
import "./tc-backup.js";
import "./tc-editor.js";
import "./tc-header.js";
import "./tc-menubar.js";
import "./tc-panel.js";
import "./tc-stock.js";
import "./tc-throttle.js";
import type { TcBackup } from "./tc-backup.js";
import type { TcEditor } from "./tc-editor.js";
import type { TcMenubar } from "./tc-menubar.js";
import type { RunStatus, TcPanel } from "./tc-panel.js";
import type { ModeWanted, ThrottleWanted } from "./tc-throttle.js";
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
  run: null,
  power: null,
  draining: false,
  trouble: null,
  placed: [],
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

  /** What backup says about the store the app is served from, and the presses
   *  that drive it (`model/backup.ts`, ADR-0053). The store is the whole
   *  app's rather than a view's, which is why this is held here beside the
   *  filing and not inside the editing view. */
  private backing = new Backing(() => this.redraw());

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

  /** Whether the operator's word is being waited on before the loaded
   *  railroad is thrown away for a new one. `File ▸ New` is the only gesture
   *  that asks: the railroad itself arrives on the bus (#371), which is not a
   *  press anybody made. */
  @state() private discarding = false;

  /** Whether the stock view holds roster edits the store has not been given,
   *  as that view last said. The drawing's own are the filing's; the roster is
   *  the second document a person can lose when the railroad changes, and what
   *  would discard it asks first the same way (#415). */
  @state() private rosterEdits = false;

  /** Whether the backup dialog is up. The store is asked once when the app
   *  comes up and again whenever the dialog is opened: what a railroad that is
   *  not being backed up needs is to reach the person who never opens this
   *  (#321), and that costs one `GET /backup` a page load. */
  @state() private backingUp = false;

  /** What the run view says about itself: the broker, how far the run has
   *  got, and what went wrong. The band reads it, and the run view is the only
   *  thing that knows any of it. */
  @state() private status: RunStatus = QUIET;

  /** The trains there are to drive, one cab each, as the view holding the
   *  session works them out (`model/throttle.ts`). The throttle is a view of
   *  this app like the others and has no session: what it draws comes down
   *  here and its gestures go back the way the band's do (ui/THROTTLE.md). */
  @state() private cabs: readonly Cab[] = [];

  override connectedCallback(): void {
    super.connectedCallback();
    window.addEventListener("keydown", this.key);
    window.addEventListener("hashchange", this.hashed);
    this.view = viewOf(location.hash);
    void this.filing.load();
    // Asked for the File menu's mark rather than for the dialog: a copy that
    // has been failing for a day, and a railroad that has never been backed up
    // at all, are both things a person finds out by not being told.
    void this.backing.load();
  }

  override disconnectedCallback(): void {
    window.removeEventListener("keydown", this.key);
    window.removeEventListener("hashchange", this.hashed);
    super.disconnectedCallback();
  }

  override render() {
    const name = this.filing.opened === "" ? null : this.filing.opened;
    // One reading of the rule for the two that wear it: the band says why, and
    // the editing view is what it is about (model/commands.ts).
    const still = frozen(this.standing);
    return html`
      <tc-header
        .drawing=${name}
        .unsaved=${!this.filing.saved}
        .derives=${this.filing.derives}
        .trouble=${this.filing.trouble ?? this.status.trouble}
        .joined=${this.status.joined}
        .linked=${this.status.linked}
        .power=${this.status.power}
        .draining=${this.status.draining}
        .frozen=${still}
        .view=${this.view}
        @power-wanted=${(event: CustomEvent<Power>) => this.supplying(event.detail)}
        @view-wanted=${(event: CustomEvent<ViewId>) => this.showing(event.detail)}
      ></tc-header>

      <tc-menubar
        .view=${this.view}
        .standing=${this.standing}
        .run=${this.status.run}
        .power=${this.status.power}
        @command=${(event: CustomEvent<CommandId>) => this.invoke(event.detail)}
        @run-wanted=${(event: CustomEvent<Run>) => this.held(event.detail)}
        @menu-open=${(event: CustomEvent<boolean>) => {
          this.barMenu = event.detail;
        }}
      ></tc-menubar>

      <tc-panel
        class=${this.view === "run" ? "" : "off"}
        .drawing=${this.editor.drawing}
        .review=${this.filing.reviewed}
        .current=${this.view === "run"}
        @railroad=${(event: CustomEvent<string>) => this.loaded(event.detail)}
        @run-status=${(event: CustomEvent<RunStatus>) => {
          this.status = event.detail;
        }}
        @cabs=${(event: CustomEvent<Cab[]>) => {
          this.cabs = event.detail;
        }}
      ></tc-panel>

      <tc-throttle
        class=${this.view === "throttle" ? "" : "off"}
        .cabs=${this.cabs}
        .power=${this.status.power}
        .linked=${this.status.linked}
        @mode-wanted=${(event: CustomEvent<ModeWanted>) =>
          this.running?.pressMode(event.detail.train, event.detail.mode)}
        @throttle-wanted=${(event: CustomEvent<ThrottleWanted>) =>
          this.running?.pressThrottle(event.detail.train, event.detail.speed)}
        @reversal-wanted=${(event: CustomEvent<string>) =>
          this.running?.pressReversal(event.detail)}
      ></tc-throttle>

      <tc-stock
        class=${this.view === "stock" ? "" : "off"}
        .railroad=${name}
        .current=${this.view === "stock"}
        .placed=${this.status.placed}
        @roster-edits=${(event: CustomEvent<boolean>) => {
          this.rosterEdits = event.detail;
        }}
      ></tc-stock>

      <tc-editor
        class=${this.view === "edit" ? "" : "off"}
        .editor=${this.editor}
        .review=${this.filing.reviewed}
        .netlist=${this.netlist}
        .frozen=${still}
        @edit=${this.edited}
        @picked=${() => this.redraw()}
      ></tc-editor>

      <tc-backup
        .backing=${this.backingUp ? this.backing : null}
        @backup-closed=${() => {
          this.backingUp = false;
        }}
      ></tc-backup>

      ${this.discarding ? this.question() : nothing}
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

  private get running(): TcPanel | null {
    return this.renderRoot.querySelector<TcPanel>("tc-panel");
  }

  /** The drawing surface the current view is showing, `null` where the current
   *  view draws no railroad. The editor and the run view share one canvas
   *  (#168), so zoom and fit are the same three commands across the two —
   *  they only have to reach the one on screen — and the throttle has no
   *  viewport to move, so `+` over it moves nothing rather than zooming a
   *  picture nobody can see. */
  private get surface(): TcEditor | TcPanel | null {
    switch (this.view) {
      case "edit":
        return this.edit;
      case "run":
        return this.running;
      default:
        return null;
    }
  }

  /** HOLD or GO, pressed on the bar. The broker's client is the run view's, so
   *  the press goes there: the bar draws the run's word and this carries it,
   *  and neither decides anything about the run. */
  private held(run: Run): void {
    this.running?.press(run);
  }

  /** ON, STOP or OFF, pressed on the band. The same path HOLD and GO take and
   *  for the same reason: the client is the run view's, and the band decides
   *  nothing about the railroad it is naming (ADR-0051). */
  private supplying(power: Power): void {
    this.running?.pressPower(power);
  }

  // --- the bar and the keyboard --------------------------------------------

  /** Where the app stands, as far as a command needs to know
   *  (model/commands.ts). Nothing here decides what is dead; that module
   *  does, and it is what both the bar and the keyboard ask. */
  private get standing(): Standing {
    // Trains on the layout freeze the drawing (ADR-0038, #169), and the run
    // view is what knows of any: the count comes up here with the rest of what
    // it says about itself, and goes back down to the band that says why and
    // the editing view whose gestures it kills.
    const one = this.inspecting;
    const spec = one === null ? undefined : this.editor.drawing.symbols[one];
    return {
      opened: this.filing.opened,
      saved: this.filing.saved,
      selection: this.editor.selection.size,
      editable: spec !== undefined && editable(spec.kind),
      undo: this.editor.canUndo,
      redo: this.editor.canRedo,
      placed: this.status.placed.length,
      backup: this.backing.standing,
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
   *  that is dead does nothing whichever way it was reached.
   *
   *  `invoke` and not `run`: a **run** is the railroad moving under a
   *  dispatcher (CONTEXT.md), which this app now has a view of, and a private
   *  method that dispatches menu items must not answer to that word. */
  private invoke(id: CommandId): void {
    if (!COMMANDS[id].enabled(this.standing)) return;
    switch (id) {
      case "new":
        this.discard();
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
        this.surface?.zoom(1 / OUT);
        return;
      case "zoom-out":
        this.surface?.zoom(OUT);
        return;
      case "fit":
        this.surface?.fit();
        return;
      case "netlist":
        this.netlist = !this.netlist;
        return;
      case "backup":
        this.backingUp = true;
        void this.backing.load();
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
  private question() {
    // Nothing is loaded until the broker names a railroad, and what is drawn
    // on the canvas before that is still an evening's work.
    const losing =
      this.filing.opened === "" ? "The canvas" : `'${this.filing.opened}'`;
    return html`
      <sl-dialog open label="Discard unsaved edits?" @sl-after-hide=${this.kept}>
        <p>
          ${losing} has edits that have not been saved: ${this.losing}.
          Starting a new railroad discards them.
        </p>
        <sl-button slot="footer" @click=${this.kept}>Cancel</sl-button>
        <sl-button slot="footer" variant="danger" @click=${this.discarded}>
          Discard
        </sl-button>
      </sl-dialog>
    `;
  }

  /** Which document the question is about: the drawing, the roster, or both.
   *  A person who spent the evening composing a rake is told that is what is
   *  at stake, rather than reading a sentence about a drawing they have not
   *  touched (#415). */
  private get losing(): string {
    if (!this.rosterEdits) return "the drawing";
    return this.filing.edits ? "the drawing and the roster" : "the roster";
  }

  /** Throw the loaded railroad away for a new one, which is what `File ▸ New`
   *  asks for and the one gesture of a person's that discards whatever has
   *  been drawn since the last save — the railroad itself arrives on the bus
   *  (#371), which nobody pressed. Edits an operator would recognise as lost
   *  are asked about first; with nothing to lose there is nothing to ask, and
   *  the canvas empties as it always did (#101). What is asked about is
   *  `edits` and not `saved`: a canvas just started is unsaved and has nothing
   *  on it (#136).
   *
   *  **Two documents, one question.** The drawing is the filing's and the
   *  roster is the stock view's, and changing the railroad throws both away —
   *  so either one being unsaved asks, and the words name which (#415). */
  private discard(): void {
    if (this.filing.edits || this.rosterEdits) this.discarding = true;
    else void this.opening(null);
  }

  /**
   * The railroad the broker runs, as the run view read it off the retained row
   * the layout interface owns
   * ([#371](https://github.com/rails49/control/issues/371)).
   *
   * One broker runs one railroad and switching is restarting the apps
   * (ADR-0059, decision 2), so this arrives once — as the run view's
   * subscription lands — and it is not a person's press: nothing is asked,
   * because there is nobody at the keyboard to have meant it.
   */
  private loaded(railroad: string): void {
    if (railroad === this.filing.opened) return;
    void this.opening(railroad);
  }

  /** The operator said the edits can go. */
  private discarded(): void {
    if (!this.discarding) return;
    this.discarding = false;
    void this.opening(null);
  }

  /** The operator said they cannot — by the Cancel button, by Escape, or by
   *  the dialog's own close. Nothing has been read or reset by this point, the
   *  question having come first. */
  private kept(): void {
    this.discarding = false;
  }

  /**
   * What was asked for, once there is nothing in the way of it. A railroad
   * arrives with the netlist shut, whatever the last one left open: it belongs
   * to the railroad being replaced, and the netlist is opened when something
   * looks wrong rather than kept up (ADR-0024).
   *
   * A new railroad is named here, after the question and not before it: a
   * prompt answered and then a discard declined would have asked for nothing.
   * Fitting the editor's canvas is what is left over for the app — the two DOM
   * touches `Filing` cannot take with it, and it says whether a railroad
   * arrived to fit to. The run view fits its own.
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
    this.running?.requestUpdate();
    // The dialog holds the same `Backing` across a press, so Lit sees no
    // changed property and would draw what git said before it said it.
    this.renderRoot.querySelector<TcBackup>("tc-backup")?.requestUpdate();
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
    if (this.discarding) {
      if (event.key === "Escape") {
        event.preventDefault();
        this.kept();
      }
      return;
    }
    // The backup dialog is up, so the keyboard is the dialog's the same way:
    // `r` behind a modal must not rotate the selection under it. Shoelace
    // closes on Escape itself, and `backup-closed` comes back from that.
    if (this.backingUp) return;
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
        this.invoke("zoom-in");
        return;
      case "-":
        this.invoke("zoom-out");
        return;
      case "0":
        this.invoke("fit");
        return;
    }
    if (this.view !== "edit") return;
    if (meta && event.key.toLowerCase() === "z") {
      event.preventDefault();
      this.invoke(event.shiftKey ? "redo" : "undo");
      return;
    }
    if (meta && event.key.toLowerCase() === "s") {
      event.preventDefault();
      this.invoke(event.shiftKey ? "save-as" : "save");
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
        this.invoke("rotate");
        return;
      case "f":
      case "F":
        this.invoke("flip");
        return;
      case "Delete":
      case "Backspace":
        event.preventDefault();
        this.invoke("delete");
        return;
      case "n":
      case "N":
        this.invoke("netlist");
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
