// @vitest-environment happy-dom

/**
 * Track power on or draining freezes the drawing
 * ([ADR-0071](../../docs/adr/0071-a-rebuild-under-the-same-name-keeps-the-placements.md),
 * decision 5): the run moves trains over what the dispatcher built, and the
 * drawing must not drift from it. Trains standing with power off freeze
 * nothing — a save of the loaded railroad names it again, and the rebuild
 * keeps them where they fit.
 *
 * The rule itself is `commands.test.ts`, where it lives without a DOM. What is
 * here is the path it travels — `state/power` off the bus, up to the shell as
 * the run's reading, and back down to a view whose verbs are dead, whose
 * canvas means nothing by a press, and whose palette has nothing to give. It
 * crosses every one of those, which is why it is a DOM suite. So do the
 * rules that come with it (ADR-0085): the Edit view does not open with power
 * on, leaving the editor with power off saves the loaded railroad and names
 * it again, and ON saves first and waits for the build.
 */

import type { LitElement } from "lit";
import type { LookView } from "@rails49/look";
import { press } from "@rails49/look/testing";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-app.js";
import type { Drawing } from "../src/model/drawing.js";
import { centreOf } from "../src/model/geometry.js";
import type { TcApp } from "../src/ui/tc-app.js";
import type { TcCanvas } from "../src/ui/tc-canvas.js";
import type { TcProperties } from "../src/ui/tc-properties.js";
import type { TcWidgetProperties } from "../src/ui/tc-widget-properties.js";
import { selectionKey } from "../src/model/widgets.js";
import {
  band,
  editing,
  inside,
  mounted,
  power,
  rail,
  railButton,
  serving,
  session,
  settled,
  shows,
} from "./support/shell.js";
import {
  Broker,
  brokering,
  DERIVES,
  joined,
  loads,
  PAPER,
  RAILROAD,
  said,
  STOCK,
  stored,
  unbrokered,
  written,
} from "./support/session.js";

const ALLOCATION = "tc49/dispatch/state/allocation";
const POWER = "tc49/layout/state/power";
const RAILROAD_WANTED = "tc49/layout/railroad_wanted";
const POWER_WANTED = "tc49/layout/power_wanted";

/** The run's picture with one train standing in block `a`. */
const STANDING = {
  trains: { goods: "a" },
  locks: { a: "goods" },
  requests: [],
};

beforeEach(brokering);

afterEach(unbrokered);

/** An app joined to a session, showing the editing view: the band's selector
 *  is how an operator gets there, and it is the view that has anything to
 *  freeze. */
async function editor(): Promise<TcApp> {
  const shell = await joined();
  await shows(shell, "edit");
  return shell;
}

/** The editing view with the drawing frozen and still open: power read off,
 *  and then the broker lost, so the page cannot know whether the track has
 *  power (#792). With power read on the view does not stay open at all
 *  (ADR-0085, decision 3). */
async function frozen(): Promise<TcApp> {
  const shell = await editor();
  await said(shell, POWER, { power: "off" });
  await closes(shell);
  return shell;
}

/** The page's link dropping, and coming back with the rows still retained. */
async function closes(shell: TcApp): Promise<void> {
  Broker.last!.closes();
  await settled(shell);
}

async function reopens(shell: TcApp): Promise<void> {
  Broker.last!.opens();
  await settled(shell);
}

/** The view that is current, by the rail's mark. */
function current(shell: TcApp): string {
  return rail(shell).querySelector<LookView>("look-view[current]")!.name;
}

/** The rail's Edit button. */
function editButton(shell: TcApp): LookView {
  return rail(shell).querySelector<LookView>('look-view[name="edit"]')!;
}

/** A key pressed with nothing focused, as the shell hears one. */
async function typed(shell: TcApp, key: string): Promise<void> {
  window.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
  await settled(shell);
}

/** A press on the canvas where a grid point is. happy-dom's `getScreenCTM` is
 *  the identity, so a client pixel reads as a square. */
