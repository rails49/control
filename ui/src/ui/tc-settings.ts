/**
 * The settings dialog: what belongs to all of control rather than to one
 * railroad (#733, #737,
 * [ADR-0072](../../../docs/adr/0072-the-railroad-is-loaded-from-a-settings-dialog-and-the-store-records-which.md)).
 *
 * Six tabs, seven where the box can turn off, the dialog opening on the one
 * `tab` names each time — Railroad from the gear, Backup from the band's
 * backup note (#899, #1075). **Railroad**
 * lists what the store holds, the loaded one ticked, and a press on another
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
 * being an ordinary one — and **Copy loaded as…** has the store copy every
 * document of the loaded railroad under it (#729); each then asks for what
 * it wrote, the same way a press on the list does. A row's **Delete** has
 * the store delete that railroad whole (#1074), asking once more in the row
 * first; the loaded railroad and the drawing the page holds have none, the
 * loaded one being deleted by loading another first, and nothing about it
 * waits on the track, which it does not touch. **Backup** is a slot the
 * app fills with `tc-backup`, which draws itself in the tab rather than in a
 * dialog of its own: being sent from one dialog to another is a step that
 * does nothing. **Points**, after Railroad, sets the point gap (#1128): how
 * long `layout` waits after one point command before the next, or before the
 * move waiting on it goes. Its one field shows `point_gap` as
 * `tc49/layout/state/settings` says it, is dead with a hint until that row is
 * heard, and on a commit — a change, not each keystroke — asks for what was
 * typed on `settings-wanted`, the app publishing `settings_wanted`; what
 * `gapChange` refuses is not sent, and the tab says why. The field goes on
 * showing the row, not the press (ADR-0035). **Driving** and **Box**, after
 * Points, do the same for the driver's speeds at clear and at caution, in
 * percent of the locomotive's top speed, and for the throttle silence, the
 * installation's whatever railroad is loaded (#1134): each commit sends the
 * one field committed, as `speedChange` and `silenceChange` say.
 * **Shutdown** turns the box off (#745), and is drawn only
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
 * It is a dialog and not a view: a view shows or edits the loaded railroad,
 * and this chooses which one that is (ADR-0072, decision 1).
 *
 * **It decides nothing.** Why the Railroad tab or the Shutdown tab is
 * refused, and what a point gap, a speed or the silence sends, is `model/settings.ts`, and what is loaded is the row's; the app hands in
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

import { emptyDrawing, nameTrouble } from "../model/drawing.js";
import { canTurnOff, turnOff } from "../model/box.js";
import {
  ANSWER_MS,
  arrived,
  ASPECTS,
  boxRefusal,
  copyRefusal,
  Drain,
  gapChange,
  percentOf,
  POINT_GAP_MAX_S,
  refusal,
  SETTINGS_UNHEARD,
  silenceChange,
  speedChange,
  STOPPING,
  THROTTLE_SILENCE_MAX_S,
  THROTTLE_SILENCE_MIN_S,
  type SettingsChange,
  type Speeds,
  UNANSWERED,
} from "../model/settings.js";
import { copyRailroad, deleteRailroad, said, saveDrawing } from "../model/store.js";
import type { Power } from "../model/trace.js";
import { settingsStyles } from "./tc-settings.styles.js";

/** The fields of the settings tabs, each with its own reason refused. */
type SettingField = "gap" | keyof Speeds | "silence";

/** What the dialog says where the drawing a load would discard could not be
 *  saved first; the band's trouble chip says why (ADR-0085). */
