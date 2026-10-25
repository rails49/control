/**
 * The settings dialog's Backup tab: whether this store is being kept
 * anywhere, the press that keeps it now, and the backups there are to come
 * back to (#321, #1075).
 *
 * One tab for all of it, because the questions are one question. A person
 * opening it either wants to know that their railroad is safe, to make it safe
 * this minute, or to get yesterday's drawing back, and each of those is
 * answered by the same three lines: where the store is, what backup has not
 * got, and what git last said. It is drawn in the tab and not in a dialog of
 * its own: `tc-settings` holds it in its `backup` slot, and the band's backup
 * note opens Settings on it.
 *
 * **It decides nothing.** Every rule is the store's — what a commit is called,
 * whether a restore is refused, what a missing remote means — and this draws
 * what came back and presses what a person chose
 * ([ADR-0053](../../../docs/adr/0053-backup-drives-git-and-does-not-own-it.md)).
 * The one rule it wears is the app's, `restoreRefusal` in `model/settings.ts`:
 * a restore waits while the physical layout could disagree with the store —
 * the loaded railroad absent from the backup, or the layout not yet having
 * said which railroad is loaded or whether the track has power (#688, #759).
 * Track power on does not refuse it: pressed with power on, Restore asks for
 * the drain on `power-wanted`, says "stopping trains…" with the stop sign
 * beside it, and restores once `tc49/layout/state/power` reads `off`;
 * closing Settings abandons the wait and leaves power as it is
 * ([ADR-0085](../../../docs/adr/0085-the-editor-saves-when-it-is-left-and-a-railroad-can-be-named-without-being-built.md),
 * decision 5). Trains on the layout do not hold it back: the rebuild keeps
 * the ones that still fit and lists the rest as unfit (#710, ADR-0071).
 * git's words are shown as they came: the app knows nothing to add to them,
 * and paraphrasing a rejected push would be inventing an explanation.
 *
 * **A store that is no repository is offered the way in.** That is the
 * ordinary state of a fresh installation, and nothing here runs `git init`: a
 * program that made a repository behind somebody's back would be owning git
 * rather than driving it. What the tab does instead is show the key the
 * store made for itself and take the address of an empty repository the
 * person made on github.com, which the store clones (#355). The key is the
 * public half; pasting it in the wrong place loses nothing.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { lookTheme } from "@rails49/look";
import "@shoelace-style/shoelace/dist/components/button/button.js";
import "@shoelace-style/shoelace/dist/components/icon/icon.js";
import "@shoelace-style/shoelace/dist/components/input/input.js";

import type { Backing } from "../model/backup.js";
import type { Backup, BackupDoc, Copy } from "../model/store.js";
import { Drain, restoreRefusal, STOPPING } from "../model/settings.js";
import type { Power } from "../model/trace.js";
import { backupStyles } from "./tc-backup.styles.js";

/** How long something has been waiting, in the coarsest words that are still
 *  true. Nothing here turns on an hour, and "2 days" is what a person checks
 *  a backup against. */
function days(since: number): string {
  const hours = Math.floor(since / 3600);
  if (hours < 1) return "less than an hour";
  if (hours < 48) return hours === 1 ? "an hour" : `${hours} hours`;
  return `${Math.floor(hours / 24)} days`;
}

@customElement("tc-backup")
export class TcBackup extends LitElement {
  static override styles = [lookTheme, backupStyles];

  /** What the app knows about backup, `null` while Settings is shut. The
   *  same shape the properties dialog takes: closed is nothing to draw. */
  @property({ attribute: false }) backing: Backing | null = null;

  /** The supply as the run reads it, `null` with no session joined. A
   *  restore changes the drawing a loaded railroad runs on, so it waits for
   *  the rails to be dead as picking a railroad does (#688), draining them
   *  first (ADR-0085). */
  @property({ attribute: false }) power: Power | null = null;

  /** The railroad the apps are running as the layout's row names it: `null`
   *  while the page has not heard the row, `""` while none is loaded. A
   *  backup without it would leave them running a railroad the store no
   *  longer holds (#688), and a row not heard says nothing either way (#759). */
  @property({ attribute: false }) railroad: string | null = null;