async function pressed(shell: TcApp, at: { x: number; y: number }): Promise<void> {
  (inside(shell, "tc-canvas") as TcCanvas).renderRoot
    .querySelector("svg")!
    .dispatchEvent(
      new PointerEvent("pointerdown", { bubbles: true, clientX: at.x, clientY: at.y }),
    );
  await settled(shell);
}

/** A click on the canvas: a press and then its release, where a portal's mate
 *  in flight would land. */
async function released(shell: TcApp, at: { x: number; y: number }): Promise<void> {
  const svg = (inside(shell, "tc-canvas") as TcCanvas).renderRoot.querySelector("svg")!;
  for (const type of ["pointerdown", "pointerup"]) {
    svg.dispatchEvent(
      new PointerEvent(type, {
        bubbles: true,
        composed: true,
        clientX: at.x,
        clientY: at.y,
      }),
    );
  }
  await settled(shell);
}

/** A right-click on the canvas, where the press helper clicks. */
async function clicked(shell: TcApp, at: { x: number; y: number }): Promise<void> {
  (inside(shell, "tc-canvas") as TcCanvas).renderRoot
    .querySelector("svg")!
    .dispatchEvent(
      new MouseEvent("contextmenu", { bubbles: true, clientX: at.x, clientY: at.y }),
    );
  await settled(shell);
}

/** What the editing view's right-click menu is offering. */
function items(shell: TcApp): string[] {
  const menu = inside(shell, "tc-menu") as LitElement;
  return [...menu.renderRoot.querySelectorAll("li button span")].map((one) =>
    one.textContent!.trim(),
  );
}

/** The properties dialog, `null` while none is open. */
function dialog(shell: TcApp): Element | null {
  return (inside(shell, "tc-properties") as TcProperties).renderRoot.querySelector(
    "look-dialog",
  );
}

/** Whether the band says anything of a frozen drawing. It no longer does:
 *  the Edit view does not open with power on (ADR-0085, decision 3). */
function says(shell: TcApp): boolean {
  return [...band(shell).querySelectorAll("look-reading")].some((one) =>
    one.textContent!.includes("frozen"),
  );
}

const drawn = (shell: TcApp): Drawing => structuredClone(session(shell).drawing);

describe("a frozen drawing", () => {
  /** The bar and the keyboard are one path through `model/commands.ts`, so a
   *  verb that is dead does nothing however it was reached — and the drawing
   *  is what says it did nothing. */
  it("kills the verbs that would change the drawing", async () => {
    const shell = await frozen();
    session(shell).select(["a"]);
    const was = drawn(shell);

    await typed(shell, "r");
    await typed(shell, "Delete");

    expect(drawn(shell)).toEqual(was);
  });

  /** The canvas goes on converting pixels to squares and asking; the machine
   *  is what answers, and while the drawing is frozen it answers nothing
   *  (model/gesture.ts). A press that does not even select is the whole of it:
   *  selecting is where every gesture on the sheet starts. */
  it("makes a press on the sheet mean nothing", async () => {
    const shell = await frozen();
    await pressed(shell, centreOf(stored("toy").symbols.a!));
    expect(session(shell).selection.size).toBe(0);
  });

  /** A palette drag starts on a tile rather than on the sheet, so it is the
   *  view and not the machine that refuses it. */
  it("leaves the palette with nothing to give", async () => {
    const shell = await frozen();
    expect(editing(shell).hasAttribute("frozen")).toBe(true);

    inside(shell, "tc-palette").dispatchEvent(
      new CustomEvent("take", { detail: "block", bubbles: true, composed: true }),
    );
    await settled(shell);

    expect(session(shell).pending).toBeNull();
  });

  /** A widget is edited only while the drawing can be (ADR-0087 decision
   *  1): it is not placed, pressed, moved or deleted on a frozen one. */
  it("leaves the widgets as they are", async () => {
    const shell = await editor();
    await said(shell, POWER, { power: "off" });
    session(shell).placeWidget("text", [20, 20]);
    session(shell).clearSelection();
    await closes(shell);
    const was = drawn(shell);

    for (const kind of ["text", "button", "toggle"]) {
      inside(shell, "tc-palette").dispatchEvent(
        new CustomEvent("take", { detail: kind, bubbles: true, composed: true }),
      );
      await settled(shell);
      expect(session(shell).pending).toBeNull();
    }
    await pressed(shell, { x: 21.5, y: 20.5 });
    expect(session(shell).selection.size).toBe(0);
    session(shell).select([selectionKey("text1")]);
    await typed(shell, "Delete");

    expect(drawn(shell)).toEqual(was);
  });

  /** Looking is what a frozen drawing is still for. */
  it("leaves the netlist and the viewport alone", async () => {
    const shell = await frozen();
    await typed(shell, "n");
    expect(inside(shell, "tc-netlist")).not.toBeNull();
  });

  /** The "drawing frozen" chip is gone (#891). */
  it("says nothing in the band", async () => {
    const shell = await frozen();
    expect(says(shell)).toBe(false);
  });
});