const UNSAVED = "the drawing could not be saved, so nothing was loaded";

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

  /** What a load would discard, in `Railroad.unsaved`'s words
   *  (`model/railroad.ts`), `null` while nothing is unsaved. The drawing is
   *  not among it: `saving` saves that before a load (ADR-0085). */
  @property({ attribute: false }) unsaved: string | null = null;

  /** Asked before a pick, New or Copy loaded as…: the drawing saved where a
   *  save is owed, answering whether nothing is left unsaved. Where something
   *  is, nothing is loaded and nothing written (ADR-0085, decision 1). */
  @property({ attribute: false }) saving: () => Promise<boolean> = () =>
    Promise.resolve(true);

  /** The drawing the page holds, `Filing.opened`'s, `""` while none is. */
  @property({ attribute: false }) opened = "";

  /** Whether the row names a railroad something was built from, as
   *  `RunStatus.built` has it. */
  @property({ attribute: false }) built = true;

  /** Whether the dispatcher has said its picture since the row named the
   *  railroad, as `RunStatus.allocated` has it. */
  @property({ attribute: false }) allocated = false;

  /** The point gap `tc49/layout/state/settings` says, in seconds, as
   *  `RunStatus.pointGap` has it: `null` while the row is unheard. */
  @property({ attribute: false }) pointGap: number | null = null;

  /** The driver's speeds `tc49/layout/state/settings` says, as
   *  `RunStatus.speeds` has them: `null` while the row is unheard. */
  @property({ attribute: false }) speeds: Speeds | null = null;

  /** The throttle silence `tc49/layout/state/settings` says, in seconds, as
   *  `RunStatus.throttleSilence` has it: `null` while the row is unheard. */
  @property({ attribute: false }) throttleSilence: number | null = null;

  /** The tab shown when the dialog opens: Railroad from the gear, Backup
   *  from the band's backup note. */
  @property() tab: "railroad" | "backup" = "railroad";

  /** The name typed for a railroad to make, as typed. */
  @state() private name = "";

  /** What the last New or Copy was refused with — a name that will not do,
   *  in `nameTrouble`'s words, or a write, in the store's — and `null` once
   *  one has gone through or the name is typed at again. */
  @state() private wrong: string | null = null;

  /** Why the setting last committed in each field was not sent, in
   *  `gapChange`'s, `speedChange`'s or `silenceChange`'s words; a field is
   *  absent once one is sent from it or the dialog opens again. */
  @state() private settingRefused: Partial<Record<SettingField, string>> = {};

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

  /** The tab whose press `drain` holds, `null` while it holds none: that tab
   *  says "stopping trains…" and its presses are dead. */
  @state() private stopping: "railroad" | "shutdown" | null = null;

  /** The railroad a press on the Railroad tab is for, from the press until
   *  it has `arrived`, `null` while none is: its row wears the spinner, and
   *  the tab's presses are dead. */
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
      <look-dialog open label="Settings" @sl-after-hide=${this.close}>
        <sl-tab-group>
          <sl-tab slot="nav" panel="railroad" ?active=${!backup}>Railroad</sl-tab>
          <sl-tab slot="nav" panel="points">Points</sl-tab>
          <sl-tab slot="nav" panel="driving">Driving</sl-tab>
          <sl-tab slot="nav" panel="box">Box</sl-tab>
          <sl-tab slot="nav" panel="backup" ?active=${backup}>Backup</sl-tab>
          ${this.canTurnOff ? html`<sl-tab slot="nav" panel="shutdown">Shutdown</sl-tab>` : nothing}
          <sl-tab-panel name="railroad" ?active=${!backup}>${this.railroads()}</sl-tab-panel>
          <sl-tab-panel name="points"><div class="points">${this.points()}</div></sl-tab-panel>
          <sl-tab-panel name="driving"><div class="driving">${this.driving()}</div></sl-tab-panel>
          <sl-tab-panel name="box"><div class="box">${this.box()}</div></sl-tab-panel>
          <sl-tab-panel name="backup" ?active=${backup}><slot name="backup"></slot></sl-tab-panel>
          ${this.canTurnOff
            ? html`<sl-tab-panel name="shutdown">
                <div class="shutdown">${this.shutdown()}</div>
              </sl-tab-panel>`
            : nothing}
        </sl-tab-group>
        <sl-button slot="footer" @click=${this.close}>Close</sl-button>
      </look-dialog>
    `;
  }

  /**
   * One button per railroad, the loaded one ticked, and beneath them the name
   * field with New and Copy loaded as…. Where the tab is refused the list
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
    const refused = refusal(this.railroad, this.power, this.unsaved);
    const copyRefused = copyRefusal(this.railroad, this.power, this.unsaved);
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
                    ?disabled=${refused !== null || busy}
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
      ${refused === null ? nothing : html`<p class="hint refused">${refused}</p>`}
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
          @click=${() => this.making(refused, (name) => saveDrawing(emptyDrawing(name)))}
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

  /**
   * The Points tab: the point gap, in seconds from `0` to `POINT_GAP_MAX_S`
   * in steps of `0.1`, `0` being no wait. Dead with a hint until the layout
   * has said its settings; a commit `gapChange` refuses stays in the field,
   * with the reason beneath it.
   */
  private points() {
    const unheard = this.pointGap === null;
    return html`
      <sl-input
        class="gap"
        type="number"
        label="Time between point commands"
        size="small"
        min="0"
        max=${POINT_GAP_MAX_S}
        step="0.1"
        ?disabled=${unheard}
        .value=${live(unheard ? "" : String(this.pointGap))}
        @sl-change=${(event: Event) => {
          const change = gapChange((event.target as HTMLInputElement).value, this.pointGap);
          this.committed(
            "gap",
            change !== null && "sent" in change ? { sent: { point_gap: change.sent } } : change,
          );
        }}
      >
        <span slot="suffix">s</span>
      </sl-input>
      <p class="hint">0 means no wait: each point command goes as soon as the last.</p>
      ${unheard ? html`<p class="hint unheard">${SETTINGS_UNHEARD}</p>` : nothing}
      ${this.refusedIn("gap")}
    `;
  }

  /**
   * The Driving tab (#1134): the speeds at clear and at caution, each in
   * percent of the locomotive's top speed from `1` to `100` in steps of `1`,
   * the row's fraction times 100 and sent as the percent over 100. Dead with
   * a hint until the layout has said its settings; a commit `speedChange`
   * refuses stays in its field, with the reason beneath it.
   */
  private driving() {
    const speeds = this.speeds;
    return html`
      ${ASPECTS.map(
        (aspect) => html`
          <sl-input
            class=${aspect}
            type="number"
            label=${`Speed at ${aspect}`}
            size="small"
            min="1"
            max="100"
            step="1"
            ?disabled=${speeds === null}
            .value=${live(speeds === null ? "" : String(percentOf(speeds[aspect])))}
            @sl-change=${(event: Event) =>
              this.committed(
                aspect,
                speedChange(
                  aspect,
                  (event.target as HTMLInputElement).value,
                  speeds === null ? null : speeds[aspect],
                ),
              )}
          >
            <span slot="suffix">%</span>
          </sl-input>
          ${this.refusedIn(aspect)}
        `,
      )}
      <p class="hint">In percent of the locomotive's top speed.</p>
      ${speeds === null ? html`<p class="hint unheard">${SETTINGS_UNHEARD}</p>` : nothing}
    `;
  }

  /**
   * The Box tab (#1134): how long a throttle holding trains may go silent
   * before `layout` lets go of them, in seconds from
   * `THROTTLE_SILENCE_MIN_S` to `THROTTLE_SILENCE_MAX_S` in steps of `1`.
   * The installation's, so it says it holds whatever railroad is loaded.
   * Dead with a hint until the layout has said its settings.
   */
  private box() {
    const unheard = this.throttleSilence === null;
    return html`
      <sl-input
        class="silence"
        type="number"
        label="Let go of a silent throttle's trains after"
        size="small"
        min=${THROTTLE_SILENCE_MIN_S}
        max=${THROTTLE_SILENCE_MAX_S}
        step="1"
        ?disabled=${unheard}
        .value=${live(unheard ? "" : String(this.throttleSilence))}
        @sl-change=${(event: Event) =>
          this.committed(
            "silence",
            silenceChange((event.target as HTMLInputElement).value, this.throttleSilence),
          )}
      >
        <span slot="suffix">s</span>
      </sl-input>
      ${this.refusedIn("silence")}
      <p class="hint">This applies whatever railroad is loaded.</p>
      ${unheard ? html`<p class="hint unheard">${SETTINGS_UNHEARD}</p>` : nothing}
    `;
  }

  /** Why the last commit in `field` was not sent, beneath it. */
  private refusedIn(field: SettingField) {
    const refused = this.settingRefused[field];
    return refused === undefined ? nothing : html`<p class="hint wrong">${refused}</p>`;
  }

  /** A setting committed in `field`: asked for on `settings-wanted` where
   *  the model's rule sends it, and the reason kept where it refuses. */
  private committed(
    field: SettingField,
    change: { sent: SettingsChange } | { refused: string } | null,
  ): void {
    const others = { ...this.settingRefused };
    delete others[field];
    if (change !== null && "refused" in change) {
      this.settingRefused = { ...others, [field]: change.refused };
      return;
    }
    this.settingRefused = others;
    if (change === null) return;
    this.dispatchEvent(
      new CustomEvent<SettingsChange>("settings-wanted", {
        detail: change.sent,
        bubbles: true,
        composed: true,
      }),
    );
  }

  /** The row of the railroad whose Delete was pressed: what deleting it
   *  costs, and **Delete** and **Cancel**, the question the Shutdown tab
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

  /** What a tab says while its press waits for the track to go dead, and the
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
   * The Shutdown tab. **Turn the server off…** is dead while the rule refuses or a
   * request is out, with the rule's reason beneath; pressed, it gives way to
   * what turning off costs and **Turn off** and **Cancel**. **Turn off** with
   * the track live drains it first, and the tab says so with the stop sign
   * beside it. Once the request is taken the tab says to unplug the box and
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
    if (refusal(this.railroad, this.power, this.unsaved) !== null) return;
    this.picking(name);
    this.draining("railroad", this.supply, () => void this.loading(name));
  }

  /** The track is dead: the drawing saved, then the railroad asked for. */
  private async loading(name: string): Promise<void> {
    if (!(await this.saving())) {
      this.wrong = UNSAVED;
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

  /** The track is dead: the drawing saved, `write` made under `name`, and
   *  what it wrote asked for. */
  private async writingAs(name: string, write: (name: string) => Promise<void>): Promise<void> {
    this.writing = true;
    try {
      if (!(await this.saving())) {
        this.wrong = UNSAVED;
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

  /** `act` once the track is dead, `tab` saying so until then, and the drain
   *  asked for where the track has power (`Drain`). */
  private draining(tab: "railroad" | "shutdown", power: Power | null, act: () => void): void {
    this.drain.abandon();
    this.stopping = tab;
    if (tab === "shutdown") this.turning = "stopping";
    this.acted = false;
    const asked = this.drain.begin(power, () => {
      this.acted = true;
      act();
    });
    this.held();
    if (asked !== null) this.powerWanted(asked);
  }

  /** What the dialog draws as waiting, brought in line with `drain`: once it
   *  acted or gave up, no tab says "stopping trains…". */
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

  /** A press on the Railroad tab for `name`: its row busy from here. */
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