  /** What a restore would discard, in the words of the app's own discard
   *  question — `"the drawing"`, `"the roster"` or both — and `null` while
   *  nothing is unsaved. The page reloads after a restore that worked, and
   *  edits held in it are not on disk for the store to refuse over (#703). */
  @property({ attribute: false }) unsaved: string | null = null;

  /** Whether *New key* has been pressed once and is waiting to be confirmed:
   *  the key in use stops working until the new one is added, which is worth
   *  one question before a working backup is broken by accident (#688). */
  @state() private renewing = false;

  /** The backup a person has picked to come back to, `null` while none is.
   *  Restoring takes two presses — the one that chooses and the one that does
   *  it — rather than a row that restores where it is clicked. */
  @state() private picked: string | null = null;

  /** Whether Restore has been pressed over unsaved edits and is waiting to
   *  be told they may go, as *New key* waits (#703). */
  @state() private discarding = false;

  /** The address typed so far of the repository to adopt. */
  @state() private address = "";

  /** The restore held for a dead track (`model/settings.ts`). */
  private readonly drain = new Drain();

  /** Whether `drain` holds the restore, the tab saying "stopping
   *  trains…" and Restore dead until it acts or the wait is given up. */
  @state() private stopping = false;

  override willUpdate(changed: Map<string, unknown>): void {
    if (changed.has("backing") && this.backing === null) this.shut();
    if (changed.has("power")) this.drain.heard(this.power);
    this.stopping = this.drain.waiting;
  }

  override render() {
    const backing = this.backing;
    if (backing === null) return nothing;
    const stands = backing.stands;
    const refused = restoreRefusal(this.railroad, this.power, this.chosen(stands));
    return html`
      ${stands === null
        ? html`<p class="hint">asking the store…</p>`
        : html`
            <p class="root">${stands.root}</p>
            ${stands.remote === null
              ? nothing
              : html`<p class="hint">the copy goes to ${stands.remote}</p>`}
            ${this.needs(stands.needs)}
            ${stands.repository
              ? html`${this.waiting(stands.outstanding)} ${this.copy(stands.copy)}
                  <details class="move">
                    <summary>back up to another repository</summary>
                    ${this.adopt(stands.key, backing.busy)}
                  </details>`
              : this.adopt(stands.key, backing.busy)}
            ${this.key(stands.key, stands.repository, backing.busy)} ${this.said()}
            <div class="presses">
              <sl-button
                variant="primary"
                ?disabled=${backing.busy}
                @click=${() => void backing.now()}
              >
                Back up now
              </sl-button>
              <sl-button
                ?disabled=${backing.busy}
                @click=${() => void backing.automatic(!stands.automatic)}
              >
                ${stands.automatic
                  ? "Turn automatic backup off"
                  : "Turn automatic backup on"}
              </sl-button>
            </div>
            <h3>Backups</h3>
            ${this.backups(stands.backups)}
          `}
      ${backing.trouble === null
        ? nothing
        : html`<p class="wrong">${backing.trouble}</p>`}
      ${refused === null ? nothing : html`<p class="hint refused">${refused}</p>`}
      ${refused === null ? this.discard(backing.busy) : nothing}
      ${this.stopping ? this.stoppingTrains() : nothing}
      <div class="restore">
        <sl-button
          variant="warning"
          ?disabled=${this.picked === null || backing.busy || refused !== null || this.stopping}
          @click=${() => this.asked()}
        >
          Restore
        </sl-button>
      </div>
    `;
  }

  /** The backup picked, as the store last listed it: what a restore is
   *  checked against (`restoreRefusal`). */
  private chosen(stands: BackupDoc | null): Backup | undefined {
    return stands?.backups.find((backup) => backup.commit === this.picked);
  }

  /** What backup has not got, each in the words of the command that would
   *  give it. Nothing where nothing is missing — a line saying all is well is
   *  a line to read every time. */
  private needs(needs: readonly string[]) {
    if (needs.length === 0) return nothing;
    return html`<ul class="needs">
      ${needs.map((need) => html`<li>${need}</li>`)}
    </ul>`;
  }

