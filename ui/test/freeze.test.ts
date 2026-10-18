// @vitest-environment happy-dom

/**
 * Track power on or stopped freezes the drawing
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
 * crosses every one of those, which is why it is a DOM suite. So do the two
 * rules that come with it: Save of the loaded railroad names it again, and ON
 * waits for that save.
 */

import type { LitElement } from "lit";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-app.js";
import type { Drawing } from "../src/model/drawing.js";
import { centreOf } from "../src/model/geometry.js";
import type { TcApp } from "../src/ui/tc-app.js";
import type { TcCanvas } from "../src/ui/tc-canvas.js";
import type { TcProperties } from "../src/ui/tc-properties.js";
import {
  band,
  editing,
  inside,
  mounted,
  power,
  pressed as pressedOnRail,
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
  said,
  STOCK,
  stored,
  unbrokered,
  written,
} from "./support/session.js";

const ALLOCATION = "tc49/dispatch/state/allocation";
const POWER = "tc49/layout/state/power";
const RAILROAD_WANTED = "tc49/layout/railroad_wanted";

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

/** The editing view with track power on. */
async function frozen(): Promise<TcApp> {
  const shell = await editor();
  await said(shell, POWER, { power: "on" });
  return shell;
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

/** What the band says about the freeze, `null` while it says nothing. */
function says(shell: TcApp): string | null {
  const said = [...band(shell).querySelectorAll("look-reading")].find(
    (one) => one.textContent!.trim() === "drawing frozen",
  );
  return said === undefined ? null : said.textContent!.trim();
}

const drawn = (shell: TcApp): Drawing => structuredClone(session(shell).drawing);

describe("track power on", () => {
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

  /** Stopped is an emergency stop somebody clears back to on, not a rest. */
  it("is frozen stopped as well", async () => {
    const shell = await editor();
    await said(shell, POWER, { power: "stopped" });
    session(shell).select(["a"]);
    const was = drawn(shell);

    await typed(shell, "r");
    await pressed(shell, centreOf(stored("toy").symbols.b!));

    expect(drawn(shell)).toEqual(was);
    expect(editing(shell).hasAttribute("frozen")).toBe(true);
  });

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

  /** Looking is what a frozen drawing is still for. */
  it("leaves the netlist and the viewport alone", async () => {
    const shell = await frozen();
    await typed(shell, "n");
    expect(inside(shell, "tc-netlist")).not.toBeNull();
  });

  it("is what the band says, in the words the rest of it uses", async () => {
    const shell = await frozen();
    expect(says(shell)).toBe("drawing frozen");
  });

  /**
   * The band says it in the editing view alone (#517).
   *
   * The mark exists to explain the verbs the freeze kills, and they are the
   * editor's. Power on is the ordinary state of a railroad being run, so in
   * the run view the same mark is a warning about nothing — and the freeze
   * itself is unchanged, the editing view still being read-only when it is
   * switched back to.
   */
  it("says nothing in the views the dead verbs are not in", async () => {
    const shell = await frozen();
    expect(says(shell)).toBe("drawing frozen");

    for (const view of ["run", "throttle", "stock"] as const) {
      await shows(shell, view);
      expect(says(shell)).toBeNull();
    }

    await shows(shell, "edit");
    expect(says(shell)).toBe("drawing frozen");
    expect(editing(shell).hasAttribute("frozen")).toBe(true);
  });
});

describe("loading another railroad", () => {
  /** The freeze rests on what a joined session is saying about *this*
   *  railroad. Loading another is how a session ends now that the loaded
   *  railroad is the session (#171), and the new run has said nothing yet — so
   *  the drawing must thaw rather than stay locked on a reading of somewhere
   *  else. */
  it("thaws the drawing, the new run having said nothing yet", async () => {
    const shell = await frozen();
    expect(says(shell)).toBe("drawing frozen");

    await loads(shell, "other");

    expect(says(shell)).toBeNull();
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

    expect(says(shell)).toBeNull();
    expect(editing(shell).hasAttribute("frozen")).toBe(false);
    await typed(shell, "r");
    expect(drawn(shell)).not.toEqual(was);
  });

  it("thaws the drawing, the band and the palette with it", async () => {
    const shell = await frozen();
    session(shell).select(["a"]);
    const was = drawn(shell);

    await said(shell, POWER, { power: "off" });

    expect(says(shell)).toBeNull();
    expect(editing(shell).hasAttribute("frozen")).toBe(false);
    await typed(shell, "r");
    expect(drawn(shell)).not.toEqual(was);
  });

  /** The rule is read off power afresh rather than latched, so a press means
   *  something again the moment it is off. */
  it("gives the sheet its gestures back", async () => {
    const shell = await frozen();
    await said(shell, POWER, { power: "off" });

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

    expect(says(shell)).toBeNull();
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
async function unsaved(power: "on" | "off"): Promise<TcApp> {
  const shell = await editor();
  await said(shell, POWER, { power: "off" });
  session(shell).select(["a"]);
  await typed(shell, "r");
  await said(shell, POWER, { power });
  return shell;
}

/**
 * Saving the loaded railroad names it again on `railroad_wanted`, so every app
 * builds what was written and keeps the trains that fit (ADR-0071). The layout
 * builds only with power off, so while power is on the save waits.
 */
describe("saving the loaded railroad", () => {
  it("is dead while power is on", async () => {
    const shell = await unsaved("on");
    expect(railButton(shell, "save")!.disabled).toBe(true);
  });

  it("writes the drawing and then names the railroad again, with power off", async () => {
    const store = serving({
      drawings: ["toy"],
      rosterOf: () => STOCK,
      read: stored,
      review: () => Promise.resolve(DERIVES),
    });
    const shell = await unsaved("off");

    await pressedOnRail(shell, "save");

    expect(store.saved.map(({ path }) => path)).toContain("/drawings/toy");
    expect(wants()).toEqual([{ topic: RAILROAD_WANTED, payload: { railroad: "toy" } }]);
  });

  /** What it wrote is toy's, and otira is what is loaded once the write
   *  answers: naming either would rebuild something nobody asked for (#798). */
  it("names nothing where the row named another railroad before the write answered", async () => {
    let answer: () => void = () => {};
    const gate = new Promise<void>((resolve) => (answer = resolve));
    serving({
      drawings: ["toy", "otira"],
      rosterOf: () => STOCK,
      read: stored,
      review: () => Promise.resolve(DERIVES),
      held: (path) => (path === "/drawings/toy" ? gate : null),
    });
    const shell = await unsaved("off");

    await pressedOnRail(shell, "save");
    await loads(shell, "otira");
    answer();
    await settled(shell);

    expect(wants()).toEqual([]);
  });

  /** ⇧⌘S was Save As, which went with #734: the editor holds the loaded
   *  railroad and no other (ADR-0072, decision 3). The key is still taken
   *  from the browser, and does nothing else. */
  it("writes nothing and renames nothing on ⇧⌘S", async () => {
    const store = serving({
      drawings: ["toy"],
      rosterOf: () => STOCK,
      read: stored,
      review: () => Promise.resolve(DERIVES),
    });
    const shell = await unsaved("off");

    const event = new KeyboardEvent("keydown", {
      key: "S",
      metaKey: true,
      shiftKey: true,
      bubbles: true,
      cancelable: true,
    });
    window.dispatchEvent(event);
    await settled(shell);

    expect(event.defaultPrevented).toBe(true);
    expect(store.saved).toEqual([]);
    expect(session(shell).drawing.drawing).toBe("toy");
    expect(band(shell).querySelector("look-about")!.detail).toBe("unsaved");
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
  /** What the band's frozen mark gives as its reason. */
  function why(shell: TcApp): string | null {
    const said = [...band(shell).querySelectorAll("look-reading")].find(
      (one) => one.textContent!.trim() === "drawing frozen",
    );
    return said === undefined ? null : said.getAttribute("title");
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

  /** ⌘S with nothing focused, as the shell hears it. */
  async function saved(shell: TcApp): Promise<void> {
    window.dispatchEvent(
      new KeyboardEvent("keydown", { key: "s", metaKey: true, bubbles: true, cancelable: true }),
    );
    await settled(shell);
  }

  it("keeps the drawing frozen with power on", async () => {
    const shell = await frozen();
    await closes(shell);
    session(shell).select(["a"]);
    const was = drawn(shell);

    await typed(shell, "r");

    expect(editing(shell).hasAttribute("frozen")).toBe(true);
    expect(drawn(shell)).toEqual(was);
    expect(railButton(shell, "save")!.disabled).toBe(true);
  });

  it("writes nothing and names nothing on ⌘S, an edit made with power off", async () => {
    const store = serving({
      drawings: ["toy"],
      rosterOf: () => STOCK,
      read: stored,
      review: () => Promise.resolve(DERIVES),
    });
    const shell = await unsaved("off");
    await closes(shell);

    await saved(shell);

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
    await pressedOnRail(shell, "save");

    expect(store.saved.map(({ path }) => path)).toContain("/drawings/toy");
    expect(wants()).toEqual([{ topic: RAILROAD_WANTED, payload: { railroad: "toy" } }]);
  });

  it("stays frozen when the row is heard again with power on", async () => {
    const shell = await frozen();
    await closes(shell);
    await reopens(shell);

    expect(editing(shell).hasAttribute("frozen")).toBe(true);
    expect(why(shell)).toBe("track power is on, so the drawing is read-only");
  });

  it("says why in the band", async () => {
    const shell = await editor();
    await said(shell, POWER, { power: "off" });
    await closes(shell);

    expect(says(shell)).toBe("drawing frozen");
    expect(why(shell)).toBe(
      "the layout has not said whether the track has power, so the drawing is read-only",
    );
  });
});

/**
 * ON waits for the save (ADR-0071, decision 6). The run view draws the open
 * drawing, so power on with the loaded railroad's edits unsaved would run
 * trains under track no app built. With the supply off, the power control is
 * dead until the save, and says why (look#12).
 */
describe("ON with the loaded railroad's edits unsaved", () => {
  it("is dead and says why", async () => {
    const shell = await unsaved("off");
    expect(power(shell).reason).toBe("Save the railroad first");
  });

  it("comes back once the save lands", async () => {
    const shell = await unsaved("off");
    await pressedOnRail(shell, "save");
    expect(power(shell).reason).toBe("");
  });
});