/**
 * The Edit view does not open while track power is on or draining
 * ([ADR-0085](../../docs/adr/0085-the-editor-saves-when-it-is-left-and-a-railroad-can-be-named-without-being-built.md),
 * decision 3; amends ADR-0071 decision 5, which kept it open read-only).
 */
describe("the Edit view with track power on", () => {
  for (const power of ["on", "draining"] as const) {
    it(`disables the rail's Edit button with power ${power}, and says why`, async () => {
      const shell = await joined();
      await said(shell, POWER, { power });

      expect(editButton(shell).disabled).toBe(true);
      expect(editButton(shell).reason).toBe("track power is on");
    });

    it(`moves the page to the run view when power comes ${power}`, async () => {
      const shell = await editor();
      await said(shell, POWER, { power });

      expect(current(shell)).toBe("run");
      expect(location.hash).toBe("#run");
      expect(editing(shell).hasAttribute("frozen")).toBe(true);
    });
  }

  it("does not open from the rail", async () => {
    const shell = await joined();
    await said(shell, POWER, { power: "on" });

    await shows(shell, "edit");

    expect(current(shell)).toBe("run");
  });

  /** A bookmark and a back button are the same choice by another route. */
  it("does not open from the hash", async () => {
    const shell = await joined();
    await said(shell, POWER, { power: "on" });

    location.hash = "#edit";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    await settled(shell);

    expect(current(shell)).toBe("run");
    expect(location.hash).toBe("#run");
  });

  /** Leaving saves nothing with power on (ADR-0085, decision 1): the edits
   *  stay on the page, marked unsaved, for the next time it is left with
   *  power off. */
  it("keeps the edits on the page, marked unsaved", async () => {
    const shell = await editor();
    await said(shell, POWER, { power: "off" });
    session(shell).select(["a"]);
    await typed(shell, "r");
    const was = drawn(shell);

    await said(shell, POWER, { power: "on" });

    expect(current(shell)).toBe("run");
    expect(drawn(shell)).toEqual(was);
    expect(band(shell).querySelector("look-about")!.detail).toBe("unsaved");
  });

  it("opens again once power is off", async () => {
    const shell = await editor();
    await said(shell, POWER, { power: "on" });
    await said(shell, POWER, { power: "off" });

    expect(editButton(shell).disabled).toBe(false);
    expect(editButton(shell).reason).toBe("");
    await shows(shell, "edit");
    expect(current(shell)).toBe("edit");
  });

  it("leaves every other view open", async () => {
    const shell = await joined();
    await said(shell, POWER, { power: "on" });

    const closed = [...rail(shell).querySelectorAll<LookView>("look-view[disabled]")].map(
      (one) => one.name,
    );
    expect(closed).toEqual(["edit"]);
  });
});

/**
 * Power can land while something is in flight in the editor, the page moving
 * to the run view on the same render. What is in flight goes with it, so it
 * does not land on the first click once the Edit view opens again.
 */
