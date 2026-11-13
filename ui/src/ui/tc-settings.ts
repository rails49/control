/**
 * The settings dialog: what belongs to all of control rather than to one
 * railroad (#733, #737,
 * [ADR-0072](../../../docs/adr/0072-the-railroad-is-loaded-from-a-settings-dialog-and-the-store-records-which.md)).
 *
 * Three tabs, the dialog opening on the one `tab` names each time — Railroad
 * from the gear, Backup from the band's backup note (#899, #1075). Railroad
 * and Installation are sections, each a tinted box with its name at its
 * head (#1246, #1248), Railroad's kept with the
 * loaded railroad and Installation's the installation's whatever railroad is
 * loaded, which its first line says (#1238). **Load a railroad**, Railroad's
 * first section, lists what the store holds, the loaded one ticked, and a press on another
 * asks for it: it publishes `railroad_wanted` through
 * the app and stops there, and the tick moves when the layout's row names the
 * new railroad, which is the only thing that loads one (ADR-0060). **A pick
 * looks busy until it has landed** (#902): the picked row wears a spinner
 * from the press — through the drain, the save and the write — until the
 * page holds the drawing, the row names it and the dispatcher has said its
 * picture since (`arrived`), and then the dialog closes on
 * `railroad-arrived`. Where that has not happened `ANSWER_MS` after the ask,
 * the spinner stops and the row says the layout did not answer. Beneath the list a name
 * and two presses make a railroad (decision 3): **New** writes an empty
 * drawing under the name — no roster and no script, a railroad with neither
 * being an ordinary one, or the page's drawing where no railroad is loaded
 * (#1225) — and **Copy loaded as…** has the store copy every
 * document of the loaded railroad under it (#729); each then asks for what
 * it wrote, the same way a press on the list does. A row's **Delete** has
 * the store delete that railroad whole (#1074), asking once more in the row
 * first; the loaded railroad and the drawing the page holds have none, the
 * loaded one being deleted by loading another first, and nothing about it
 * waits on the track, which it does not touch. **Backup** is a slot the
 * app fills with `tc-backup`, which draws itself in the tab rather than in a
 * dialog of its own: being sent from one dialog to another is a step that
 * does nothing. **Points (turnouts and slips)**, after Load a railroad, sets the point gap (#1128): how
 * long `layout` waits after one point command before the next, or before the
 * move waiting on it goes. Its one field shows `point_gap` as
 * `tc49/layout/state/settings` says it, is dead with a hint until that row is
 * heard, and on a commit — a change, not each keystroke — asks for what was
 * typed on `settings-wanted`, the app publishing `settings_wanted`; what
 * `settingChange` refuses is not sent, and the section says why. The field goes on
 * showing the row, not the press (ADR-0035), except that a refused commit
 * stays in it beside the reason until a commit is not refused or the row
 * says a different value for it (#1137). **Automatic driving**, after Points, does
 * the same for the driver's speeds at clear and at caution, in percent of
 * the locomotive's top speed (#1134): each commit sends the one field
 * committed. Installation's **Throttles** does the same for the throttle
 * silence (#1142), and **Sensors**, after it, for the sensor silence and the
 * arrival allowance (#1149, #1192). Each field of these sections is drawn
 * from its `SETTING_FIELDS` entry (#1185).
 * **Shutdown**, Installation's last section, turns the box off (#745), and is drawn only
 * where the installation says this box can be: it is asked each time the
 * dialog opens, and the rest of the dialog does not wait on it. The press asks
 * once more before anything is sent, and then says to unplug the box once its
 * lights go out.
 *
 * **A press that needs the track dead takes the power off itself**
 * ([ADR-0085](../../../docs/adr/0085-the-editor-saves-when-it-is-left-and-a-railroad-can-be-named-without-being-built.md),
 * decision 5). A load, New, Copy loaded as… and turning the box off, pressed
 * with power on, ask for the drain on `power-wanted`, say "stopping trains…"
 * with the stop sign beside it, and act once `tc49/layout/state/power` reads
 * `off` (`Drain`). The stop sign asks for `off` at once, a drain having no
 * time limit. Closing the dialog abandons the wait and leaves power as it is,
 * and a restore's wait in the Backup tab with it: the app hands `tc-backup`
 * no `backing` while the dialog is shut.
 *
 * The dialog is look's large one, growing with the window (look#48), so a
 * long backup message has room on a large screen.
 *
 * It is a dialog and not a view: a view shows or edits the loaded railroad,
 * and this chooses which one that is (ADR-0072, decision 1).
 *
 * **It decides nothing.** Why Load a railroad or Shutdown is
 * refused, and what a point gap, a speed or a silence sends, is `model/settings.ts`, and what is loaded is the row's; the app hands in
 * the row and the power. Whether a name will do is `nameTrouble`'s, as it is for the editor, and
 * a write is refused by the store in its own words (`said`): the dialog shows
 * whichever refused and asks for nothing, so nothing is loaded that was not
 * written.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { live } from "lit/directives/live.js";
import { lookTheme } from "@rails49/look";
import "@shoelace-style/shoelace/dist/components/button/button.js";
import "@shoelace-style/shoelace/dist/components/icon/icon.js";
import "@shoelace-style/shoelace/dist/components/input/input.js";
import "@shoelace-style/shoelace/dist/components/spinner/spinner.js";
import "@shoelace-style/shoelace/dist/components/tab/tab.js";
import "@shoelace-style/shoelace/dist/components/tab-group/tab-group.js";
import "@shoelace-style/shoelace/dist/components/tab-panel/tab-panel.js";

import { emptyDrawing, nameTrouble, type Drawing } from "../model/drawing.js";
import { canTurnOff, turnOff } from "../model/box.js";
import {
  ANSWER_MS,
  arrived,
  boxRefusal,
  committed,
  copyRefusal,
  Drain,
  pickRefusal,
  refusal,
  reheard,
  SETTING_FIELDS,
  SETTINGS_UNHEARD,
  shownIn,
  STOPPING,
  UNANSWERED,
  type LayoutSettings,
  type Refusals,
  type SettingField,
  type SettingsChange,
} from "../model/settings.js";
import { copyRailroad, deleteRailroad, said, saveDrawing } from "../model/store.js";
import type { Power } from "../model/trace.js";
import { settingsStyles } from "./tc-settings.styles.js";

/** What the dialog says where what a load would discard — the drawing, the
 *  roster or both — could not be saved first; the band and the stock view's
 *  bar say why (ADR-0085, #1233). */
