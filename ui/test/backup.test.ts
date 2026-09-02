// @vitest-environment happy-dom

/**
 * Backing the store up, from the app's side (#321).
 *
 * Three parts. The model against a fake store, because what it holds — git's
 * words, a refusal that is not a failure, the store not answering at all — has
 * nothing to do with HTTP (EDITOR.md#tests). Then the dialog, which decides
 * nothing and is asked only what it draws for the answer it is handed and what
 * it presses. Then the one path through the app: the File menu's item opens
 * it, and nothing is asked of git until it does.
 */

import { describe, expect, it, beforeEach, afterEach } from "vitest";

import "../src/ui/tc-backup.js";
import "../src/ui/tc-app.js";
import { Backing, type BackupStore } from "../src/model/backup.js";
import type { BackupDoc } from "../src/model/store.js";
import type { TcApp } from "../src/ui/tc-app.js";
import type { TcBackup } from "../src/ui/tc-backup.js";
import { bar, mounted, serving, settled, UNBACKED } from "./support/shell.js";

/** A store that is a repository with one drawing waiting and one backup in
 *  it: the ordinary state, which is what most of these are about. */
const KEPT: BackupDoc = {
  root: "/home/somebody/tc49",
  repository: true,
  automatic: false,
  needs: [],
  outstanding: ["reversing-loops"],
  backups: [
    { commit: "a1b2c3d", said: "backup: reversing-loops", when: "2026-09-01 21:40" },
    { commit: "9f8e7d6", said: "backup: crossover-yard", when: "2026-08-30 18:02" },
  ],
};

/** The store the model is driven against: what it answers, and what it was
 *  asked. */
class Fake implements BackupStore {
  stands: BackupDoc = { ...KEPT };
  asked: string[] = [];
  broken: Error | null = null;

  private answer(what: string, more: Partial<BackupDoc> = {}): Promise<BackupDoc> {
    this.asked.push(what);
    if (this.broken !== null) return Promise.reject(this.broken);
    return Promise.resolve({ ...this.stands, ...more });
  }

  readBackup(): Promise<BackupDoc> {
    return this.answer("read");
  }

  switchBackup(automatic: boolean): Promise<BackupDoc> {
    this.stands = { ...this.stands, automatic };
    return this.answer(`switch ${String(automatic)}`);
  }

  backUpNow(): Promise<BackupDoc> {
    return this.answer("now", {
      ok: true,
      said: "[main 1a2b3c4] backup: reversing-loops",
      outstanding: [],
    });
  }

  restoreBackup(commit: string): Promise<BackupDoc> {
    return this.answer(`restore ${commit}`, {
      ok: false,
      said: "refused: reversing-loops changed since the last backup",
    });
  }
}

/** A `Backing` over a fake, and the count of how often it said it had moved —
 *  the one thing the shell wires to it. */
function backing(store: Fake = new Fake()): {
  backing: Backing;
  store: Fake;
  drawn: () => number;
} {
  let drawn = 0;
  return {
    backing: new Backing(() => {
      drawn += 1;
    }, store),
    store,
    drawn: () => drawn,
  };
}

describe("what the app knows about backup", () => {
  it("holds where backup stands once it has asked", async () => {
    const { backing: held, store } = backing();
    expect(held.stands).toBeNull();

    await held.load();

    expect(store.asked).toEqual(["read"]);
    expect(held.stands?.root).toBe("/home/somebody/tc49");
    expect(held.stands?.outstanding).toEqual(["reversing-loops"]);
  });

  it("keeps what git said about a press", async () => {
    const { backing: held } = backing();
    await held.now();

    expect(held.words).toContain("backup: reversing-loops");
    expect(held.refusal).toBe(false);
    expect(held.stands?.outstanding).toEqual([]);
  });

  /** A refusal over a dirty tree is git's answer and not a failure: it arrives
   *  inside a 200 and reads as words, where a store that is not running is
   *  trouble. */
  it("reads a refusal as words and not as trouble", async () => {
    const { backing: held } = backing();
    await held.restore("a1b2c3d");

    expect(held.refusal).toBe(true);
    expect(held.words).toContain("changed since the last backup");
    expect(held.trouble).toBeNull();
  });

  it("keeps those words while it goes on asking where things stand", async () => {
    const { backing: held } = backing();
    await held.restore("a1b2c3d");
    await held.load();

    expect(held.words).toContain("changed since the last backup");
  });

  it("turns the switch and takes the store's answer for where it now is", async () => {
    const { backing: held, store } = backing();
    await held.automatic(true);

    expect(store.asked).toEqual(["switch true"]);
    expect(held.stands?.automatic).toBe(true);
  });

  it("says the store is not answering rather than throwing", async () => {
    const { backing: held, store } = backing();
    store.broken = new Error("connection refused");
    await held.load();

    expect(held.trouble).toContain("connection refused");
    expect(held.words).toBeNull();
  });

  /** The button that asked is greyed while the ask is in flight, so a second
   *  press is a double-click on a slow store — and two commits is not what it
   *  asked for. */
  it("drops a press while one is still in flight", async () => {
    const { backing: held, store } = backing();
    const first = held.now();
    await held.now();
    await first;

    expect(store.asked).toEqual(["now"]);
  });

  it("says it has moved so the dialog redraws", async () => {
    const { backing: held, drawn } = backing();
    await held.load();
    expect(drawn()).toBeGreaterThan(0);
  });
});

