// @vitest-environment happy-dom

/**
 * Backing the store up, from the app's side (#321).
 *
 * Three parts. The model against a fake store, because what it holds — git's
 * words, a refusal that is not a failure, the store not answering at all — has
 * nothing to do with HTTP (EDITOR.md#tests). Then the settings dialog's Backup
 * tab, which decides nothing and is asked only what it draws for the answer it
 * is handed and what it presses. Then the paths through the app: the gear and
 * the band's note open Settings, the note on its Backup tab (#1075).
 */

import type { LookBandPress } from "@rails49/look";
import { press as pressOn } from "@rails49/look/testing";
import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";

import "../src/ui/tc-backup.js";
import "../src/ui/tc-app.js";
import { ASK_MS, Backing, type BackupStore } from "../src/model/backup.js";
import type { BackupDoc } from "../src/model/store.js";
import type { TcApp } from "../src/ui/tc-app.js";
import type { TcBackup } from "../src/ui/tc-backup.js";
import type { TcSettings } from "../src/ui/tc-settings.js";
import {
  band,
  edited,
  mounted,
  serving,
  session,
  settings,
  settingsOpened,
  shows,
  settled,
  UNBACKED,
} from "./support/shell.js";
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
  // The row heard and naming none: what a dialog with no railroad loaded is
  // handed (#759). The suites that load one set it.
  surface.railroad = "";
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