function notLoaded(what: string): string {
  return `${what} could not be saved, so nothing was loaded`;
}

@customElement("tc-settings")
export class TcSettings extends LitElement {
  static override styles = [lookTheme, settingsStyles];

  /** Whether the dialog is up. Closed is nothing to draw, as `tc-backup`'s
   *  `backing` is. */
  @property({ type: Boolean }) open = false;

  /** The railroads there are to load, as the store lists them. */
  @property({ attribute: false }) drawings: readonly string[] = [];

  /** The loaded railroad as `RunStatus.railroad` has it: `null` while the
   *  layout has not said, `""` where it says none is loaded (#727). */
  @property({ attribute: false }) railroad: string | null = null;

  /** The supply as the run reads it, `null` with no session joined. */
  @property({ attribute: false }) power: Power | null = null;

  /** Asked before a pick, New or Copy loaded as…: the drawing and the roster
   *  saved where each holds edits, answering what is left unsaved in
   *  `Railroad.unsaved`'s words (`model/railroad.ts`), `null` for nothing.
   *  Where something is, nothing is loaded and nothing written, and the
   *  dialog says which (ADR-0085, decision 1; #1233). */
  @property({ attribute: false }) saving: () => Promise<string | null> = () =>
    Promise.resolve(null);

  /** The drawing the page holds where no railroad is loaded and it has
   *  edits, `null` otherwise. New writes it under the name typed, and a pick
   *  is refused (#1225). */
  @property({ attribute: false }) unfiled: Drawing | null = null;

  /** The drawing the page holds, `Filing.opened`'s, `""` while none is. */
  @property({ attribute: false }) opened = "";

  /** Whether the row names a railroad something was built from, as
   *  `RunStatus.built` has it. */
  @property({ attribute: false }) built = true;

  /** Whether the dispatcher has said its picture since the row named the
   *  railroad, as `RunStatus.allocated` has it. */
  @property({ attribute: false }) allocated = false;

  /** What `tc49/layout/state/settings` says, as `RunStatus.settings` has
   *  it: `null` while the row is unheard. */
  @property({ attribute: false }) settings: LayoutSettings | null = null;

  /** The tab shown when the dialog opens: Railroad from the gear, Backup
   *  from the band's backup note. */
  @property() tab: "railroad" | "backup" = "railroad";