  /**
   * The address of a repository the person made, and the press that backs up
   * to it: the way in for a store that is no repository, and folded away for
   * one that is, where the same press moves backup to an empty repository.
   * Which of those it is, and bringing a repository's backups into an empty
   * store, is the store's to say (#355, #688).
   */
  private adopt(key: string | null, busy: boolean) {
    return html`<div class="adopt">
      <sl-input
        label="Repository"
        placeholder="git@github.com:you/my-railroad.git"
        value=${this.address}
        @sl-input=${(event: Event) => {
          this.address = (event.target as HTMLInputElement).value;
        }}
      ></sl-input>
      <sl-button
        variant="primary"
        ?disabled=${busy || this.address.trim() === ""}
        @click=${() => void this.backing?.adopt(this.address)}
      >
        Back up to it
      </sl-button>
      ${key === null
        ? html`<p class="hint">
            this store has no key of its own, so git pushes with whatever this
            machine's ssh already has
          </p>`
        : html`<p class="hint">
            a deploy key opens one repository: remove it from a repository
            before deleting that repository, or GitHub refuses it on the next
            as already in use
          </p>`}
      <p class="hint">
        an empty repository is backed up to; one holding backups is brought
        into an empty store
      </p>
    </div>`;
  }

  /**
   * The store's own key, the public half, for the repository's deploy keys.
   * Always there once the store has one: a key that has to be pasted again —
   * the repository was remade, the box was — is needed exactly when the
   * store is a repository already, so it folds away rather than going.
   */
  private key(key: string | null, repository: boolean, busy: boolean) {
    if (key === null) return nothing;
    const shown = html`<pre class="key">${key}</pre>
      <sl-button size="small" @click=${() => void copy(key)}>Copy the key</sl-button>
      ${this.renewal(busy)}`;
    return repository
      ? html`<details class="key">
          <summary>this store's key</summary>
          ${shown}
        </details>`
      : shown;
  }

  /**
   * *New key*, for a key a deleted repository still holds — GitHub refuses one
   * key on two repositories. Asked once, because the key in use stops working
   * until the new one is added (#688).
   */
  private renewal(busy: boolean) {
    if (!this.renewing) {
      return html`<sl-button
        size="small"
        ?disabled=${busy}
        @click=${() => {
          this.renewing = true;
        }}
      >
        New key
      </sl-button>`;
    }
    return html`<p class="waiting">
        the key above stops working until the new one is added to the
        repository's deploy keys
      </p>
      <sl-button
        size="small"
        variant="warning"
        ?disabled=${busy}
        @click=${() => {
          this.renewing = false;
          void this.backing?.renewKey();
        }}
      >
        Replace the key
      </sl-button>
      <sl-button
        size="small"
        @click=${() => {
          this.renewing = false;
        }}
      >
        Keep this key
      </sl-button>`;
  }

  /** The documents that have moved since the last backup, named. It is what
   *  `Back up now` is about to commit and what a restore is refused over, so
   *  it is the one count worth drawing. */
  private waiting(outstanding: readonly string[]) {
    return outstanding.length === 0
      ? html`<p class="hint">nothing has moved since the last backup</p>`
      : html`<p class="waiting">
          waiting to be backed up: ${outstanding.join(", ")}
        </p>`;
  }

  /**
   * How the copy on the other machine stands.
   *
   * The one thing in this tab that is not about a press somebody just made.
   * `Back up now` answers with the commit, which is the backup and is made at
   * once; the copy off this machine is the next tick's and may not have
   * happened yet, so what it did last time is the honest thing to draw
   * (#321).
   */
  private copy(copy: Copy) {
    if (copy.waiting === 0) {
      return html`<p class="hint">the other machine has every backup</p>`;
    }
    const backups = copy.waiting === 1 ? "1 backup" : `${copy.waiting} backups`;
    const behind =
      copy.since === null ? "" : `, the oldest ${days(copy.since)} old`;
    return html`<p class=${copy.stale ? "wrong" : "waiting"}>
      not on the other machine yet: ${backups}${behind}
    </p>`;
  }

  /** What git last said, whether it worked or not. A refusal is marked as one
   *  and the words are git's either way. */
  private said() {
    const backing = this.backing;
    if (backing === null || backing.words === null) return nothing;
    return html`<p class=${backing.refusal ? "wrong" : "said"}>
      ${backing.words}
    </p>`;
  }