describe("track power coming on", () => {
  /** The freeze can land under an open dialog, whose Apply is an edit. */
  it("takes down a properties dialog it lands under", async () => {
    const shell = await editor();
    session(shell).select(["a"]);
    editing(shell).editSelected();
    await settled(shell);
    expect(dialog(shell)).not.toBeNull();

    await said(shell, POWER, { power: "on" });

    expect(dialog(shell)).toBeNull();
  });
  it("takes down a widget's properties dialog it lands under", async () => {
    const shell = await editor();
    session(shell).placeWidget("toggle", [20, 20]);
    editing(shell).editSelected();
    await settled(shell);
    const widgetDialog = () =>
      (inside(shell, "tc-widget-properties") as TcWidgetProperties).renderRoot.querySelector(
        "look-dialog",
      );
    expect(widgetDialog()).not.toBeNull();

    await said(shell, POWER, { power: "on" });

    expect(widgetDialog()).toBeNull();
  });

  /** The right-click menu is the one edit path that does not go through
   *  `model/commands.ts`, so a menu the freeze lands under would still act on
   *  the drawing. It goes with the dialog. */
  it("takes down a right-click menu it lands under", async () => {
    const shell = await editor();
    await clicked(shell, centreOf(stored("toy").symbols.a!));
    expect(items(shell)).not.toEqual([]);

    await said(shell, POWER, { power: "on" });

    expect(items(shell)).toEqual([]);
  });

  /** A wire in flight is the document's rather than the gesture's, so
   *  abandoning presses does not reach it: it would go on following the
   *  pointer across a drawing nobody may draw on, and land on the first click
   *  after the thaw. */
  it("cancels a wire left in flight", async () => {
    const shell = await editor();
    await pressed(shell, centreOf(stored("toy").symbols.a!)); // selects it
    session(shell).startWire("a.B");

    await said(shell, POWER, { power: "on" });

    expect(session(shell).pendingFrom).toBeNull();
  });

  /** A portal's mate stays in flight after its first half drops, until a
   *  click of its own (ADR-0020). It is a placement begun before the freeze,
   *  so it goes like a wire: kept, it would follow the pointer across the
   *  frozen sheet and land on the first click after the thaw. */
  it("cancels a portal's mate left in flight", async () => {
    const shell = await editor();
    session(shell).beginPlace("portal");
    session(shell).dropPending(10.5, 10.5);
    expect(session(shell).mating).toBe(true);

    await said(shell, POWER, { power: "on" });
    expect(session(shell).pending).toBeNull();

    await said(shell, POWER, { power: "off" });
    await released(shell, PAPER);

    const portals = Object.values(session(shell).drawing.symbols).filter(
      (one) => one.kind === "portal",
    );
    expect(portals).toHaveLength(1);
  });

  /** A tile still held when the freeze lands: the release would cancel it,
   *  but the turn while held would get through first. */
  it("cancels a palette drag it lands under", async () => {
    const shell = await editor();
    inside(shell, "tc-palette").dispatchEvent(
      new CustomEvent("take", { detail: "block", bubbles: true, composed: true }),
    );
    await settled(shell);
    expect(session(shell).pending).not.toBeNull();

    await said(shell, POWER, { power: "on" });

    expect(session(shell).pending).toBeNull();
  });
});

describe("loading another railroad", () => {
  /** The freeze rests on what a joined session is saying about *this*
   *  railroad. Loading another is how a session ends now that the loaded
   *  railroad is the session (#171), and the new run has said nothing yet — so
   *  the drawing must thaw rather than stay locked on a reading of somewhere
   *  else. */
  it("thaws the drawing, the new run having said nothing yet", async () => {
    const shell = await editor();
    await said(shell, POWER, { power: "on" });

    await loads(shell, "other");

    expect(editButton(shell).hasAttribute("disabled")).toBe(false);
    expect(editing(shell).hasAttribute("frozen")).toBe(false);
  });
});