  /** The name typed for a railroad to make, as typed. */
  @state() private name = "";

  /** What the last New or Copy was refused with — a name that will not do,
   *  in `nameTrouble`'s words, or a write, in the store's — and `null` once
   *  one has gone through or the name is typed at again. */
  @state() private wrong: string | null = null;

  /** The setting last committed in each field where it was not sent, with
   *  why in `settingChange`'s words; a field is absent once a commit from it
   *  is not refused, the row says a different value for it, or the dialog
   *  opens again (#1137). */
  @state() private settingRefused: Refusals = {};

  /** Whether a write is out: one at a time, so a second press cannot ask for
   *  a railroad the first is still writing. */
  @state() private writing = false;

  /** The railroad whose Delete was pressed, its row asking once more,
   *  `null` while no row asks. One at a time. */
  @state() private deleting: string | null = null;

  /** Whether the installation said this box can be turned off, asked each
   *  time the dialog opens and no until it answers. */
  @state() private canTurnOff = false;

  /** Where turning the box off has got to: not pressed, asking once more,
   *  the track draining, the request out, or the box going. */
  @state() private turning: "idle" | "asking" | "stopping" | "sending" | "going" = "idle";

  /** The press held for a dead track, at most one (`model/settings.ts`). */
  private readonly drain = new Drain();

  /** The section whose press `drain` holds, `null` while it holds none:
   *  that section says "stopping trains…" and its presses are dead. */
  @state() private stopping: "railroad" | "shutdown" | null = null;

  /** The railroad a press in Load a railroad is for, from the press until
   *  it has `arrived`, `null` while none is: its row wears the spinner, and
   *  the section's presses are dead. */
  @state() private picked: string | null = null;

  /** The railroad last asked for that did not arrive within `ANSWER_MS`,
   *  `null` where none: its row says so. */
  @state() private unanswered: string | null = null;

  /** Whether the press `drain` holds has been acted on: a drain that ends
   *  without it was abandoned, and the pick with it. */
  private acted = false;

  /** The `ANSWER_MS` wait once a railroad is asked for. */
  private answer: ReturnType<typeof setTimeout> | null = null;

  /** What the installation refused the last request with, or what kept it
   *  from arriving, `null` where nothing did. */
  @state() private refusedOff: string | null = null;

  override willUpdate(changed: Map<string, unknown>): void {
    if (changed.has("open") && !this.open) this.abandoned();
    if (changed.has("power")) {
      this.drain.heard(this.power);
      this.held();
    }
    this.landed();
    this.settingRefused = reheard(this.settingRefused, this.settings);
    if (changed.has("open") && this.open) {
      this.canTurnOff = false;
      if (this.turning !== "sending") this.turning = "idle";
      this.deleting = null;
      this.refusedOff = null;
      this.settingRefused = {};
      void canTurnOff().then((can) => {
        this.canTurnOff = can;
      });
    }
  }

  override disconnectedCallback(): void {
    this.unanswering();
    super.disconnectedCallback();
  }

  override render() {
    if (!this.open) return nothing;
    // Closed draws nothing, so each opening makes the tabs afresh, `tab` the
    // one shown.
    const backup = this.tab === "backup";
    return html`
      <look-dialog open label="Settings" size="large" @sl-after-hide=${this.close}>
        <sl-tab-group>
          <sl-tab slot="nav" panel="railroad" ?active=${!backup}>Railroad</sl-tab>
          <sl-tab slot="nav" panel="installation">Installation</sl-tab>
          <sl-tab slot="nav" panel="backup" ?active=${backup}>Backup</sl-tab>
          <sl-tab-panel name="railroad" ?active=${!backup}>
            <fieldset>
              <legend>Load a railroad</legend>
              ${this.railroads()}
            </fieldset>
            <fieldset>
              <legend>Points (turnouts and slips)</legend>
              <div class="points">${this.points()}</div>
            </fieldset>
            <fieldset>
              <legend>Automatic driving</legend>
              <div class="driving">${this.driving()}</div>
            </fieldset>
          </sl-tab-panel>
          <sl-tab-panel name="installation">
            <p class="hint">This applies whatever railroad is loaded.</p>
            <fieldset>
              <legend>Throttles</legend>
              <div class="throttles">${this.throttles()}</div>
            </fieldset>
            <fieldset>
              <legend>Sensors</legend>
              <div class="sensors">${this.sensors()}</div>
            </fieldset>
            ${this.canTurnOff
              ? html`<fieldset>
                  <legend>Shutdown</legend>
                  <div class="shutdown">${this.shutdown()}</div>
                </fieldset>`
              : nothing}
          </sl-tab-panel>
          <sl-tab-panel name="backup" ?active=${backup}><slot name="backup"></slot></sl-tab-panel>
        </sl-tab-group>
        <sl-button slot="footer" @click=${this.close}>Close</sl-button>
      </look-dialog>
    `;
  }