/** The dialog, over a `Backing` that has already asked. */
async function dialog(stands: BackupDoc = KEPT): Promise<{
  dialog: TcBackup;
  store: Fake;
}> {
  const store = new Fake();
  store.stands = { ...stands };
  const surface = document.createElement("tc-backup");
  document.body.append(surface);
  const held = new Backing(() => {
    surface.requestUpdate();
  }, store);
  await held.load();
  surface.backing = held;
  await surface.updateComplete;
  return { dialog: surface, store };
}

/** What the dialog reads, whitespace collapsed. */
function reads(surface: TcBackup): string {
  return (surface.renderRoot.textContent ?? "").replace(/\s+/g, " ").trim();
}

function press(surface: TcBackup, label: string): void {
  const found = [...surface.renderRoot.querySelectorAll("sl-button")].find((button) =>
    (button.textContent ?? "").includes(label),
  );
  (found as HTMLElement).click();
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("the backup dialog", () => {
  it("says where the store is and what is waiting to be backed up", async () => {
    const { dialog: surface } = await dialog();
    expect(reads(surface)).toContain("/home/somebody/tc49");
    expect(reads(surface)).toContain("waiting to be backed up: reversing-loops");
  });

  /** A store nobody has run `git init` in is the ordinary state of a fresh
   *  installation, and what it needs reads as the command that supplies it.
   *  Nothing here runs it (ADR-0053). */
  it("says what backup needs, in the words of the command that gives it", async () => {
    const { dialog: surface } = await dialog(UNBACKED);
    expect(reads(surface)).toContain("git init");
  });

  it("lists the backups newest first, each by what moved in it", async () => {
    const { dialog: surface } = await dialog();
    const rows = [...surface.renderRoot.querySelectorAll("ul.backups button")].map(
      (row) => (row.textContent ?? "").replace(/\s+/g, " ").trim(),
    );
    expect(rows).toEqual([
      "2026-09-01 21:40 backup: reversing-loops",
      "2026-08-30 18:02 backup: crossover-yard",
    ]);
  });

  it("backs up on the press, and shows what git said", async () => {
    const { dialog: surface, store } = await dialog();
    press(surface, "Back up now");
    await new Promise((settle) => setTimeout(settle, 0));
    await surface.updateComplete;

    expect(store.asked).toContain("now");
    expect(reads(surface)).toContain("backup: reversing-loops");
  });

  it("names the switch by what pressing it will do", async () => {
    const { dialog: surface, store } = await dialog();
    expect(reads(surface)).toContain("Turn automatic backup on");

    press(surface, "Turn automatic backup on");
    await new Promise((settle) => setTimeout(settle, 0));
    await surface.updateComplete;

    expect(store.asked).toContain("switch true");
    expect(reads(surface)).toContain("Turn automatic backup off");
  });

  /** Restoring takes two presses — the one that chooses a backup and the one
   *  that does it — so a click in a list cannot rewrite the store. */
  it("restores the backup that was chosen, and not before it is", async () => {
    const { dialog: surface, store } = await dialog();
    press(surface, "Restore");
    expect(store.asked).not.toContain("restore 9f8e7d6");

    const older = surface.renderRoot.querySelectorAll<HTMLButtonElement>(
      "ul.backups button",
    )[1]!;
    older.click();
    await surface.updateComplete;
    press(surface, "Restore");
    await new Promise((settle) => setTimeout(settle, 0));
    await surface.updateComplete;

    expect(store.asked).toContain("restore 9f8e7d6");
    expect(reads(surface)).toContain("changed since the last backup");
  });

  it("says it was closed rather than closing anything itself", async () => {
    const { dialog: surface } = await dialog();
    let closed = 0;
    surface.addEventListener("backup-closed", () => {
      closed += 1;
    });
    press(surface, "Close");
    expect(closed).toBe(1);
  });
});

describe("the app's way in", () => {
  beforeEach(() => {
    serving({ drawings: ["reversing-loops"], backup: KEPT });
  });

  afterEach(() => {
    document.body.replaceChildren();
  });

  /** A person who never opens it has no interest in git, and a page that
   *  asked anyway would put a `git` process behind every reload. */
  it("asks the store nothing about git until the dialog is opened", async () => {
    const shell = await mounted();
    expect(open(shell)).toBeNull();

    await chooseBackup(shell);

    expect(open(shell)).not.toBeNull();
    expect(reads(open(shell)!)).toContain("/home/somebody/tc49");
  });

  it("shuts it again when the dialog says it was closed", async () => {
    const shell = await mounted();
    await chooseBackup(shell);
    open(shell)!.dispatchEvent(
      new CustomEvent("backup-closed", { bubbles: true, composed: true }),
    );
    await settled(shell);

    expect(open(shell)).toBeNull();
  });
});

/** The dialog the app has up, `null` while it has none. */
function open(shell: TcApp): TcBackup | null {
  const surface = shell.renderRoot.querySelector<TcBackup>("tc-backup");
  return surface === null || surface.backing === null ? null : surface;
}

/** `File ▸ Backup…`, the way a pointer chooses it. */
async function chooseBackup(shell: TcApp): Promise<void> {
  const menubar = bar(shell);
  [...menubar.renderRoot.querySelectorAll<HTMLButtonElement>("button.title")]
    .find((title) => title.textContent!.trim() === "File")!
    .click();
  await menubar.updateComplete;
  [...menubar.renderRoot.querySelectorAll<HTMLButtonElement>("menu li button")]
    .find((item) => (item.textContent ?? "").includes("Backup…"))!
    .click();
  await settled(shell);
}
