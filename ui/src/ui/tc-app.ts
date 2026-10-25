/**
 * The app: one railroad, a list of views of it, and the band and rail they
 * share
 * ([ADR-0038](../../../docs/adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md)).
 *
 * It holds the loaded railroad — its name, the document, and what the store
 * says the document means — and hands it to whichever view is current. The
 * views hold what is theirs: the editor its selection and its dialogs, the run
 * view its drag and its menu, the throttle where a person has put the slider
 * and the reverser. Which railroad they are about is not one of those
 * things, which is why it is here.
 *
 * **One session, and it is the app's** (`model/session.ts`, #756). The page's
 * one connection to the broker, and what follows from it — the railroad the
 * row names, the run's picture, power and the driving mode — is held here
 * beside the loaded railroad, and every press goes to it: the band's, its
 * driving control among them, the settings dialog's railroad and the
 * throttle's gestures (ui/THROTTLE.md). What it answers comes down as properties: the
 * panel model to the run view, the cabs to the throttle, and to the stock
 * screen which trains are placed and track power, which is what its length
 * guard reads (ui/STOCK.md).
 *
 * It also draws the chrome, out of `@rails49/look`'s elements
 * ([ADR-0073](../../../docs/adr/0073-the-chrome-comes-from-look.md)). The band
 * is the system's, so the gear that opens the settings dialog, where a
 * railroad is asked for, reports here; the rail is the current view's
 * document's, so a command comes here and is either run against the document
 * this holds or passed to the view that owns the surface, and the views that
 * switch report here too. The keyboard is the same single path —
 * `model/commands.ts` decides what is dead, and a button and the key its
 * tooltip names cannot come to mean different things.
 *
 * **The broker is the only thing that loads a railroad**
 * ([#371](https://github.com/rails49/control/issues/371)). One broker runs one
 * railroad and the layout interface says which on a retained row
 * ([ADR-0059](../../../docs/adr/0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md),
 * decision 2), so the session reads that row and hands the name up here, and
 * the loaded railroad (`model/railroad.ts`) reads the documents off the store
 * and holds them for every view (#758). The settings dialog does not load one
 * either: it asks on `tc49/layout/railroad_wanted` and this carries the press
 * out the way the band's power presses go
 * ([ADR-0060](../../../docs/adr/0060-the-railroad-is-chosen-while-the-apps-run-not-at-startup.md)),
 * so what is loaded is still whatever the row says and the session and this
 * cannot come to name different ones. The editor holds that railroad and no
 * other (ADR-0072, decision 3): nothing here starts or forks a drawing, and a
 * row naming none closes the one open, so nothing asks before edits are
 * thrown away — no gesture of a person's throws them away.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, state } from "lit/decorators.js";
import "@rails49/look";
import type { PowerState } from "@rails49/look";

import {
  COMMANDS,
  RAIL,
  backupWords,
  frozen,
  owed,
  stranded,
  asked,
  driving,
  supply,
  type CommandId,
  type Standing,
} from "../model/commands.js";
import { Backing } from "../model/backup.js";
import type { ClockChange, FastClock } from "../model/clock.js";
import { emptyDrawing } from "../model/drawing.js";
import { Editor } from "../model/editor.js";
import { Filing } from "../model/filing.js";
import { Railroad } from "../model/railroad.js";
import { brokerAt, connecting, QUIET, Session, type RunStatus } from "../model/session.js";
import { Wake } from "./wake.js";
import type { Cab } from "../model/throttle.js";
import type { DrivingMode, Power } from "../model/trace.js";
import { hashOf, shut, viewOf, VIEWS, type ViewId } from "../model/views.js";
import { widgetOf } from "../model/widgets.js";
import { appStyles } from "./tc-app.styles.js";
import "./tc-backup.js";
import "./tc-band-clock.js";
import "./tc-editor.js";
import "./tc-panel.js";
import "./tc-settings.js";
import "./tc-stock.js";
import "./tc-throttle.js";
import type { TcBackup } from "./tc-backup.js";
import type { TcEditor } from "./tc-editor.js";
import type { TcPanel } from "./tc-panel.js";
import type { TcStock } from "./tc-stock.js";
import type { FunctionWanted, ThrottleWanted } from "./tc-driving.js";
import type { TakeWanted } from "./tc-train-picker.js";
import { editable } from "./tc-properties.js";

/** One press of the zoom-out button, and the reciprocal for zoom in. A quarter
 *  again is about what the wheel gives for a comfortable turn of it. */