  /**
   * One button per railroad, the loaded one ticked, and beneath them the name
   * field with New and Copy loaded as…. Where the section is refused the list
   * and both presses are dead and say why once beneath the list, because a
   * list that is dead and silent reads as an app that is broken; Copy alone
   * is dead with nothing loaded, and says so under the presses. A press on
   * the loaded one asks for nothing (#101): the app would throw away
   * whatever has been drawn since when the row came back.
   *
   * A store listing no railroad still offers New: that is the box a first
   * railroad is made on (ADR-0072, decision 6).
   */
  private railroads() {
    const refused = refusal(this.railroad, this.power);
    const pickRefused = this.pickRefused;
    const copyRefused = copyRefusal(this.railroad, this.power);
    const unnamed = this.name.trim() === "";
    const stopping = this.stopping === "railroad";
    const busy = stopping || this.picked !== null;
    return html`
      ${this.drawings.length === 0
        ? html`<p class="hint">the store lists no railroad</p>`
        : html`<ul class="railroads">
            ${this.drawings.map((one) =>
              one === this.deleting
                ? this.deletingRow(one)
                : html`
                <li>
                  <button
                    class=${one === this.railroad ? "loaded" : ""}
                    ?disabled=${pickRefused !== null || busy}
                    @click=${() => void this.wanting(one)}
                  >
                    <span class="tick">${one === this.railroad ? "✓" : ""}</span>
                    <span class="label">${one}</span>
                    ${one === this.picked ? html`<sl-spinner></sl-spinner>` : nothing}
                    ${one === this.unanswered
                      ? html`<span class="unanswered">${UNANSWERED}</span>`
                      : nothing}
                  </button>
                  ${one === this.railroad || one === this.opened
                    ? nothing
                    : html`<button
                        class="delete"
                        title="Delete ${one}"
                        ?disabled=${this.railroad === null || busy || this.writing}
                        @click=${() => {
                          this.deleting = one;
                        }}
                      >
                        <sl-icon name="trash"></sl-icon>
                      </button>`}
                </li>
              `,
            )}
          </ul>`}
      ${pickRefused === null ? nothing : html`<p class="hint refused">${pickRefused}</p>`}
      ${stopping ? this.stoppingTrains() : nothing}
      <div class="making">
        <sl-input
          class="name"
          label="Name"
          size="small"
          value=${this.name}
          @sl-input=${(event: Event) => {
            this.name = (event.target as HTMLInputElement).value;
            this.wrong = null;
          }}
        ></sl-input>
        <sl-button
          class="new"
          size="small"
          ?disabled=${refused !== null || unnamed || this.writing || busy}
          @click=${() => this.making(refused, (name) => saveDrawing(this.newDrawing(name)))}
        >
          New
        </sl-button>
        <sl-button
          class="copy"
          size="small"
          ?disabled=${copyRefused !== null || unnamed || this.writing || busy}
          @click=${() => this.making(copyRefused, (name) => copyRailroad(this.railroad!, name))}
        >
          Copy loaded as…
        </sl-button>
      </div>
      ${copyRefused === null || refused !== null
        ? nothing
        : html`<p class="hint copy">${copyRefused}</p>`}
      ${this.wrong === null ? nothing : html`<p class="hint wrong">${this.wrong}</p>`}
    `;
  }

  /** The Points section: the point gap (#1128, #1250). */
  private points() {
    return this.setting(["gap"], nothing);
  }

  /** The Automatic driving section (#1134, #1250): the speeds at clear and at caution, in percent
   *  of the locomotive's top speed. */
  private driving() {
    return this.setting(
      ["clear", "caution"],
      html`<p class="hint">In percent of the locomotive's top speed.</p>`,
    );
  }

  /** The Throttles section (#1134, #1142): how long a throttle holding
   *  trains may go silent before `layout` lets go of them. */
  private throttles() {
    return this.setting(["silence"], nothing);
  }