describe("track power off", () => {
  /** A train standing with power off freezes nothing: the rebuild a save sets
   *  off keeps it where it fits (ADR-0071). */
  it("leaves the drawing editable with trains placed", async () => {
    const shell = await editor();
    await said(shell, POWER, { power: "off" });
    await said(shell, ALLOCATION, STANDING);
    session(shell).select(["a"]);
    const was = drawn(shell);

    expect(editing(shell).hasAttribute("frozen")).toBe(false);
    await typed(shell, "r");
    expect(drawn(shell)).not.toEqual(was);
  });

  it("thaws the drawing and the palette with it", async () => {
    const shell = await editor();
    await said(shell, POWER, { power: "on" });
    session(shell).select(["a"]);
    const was = drawn(shell);

    await said(shell, POWER, { power: "off" });
    await shows(shell, "edit");

    expect(editing(shell).hasAttribute("frozen")).toBe(false);
    await typed(shell, "r");
    expect(drawn(shell)).not.toEqual(was);
  });

  /** The rule is read off power afresh rather than latched, so a press means
   *  something again the moment it is off. */
  it("gives the sheet its gestures back", async () => {
    const shell = await editor();
    await said(shell, POWER, { power: "on" });
    await said(shell, POWER, { power: "off" });
    await shows(shell, "edit");

    await pressed(shell, centreOf(stored("toy").symbols.a!));

    expect([...session(shell).selection]).toEqual(["a"]);
  });
});

describe("no reading of power", () => {
  /** No session is no run to drift from. */
  it("leaves the drawing editable with no session", async () => {
    const shell = await mounted("edit");

    inside(shell, "tc-palette").dispatchEvent(
      new CustomEvent("take", { detail: "block", bubbles: true, composed: true }),
    );
    await settled(shell);

    expect(editing(shell).hasAttribute("frozen")).toBe(false);
    expect(session(shell).pending).not.toBeNull();
  });

  /** A session whose layout has not said is the same: nothing is known to
   *  move, and a train the dispatcher shows freezes nothing on its own. */
  it("leaves the drawing editable before the layout has said", async () => {
    const shell = await editor();
    await said(shell, ALLOCATION, STANDING);
    session(shell).select(["a"]);
    const was = drawn(shell);

    await typed(shell, "r");

    expect(drawn(shell)).not.toEqual(was);
  });
});

/** What the page has asked for on `railroad_wanted`. */
function wants(): unknown[] {
  return written().filter((one) => (one as { topic: string }).topic === RAILROAD_WANTED);
}

/** The loaded railroad, with an edit in it the store has not been given. */
async function unsaved(power: "on" | "draining" | "off"): Promise<TcApp> {
  const shell = await editor();
  await said(shell, POWER, { power: "off" });
  session(shell).select(["a"]);
  await typed(shell, "r");
  await said(shell, POWER, { power });
  return shell;
}

/** What the page has asked for on `power_wanted`. */
function powers(): unknown[] {
  return written().filter((one) => (one as { topic: string }).topic === POWER_WANTED);
}

/** The band's power control pressed: the toggle, which asks `on` from
 *  `off`, or the stop sign. */
async function supplied(shell: TcApp, which: "on" | "stopped"): Promise<void> {
  press(power(shell), which === "on" ? "toggle" : "stop");
  await settled(shell);
}

/** The Edit view left for the run view, as an operator leaves it. */
async function leaves(shell: TcApp): Promise<void> {
  await shows(shell, "run");
}

/** The band's word beside the railroad's name. */
function marked(shell: TcApp): string {
  return band(shell).querySelector("look-about")!.detail;
}

/**
 * The editor saves when it is left, and there is no Save of a person's own
 * ([ADR-0085](../../docs/adr/0085-the-editor-saves-when-it-is-left-and-a-railroad-can-be-named-without-being-built.md),
 * decision 1). The save names the loaded railroad again on `railroad_wanted`,
 * so every app builds what was written and keeps the trains that fit
 * (ADR-0071); the layout builds only with power off, so with power on or
 * draining nothing is written and the edits stay on the page, marked unsaved.
 * What the save writes and names is `Railroad`'s, and tested there
 * (test/railroad.test.ts); these check the way in.
 */
