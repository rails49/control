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

import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";

import "../src/ui/tc-backup.js";
import "../src/ui/tc-app.js";
import { ASK_MS, Backing, type BackupStore } from "../src/model/backup.js";
import type { BackupDoc } from "../src/model/store.js";
import type { TcApp } from "../src/ui/tc-app.js";
import type { TcBackup } from "../src/ui/tc-backup.js";
import { band, mounted, pressed, serving, settled, UNBACKED } from "./support/shell.js";
import { brokering, joined, loads, said, unbrokered, written } from "./support/session.js";

/** A store that is a repository with one drawing waiting and one backup in
 *  it: the ordinary state, which is what most of these are about. */
const KEPT: BackupDoc = {
  root: "/home/somebody/tc49",
  repository: true,
  inside: null,
  remote: "git@github.com:somebody/railroad.git",
  key: "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFakeKeyForTheSuite tc49 backup",
  automatic: false,
  needs: [],
  outstanding: ["reversing-loops"],
  backups: [
    {
      commit: "a1b2c3d",
      said: "backup: reversing-loops",
      when: "2026-09-01 21:40",
      railroads: ["crossover-yard", "reversing-loops"],
    },
    {
      commit: "9f8e7d6",
      said: "backup: crossover-yard",
      when: "2026-08-30 18:02",
      railroads: ["crossover-yard"],
    },
  ],
  copy: { waiting: 0, since: null, stale: false, ok: true, said: "" },
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

  /** What a restore answers: refused over a dirty tree unless a suite says
   *  it worked. */
  restores = false;

  restoreBackup(commit: string): Promise<BackupDoc> {
    if (this.restores) {
      return this.answer(`restore ${commit}`, {
        ok: true,
        said: `restored reversing-loops from ${commit}`,
      });
    }
    return this.answer(`restore ${commit}`, {
      ok: false,
      said: "refused: reversing-loops changed since the last backup",
    });
  }

  newKey(): Promise<BackupDoc> {
    this.stands = { ...this.stands, key: "ssh-ed25519 AAAANewKey tc49 backup" };
    return this.answer("new key", {
      ok: true,
      said: "a new key: add it to the repository — ssh-ed25519 AAAANewKey tc49 backup",
    });
  }

  adoptRepository(url: string): Promise<BackupDoc> {
    this.stands = { ...this.stands, repository: true, remote: url, needs: [] };
    return this.answer(`adopt ${url}`, {
      ok: true,
      said: `backing up to ${url}; nothing is in it yet`,
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

/** The footer's Restore press. */
function restoring(surface: TcBackup): HTMLButtonElement {
  return [...surface.renderRoot.querySelectorAll("sl-button")].find((button) =>
    (button.textContent ?? "").includes("Restore"),
  ) as unknown as HTMLButtonElement;
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

  /** A store that is no repository is the ordinary state of a fresh
   *  installation. What it needs reads as what to make; the key the store
   *  made for itself is there to paste; and nothing here runs `git init`
   *  (ADR-0053, #355). */
  it("says what backup needs, and shows the key to paste", async () => {
    const { dialog: surface } = await dialog(UNBACKED);
    expect(reads(surface)).toContain("create an empty private repository");
    expect(reads(surface)).toContain("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFakeKeyForTheSuite");
    expect(reads(surface)).not.toContain("git init");
  });

  /** The way in: an address typed, one press, and the store clones it. The
   *  press is greyed until there is an address, so a click on nothing asks
   *  the store nothing. */
  it("adopts the repository whose address was entered", async () => {
    const { dialog: surface, store } = await dialog(UNBACKED);
    press(surface, "Back up to it");
    expect(store.asked).not.toContain("adopt git@github.com:somebody/railroad.git");

    const input = surface.renderRoot.querySelector("sl-input")!;
    input.value = "git@github.com:somebody/railroad.git";
    input.dispatchEvent(new Event("sl-input", { bubbles: true }));
    await surface.updateComplete;
    press(surface, "Back up to it");
    await new Promise((settle) => setTimeout(settle, 0));
    await surface.updateComplete;

    expect(store.asked).toContain("adopt git@github.com:somebody/railroad.git");
    expect(reads(surface)).toContain("the copy goes to git@github.com:somebody/railroad.git");
  });

  /** The key and the address both fold away once the store is a
   *  repository: the key is pasted again when the repository or the box is
   *  remade, and the address is how backup moves to another repository
   *  without a terminal (#688). */
  it("keeps the key and another address to hand once the store is a repository", async () => {
    const { dialog: surface } = await dialog();
    expect(surface.renderRoot.querySelector("details.key")).not.toBeNull();
    expect(surface.renderRoot.querySelector("details.move sl-input")).not.toBeNull();
  });

  /** A store already backed up, whose repository went or which wants
   *  another: the address field and the press are there under a label that
   *  says it moves, and the press hands the store the new address, which
   *  says whether it moved (#698). */
  it("moves a store that is a repository to the address entered", async () => {
    const { dialog: surface, store } = await dialog();
    const move = surface.renderRoot.querySelector("details.move")!;
    expect(move.querySelector("summary")!.textContent).toContain(
      "back up to another repository",
    );
    const input = move.querySelector("sl-input")!;
    const button = [...move.querySelectorAll("sl-button")].find((found) =>
      (found.textContent ?? "").includes("Back up to it"),
    );
    expect(button).toBeDefined();

    input.value = "git@github.com:somebody/railroad-2.git";
    input.dispatchEvent(new Event("sl-input", { bubbles: true }));
    await surface.updateComplete;
    (button as HTMLElement).click();
    await new Promise((settle) => setTimeout(settle, 0));
    await surface.updateComplete;

    expect(store.asked).toContain("adopt git@github.com:somebody/railroad-2.git");
    expect(reads(surface)).toContain(
      "the copy goes to git@github.com:somebody/railroad-2.git",
    );
  });

  it("says a deploy key opens one repository", async () => {
    const { dialog: surface } = await dialog(UNBACKED);
    expect(reads(surface)).toContain("a deploy key opens one repository");
    expect(reads(surface)).toContain("before deleting that repository");
  });

  /** The key in use stops working until the new one is added, so *New key*
   *  asks once before it replaces anything (#688). */
  it("makes a new key only once it is confirmed", async () => {
    const { dialog: surface, store } = await dialog(UNBACKED);
    press(surface, "New key");
    await surface.updateComplete;
    expect(store.asked).not.toContain("new key");
    expect(reads(surface)).toContain("stops working until the new one is added");

    press(surface, "Keep this key");
    await surface.updateComplete;
    expect(reads(surface)).not.toContain("stops working");
    expect(store.asked).not.toContain("new key");

    press(surface, "New key");
    await surface.updateComplete;
    press(surface, "Replace the key");
    await new Promise((settle) => setTimeout(settle, 0));
    await surface.updateComplete;

    expect(store.asked).toContain("new key");
    expect(reads(surface)).toContain("ssh-ed25519 AAAANewKey");
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

  /** A restore can take away track a train stands on, so it is refused
   *  while any is placed — the rule a layout edit follows (#684). The press
   *  is greyed and says why, rather than asking the store and being told. */
  it("will not restore while trains are on the layout", async () => {
    const { dialog: surface, store } = await dialog();
    surface.frozen = true;
    surface.renderRoot.querySelectorAll<HTMLButtonElement>("ul.backups button")[1]!.click();
    await surface.updateComplete;

    expect(restoring(surface).disabled).toBe(true);
    expect(reads(surface)).toContain(
      "trains are on the layout — take them off to restore",
    );
    press(surface, "Restore");
    await new Promise((settle) => setTimeout(settle, 0));
    expect(store.asked).not.toContain("restore 9f8e7d6");

    surface.frozen = false;
    await surface.updateComplete;
    expect(restoring(surface).disabled).toBe(false);
    expect(reads(surface)).not.toContain("trains are on the layout");
  });

  /** With a railroad loaded, the rails and the drawing are never changed
   *  under a moving train (#688). */
  it("will not restore while a loaded railroad's track has power", async () => {
    const { dialog: surface, store } = await dialog();
    surface.railroad = "crossover-yard";
    surface.power = "on";
    surface.renderRoot.querySelectorAll<HTMLButtonElement>("ul.backups button")[1]!.click();
    await surface.updateComplete;

    expect(restoring(surface).disabled).toBe(true);
    expect(reads(surface)).toContain("track power is on — turn it off to restore");
    press(surface, "Restore");
    await new Promise((settle) => setTimeout(settle, 0));
    expect(store.asked).not.toContain("restore 9f8e7d6");

    surface.power = "off";
    await surface.updateComplete;
    expect(restoring(surface).disabled).toBe(false);
  });

  /** A person pressing Restore on a run that is up is told what follows it
   *  before pressing, not after (#699). */
  it("says the apps and the page reload after a restore", async () => {
    const { dialog: surface } = await dialog();
    expect(reads(surface)).toContain(
      "Restore puts the store back as the picked backup held it; the apps and this page then reload",
    );
  });

  /** With nothing loaded no app runs a drawing, so any backup will do —
   *  one without a railroad drawn since among them (#697). */
  it("restores any backup with no railroad loaded, whatever the supply", async () => {
    const { dialog: surface } = await dialog();
    surface.power = "on";
    for (const row of surface.renderRoot.querySelectorAll<HTMLButtonElement>("ul.backups button")) {
      row.click();
      await surface.updateComplete;
      expect(restoring(surface).disabled).toBe(false);
      expect(reads(surface)).not.toContain("this backup has no");
    }
  });

  /** The apps would otherwise go on running a railroad the store no longer
   *  holds (#688). */
  it("will not restore a backup without the loaded railroad", async () => {
    const { dialog: surface } = await dialog();
    surface.railroad = "reversing-loops";
    surface.power = "off";
    const rows = surface.renderRoot.querySelectorAll<HTMLButtonElement>("ul.backups button");
    rows[1]!.click();
    await surface.updateComplete;

    expect(restoring(surface).disabled).toBe(true);
    expect(reads(surface)).toContain(
      "this backup has no reversing-loops — load another railroad first",
    );

    rows[0]!.click();
    await surface.updateComplete;
    expect(restoring(surface).disabled).toBe(false);
  });

  it("says a restore that worked, and only one that worked", async () => {
    const { dialog: surface, store } = await dialog();
    let restored = 0;
    surface.addEventListener("restored", () => {
      restored += 1;
    });
    surface.renderRoot.querySelectorAll<HTMLButtonElement>("ul.backups button")[1]!.click();
    await surface.updateComplete;

    press(surface, "Restore");
    await new Promise((settle) => setTimeout(settle, 0));
    expect(restored).toBe(0);

    store.restores = true;
    press(surface, "Restore");
    await new Promise((settle) => setTimeout(settle, 0));
    expect(restored).toBe(1);
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

/**
 * The run view's note: backup that is not running, said where a person
 * running trains is looking, and one press from its dialog (#688).
 */
describe("the note in the band", () => {
  afterEach(() => {
    document.body.replaceChildren();
  });

  function note(shell: TcApp): HTMLButtonElement | null {
    return band(shell).renderRoot.querySelector<HTMLButtonElement>("button.backup");
  }

  it("says a store with no repository has no backup set up", async () => {
    serving({ drawings: ["reversing-loops"], backup: UNBACKED });
    const shell = await mounted("run");
    expect(note(shell)?.textContent?.trim()).toBe("no backup set up");
  });

  it("says a copy that is behind, with git's words as its tooltip", async () => {
    serving({
      drawings: ["reversing-loops"],
      backup: {
        ...KEPT,
        automatic: true,
        copy: {
          waiting: 4,
          since: 200000,
          stale: true,
          ok: false,
          said: "ERROR: Repository not found.",
        },
      },
    });
    const shell = await mounted("run");
    expect(note(shell)?.textContent?.trim()).toBe("backup behind");
    expect(note(shell)?.title).toBe("ERROR: Repository not found.");
  });

  it("says nothing of a store backing up as it should", async () => {
    serving({ drawings: ["reversing-loops"], backup: { ...KEPT, automatic: true } });
    const shell = await mounted("run");
    expect(note(shell)).toBeNull();
  });

  it("opens the backup dialog when pressed", async () => {
    serving({ drawings: ["reversing-loops"], backup: UNBACKED });
    const shell = await mounted("run");
    note(shell)!.click();
    await settled(shell);
    expect(open(shell)).not.toBeNull();
  });

  /** The band is the app's, so the note is in every view (#691). */
  it("says the same in the editing view", async () => {
    serving({ drawings: ["reversing-loops"], backup: { ...KEPT, automatic: false } });
    const shell = await mounted("edit");
    expect(note(shell)?.textContent?.trim()).toBe("backup is off");
  });

  /** A page left open: an hour after it loaded the app asks again, and the
   *  note follows the answer (#691). */
  it("follows the store's answer an hour after load", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    try {
      const store = serving({
        drawings: ["reversing-loops"],
        backup: { ...KEPT, automatic: true },
      });
      const shell = await mounted("run");
      expect(note(shell)).toBeNull();
      store.backup = {
        ...KEPT,
        automatic: true,
        copy: { waiting: 4, since: 200000, stale: true, ok: false, said: "no route" },
      };
      await vi.advanceTimersByTimeAsync(ASK_MS);
      await settled(shell);
      expect(note(shell)?.textContent?.trim()).toBe("backup behind");
      expect(note(shell)?.title).toBe("no route");
    } finally {
      vi.useRealTimers();
    }
  });
});

/**
 * After a restore, everything that read the store before it reads it again:
 * the running apps, asked for the loaded railroad by name, and the page,
 * reloaded so the editor cannot save back what it read before (#688).
 */
describe("what follows a restore", () => {
  const RESTORED: BackupDoc = {
    ...KEPT,
    automatic: true,
    outstanding: [],
    ok: true,
    said: "restored reversing-loops from 9f8e7d6 of 2026-08-30 18:02",
    backups: KEPT.backups.map((backup) => ({ ...backup, railroads: ["reversing-loops", "toy"] })),
  };

  beforeEach(() => {
    brokering();
  });

  afterEach(unbrokered);

  /** Restore the older backup, and what the bus had heard each time the page
   *  reloaded — so a reload before the press would show as one without it. */
  async function restores(shell: TcApp): Promise<unknown[][]> {
    const reloads: unknown[][] = [];
    shell.reload = () => {
      reloads.push(written());
    };
    await chooseBackup(shell);
    const surface = open(shell)!;
    surface.renderRoot.querySelectorAll<HTMLButtonElement>("ul.backups button")[1]!.click();
    await surface.updateComplete;
    press(surface, "Restore");
    await settled(shell);
    await new Promise((settle) => setTimeout(settle, 600));
    return reloads;
  }

  /** What the page has asked for on `railroad_wanted`. */
  function wants(): unknown[] {
    return written().filter(
      (one) => (one as { topic: string }).topic === "tc49/layout/railroad_wanted",
    );
  }

  /** Every app builds the loaded railroad again from what the restore wrote,
   *  and the page reads it afresh, so the editor cannot save back what it
   *  read before (#699). */
  it("names the loaded railroad again, then reloads the page", async () => {
    const shell = await mounted("edit");
    await loads(shell, "reversing-loops");
    await said(shell, "tc49/layout/state/power", { power: "off" });
    serving({ drawings: ["reversing-loops"], backup: RESTORED });

    const wanted = { topic: "tc49/layout/railroad_wanted", payload: { railroad: "reversing-loops" } };
    const reloads = await restores(shell);
    expect(reloads).toHaveLength(1);
    expect(reloads[0]).toContainEqual(wanted);
    expect(wants()).toEqual([wanted]);
  });

  /** The dialog is told the loaded railroad by the app, as it is told the
   *  placed trains (#697): a backup drawn before it is refused by name. */
  it("refuses a backup without the railroad the app has loaded", async () => {
    const shell = await joined("edit");
    await said(shell, "tc49/layout/state/power", { power: "off" });
    serving({ drawings: ["toy"], backup: KEPT });
    await chooseBackup(shell);
    const surface = open(shell)!;
    surface.renderRoot.querySelectorAll<HTMLButtonElement>("ul.backups button")[1]!.click();
    await surface.updateComplete;

    expect(restoring(surface).disabled).toBe(true);
    expect(reads(surface)).toContain("this backup has no toy — load another railroad first");
  });

  /** The track power the app hears is what the dialog wears (#699). */
  it("will not restore while the loaded railroad's track has power", async () => {
    const shell = await joined("edit");
    await said(shell, "tc49/layout/state/power", { power: "on" });
    serving({ drawings: ["toy"], backup: RESTORED });
    await chooseBackup(shell);
    const surface = open(shell)!;
    surface.renderRoot.querySelectorAll<HTMLButtonElement>("ul.backups button")[1]!.click();
    await surface.updateComplete;

    expect(restoring(surface).disabled).toBe(true);
    expect(reads(surface)).toContain("track power is on — turn it off to restore");

    await said(shell, "tc49/layout/state/power", { power: "off" });
    await surface.updateComplete;
    expect(restoring(surface).disabled).toBe(false);
  });

  it("reloads the page with no railroad loaded, naming none", async () => {
    serving({ drawings: [], backup: RESTORED });
    const shell = await mounted("edit");

    expect(await restores(shell)).toHaveLength(1);
    expect(written()).toEqual([]);
  });

  /** A refusal changed nothing, so there is nothing to read again (#699). */
  it("neither names the railroad nor reloads after a refused restore", async () => {
    const shell = await mounted("edit");
    await loads(shell, "reversing-loops");
    await said(shell, "tc49/layout/state/power", { power: "off" });
    serving({
      drawings: ["reversing-loops"],
      backup: { ...RESTORED, ok: false, said: "refused: reversing-loops changed since the last backup" },
    });

    expect(await restores(shell)).toEqual([]);
    expect(wants()).toEqual([]);
  });
});

/** The dialog the app has up, `null` while it has none. */
function open(shell: TcApp): TcBackup | null {
  const surface = shell.renderRoot.querySelector<TcBackup>("tc-backup");
  return surface === null || surface.backing === null ? null : surface;
}

/** The rail's Backup button, the way a pointer presses it. */
async function chooseBackup(shell: TcApp): Promise<void> {
  await pressed(shell, "backup");
}

/**
 * What backup says from outside its own dialog (#321).
 *
 * The person this reaches is the one who never opens the dialog, so the rule
 * has to hold before anything is pressed and has to stay quiet about anything
 * that is only worth reading once it is open.
 */
describe("what backup says without being opened", () => {
  async function held(stands: Partial<BackupDoc>): Promise<Backing> {
    const store = new Fake();
    store.stands = { ...KEPT, automatic: true, ...stands };
    const backing = new Backing(() => {}, store);
    await backing.load();
    return backing;
  }

  async function standing(stands: Partial<BackupDoc>) {
    return (await held(stands)).standing;
  }

  const STALE = { waiting: 3, since: 200000, stale: true, ok: false, said: "ERROR: Repository not found." };

  it("says nothing until the store has been asked", () => {
    expect(new Backing(() => {}, new Fake()).standing).toBe("quiet");
  });

  it("says nothing of a store backing up as it should", async () => {
    expect(await standing({})).toBe("quiet");
  });

  /** A developer's session on the bench store of a checkout, which is not
   *  meant to be backed up, whatever else is true of it. */
  it("says nothing of a store inside another repository", async () => {
    expect(
      await standing({
        inside: "/home/somebody/control",
        repository: false,
        needs: ["inside"],
      }),
    ).toBe("inside");
  });

  /** A newly deployed box, and a store copied to a new box with backup
   *  switched on and no repository with it: a switch that says on cannot hide
   *  that nothing is backed up. */
  it("says a store that is no repository has no backup set up", async () => {
    expect(await standing({ repository: false, automatic: false })).toBe("unset");
    expect(await standing({ repository: false, automatic: true })).toBe("unset");
  });

  it("says a copy that has been failing for a day is behind", async () => {
    expect(await standing({ copy: STALE, needs: ["no remote"], automatic: false })).toBe(
      "behind",
    );
  });

  /** A failed copy an hour old is a network coming and going. */
  it("says nothing of a copy that failed an hour ago", async () => {
    expect(
      await standing({
        copy: { waiting: 1, since: 3600, stale: false, ok: false, said: "no route" },
      }),
    ).toBe("quiet");
  });

  it("says a repository with something missing cannot run", async () => {
    expect(await standing({ needs: ["no remote, so a backup stays on this machine"] })).toBe(
      "blocked",
    );
  });

  it("says backup switched off is off", async () => {
    expect(await standing({ automatic: false })).toBe("off");
  });

  /** The tooltip tells a missing key from a deleted repository, in git's own
   *  words; a store that cannot run says which of its needs it is. */
  it("says why, in git's words or the store's", async () => {
    expect((await held({ copy: STALE })).why).toBe("ERROR: Repository not found.");
    expect((await held({ needs: ["no remote, so a backup stays on this machine"] })).why).toBe(
      "no remote, so a backup stays on this machine",
    );
    expect((await held({})).why).toBeNull();
  });

  /** A page left open for days: a copy that went behind after it loaded
   *  still shows (#688). */
  it("asks again every hour", async () => {
    vi.useFakeTimers();
    try {
      const store = new Fake();
      const backing = new Backing(() => {}, store);
      const stop = backing.watch();
      await vi.advanceTimersByTimeAsync(ASK_MS - 1);
      expect(store.asked).toEqual([]);
      await vi.advanceTimersByTimeAsync(1);
      expect(store.asked).toEqual(["read"]);
      await vi.advanceTimersByTimeAsync(ASK_MS);
      expect(store.asked).toEqual(["read", "read"]);
      stop();
      await vi.advanceTimersByTimeAsync(ASK_MS);
      expect(store.asked).toEqual(["read", "read"]);
    } finally {
      vi.useRealTimers();
    }
  });
});