  /** The Sensors section (#1149, #1192): how long a sensor may go unheard,
   *  and how long a move may take to arrive. */
  private sensors() {
    return this.setting(["sensorSilence", "arrivalAllowance"], nothing);
  }

  /**
   * A setting section: an input for each of `fields`, drawn from its
   * `SETTING_FIELDS` entry, then the section's `hint`. Each input is dead until
   * the row says its value, the section saying so beneath; a commit
   * `settingChange` refuses stays in its field, with the reason beneath it.
   */
  private setting(fields: readonly SettingField[], hint: unknown) {
    const unheard = fields.some((field) => this.unheard(field));
    return html`
      ${fields.map((field) => this.input(field))} ${hint}
      ${unheard ? html`<p class="hint unheard">${SETTINGS_UNHEARD}</p>` : nothing}
    `;
  }

  /** Whether the row has no value for `field`: unheard, or its field
   *  unreadable. */
  private unheard(field: SettingField): boolean {
    return this.settings === null || SETTING_FIELDS[field].of(this.settings) === null;
  }

  /** The input for `field`, as its `SettingSpec` says, and why its last
   *  commit was not sent beneath it. */
  private input(field: SettingField) {
    const spec = SETTING_FIELDS[field];
    return html`
      <sl-input
        class=${spec.class}
        type="number"
        label=${spec.label}
        size="small"
        min=${spec.min}
        max=${spec.max}
        step=${spec.step}
        ?disabled=${this.unheard(field)}
        .value=${live(shownIn(this.settingRefused, field, this.settings))}
        @sl-change=${(event: Event) => this.committed(field, event)}
      >
        <span slot="suffix">${spec.unit === "seconds" ? "s" : "%"}</span>
      </sl-input>
      ${this.refusedIn(field)}
    `;
  }

  /** Why the last commit in `field` was not sent, beneath it. */
  private refusedIn(field: SettingField) {
    const refused = this.settingRefused[field];
    return refused === undefined ? nothing : html`<p class="hint wrong">${refused.reason}</p>`;
  }

  /** What was typed in `field` committed, as `event` carries it: asked for
   *  on `settings-wanted` where `settingChange` sends it, and kept with the
   *  reason where it refuses. */
  private committed(field: SettingField, event: Event): void {
    const typed = (event.target as HTMLInputElement).value;
    const { refusals, sent } = committed(this.settingRefused, field, typed, this.settings);
    this.settingRefused = refusals;
    if (sent === null) return;
    this.dispatchEvent(
      new CustomEvent<SettingsChange>("settings-wanted", {
        detail: sent,
        bubbles: true,
        composed: true,
      }),
    );
  }

  /** The row of the railroad whose Delete was pressed: what deleting it
   *  costs, and **Delete** and **Cancel**, the question the Shutdown section
   *  asks before it turns the box off. */
  private deletingRow(name: string) {
    return html`<li class="deleting">
      <span class="asking">Delete ${name}? Its drawing, roster, script, clock and scenarios go.</span>
      <div class="presses">
        <sl-button
          class="confirm"
          size="small"
          variant="danger"
          ?disabled=${this.writing}
          @click=${() => void this.deletingRailroad(name)}
        >
          Delete
        </sl-button>
        <sl-button
          class="cancel"
          size="small"
          @click=${() => {
            this.deleting = null;
          }}
        >
          Cancel
        </sl-button>
      </div>
    </li>`;
  }

  /** **Delete** was pressed: the store deletes `name`, and the app asks for
   *  the list again on `railroads-changed`. A refusal — the railroad loaded
   *  on another page since, or the backup made first failing — shows the
   *  store's words, and the row stays. */
  private async deletingRailroad(name: string): Promise<void> {
    if (this.writing) return;
    this.writing = true;
    try {
      await deleteRailroad(name);
    } catch (failure) {
      this.wrong = said(failure);
      return;
    } finally {
      this.writing = false;
      this.deleting = null;
    }
    this.wrong = null;
    this.dispatchEvent(
      new CustomEvent<void>("railroads-changed", { bubbles: true, composed: true }),
    );
  }