const OUT = 1.25;

/** What a keystroke belongs to rather than to the canvas: the controls the app
 *  puts on screen, and the native ones they are built from. */
const CONTROLS = "sl-input, sl-select, input, textarea";

/** How long the page waits after a restore before it reloads: long enough for
 *  the press asking for the loaded railroad again to leave on the bus. */
const RELOAD_MS = 500;

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

  /** The loaded railroad's documents — the drawing through the filing, the
   *  roster and the catalogue, the trains — read and held in one place
   *  (`model/railroad.ts`, #758). The row drives it, through `loaded`, and
   *  every view reads it rather than the store. A save of it that lands
   *  names it again on the session. */
  private railroad = new Railroad(
    this.filing,
    () => this.editor,
    () => this.redraw(),
    (railroad) => this.session?.pressRailroad(railroad),
  );

  /** The railroad the editor's canvas was last fitted to, so it is fitted
   *  once per railroad that arrives and left where a person put it after. */
  private fitted = "";

  /** What backup says about the store the app is served from, and the presses
   *  that drive it (`model/backup.ts`, ADR-0053). The store is the whole
   *  app's rather than a view's, which is why this is held here beside the
   *  filing and not inside the editing view. */
  private backing = new Backing(() => this.redraw());

  /** What stops the hourly ask about backup, held for when the app goes. */
  private unwatch: (() => void) | null = null;

  /** How the page reloads after a restore. A seam so a suite can see that it
   *  would, `location.reload` ending the document the suite runs in. */
  reload: () => void = () => location.reload();

  /** The view that is current. The app opens in the run view: it is a control
   *  surface, and the editor is the setup tool you go to deliberately. */
  @state() private view: ViewId = VIEWS[0]!.id;

  /** Whether the netlist pane is open in the editor. It is the rail's
   *  Netlist button that opens it, so the flag is the chrome's side of the app
   *  rather than the view's. */
  @state() private netlist = false;

  /** Whether the settings dialog is up: loading a railroad, and backup in its
   *  Backup tab (ADR-0072, #1075). The list of railroads and backup's standing
   *  are asked for again each time it opens, so a railroad another page made
   *  is there to load. Backup is asked when the app comes up and every hour
   *  after as well: what a railroad that is not being backed up needs is to
   *  reach the person who never opens this (#321), on a page that may stay
   *  open for days (#691). */
  @state() private settling = false;

  /** The tab Settings opens on: Railroad from the gear, Backup from the
   *  band's backup note. */
  @state() private settingsTab: "railroad" | "backup" = "railroad";

  /** The page's one session with the broker (`model/session.ts`, #756),
   *  opened as the app comes onto the page and let go of as it leaves. */
  private session: Session | null = null;

  /** The status and the cabs this last drew with. The session keeps each the
   *  same object until it says something new, so a frame that moves neither
   *  redraws the run view and not the whole page. */
  private drewStatus: RunStatus = QUIET;
  private drewCabs: readonly Cab[] = [];
  private drewClock: FastClock | null = null;

  /** The railroad the page owes an open of the Edit view: the row said
   *  `built: false` of it while power kept the view shut. `null` for none. */
  private unopened: string | null = null;

  /** The screen kept awake while any of this page's throttles holds a
   *  train, on the condition the session's `throttle_alive` runs on
   *  (`ui/wake.ts`, #854). */
  private wake: Wake | null = null;

  override connectedCallback(): void {
    super.connectedCallback();
    window.addEventListener("keydown", this.key);
    window.addEventListener("hashchange", this.hashed);
    window.addEventListener("pagehide", this.hiding);
    document.addEventListener("visibilitychange", this.hiding);
    this.view = viewOf(location.hash);
    this.session = new Session(brokerAt(location), connecting, {
      notify: () => this.told(),
      named: (railroad) => this.loaded(railroad),
    });
    this.wake = new Wake(navigator.wakeLock as WakeLock | undefined, document);
    void this.filing.load();
    // Asked for the band's note and the File menu's mark rather than for
    // the Backup tab: a copy that has been failing for a day, and a railroad
    // that has never been backed up at all, are both things a person finds
    // out by not being told. Asked again every hour, so a copy that went
    // behind after the page loaded still shows on a page left open for days
    // (#688).
    void this.backing.load();
    this.unwatch = this.backing.watch();
  }

  override disconnectedCallback(): void {
    this.unwatch?.();
    this.unwatch = null;
    window.removeEventListener("keydown", this.key);
    window.removeEventListener("hashchange", this.hashed);
    window.removeEventListener("pagehide", this.hiding);
    document.removeEventListener("visibilitychange", this.hiding);
    this.session?.end();
    this.session = null;
    this.wake?.end();
    this.wake = null;
    super.disconnectedCallback();
  }

  /** What the session says about the run: the broker, how far the run has
   *  got, and what went wrong. The band reads it, and the session is the only
   *  thing that knows any of it. */
  private get status(): RunStatus {
    return this.session?.status ?? QUIET;
  }

  /** The trains there are to drive, one cab each, as the session works them
   *  out (`model/throttle.ts`). The throttle is a view of this app like the
   *  others and has no session: what it draws comes down here and its
   *  gestures go back the way the band's do (ui/THROTTLE.md). */
  /** The throttle id of the throttle view's panel `slot`, the session's
   *  (`Session.throttleFor`): one function for the life of the page, handed
   *  to the view. */
  private readonly throttleFor = (slot: number): string =>
    this.session?.throttleFor(slot) ?? "";

  private get cabs(): readonly Cab[] {
    return this.session?.cabs ?? [];
  }

  /** The fast clock as the session last read it off `state/clock`, `null`
   *  for none (ADR-0090). The band's face and the throttle's station clock
   *  draw it. */
  private get clock(): FastClock | null {
    return this.session?.clock ?? null;
  }

  /**
   * The session said something moved. The run view paints every frame; the
   * app redraws only where the status, the cabs or the fast clock are a
   * different object from the ones it last drew with, so a frame that
   * changes nothing the app shows does not redraw the page.
   */
  private told(): void {
    this.running?.requestUpdate();
    if (
      this.status !== this.drewStatus ||
      this.cabs !== this.drewCabs ||
      this.clock !== this.drewClock
    )
      this.requestUpdate();
  }

  /** The loaded railroad's documents handed to the session on every render,
   *  which rebuilds its panel model only when the railroad or whether its
   *  drawing is valid has changed (`model/session.ts`). */
  override willUpdate(): void {
    this.session?.documents(this.editor.drawing, this.filing.reviewed, this.railroad.trains);
    // Power come on while the Edit view is current moves the page to the run
    // view (ADR-0085, decision 3). Leaving saves nothing with power on, so
    // the edits stay on the page, marked unsaved.
    if (shut(this.view, this.status.power) !== "") this.showing(VIEWS[0]!.id);
    // A railroad named and not built has a drawing that is not a valid
    // drawing, and the editor is where it is fixed: the page opens it there
    // when the row first says so — after a restart, a save or a pick — and
    // leaves a person who walks away from it where they went (ADR-0085,
    // decision 4, #885).
    // Where the row says so while power keeps the Edit view shut, the open
    // is owed to that railroad and made the first time power lets it, unless
    // the railroad is built again or another is named first (#906).
    const { built, power, railroad } = this.status;
    if (!built && this.drewStatus.built) this.unopened = railroad;
    if (built || railroad !== this.unopened) this.unopened = null;
    if (this.unopened !== null && shut("edit", power) === "") {
      this.unopened = null;
      this.showing("edit");
    }
    this.drewStatus = this.status;
    this.drewCabs = this.cabs;
    this.drewClock = this.clock;
  }

  override updated(): void {
    // A railroad that has arrived in the editor is fitted to once. The run view
    // fits its own.
    const opened = this.filing.opened;
    if (opened !== this.fitted) {
      this.fitted = opened;
      if (opened !== "") this.edit?.fit();
    }
    this.wake?.hold(this.cabs.some((cab) => this.session?.ours(cab.holder) === true));
  }

  override render() {
    const loaded = this.loadedRailroad;
    // The editing view is what the rule is about (model/commands.ts). A
    // restore does not wear it: its rebuild keeps the trains that fit (#710).
    const still = frozen(this.standing);
    return html`
      <look-shell>
        ${this.band(loaded)}
        <look-rail
          @look-view=${(event: CustomEvent<{ name: string }>) =>
            this.showing(viewOf(event.detail.name))}
        >
          ${VIEWS.map((view) => {
            // A view that does not open is disabled, saying why, and refused
            // in `showing`.
            const why = shut(view.id, this.status.power);
            return html`
              <look-view
                name=${view.id}
                icon=${view.icon}
                label=${view.label}
                reason=${why}
                ?disabled=${why !== ""}
                ?current=${view.id === this.view}
              ></look-view>
            `;
          })}
          ${RAIL[this.view].map(
            (group) => html`
              <look-group label=${group.name}>
                ${group.items.map((id) => this.command(id))}
              </look-group>
            `,
          )}
        </look-rail>

      <tc-panel
        class=${this.view === "run" ? "" : "off"}
        .drawing=${this.editor.drawing}
        .review=${this.filing.reviewed}
        .current=${this.view === "run"}
        .session=${this.session}
      ></tc-panel>

      <tc-throttle
        class=${this.view === "throttle" ? "" : "off"}
        .cabs=${this.cabs}
        .throttleFor=${this.throttleFor}
        .power=${this.status.power}
        .linked=${this.status.linked}
        .current=${this.view === "throttle"}
        .railroad=${this.status.railroad}
        .clock=${this.clock?.time ?? null}
        @take-wanted=${(event: CustomEvent<TakeWanted>) =>
          this.session?.pressTake(event.detail.train, event.detail.throttle)}
        @release-wanted=${(event: CustomEvent<string>) =>
          this.session?.pressRelease(event.detail)}
        @throttle-wanted=${(event: CustomEvent<ThrottleWanted>) =>
          this.session?.pressThrottle(
            event.detail.train,
            event.detail.speed,
            event.detail.throttle,
          )}
        @function-wanted=${(event: CustomEvent<FunctionWanted>) =>
          this.session?.pressFunction(
            event.detail.train,
            event.detail.throttle,
            event.detail.function,
            event.detail.on,
          )}
      ></tc-throttle>

      <tc-stock
        class=${this.view === "stock" ? "" : "off"}
        .railroad=${this.railroad}
        .placed=${this.status.placed}
        .power=${this.status.power}
        .loaded=${this.status.railroad}
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

      <tc-settings
        .open=${this.settling}
        .tab=${this.settingsTab}
        .drawings=${this.filing.drawings}
        .railroad=${this.status.railroad}
        .power=${this.status.power}
        .unsaved=${this.railroad.stock?.edits ? "the roster" : null}
        .saving=${this.keeping}
        .opened=${this.filing.opened}
        .built=${this.status.built}
        .allocated=${this.status.allocated}
        @railroad-wanted=${(event: CustomEvent<string>) => this.wanting(event.detail)}
        @railroad-arrived=${() => this.arrived()}
        @power-wanted=${(event: CustomEvent<Power>) => this.draining(event.detail)}
        @settings-closed=${() => {
          this.settling = false;
        }}
      >
        <tc-backup
          slot="backup"
          .backing=${this.settling ? this.backing : null}
          .power=${this.status.power}
          .railroad=${this.status.railroad}
          .unsaved=${this.unsaved}
          @restored=${() => this.restored()}
          @power-wanted=${(event: CustomEvent<Power>) => {
            event.stopPropagation();
            this.draining(event.detail);
          }}
        ></tc-backup>
      </tc-settings>
      </look-shell>
    `;
  }

  // --- the band and the rail ------------------------------------------------

  /**
   * The band: what is true of the whole system. After look's mark, the UI by
   * its name, control (org ADR-0019); then the loaded railroad's name and
   * whether it holds edits that could not be saved (`stranded`); then only
   * what a person would act on (#517) — what the app could not do, an
   * invalid drawing (its title the store's refusal), what the hardware says is wrong with the supply,
   * and backup that is not running — and the fast clock (ADR-0090);
   * then the driving control, the last of the band's items, and track power;
   * then the gear, and look's Help after it (org ADR-0020, #873).
   *
   * A fault is a chip with the whole sentence as its title, so a long one is
   * read by hovering. A frozen drawing says nothing here: with track power on
   * the Edit view does not open (ADR-0085, decision 3), and its button on the
   * rail says why.
   */
  private band(loaded: string | null) {
    const trouble = this.filing.trouble ?? this.railroad.trouble ?? this.status.trouble;
    const fault = this.status.fault;
    const note = this.backupNote();
    const power = supply(this.standing, this.status);
    return html`
      <look-band ui="control">
        <look-about
          name=${loaded ?? "no railroad loaded"}
          detail=${stranded(this.standing) ? "unsaved" : ""}
        ></look-about>
        ${this.filing.valid
          ? nothing
          : chip("invalid drawing", this.filing.reviewed?.refused ?? "")}
        ${trouble === null ? nothing : chip(trouble)} ${fault === null ? nothing : chip(fault)}
        ${note === null
          ? nothing
          : html`<look-band-press
              data-backup
              word=${note.says}
              label=${note.why}
              @look-press=${() => this.settingsOpen("backup")}
            ></look-band-press>`}
        <tc-band-clock
          .clock=${this.clock}
          @clock-wanted=${(event: CustomEvent<ClockChange>) =>
            this.session?.pressClock(event.detail)}
        ></tc-band-clock>
        ${this.drivingPress()}
        <look-power
          state=${power.state}
          reason=${power.reason}
          toggle-reason=${power.toggle}
          @look-power=${(event: CustomEvent<{ state: PowerState }>) =>
            void this.supplying(event.detail.state)}
        ></look-power>
        <look-gear @look-press=${() => this.settingsOpen("railroad")}></look-gear>
      </look-band>
    `;
  }

  /** One command on the rail, with its label and key as its tooltip. What is
   *  dead is `model/commands.ts`'s. */
  private command(id: CommandId) {
    const command = COMMANDS[id];
    return html`
      <look-command
        data-command=${id}
        icon=${command.icon}
        label=${command.label}
        key=${command.key ?? ""}
        ?disabled=${!command.enabled(this.standing)}
        @look-press=${() => this.invoke(id)}
      ></look-command>
    `;
  }

  /** The driving control, on the band in every view, the last of its items
   *  and just left of track power: the mode is the whole railroad's (#871,
   *  #873). What it shows and when it is
   *  dead is `driving` in `model/commands.ts`. */
  private drivingPress() {
    const { icon, label, next, dead } = driving(this.status.driving);
    return html`
      <look-band-press
        data-driving
        icon=${icon}
        label=${label}
        ?disabled=${dead}
        @look-press=${() => this.drive(next)}
      ></look-band-press>
    `;
  }

  // --- the views ------------------------------------------------------------

  /** Switch view, and say so in the hash so a reload and a bookmark keep it.
   *  Nothing about the loaded railroad moves: the two views are of it, and it
   *  is this that holds it. A view that does not open (`shut`) is not
   *  switched to. */
  private showing(view: ViewId): void {
    if (this.view === view || shut(view, this.status.power) !== "") return;
    this.viewing(view);
    location.hash = hashOf(view);
  }

  /** The hash changed under the app — a bookmark opened, a back button
   *  pressed — which is the same choice by another route. A hash naming a
   *  view that does not open is put back to the one that is current. */
  private hashed = (): void => {
    const view = viewOf(location.hash);
    if (shut(view, this.status.power) !== "") location.hash = hashOf(this.view);
    else if (this.view !== view) this.viewing(view);
  };

  /** Another view current. **Leaving the Edit view saves the drawing**,
   *  where a save is owed, and names the railroad again where it lands
   *  (`saveDrawing`, model/railroad.ts; ADR-0085). **The trains are read again
   *  when the run view becomes current**: the store is not on the bus, so
   *  nothing publishes a roster change (ADR-0010), and a person who adds a
   *  locomotive on the stock screen and switches to the run must see it
   *  (ui/STOCK.md). */
  private viewing(view: ViewId): void {
    if (this.view === "edit" && view !== "edit") {
      void this.railroad.saveDrawing(this.status.power);
    }
    this.view = view;
    if (view === "run") void this.railroad.reread();
  }

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

  /** The driving mode asked for on the band. The broker's client is the
   *  session's, so the press goes there: the band draws `state/driving` and
   *  this carries the press, and neither decides anything about the mode. */
  private drive(mode: DrivingMode): void {
    this.session?.pressDriving(mode);
  }

  /** Power asked for on the band, in look's words, and sent in the
   *  railroad's: the toggle's `off` is the drain and the stop sign is `off`
   *  at once (`asked`, ADR-0078). The same path the driving control takes and
   *  for the same reason: the client is the session's, and the band decides
   *  nothing about the railroad it is naming (ADR-0074).
   *
   *  ON over edits a save is owed for saves them first, and the session
   *  sends `on` once the apps have built what was saved (ADR-0085, decision
   *  2): the save and its naming are `saveDrawing` (model/railroad.ts), the
   *  wait — and what cancels it — `pressOnSaved` (model/session.ts). A save
   *  that did not land sends nothing: the band says why.
   *
   *  ON is refused outright while the loaded railroad reads `built: false`
   *  (`supply`; ADR-0085, decision 4): nothing is saved and nothing sent. */
  private supplying(press: PowerState): void {
    const wanted = asked(press);
    if (wanted === "on" && !this.status.built) return;
    if (wanted !== "on" || !owed(this.standing)) {
      this.session?.pressPower(wanted);
      return;
    }
    this.session?.pressOnSaved(
      this.filing.opened,
      this.railroad.saveDrawing(this.status.power),
    );
  }

  /** Power asked for by a dialog whose press waits on a dead track — the
   *  drain, or the stop sign beside "stopping trains…" (ADR-0085, decision
   *  5). Sent as the band's presses are, so an ON still waiting on a save
   *  or a build is overtaken (`pressPower`, model/session.ts). */
  private draining(power: Power): void {
    this.session?.pressPower(power);
  }

  /** A railroad pressed in the settings dialog, or one its New or Copy
   *  loaded as… just wrote (#737). The same path again, and it loads nothing
   *  here: the gesture goes out on the bus, the binding of the layout
   *  interface that is running answers it, and what arrives back is the row
   *  that says which railroad is loaded — which is the one thing this app
   *  opens a railroad on (ADR-0060). A gesture nothing answered, because the
   *  rails have power or the store has no such railroad, leaves the app
   *  exactly where it was. The store's list is asked for again, so a railroad
   *  the dialog just made is there to tick when the row names it. */
  private wanting(railroad: string): void {
    this.session?.pressRailroad(railroad);
    void this.filing.load();
  }

  /** The railroad the settings dialog asked for has landed (#902): the
   *  dialog goes, and the page shows the Run view — or the Edit view, where
   *  the row says nothing was built and the drawing is there to be fixed
   *  (ADR-0085, decision 4). */
  private arrived(): void {
    this.settling = false;
    this.showing(this.status.built ? VIEWS[0]!.id : "edit");
  }

  /** What the settings dialog asks before a pick, New or Copy loaded as…:
   *  the drawing saved where a save is owed, which the load would otherwise
   *  discard (ADR-0085, decision 1; `saveDrawing`, model/railroad.ts). It
   *  answers whether nothing is left unsaved, and the dialog loads nothing
   *  where something is. */
  private keeping = async (): Promise<boolean> => {
    await this.railroad.saveDrawing(this.status.power);
    return this.filing.saved;
  };

  // --- settings and backup -------------------------------------------------

  /** Settings, on `tab`: the gear opens it on Railroad and the band's backup
   *  note on Backup (#688, #1075). The store's list and backup's standing are
   *  asked for again, so the dialog shows what is there now and not what was
   *  there when the page loaded, the note's reading being up to an hour old. */
  private settingsOpen(tab: "railroad" | "backup"): void {
    this.settingsTab = tab;
    this.settling = true;
    void this.filing.load();
    void this.backing.load();
  }

  /** What the band says about backup, and why (`model/commands.ts`), `null`
   *  where it says nothing. */
  private backupNote(): { says: string; why: string } | null {
    const says = backupWords(this.backing.standing);
    return says === null ? null : { says, why: this.backing.why ?? says };
  }

  /**
   * A restore worked, and everything that read the store before it reads it
   * again (#688). The loaded railroad is asked for by name, which the binding
   * of the layout interface answers by building it again from the store, and
   * every app following its row rebuilds on that; then the page reloads, so
   * the editor cannot save back a copy it read before the restore — with no
   * railroad loaded too, the catalogue and every other document being read
   * fresh. The reload waits a moment, so the press is on the wire first.
   */
  private restored(): void {
    const loaded = this.loadedRailroad;
    if (loaded !== null) this.session?.pressRailroad(loaded);
    setTimeout(() => this.reload(), RELOAD_MS);
  }

  // --- the rail and the keyboard -------------------------------------------

  /** Where the app stands, as far as a command needs to know
   *  (model/commands.ts). Nothing here decides what is dead; that module
   *  does, and it is what both the rail and the keyboard ask. */
  private get standing(): Standing {
    // Track power freezes the drawing, and so does a drawing open with no
    // railroad heard; the loaded railroad's edits hold ON (ADR-0071). The
    // session is what knows any of it: power and the railroad's name are read
    // off it with the rest of what it says about the run, and go down to the
    // band that says why and the editing view whose gestures it kills.
    const one = this.inspecting;
    const spec = one === null ? undefined : this.editor.drawing.symbols[one];
    // Every widget has a name to set, so one selected alone is editable.
    const widget = one === null ? null : widgetOf(one);
    return {
      opened: this.filing.opened,
      saved: this.filing.saved,
      failed: this.filing.failed,
      selection: this.editor.selection.size,
      turnable: [...this.editor.selection].some((key) => widgetOf(key) === null),
      editable:
        (widget !== null && widget in this.editor.widgets) ||
        (spec !== undefined && editable(spec.kind)),
      undo: this.editor.canUndo,
      redo: this.editor.canRedo,
      power: this.status.power,
      loaded: this.status.railroad,
    };
  }

  /** The page hidden or going: what is owed is saved, with a write that
   *  outlives the page, and the railroad named again where it lands
   *  (`saveDrawing`, model/railroad.ts; ADR-0085, decision 1). */
  private hiding = (event: Event): void => {
    if (event.type === "pagehide" || document.visibilityState === "hidden") {
      void this.railroad.saveDrawing(this.status.power, true);
    }
  };

  /** The one symbol the netlist pane inspects, where exactly one is selected.
   *  A group selection is a move about to happen, not a question about a
   *  frog. */
  private get inspecting(): string | null {
    const selected = [...this.editor.selection];
    return selected.length === 1 ? selected[0]! : null;
  }

  /** One command, however it was asked for. A rail button and the key its
   *  title names come through here, so the two cannot diverge, and a command
   *  that is dead does nothing whichever way it was reached.
   *
   *  `invoke` and not `run`: a **run** is the railroad moving under a
   *  dispatcher (GLOSSARY.md), which this app now has a view of, and a private
   *  method that dispatches rail buttons must not answer to that word. */
  private invoke(id: CommandId): void {
    if (!COMMANDS[id].enabled(this.standing)) return;
    switch (id) {
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
      // A command with no arm above narrows to something other than `never`
      // here and fails to typecheck, so adding one to `CommandId` cannot leave
      // a live menu item that does nothing. The same guarantee `COMMANDS`
      // gives over the same union, for the verb rather than its label.
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

  /** The railroad the apps run, as the layout interface's row names it, and
   *  `null` where it names none or has not said (#732). The band and the
   *  name a restore asks for again are about what runs. A restore's refusal
   *  tells the two apart, and is handed the row itself (#759). */
  private get loadedRailroad(): string | null {
    const railroad = this.status.railroad;
    return railroad === null || railroad === "" ? null : railroad;
  }

  /** What changing the railroad would discard, `null` while nothing is
   *  unsaved: what a restore is refused over (#703, #733). A load is refused
   *  over the roster's alone, the drawing being saved first (ADR-0085). The
   *  loaded railroad's to say, holding both documents (#758). */
  private get unsaved(): string | null {
    return this.railroad.unsaved;
  }

  /**
   * The railroad the broker runs, as the session read it off the retained row
   * the layout interface owns
   * ([#371](https://github.com/rails49/control/issues/371)).
   *
   * One broker runs one railroad at a time. The row arrives as the session's
   * subscription lands, and again whenever another railroad is loaded while
   * the apps run (ADR-0060). Either way it is not a person's press: the
   * settings dialog asks on the bus and the load comes back here as a fact the
   * layout interface reports, so nothing is asked at this point. A row naming
   * none is a broker with no railroad loaded (#727), and the editor and the
   * stock view hold nothing for it: there is no drawing called `""` to open,
   * and whatever was open is a railroad nothing runs (ADR-0072, decision 3).
   *
   * Everything about the documents is the loaded railroad's
   * (`model/railroad.ts`). Another railroad arrives with the netlist shut,
   * whatever the last one left open: it belongs to the railroad being
   * replaced, and the netlist is opened when something looks wrong rather
   * than kept up (ADR-0024).
   */
  private loaded(railroad: string): void {
    if (railroad !== this.railroad.name) this.netlist = false;
    this.railroad.named(railroad);
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
   *  rail button show its effect without waiting for `/review`. */
  private redraw(): void {
    this.requestUpdate();
    this.edit?.redraw();
    this.running?.requestUpdate();
    // The stock view holds the same `Railroad`, and the `Stock` inside it
    // keeps its identity across an edit and a Save.
    this.renderRoot.querySelector<TcStock>("tc-stock")?.requestUpdate();
    // The Backup tab holds the same `Backing` across a press, so Lit sees no
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
    // The settings dialog is up, so the keyboard is the dialog's: `r` behind
    // a modal must not rotate the selection under it, and Escape clearing the
    // selection while taking the dialog down is the same bug the open menu
    // has below. Shoelace closes on Escape itself, and `settings-closed`
    // comes back from that.
    if (this.settling) return;
    // Nothing on the rail or the band comes down over the work, so there is no
    // state in which the keyboard belongs to the chrome (ADR-0073).
    const meta = event.metaKey || event.ctrlKey;
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
    // ⌘S was Save, which went with ADR-0085, and ⇧⌘S Save As, which went
    // with #734. Both are still taken from the browser, so a hand that
    // remembers them saves nothing as a web page either.
    if (meta && event.key.toLowerCase() === "s") {
      event.preventDefault();
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

    // Every one of these is a command the rail also names, so the two cannot
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

/** A fault on the band, its whole sentence the title of the chip that may
 *  cut it short, or `why` where the chip says less than the sentence. */
function chip(said: string, why: string = said) {
  return html`<look-chip title=${why}>${said}</look-chip>`;
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-app": TcApp;
  }
}
