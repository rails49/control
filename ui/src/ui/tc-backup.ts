/**
 * The backup dialog: whether this store is being kept anywhere, the press that
 * keeps it now, and the backups there are to come back to (#321).
 *
 * One dialog for all of it, because the questions are one question. A person
 * opening it either wants to know that their railroad is safe, to make it safe
 * this minute, or to get yesterday's drawing back, and each of those is
 * answered by the same three lines: where the store is, what backup has not
 * got, and what git last said.
 *
 * **It decides nothing.** Every rule is the store's — what a commit is called,
 * whether a restore is refused, what a missing remote means — and this draws
 * what came back and presses what a person chose
 * ([ADR-0053](../../../docs/adr/0053-backup-drives-git-and-does-not-own-it.md)).
 * git's words are shown as they came: the app knows nothing to add to them,
 * and paraphrasing a rejected push would be inventing an explanation.
 *
 * **A store that is no repository is offered the way in.** That is the
 * ordinary state of a fresh installation, and nothing here runs `git init`: a
 * program that made a repository behind somebody's back would be owning git
 * rather than driving it. What the dialog does instead is show the key the
 * store made for itself and take the address of an empty repository the
 * person made on github.com, which the store clones (#355). The key is the
 * public half; pasting it in the wrong place loses nothing.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import "@shoelace-style/shoelace/dist/components/button/button.js";
import "@shoelace-style/shoelace/dist/components/dialog/dialog.js";
import "@shoelace-style/shoelace/dist/components/input/input.js";

import type { Backing } from "../model/backup.js";
import type { Copy } from "../model/store.js";
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
  static override styles = backupStyles;

  /** What the app knows about backup, `null` while the dialog is shut. The
   *  same shape the properties dialog takes: closed is nothing to draw. */
  @property({ attribute: false }) backing: Backing | null = null;

  /** The backup a person has picked to come back to, `null` while none is.
   *  Restoring takes two presses — the one that chooses and the one that does
   *  it — rather than a row that restores where it is clicked. */
  @state() private picked: string | null = null;

  /** The address typed so far of the repository to adopt. */
  @state() private address = "";

  override render() {
    const backing = this.backing;
    if (backing === null) return nothing;
    const stands = backing.stands;
    return html`
      <sl-dialog open label="Backup" @sl-after-hide=${this.close}>
        ${stands === null
          ? html`<p class="hint">asking the store…</p>`
          : html`
              <p class="root">${stands.root}</p>
              ${stands.remote === null
                ? nothing
                : html`<p class="hint">the copy goes to ${stands.remote}</p>`}
              ${this.needs(stands.needs)}
              ${stands.repository
                ? html`${this.waiting(stands.outstanding)} ${this.copy(stands.copy)}`
                : this.adopt(stands.key, backing.busy)}
              ${this.key(stands.key, stands.repository)} ${this.said()}
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
        <sl-button slot="footer" @click=${this.close}>Close</sl-button>
        <sl-button
          slot="footer"
          variant="warning"
          ?disabled=${this.picked === null || backing.busy}
          @click=${this.restore}
        >
          Restore
        </sl-button>
      </sl-dialog>
    `;
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
   * The way in, for a store that is no repository: the address of an empty
   * one the person made, and the press that adopts it. Drawn under what
   * backup needs, which says what to make and where the key goes.
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
        : nothing}
    </div>`;
  }

  /**
   * The store's own key, the public half, for the repository's deploy keys.
   * Always there once the store has one: a key that has to be pasted again —
   * the repository was remade, the box was — is needed exactly when the
   * store is a repository already, so it folds away rather than going.
   */
  private key(key: string | null, repository: boolean) {
    if (key === null) return nothing;
    const shown = html`<pre class="key">${key}</pre>
      <sl-button size="small" @click=${() => void copy(key)}>Copy the key</sl-button>`;
    return repository
      ? html`<details class="key">
          <summary>this store's key</summary>
          ${shown}
        </details>`
      : shown;
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
   * The one thing in this dialog that is not about a press somebody just made.
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
   *  to get out of was backed up like any other. */
  private backups(backups: readonly { commit: string; said: string; when: string }[]) {
    if (backups.length === 0) {
      return html`<p class="hint">no backups yet</p>`;
    }
    return html`<ul class="backups">
      ${backups.map(
        (backup) => html`
          <li>
            <button
              class=${this.picked === backup.commit ? "on" : ""}
              aria-pressed=${this.picked === backup.commit}
              @click=${() => {
                this.picked = backup.commit;
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

  private restore(): void {
    if (this.picked !== null) void this.backing?.restore(this.picked);
  }

  /** Shut it. What was picked goes with it: the next time this opens, the
   *  history may be another one — a restore of its own is in it. */
  private close(): void {
    this.picked = null;
    this.address = "";
    this.dispatchEvent(
      new CustomEvent<void>("backup-closed", { bubbles: true, composed: true }),
    );
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