  /** What a section says while its press waits for the track to go dead, and the
   *  stop sign beside it: `off` at once, a drain having no time limit. */
  private stoppingTrains() {
    return html`<div class="stopping">
      <span class="hint">${STOPPING}</span>
      <sl-button
        class="stop"
        size="small"
        variant="danger"
        title="Stop every train"
        @click=${() => this.powerWanted("off")}
      >
        <sl-icon slot="prefix" name="sign-stop-fill"></sl-icon>
        Stop
      </sl-button>
    </div>`;
  }

  /**
   * The Shutdown section. **Turn the server off…** is dead while the rule refuses or a
   * request is out, with the rule's reason beneath; pressed, it gives way to
   * what turning off costs and **Turn off** and **Cancel**. **Turn off** with
   * the track live drains it first, and the section says so with the stop
   * sign beside it. Once the request is taken the section says to unplug the box and
   * offers no press.
   */
  private shutdown() {
    if (this.turning === "stopping") return this.stoppingTrains();
    if (this.turning === "going") {
      return html`<p class="hint">The server is turning off. Unplug it once its lights go out.</p>`;
    }
    if (this.turning === "asking") {
      return html`
        <p class="asking">
          Every app on this server stops, and starting it again takes a person at the server.
        </p>
        <div class="presses">
          <sl-button class="off" size="small" variant="danger" @click=${this.turningOff}>
            Turn off
          </sl-button>
          <sl-button
            class="cancel"
            size="small"
            @click=${() => {
              this.turning = "idle";
            }}
          >
            Cancel
          </sl-button>
        </div>
      `;
    }
    const refused = boxRefusal(this.power);
    return html`
      <sl-button
        class="turn"
        ?disabled=${refused !== null || this.turning === "sending"}
        @click=${() => {
          this.refusedOff = null;
          this.turning = "asking";
        }}
      >
        Turn the server off…
      </sl-button>
      ${refused === null ? nothing : html`<p class="hint">${refused}</p>`}
      ${this.refusedOff === null ? nothing : html`<p class="hint wrong">${this.refusedOff}</p>`}
    `;
  }

  /** **Turn off** was pressed. The rule is read again, as `wanting` reads
   *  `refusal` again, so a supply gone unheard since the first press sends
   *  nothing; a live track is drained first. */
  private turningOff(): void {
    this.turning = "idle";
    if (boxRefusal(this.power) !== null) return;
    this.abandoned();
    this.draining("shutdown", this.power, () => void this.sendingOff());
  }

  /** The track is dead: the request goes. */
  private async sendingOff(): Promise<void> {
    this.turning = "sending";
    const refused = await turnOff();
    this.refusedOff = refused;
    this.turning = refused === null ? "going" : "idle";
  }

  /** A railroad was pressed. The dialog says which is wanted and stops there
   *  — the bus is what loads it, and the app is what carries the press. A
   *  live track is drained first; the drawing is saved once it is dead, a
   *  save waiting on power `off` (ADR-0085, decision 1). */
  private wanting(name: string): void {
    if (name === this.railroad || this.picked !== null) return;
    if (this.pickRefused !== null) return;
    this.picking(name);
    this.draining("railroad", this.supply, () => void this.loading(name));
  }

  /** The track is dead: the drawing and the roster saved, then the railroad
   *  asked for. */
  private async loading(name: string): Promise<void> {
    const left = await this.saving();
    if (left !== null) {
      this.wrong = notLoaded(left);
      this.picked = null;
      return;
    }
    this.wanted(name);
  }

  /**
   * New or Copy loaded as… was pressed: `write` is which, and `refused` is
   * why that one is dead, re-read as `wanting` re-reads the list's. The name
   * is checked against the list first, as the editor checks it
   * (`nameTrouble`), so a taken name is refused in the same words wherever it
   * is typed and the store is not asked; a name the list did not have but the
   * store does — made on another page since the dialog opened — is the
   * store's to refuse, and its words are shown. Only a write that went
   * through asks for the railroad, so what is loaded is always something that
   * exists. Copy's `from` is the row's railroad, which `copyRefusal` has
   * seen to be a name by the time the press is live. Each ends in a load, so
   * a live track is drained before anything is written.
   */
  private making(refused: string | null, write: (name: string) => Promise<void>): void {
    const name = this.name.trim();
    if (refused !== null || name === "" || this.writing || this.picked !== null) return;
    const trouble = nameTrouble(name, this.drawings);
    if (trouble !== null) {
      this.wrong = trouble;
      return;
    }
    this.picking(name);
    this.draining("railroad", this.supply, () => void this.writingAs(name, write));
  }