describe("leaving the editor", () => {
  it("has no Save on the rail", async () => {
    const shell = await unsaved("off");
    expect(railButton(shell, "save")).toBeNull();
  });

  it("writes the drawing once and then names the railroad again, with power off", async () => {
    const store = serving({
      drawings: ["toy"],
      rosterOf: () => STOCK,
      read: stored,
      review: () => Promise.resolve(DERIVES),
    });
    const shell = await unsaved("off");
    expect(marked(shell)).toBe("");

    await leaves(shell);

    expect(store.saved.map(({ path }) => path)).toEqual(["/drawings/toy"]);
    expect(wants()).toEqual([{ topic: RAILROAD_WANTED, payload: { railroad: "toy" } }]);
    expect(marked(shell)).toBe("");
  });

  /** Edits held while power was on are saved the next time the Edit view is
   *  left with power off. */
  it("saves held edits the next time it is left with power off", async () => {
    const store = serving({
      drawings: ["toy"],
      rosterOf: () => STOCK,
      read: stored,
      review: () => Promise.resolve(DERIVES),
    });
    const shell = await unsaved("on");
    await leaves(shell);
    await said(shell, POWER, { power: "off" });
    await shows(shell, "edit");

    await leaves(shell);

    expect(store.saved.map(({ path }) => path)).toEqual(["/drawings/toy"]);
    expect(marked(shell)).toBe("");
  });

  /** ⌘S was Save and ⇧⌘S Save As; both keys are still taken from the
   *  browser, and do nothing else. */
  for (const shiftKey of [false, true]) {
    it(`writes nothing and renames nothing on ${shiftKey ? "⇧⌘S" : "⌘S"}`, async () => {
      const store = serving({
        drawings: ["toy"],
        rosterOf: () => STOCK,
        read: stored,
        review: () => Promise.resolve(DERIVES),
      });
      const shell = await unsaved("off");

      const event = new KeyboardEvent("keydown", {
        key: shiftKey ? "S" : "s",
        metaKey: true,
        shiftKey,
        bubbles: true,
        cancelable: true,
      });
      window.dispatchEvent(event);
      await settled(shell);

      expect(event.defaultPrevented).toBe(true);
      expect(store.saved).toEqual([]);
      expect(session(shell).drawing.drawing).toBe("toy");
    });
  }
});

/**
 * The page hidden or going saves too, with a write that outlives the page
 * (ADR-0085, decision 1).
 */
describe("hiding the page", () => {
  /** Whether each `PUT` went with `keepalive`, wrapped round the store. */
  function kept(): boolean[] {
    const through = globalThis.fetch;
    const seen: boolean[] = [];
    globalThis.fetch = ((path: string, init?: RequestInit) => {
      if (init?.method === "PUT") seen.push(init.keepalive === true);
      return through(path, init);
    }) as typeof fetch;
    return seen;
  }

  it("writes once with keepalive when the page goes", async () => {
    const store = serving({
      drawings: ["toy"],
      rosterOf: () => STOCK,
      read: stored,
      review: () => Promise.resolve(DERIVES),
    });
    const shell = await unsaved("off");
    const seen = kept();

    window.dispatchEvent(new Event("pagehide"));
    window.dispatchEvent(new Event("pagehide"));
    await settled(shell);

    expect(store.saved.map(({ path }) => path)).toEqual(["/drawings/toy"]);
    expect(seen).toEqual([true]);
    expect(wants()).toEqual([{ topic: RAILROAD_WANTED, payload: { railroad: "toy" } }]);
  });

});

/**
 * Losing the broker freezes the drawing too. The editor holds no railroad but
 * the one the row last named (ADR-0072, decision 3), so a drawing still open
 * with no row heard is the loaded railroad's, and the page cannot know whether
 * its track has power: a page's link drops while the broker, `layout` and the
 * dispatcher go on, and trains with them. Nothing is latched: the row heard
 * again with power off lifts it.
 */
