/**
 * What the app knows about backing the store up: where it stands, what git
 * last said, and what could not be asked at all (#321).
 *
 * The app drives git and does not own it
 * ([ADR-0053](../../../docs/adr/0053-backup-drives-git-and-does-not-own-it.md)),
 * and this side of it drives less than that: git runs where the store is, so
 * everything here is a route and an answer. What it holds is the answer, so
 * the dialog draws one picture rather than four components each asking again.
 *
 * **A refusal is not a failure.** The store not being a repository, a remote
 * that cannot be reached and a restore over documents that were never backed
 * up all arrive inside a 200 with `ok` false, and they read as git's own
 * words. `trouble` is the other thing: the store did not answer at all, which
 * is what `Filing` calls by the same name and for the same reason.
 *
 * Like `Filing`, the store is a dependency rather than something reached for,
 * so a test drives the rules against a fake instead of forging HTTP answers to
 * reach rules that have nothing to do with HTTP (EDITOR.md#tests).
 */

import type { BackupStanding } from "./commands.js";
import {
  backUpNow,
  readBackup,
  restoreBackup,
  switchBackup,
  type BackupDoc,
} from "./store.js";

/** The backup routes, as the app uses them. */
export interface BackupStore {
  readBackup(): Promise<BackupDoc>;
  switchBackup(automatic: boolean): Promise<BackupDoc>;
  backUpNow(): Promise<BackupDoc>;
  restoreBackup(commit: string): Promise<BackupDoc>;
}

/** The store as it is over HTTP, which is what the app runs against. */
const live: BackupStore = { readBackup, switchBackup, backUpNow, restoreBackup };

export class Backing {
  private answer: BackupDoc | null = null;
  private wording: string | null = null;
  private refused = false;
  private wrong: string | null = null;
  private asking = false;

  constructor(
    private readonly notify: () => void,
    private readonly store: BackupStore = live,
  ) {}

  /** Where backup stands, `null` until it has been asked.
   *
   *  The app asks once when it comes up. It did not, on the reasoning that a
   *  person who never opens the dialog has no interest in git — which is
   *  exactly backwards for the two things `standing` reports (#321): somebody
   *  who never opens the dialog is who a railroad that is not being backed up
   *  has to reach. One `GET /backup` a page load is the cost. */
  get stands(): BackupDoc | null {
    return this.answer;
  }

  /**
   * What backup has to say from outside its own dialog, which the `Backup…`
   * item on the File menu marks itself with.
   *
   * `quiet` until it has been asked, and `quiet` for everything that is only
   * worth reading once the dialog is open. A store that is not a repository at
   * all reads as `never` like any other store with no backups: what a person
   * has to know is the same either way, and the dialog is where the difference
   * is spelled out.
   */
  get standing(): BackupStanding {
    if (this.answer === null) return "quiet";
    if (this.answer.copy.stale) return "behind";
    if (!this.answer.automatic && this.answer.backups.length === 0) {
      return "never";
    }
    return "quiet";
  }

  /** What git said about the last thing it was asked to do, `null` where it
   *  has not been asked to do anything this session. Kept whether it worked or
   *  not: the words are the whole of what this app can say about a rejected
   *  push, and a refusal that vanished would be a press that did nothing. */
  get words(): string | null {
    return this.wording;
  }

  /** Whether those words are a refusal rather than a report. */
  get refusal(): boolean {
    return this.refused;
  }

  /** The store not answering at all — not a refusal, which arrives as words
   *  above. */
  get trouble(): string | null {
    return this.wrong;
  }

  /** Whether a press is still in flight. What the dialog greys, so that two
   *  clicks on `Back up now` are not two commits. */
  get busy(): boolean {
    return this.asking;
  }

  /** Where backup stands, asked for when the dialog opens and after anything
   *  that could have moved it. */
  async load(): Promise<void> {
    await this.asked(() => this.store.readBackup());
  }

  /** Turn automated backup on or off. It is the store's switch and not this
   *  page's, so what comes back is what it now says rather than what was
   *  asked for. */
  async automatic(on: boolean): Promise<void> {
    await this.asked(() => this.store.switchBackup(on));
  }

  /** Back the store up now: a commit of whatever has moved, and a push after
   *  it. */
  async now(): Promise<void> {
    await this.asked(() => this.store.backUpNow());
  }

  /** Put the store back as one named backup held it. Refused over documents
   *  that have not been backed up, in words naming them — which is an answer
   *  and not a failure. */
  async restore(commit: string): Promise<void> {
    await this.asked(() => this.store.restoreBackup(commit));
  }

  /**
   * One ask, and what it leaves behind: the standing, git's words where the
   * route carried any, and the trouble where there was no answer at all.
   *
   * Written once because all four differ only in the route. A press while one
   * is in flight is dropped rather than queued: the button it came from is
   * greyed, so the second click is a double-click on a slow store, and two
   * commits is not what it asked for.
   */
  private async asked(route: () => Promise<BackupDoc>): Promise<void> {
    if (this.asking) return;
    this.asking = true;
    this.notify();
    try {
      const said = await route();
      this.answer = said;
      this.wrong = null;
      if (said.said !== undefined) {
        this.wording = said.said;
        this.refused = said.ok === false;
      }
    } catch (failure) {
      this.wrong = `the store is not answering: ${String(failure)}`;
    } finally {
      this.asking = false;
      this.notify();
    }
  }
}