  /** Why a pick from the list is refused, `null` where it is not. */
  private get pickRefused(): string | null {
    return pickRefusal(this.railroad, this.power, this.unfiled !== null);
  }

  /** What New writes under `name`: the unfiled drawing where there is one,
   *  an empty one otherwise. */
  private newDrawing(name: string): Drawing {
    return this.unfiled === null ? emptyDrawing(name) : { ...this.unfiled, drawing: name };
  }

  /** The track is dead: the drawing and the roster saved, `write` made under
   *  `name`, and what it wrote asked for. An unfiled drawing is not saved
   *  first: New writes it. */
  private async writingAs(name: string, write: (name: string) => Promise<void>): Promise<void> {
    this.writing = true;
    try {
      const left = this.unfiled === null ? await this.saving() : null;
      if (left !== null) {
        this.wrong = notLoaded(left);
        this.picked = null;
        return;
      }
      await write(name);
    } catch (failure) {
      this.wrong = said(failure);
      this.picked = null;
      return;
    } finally {
      this.writing = false;
    }
    this.wrong = null;
    this.name = "";
    this.wanted(name);
  }

  /** The supply as a load reads it: `null` with no railroad loaded, a
   *  binding with nothing loaded reading none and there being no rails to
   *  change under a train (`refusal`). */
  private get supply(): Power | null {
    return this.railroad === "" ? null : this.power;
  }

  /** `act` once the track is dead, `section` saying so until then, and the
   *  drain asked for where the track has power (`Drain`). */
  private draining(
    section: "railroad" | "shutdown",
    power: Power | null,
    act: () => void,
  ): void {
    this.drain.abandon();
    this.stopping = section;
    if (section === "shutdown") this.turning = "stopping";
    this.acted = false;
    const asked = this.drain.begin(power, () => {
      this.acted = true;
      act();
    });
    this.held();
    if (asked !== null) this.powerWanted(asked);
  }

  /** What the dialog draws as waiting, brought in line with `drain`: once it
   *  acted or gave up, no section says "stopping trains…". */
  private held(): void {
    if (this.drain.waiting) return;
    if (this.turning === "stopping") this.turning = "idle";
    // A drain that ended without acting was given up, and so was the pick.
    if (this.stopping === "railroad" && !this.acted) this.picked = null;
    this.stopping = null;
  }

  /** The wait given up, power left as it is, and a pick given up with it:
   *  whatever the layout then answers, nothing here waits for it. */
  private abandoned(): void {
    this.drain.abandon();
    this.acted = false;
    this.held();
    this.picked = null;
    this.unanswered = null;
    this.unanswering();
  }

  /** A press in Load a railroad for `name`: its row busy from here. */
  private picking(name: string): void {
    this.abandoned();
    this.picked = name;
  }

  /** The pick, once it has `arrived`: the wait over, and the dialog closed
   *  on `railroad-arrived`, the app showing the view it lands in. */
  private landed(): void {
    const now = {
      opened: this.opened,
      railroad: this.railroad,
      built: this.built,
      allocated: this.allocated,
    };
    if (this.unanswered !== null && arrived(this.unanswered, now)) this.unanswered = null;
    if (this.picked === null || this.answer === null || !arrived(this.picked, now)) return;
    this.picked = null;
    this.unanswering();
    this.dispatchEvent(
      new CustomEvent<void>("railroad-arrived", { bubbles: true, composed: true }),
    );
  }

  /** The `ANSWER_MS` wait stopped, where one is running. */
  private unanswering(): void {
    if (this.answer !== null) clearTimeout(this.answer);
    this.answer = null;
  }

  private powerWanted(power: Power): void {
    this.dispatchEvent(
      new CustomEvent<Power>("power-wanted", { detail: power, bubbles: true, composed: true }),
    );
  }

  /** `name` asked for, and `ANSWER_MS` given to it. */
  private wanted(name: string): void {
    this.unanswering();
    this.answer = setTimeout(() => {
      this.answer = null;
      if (this.picked !== name) return;
      this.picked = null;
      this.unanswered = name;
    }, ANSWER_MS);
    this.dispatchEvent(
      new CustomEvent<string>("railroad-wanted", {
        detail: name,
        bubbles: true,
        composed: true,
      }),
    );
  }

  private close(): void {
    this.abandoned();
    this.dispatchEvent(
      new CustomEvent<void>("settings-closed", { bubbles: true, composed: true }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-settings": TcSettings;
  }
}