describe("losing the broker", () => {
  /** Power is no longer read, so the Edit view opens again; but the page
   *  cannot know whether the track has power, and the drawing stays frozen. */
  it("opens the Edit view frozen, where power was on", async () => {
    const shell = await editor();
    await said(shell, POWER, { power: "on" });
    await closes(shell);
    await shows(shell, "edit");
    session(shell).select(["a"]);
    const was = drawn(shell);

    await typed(shell, "r");

    expect(current(shell)).toBe("edit");
    expect(editing(shell).hasAttribute("frozen")).toBe(true);
    expect(drawn(shell)).toEqual(was);
  });

  it("writes nothing and names nothing on leaving, an edit made with power off", async () => {
    const store = serving({
      drawings: ["toy"],
      rosterOf: () => STOCK,
      read: stored,
      review: () => Promise.resolve(DERIVES),
    });
    const shell = await unsaved("off");
    await closes(shell);

    await leaves(shell);

    expect(store.saved).toEqual([]);
    expect(wants()).toEqual([]);
  });

  it("lifts when the row is heard again and power reads off", async () => {
    const store = serving({
      drawings: ["toy"],
      rosterOf: () => STOCK,
      read: stored,
      review: () => Promise.resolve(DERIVES),
    });
    const shell = await unsaved("off");
    await closes(shell);
    await reopens(shell);

    expect(editing(shell).hasAttribute("frozen")).toBe(false);
    await leaves(shell);

    expect(store.saved.map(({ path }) => path)).toContain("/drawings/toy");
    expect(wants()).toEqual([{ topic: RAILROAD_WANTED, payload: { railroad: "toy" } }]);
  });

  it("stays frozen, and the Edit view shut, when the row is heard again with power on", async () => {
    const shell = await editor();
    await said(shell, POWER, { power: "on" });
    await closes(shell);
    await reopens(shell);

    expect(editing(shell).hasAttribute("frozen")).toBe(true);
    expect(editButton(shell).hasAttribute("disabled")).toBe(true);
  });
});

/**
 * ON with unsaved edits saves first, and power comes on once the apps have
 * built what was saved (ADR-0085, decision 2): the row naming the railroad
 * again is the build arriving, and `on` goes only after it. What cancels the
 * wait is the session's, and tested there (test/session.test.ts).
 */
describe("ON with the loaded railroad's edits unsaved", () => {
  it("is live", async () => {
    const shell = await unsaved("off");
    expect(power(shell).reason).toBe("");
  });

  it("writes, names the railroad again, and sends on only once the build arrives", async () => {
    const store = serving({
      drawings: ["toy"],
      rosterOf: () => STOCK,
      read: stored,
      review: () => Promise.resolve(DERIVES),
    });
    const shell = await unsaved("off");

    await supplied(shell, "on");

    expect(store.saved.map(({ path }) => path)).toEqual(["/drawings/toy"]);
    expect(wants()).toEqual([{ topic: RAILROAD_WANTED, payload: { railroad: "toy" } }]);
    expect(powers()).toEqual([]);

    await said(shell, RAILROAD, { name: "toy", built: true });

    expect(powers()).toEqual([{ topic: POWER_WANTED, payload: { power: "on" } }]);
  });

  /** ON pressed while leaving the Edit view writes is the same save: the
   *  railroad is named once, not once for each (#910). */
  it("names the railroad once for ON pressed while leaving's write is out", async () => {
    let answer: () => void = () => {};
    const gate = new Promise<void>((resolve) => (answer = resolve));
    const store = serving({
      drawings: ["toy"],
      rosterOf: () => STOCK,
      read: stored,
      review: () => Promise.resolve(DERIVES),
      held: (path) => (path === "/drawings/toy" ? gate : null),
    });
    const shell = await unsaved("off");

    await leaves(shell);
    await supplied(shell, "on");
    answer();
    await settled(shell);

    expect(store.saved.map(({ path }) => path)).toEqual(["/drawings/toy"]);
    expect(wants()).toEqual([{ topic: RAILROAD_WANTED, payload: { railroad: "toy" } }]);
    expect(powers()).toEqual([]);

    await said(shell, RAILROAD, { name: "toy", built: true });

    expect(powers()).toEqual([{ topic: POWER_WANTED, payload: { power: "on" } }]);
  });

  it("sends on at once with nothing unsaved", async () => {
    const shell = await editor();
    await said(shell, POWER, { power: "off" });

    await supplied(shell, "on");

    expect(wants()).toEqual([]);
    expect(powers()).toEqual([{ topic: POWER_WANTED, payload: { power: "on" } }]);
  });
});