/** The Restore press, beneath the backups. */
function restoring(surface: TcBackup): HTMLButtonElement {
  return [...surface.renderRoot.querySelectorAll("sl-button")].find((button) =>
    (button.textContent ?? "").includes("Restore"),
  ) as unknown as HTMLButtonElement;
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("the Backup tab", () => {
  /** Everything the backup dialog held, drawn without a dialog of its own:
   *  Settings is the dialog (#1075). */
  it("draws the store, its presses, its backups and Restore, in no dialog", async () => {
    const { dialog: surface } = await dialog();
    expect(surface.renderRoot.querySelector("look-dialog")).toBeNull();
    expect(reads(surface)).toContain("/home/somebody/tc49");
    expect(reads(surface)).toContain("Back up now");
    expect(reads(surface)).toContain("Turn automatic backup on");
    expect(surface.renderRoot.querySelectorAll("ul.backups button")).toHaveLength(2);
    const restore = restoring(surface);
    expect(restore.getAttribute("variant")).toBe("warning");
    expect(restore.hasAttribute("slot")).toBe(false);
    expect(restore.closest(".restore")).not.toBeNull();
  });

  it("draws nothing without backing", async () => {
    const { dialog: surface } = await dialog();
    surface.backing = null;
    await surface.updateComplete;
    expect(reads(surface)).toBe("");
  });

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

  /** The page reloads after a restore that worked, so edits it holds that
   *  the store has not been given are asked about first, as *New key* asks
   *  before replacing a key (#703). */
  describe("over edits that have not been saved", () => {
    const ASKED = "the drawing has edits that have not been saved; restoring discards them";

    async function asking(): Promise<{ dialog: TcBackup; store: Fake }> {
      const held = await dialog();
      held.dialog.unsaved = "the drawing";
      held.dialog.renderRoot
        .querySelectorAll<HTMLButtonElement>("ul.backups button")[1]!
        .click();
      await held.dialog.updateComplete;
      press(held.dialog, "Restore");
      await new Promise((settle) => setTimeout(settle, 0));
      await held.dialog.updateComplete;
      return held;
    }

    it("asks on the first press, naming what would be lost", async () => {
      const { dialog: surface, store } = await asking();
      expect(store.asked).not.toContain("restore 9f8e7d6");
      expect(reads(surface)).toContain(ASKED);
    });

    it("restores once the edits are discarded", async () => {
      const { dialog: surface, store } = await asking();
      press(surface, "Discard and restore");
      await new Promise((settle) => setTimeout(settle, 0));
      await surface.updateComplete;
      expect(store.asked).toContain("restore 9f8e7d6");
    });

    it("restores nothing when the edits are kept, and stops asking", async () => {
      const { dialog: surface, store } = await asking();
      press(surface, "Keep the edits");
      await new Promise((settle) => setTimeout(settle, 0));
      await surface.updateComplete;
      expect(store.asked).not.toContain("restore 9f8e7d6");
      expect(reads(surface)).not.toContain("restoring discards them");
    });

    it("stops asking when another backup is picked", async () => {
      const { dialog: surface } = await asking();
      surface.renderRoot.querySelectorAll<HTMLButtonElement>("ul.backups button")[0]!.click();
      await surface.updateComplete;
      expect(reads(surface)).not.toContain("restoring discards them");
    });

    /** A refused restore says why it is refused, not what it would lose. */
    it("shows a refusal rather than the question", async () => {
      const { dialog: surface, store } = await dialog();
      surface.unsaved = "the drawing";
      surface.railroad = "crossover-yard";
      surface.power = null;
      surface.renderRoot.querySelectorAll<HTMLButtonElement>("ul.backups button")[1]!.click();
      await surface.updateComplete;
      press(surface, "Restore");
      await surface.updateComplete;
      expect(reads(surface)).toContain("the layout has not said whether the track has power");
      expect(reads(surface)).not.toContain("restoring discards them");
      expect(store.asked).not.toContain("restore 9f8e7d6");
    });
  });

  /** With a railroad loaded, the rails and the drawing are never changed
   *  under a moving train (#688): Restore takes the power off itself, and
   *  restores once the track reads off (ADR-0085, decision 5). */
  describe("with a loaded railroad's track live", () => {
    /** The dialog on a loaded railroad with track power on, the older backup
     *  picked and Restore pressed, and what power it asked for. */
    async function draining(): Promise<{ dialog: TcBackup; store: Fake; asked: string[] }> {
      const held = await dialog();
      const asked: string[] = [];
      held.dialog.addEventListener("power-wanted", (event) =>
        asked.push((event as CustomEvent<string>).detail),
      );
      held.dialog.railroad = "crossover-yard";
      held.dialog.power = "on";
      held.dialog.renderRoot.querySelectorAll<HTMLButtonElement>("ul.backups button")[1]!.click();
      await held.dialog.updateComplete;
      expect(restoring(held.dialog).disabled).toBe(false);
      press(held.dialog, "Restore");
      await new Promise((settle) => setTimeout(settle, 0));
      await held.dialog.updateComplete;
      return { ...held, asked };
    }

    it("asks for the drain, says it is stopping trains, and restores nothing yet", async () => {
      const { dialog: surface, store, asked } = await draining();

      expect(asked).toEqual(["draining"]);
      expect(reads(surface)).toContain("stopping trains…");
      expect(restoring(surface).disabled).toBe(true);
      expect(store.asked).not.toContain("restore 9f8e7d6");
    });

    it("restores once the track reads off", async () => {
      const { dialog: surface, store } = await draining();

      surface.power = "draining";
      await surface.updateComplete;
      expect(store.asked).not.toContain("restore 9f8e7d6");
      surface.power = "off";
      await surface.updateComplete;
      await new Promise((settle) => setTimeout(settle, 0));

      expect(store.asked).toContain("restore 9f8e7d6");
      expect(reads(surface)).not.toContain("stopping trains…");
    });

    it("asks for off at once on the stop sign", async () => {
      const { dialog: surface, asked } = await draining();

      press(surface, "Stop");

      expect(asked).toEqual(["draining", "off"]);
    });

    /** Closing gives the wait up and leaves power as it is. */
    it("restores nothing once closed", async () => {
      const { dialog: surface, store, asked } = await draining();

      surface.backing = null;
      await surface.updateComplete;
      surface.power = "off";
      await surface.updateComplete;
      await new Promise((settle) => setTimeout(settle, 0));

      expect(asked).toEqual(["draining"]);
      expect(store.asked).not.toContain("restore 9f8e7d6");
    });
  });

  /** A person pressing Restore on a run that is up is told what follows it
   *  before pressing, not after (#699). */
  it("says the apps and the page reload after a restore", async () => {
    const { dialog: surface } = await dialog();
    expect(reads(surface)).toContain(
      "Restore puts the store back as the picked backup held it; the apps and this page then reload",
    );
  });

  /** JMRI writes back the roster it read at launch, so a restore under an
   *  open DecoderPro is undone by its next save; the dialog says so (#714). */
  it("says to quit DecoderPro and PanelPro before a restore", async () => {
    const { dialog: surface } = await dialog();
    expect(reads(surface)).toContain(
      "Quit DecoderPro and PanelPro before restoring, and open them again after.",
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

  /** The press reaches the store's route, through the app's own client. */
  it("sends the picked backup to POST /backup/restore", async () => {
    serving({ backup: KEPT });
    const sent = requests();
    const surface = document.createElement("tc-backup");
    surface.railroad = "";
    document.body.append(surface);
    const held = new Backing(() => surface.requestUpdate());
    await held.load();
    surface.backing = held;
    await surface.updateComplete;
    surface.renderRoot.querySelectorAll<HTMLButtonElement>("ul.backups button")[1]!.click();
    await surface.updateComplete;

    press(surface, "Restore");
    await new Promise((settle) => setTimeout(settle, 0));

    expect(sent).toContain("POST /backup/restore");
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
});

describe("the app's way in", () => {
  beforeEach(() => {
    serving({ drawings: ["reversing-loops"], backup: KEPT });
  });

  afterEach(() => {
    document.body.replaceChildren();
  });

  /** The gear opens Settings on Railroad, as it did before the Backup tab
   *  held anything (#899). */
  it("opens Settings on Railroad from the gear", async () => {
    const shell = await mounted();
    const dialog = await settingsOpened(shell);

    expect(dialog.open).toBe(true);
    expect(activeTab(dialog)).toBe("Railroad");
  });

  /** The band's note opens Settings on its Backup tab, drawing what the
   *  store answered (#1075). */
  it("opens Settings on Backup from the band's note", async () => {
    serving({ drawings: ["reversing-loops"], backup: { ...KEPT, root: "/srv/noted" } });
    const shell = await mounted("run");
    pressOn(band(shell).querySelector<LookBandPress>("look-band-press[data-backup]")!);
    await settled(shell);

    expect(settings(shell).open).toBe(true);
    expect(activeTab(settings(shell))).toBe("Backup");
    expect(reads(open(shell)!)).toContain("/srv/noted");
  });

  /** Opening Settings asks the store afresh, so the tab draws what it says
   *  now rather than what it said up to an hour ago. */
  it("asks the store where backup stands each time Settings opens", async () => {
    const store = serving({ drawings: ["reversing-loops"], backup: KEPT });
    const shell = await mounted();
    store.backup = { ...KEPT, root: "/srv/moved" };
    await chooseBackup(shell);

    expect(reads(open(shell)!)).toContain("/srv/moved");
  });

  /** Being in one dialog only to be sent to another was a step that did
   *  nothing, and it went (#1075). */
  it("puts up no backup dialog of its own", async () => {
    const shell = await mounted();
    const dialogs = (): string[] =>
      [
        ...shell.renderRoot.querySelectorAll("look-dialog"),
        ...settings(shell).renderRoot.querySelectorAll("look-dialog"),
      ].map((one) => one.getAttribute("label") ?? "");
    expect(dialogs()).not.toContain("Backup");
    await chooseBackup(shell);
    expect(open(shell)).not.toBeNull();
    expect(dialogs()).not.toContain("Backup");
    expect(open(shell)!.renderRoot.querySelector("look-dialog")).toBeNull();
  });

  it("shows nothing of backup once Settings is closed", async () => {
    const shell = await mounted();
    await chooseBackup(shell);
    settings(shell)
      .renderRoot.querySelector("look-dialog")!
      .dispatchEvent(new Event("sl-after-hide"));
    await settled(shell);

    expect(settings(shell).open).toBe(false);
    expect(open(shell)).toBeNull();
  });
});

describe("what a restore would discard", () => {
  afterEach(unbrokered);

  /** What a restore would discard is the app's to say, in the words its
   *  own discard question uses, and by the same test: edits, not `saved`
   *  (#703). Leaving the Edit view with power off saves them (ADR-0085). */
  it("tells the dialog the drawing has edits until it is saved", async () => {
    brokering();
    serving({
      drawings: ["reversing-loops"],
      backup: KEPT,
      read: (name) => ({
        drawing: name,
        symbols: { e1: { kind: "terminal", at: [0, 0] } },
        wires: [],
      }),
    });
    const shell = await mounted();
    await loads(shell, "reversing-loops");
    await chooseBackup(shell);
    expect(open(shell)!.unsaved).toBeNull();

    session(shell).place("block", [4, 0]);
    edited(shell);
    await settled(shell);
    expect(open(shell)!.unsaved).toBe("the drawing");

    await said(shell, "tc49/layout/state/power", { power: "off" });
    await shows(shell, "run");
    expect(open(shell)!.unsaved).toBeNull();
  });
});

/**
 * The run view's note: backup that is not running, said where a person
 * running trains is looking, and one press from Settings ▸ Backup (#688).
 */
describe("the note in the band", () => {
  afterEach(() => {
    document.body.replaceChildren();
  });

  function note(shell: TcApp): LookBandPress | null {
    return band(shell).querySelector("look-band-press[data-backup]");
  }

  it("says a store with no repository has no backup set up", async () => {
    serving({ drawings: ["reversing-loops"], backup: UNBACKED });
    const shell = await mounted("run");
    expect(note(shell)?.word).toBe("no backup set up");
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
    expect(note(shell)?.word).toBe("backup behind");
    expect(note(shell)?.label).toBe("ERROR: Repository not found.");
  });

  it("says nothing of a store backing up as it should", async () => {
    serving({ drawings: ["reversing-loops"], backup: { ...KEPT, automatic: true } });
    const shell = await mounted("run");
    expect(note(shell)).toBeNull();
  });

  it("opens Settings on Backup when pressed", async () => {
    serving({ drawings: ["reversing-loops"], backup: UNBACKED });
    const shell = await mounted("run");
    pressOn(note(shell)!);
    await settled(shell);
    expect(open(shell)).not.toBeNull();
  });

  /** The band is the app's, so the note is in every view (#691). */
  it("says the same in the editing view", async () => {
    serving({ drawings: ["reversing-loops"], backup: { ...KEPT, automatic: false } });
    const shell = await mounted("edit");
    expect(note(shell)?.word).toBe("backup is off");
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
      expect(note(shell)?.word).toBe("backup behind");
      expect(note(shell)?.label).toBe("no route");
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

  /** A rebuild keeps the placements that still fit and lists those that do
   *  not, so trains on the layout no longer hold a restore back: with the
   *  track off and the backup holding the loaded railroad, it restores
   *  (#710, ADR-0071). */
  it("restores with trains on the layout", async () => {
    const shell = await mounted("edit");
    await loads(shell, "reversing-loops");
    await said(shell, "tc49/layout/state/power", { power: "off" });
    await said(shell, "tc49/dispatch/state/allocation", {
      trains: { goods: "a" },
      locks: { a: "goods" },
      requests: [],
    });
    serving({ drawings: ["reversing-loops"], backup: RESTORED });
    await chooseBackup(shell);
    const surface = open(shell)!;
    surface.renderRoot.querySelectorAll<HTMLButtonElement>("ul.backups button")[1]!.click();
    await surface.updateComplete;
    expect(restoring(surface).disabled).toBe(false);
    expect(reads(surface)).not.toContain("trains are on the layout");

    let reloads = 0;
    shell.reload = () => {
      reloads += 1;
    };
    press(surface, "Restore");
    await settled(shell);
    await new Promise((settle) => setTimeout(settle, 600));
    expect(reloads).toBe(1);
    expect(wants()).toEqual([
      { topic: "tc49/layout/railroad_wanted", payload: { railroad: "reversing-loops" } },
    ]);
  });

  /** The dialog is told the loaded railroad by the app (#697): a backup drawn
   *  before it is refused by name. */
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

  /** The track power the app hears is what the dialog drains (#699,
   *  ADR-0085 decision 5): the drain goes out on `power_wanted`, and the
   *  restore follows once the row reads off. */
  it("drains the loaded railroad's track, and restores once it reads off", async () => {
    const shell = await joined("edit");
    await said(shell, "tc49/layout/state/power", { power: "on" });
    serving({ drawings: ["toy"], backup: RESTORED });
    let reloads = 0;
    shell.reload = () => {
      reloads += 1;
    };
    await chooseBackup(shell);
    const surface = open(shell)!;
    surface.renderRoot.querySelectorAll<HTMLButtonElement>("ul.backups button")[1]!.click();
    await surface.updateComplete;

    press(surface, "Restore");
    await settled(shell);
    expect(written()).toEqual([
      { topic: "tc49/layout/power_wanted", payload: { power: "draining" } },
    ]);
    await new Promise((settle) => setTimeout(settle, 600));
    expect(reloads).toBe(0);

    await said(shell, "tc49/layout/state/power", { power: "off" });
    await settled(shell);
    await new Promise((settle) => setTimeout(settle, 600));
    expect(reloads).toBe(1);
    expect(wants()).toEqual([
      { topic: "tc49/layout/railroad_wanted", payload: { railroad: "toy" } },
    ]);
  });

  /** Closing Settings while the drain is out gives the wait up and leaves
   *  power as it is: the restore is never sent (ADR-0085, decision 5). */
  it("restores nothing once Settings is closed before the track reads off", async () => {
    const shell = await joined("edit");
    await said(shell, "tc49/layout/state/power", { power: "on" });
    serving({ drawings: ["toy"], backup: RESTORED });
    const sent = requests();
    await chooseBackup(shell);
    const surface = open(shell)!;
    surface.renderRoot.querySelectorAll<HTMLButtonElement>("ul.backups button")[1]!.click();
    await surface.updateComplete;
    press(surface, "Restore");
    await settled(shell);

    settings(shell)
      .renderRoot.querySelector("look-dialog")!
      .dispatchEvent(new Event("sl-after-hide"));
    await settled(shell);
    await said(shell, "tc49/layout/state/power", { power: "off" });
    await settled(shell);
    await new Promise((settle) => setTimeout(settle, 0));

    expect(sent).not.toContain("POST /backup/restore");
    expect(written()).toEqual([
      { topic: "tc49/layout/power_wanted", payload: { power: "draining" } },
    ]);
  });

  it("reloads the page with no railroad loaded, naming none", async () => {
    serving({ drawings: [], backup: RESTORED });
    const shell = await mounted("edit");
    await loads(shell, "");

    expect(await restores(shell)).toHaveLength(1);
    expect(written()).toEqual([]);
  });

  /** With the broker not answering, nothing says which railroad the apps
   *  run, so nothing says the backup holds it: Restore waits, as a load does
   *  (#759). */
  it("will not restore while the layout has not said which railroad is loaded", async () => {
    serving({ drawings: ["reversing-loops"], backup: RESTORED });
    const shell = await mounted("edit");
    await chooseBackup(shell);
    const surface = open(shell)!;
    surface.renderRoot.querySelectorAll<HTMLButtonElement>("ul.backups button")[1]!.click();
    await surface.updateComplete;

    expect(restoring(surface).disabled).toBe(true);
    expect(reads(surface)).toContain("the layout has not said which railroad is loaded");
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

/** Every request the page sends from here, as `METHOD path`, through the
 *  store `serving` put behind `fetch`. */
function requests(): string[] {
  const sent: string[] = [];
  const inner = globalThis.fetch;
  globalThis.fetch = ((path: string, init?: RequestInit) => {
    sent.push(`${init?.method ?? "GET"} ${path}`);
    return inner(path, init);
  }) as typeof fetch;
  return sent;
}

/** The Backup tab the app has up, `null` while Settings is shut. */
function open(shell: TcApp): TcBackup | null {
  const surface = shell.renderRoot.querySelector<TcBackup>("tc-backup");
  return surface === null || surface.backing === null ? null : surface;
}

/** Settings ▸ Backup, the way a pointer gets there: the gear on the band,
 *  and the dialog's Backup tab (ADR-0072, #1075). */
async function chooseBackup(shell: TcApp): Promise<void> {
  const dialog = await settingsOpened(shell);
  dialog.renderRoot.querySelector("sl-tab-group")!.show("backup");
  await settled(shell);
}

/** The tab Settings shows, by its label. */
function activeTab(dialog: TcSettings): string | null {
  return dialog.renderRoot.querySelector("sl-tab[active]")?.textContent?.trim() ?? null;
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