  /** The backups there are, newest first, each named by what moved in it. The
   *  newest is rarely the one wanted: the editing session a person is trying
   *  to get out of was backed up like any other. Above them, what a restore
   *  does to a run that is up, said before the press (#699), and that JMRI,
   *  which reads its profile in the store once at launch and nothing here can
   *  see, is quit first (#714). */
  private backups(backups: readonly Backup[]) {
    if (backups.length === 0) {
      return html`<p class="hint">no backups yet</p>`;
    }
    return html`<p class="hint">
        Restore puts the store back as the picked backup held it; the apps and
        this page then reload. Quit DecoderPro and PanelPro before restoring,
        and open them again after.
      </p>
      <ul class="backups">
      ${backups.map(
        (backup) => html`
          <li>
            <button
              class=${this.picked === backup.commit ? "on" : ""}
              aria-pressed=${this.picked === backup.commit}
              @click=${() => {
                this.picked = backup.commit;
                this.discarding = false;
              }}
            >
              <span class="when">${backup.when}</span>
              <span class="what">${backup.said}</span>
            </button>
          </li>
        `,
      )}
    </ul>`;
  }

  /** The press on Restore: over unsaved edits it asks first, since the
   *  reload after a restore that worked discards them; otherwise it
   *  restores (#703). */
  private asked(): void {
    if (this.unsaved !== null) {
      this.discarding = true;
      return;
    }
    void this.restore();
  }

  /** The question Restore asks over unsaved edits, nothing while it has not
   *  been asked. Answered either way, it goes. */
  private discard(busy: boolean) {
    if (!this.discarding || this.unsaved === null) return nothing;
    return html`<p class="waiting">
        ${this.unsaved} has edits that have not been saved; restoring discards
        them
      </p>
      <sl-button
        size="small"
        variant="danger"
        ?disabled=${busy}
        @click=${() => {
          this.discarding = false;
          void this.restore();
        }}
      >
        Discard and restore
      </sl-button>
      <sl-button
        size="small"
        @click=${() => {
          this.discarding = false;
        }}
      >
        Keep the edits
      </sl-button>`;
  }

  /** What the tab says while the restore waits for the track to go dead,
   *  and the stop sign beside it: `off` at once, a drain having no time
   *  limit. */
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

  /** Restore the picked backup once the track is dead, draining it first
   *  where it has power; with no railroad loaded the supply is not asked
   *  (`restoreRefusal`). */
  private restore(): void {
    const backing = this.backing;
    if (backing === null || this.picked === null) return;
    if (restoreRefusal(this.railroad, this.power, this.chosen(backing.stands)) !== null) return;
    const commit = this.picked;
    const asked = this.drain.begin(this.railroad === "" ? null : this.power, () => {
      void this.restoring(commit);
    });
    this.stopping = this.drain.waiting;
    if (asked !== null) this.powerWanted(asked);
  }

  /** The track is dead: the backup restored, and said so where it worked:
   *  what follows — the running apps and this page reading what it wrote —
   *  is the app's (#688). */
  private async restoring(commit: string): Promise<void> {
    const backing = this.backing;
    if (backing === null) return;
    if (!(await backing.restore(commit))) return;
    this.dispatchEvent(
      new CustomEvent<void>("restored", { bubbles: true, composed: true }),
    );
  }

  private powerWanted(power: Power): void {
    this.dispatchEvent(
      new CustomEvent<Power>("power-wanted", { detail: power, bubbles: true, composed: true }),
    );
  }

  /** Settings shut: the wait given up and power left as it is, and what was
   *  picked goes with it — the next time this opens, the history may be
   *  another one, a restore of its own being in it. */
  private shut(): void {
    this.drain.abandon();
    this.stopping = false;
    this.picked = null;
    this.address = "";
    this.renewing = false;
    this.discarding = false;
  }
}

/** The key onto the clipboard, where the browser allows it. Where it does
 *  not — a page not served over TLS, a browser asked too soon — the key is
 *  still on the screen to select, so a refusal here is nothing to say. */
async function copy(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // selectable on the screen either way
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-backup": TcBackup;
  }
}
