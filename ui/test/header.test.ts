// @vitest-environment happy-dom

/**
 * The band across the top of both pages: what is open, and the status that is
 * nobody's mistake — the store not answering, the broker, the session clock.
 *
 * A DOM test, the whole of the behaviour being what the component renders,
 * as `tc-menu`'s is.
 */

import { describe, expect, it, vi } from "vitest";

import { VIEWS } from "../src/model/views.js";
import "../src/ui/tc-header.js";
import type { TcHeader } from "../src/ui/tc-header.js";

/** One band, with the facts a page would hand it. */
async function band(facts: Partial<TcHeader> = {}): Promise<TcHeader> {
  const header = document.createElement("tc-header");
  Object.assign(header, facts);
  document.body.append(header);
  await header.updateComplete;
  return header;
}

/** What the band says in one of its parts, or `null` where it draws none. */
function reads(header: TcHeader, part: string): string | null {
  const found = header.renderRoot.querySelector(part);
  return found === null ? null : found.textContent!.trim();
}

/** The selector's buttons, one per view, in the order they are drawn. */
function views(header: TcHeader): HTMLButtonElement[] {
  return [...header.renderRoot.querySelectorAll<HTMLButtonElement>("button.view")];
}

/** Put the picker's list down, which is where a railroad is chosen. */
async function listing(header: TcHeader): Promise<TcHeader> {
  (header.renderRoot.querySelector("button.chosen") as HTMLElement).click();
  await header.updateComplete;
  return header;
}

/** Click one of the railroads the picker lists. */
async function choose(header: TcHeader, name: string): Promise<TcHeader> {
  const entries = [...header.renderRoot.querySelectorAll("menu.drawings li button")];
  const entry = entries.find(
    (one) => one.querySelector(".label")!.textContent!.trim() === name,
  ) as HTMLElement;
  entry.click();
  await header.updateComplete;
  return header;
}

/** The railroads the picker was asked for while `act` ran. */
async function asked(header: TcHeader, act: () => Promise<void>): Promise<string[]> {
  const heard: string[] = [];
  header.addEventListener("railroad-wanted", (event) => {
    heard.push((event as CustomEvent<string>).detail);
  });
  await act();
  return heard;
}

/** A band with three railroads to pick from, one of them loaded, and the
 *  rails dead — which is the whole of the precondition on picking one
 *  (ADR-0060). */
const LOADED = {
  drawing: "reversing-loops",
  drawings: ["crossover-yard", "reversing-loops", "otira"],
  power: "off" as const,
};

/** Which railroad is loaded is the whole system's, both views being of it, so
 *  the name reads in the band and not on a view's bar (#167, ADR-0038). */
describe("what the band names", () => {
  it("names the railroad that is loaded", async () => {
    expect(reads(await band({ drawing: "reversing-loops" }), ".drawing")).toBe(
      "reversing-loops",
    );
  });

  it("says plainly when none is", async () => {
    expect(reads(await band(), ".drawing")).toBe("no railroad");
  });
});

/** Which railroad is loaded is the whole system's, so the control that asks
 *  for another is the band's and not a menu on one view's bar (#167,
 *  ADR-0038). It asks and does not load: the gesture goes on the bus and the
 *  layout interface answers it (ADR-0060). */
describe("the railroad picker", () => {
  it("lists what the store has and ticks the one that is loaded", async () => {
    const header = await listing(await band(LOADED));
    const listed = [...header.renderRoot.querySelectorAll("menu.drawings li")].map(
      (one) => [
        one.querySelector(".label")!.textContent!.trim(),
        one.querySelector(".tick")!.textContent!.trim(),
      ],
    );
    expect(listed).toEqual([
      ["crossover-yard", ""],
      ["reversing-loops", "✓"],
      ["otira", ""],
    ]);
  });

  it("says which railroad was chosen, and puts the list up", async () => {
    const header = await listing(await band(LOADED));
    const heard = await asked(header, async () => {
      await choose(header, "otira");
    });
    expect(heard).toEqual(["otira"]);
    expect(header.renderRoot.querySelector("menu.drawings")).toBeNull();
  });

  /** The name goes on being the row the layout interface answered with: the
   *  band asks, and the app is told what is loaded by the bus (ADR-0035). */
  it("goes on naming the railroad that is loaded after a choice", async () => {
    const header = await listing(await band(LOADED));
    await choose(header, "otira");
    expect(reads(header, ".drawing")).toBe("reversing-loops");
  });

  /** The tick says which railroad is loaded, and that is all it says:
   *  re-reading it would throw away whatever has been drawn since (#101). The
   *  rule moves here whole from `File ▸ Open`. */
  it("asks for nothing when the loaded railroad is chosen", async () => {
    const header = await listing(await band(LOADED));
    const heard = await asked(header, async () => {
      await choose(header, "reversing-loops");
    });
    expect(heard).toEqual([]);
    expect(header.renderRoot.querySelector("menu.drawings")).toBeNull();
  });

  /** A list of nothing is an empty box that looks broken — the lesson the
   *  right-click menu already learnt (tc-menu). */
  it("is dead where the store has nothing to list", async () => {
    const header = await band({ ...LOADED, drawings: [] });
    const button = header.renderRoot.querySelector<HTMLButtonElement>("button.chosen")!;
    expect(button.disabled).toBe(true);
    expect(button.title).toBe("the store lists no railroad");
  });

  /** Track power off is the precondition (ADR-0060): a train already under a
   *  committed route keeps rolling whatever the software forgets, so nothing
   *  is loaded under live rails. Dead and saying why, because a control that
   *  is dead and silent reads as an app that is broken — and dead rather than
   *  turning the power off for you, which is the panel's OFF, drains the run
   *  first, and is already a gesture a person has (ADR-0051). */
  it.each(["on", "stopped"] as const)(
    "is dead while the track reads %s, and offers no way past it",
    async (power) => {
      const header = await band({ ...LOADED, power });
      const button =
        header.renderRoot.querySelector<HTMLButtonElement>("button.chosen")!;
      expect(button.disabled).toBe(true);
      expect(button.title).toBe(
        "the track has power: switch it off to load another railroad",
      );

      button.click();
      await header.updateComplete;

      expect(header.renderRoot.querySelector("menu.drawings")).toBeNull();
    },
  );

  /** With no session joined there is nothing on the other end of the gesture:
   *  the client is the run view's, and a press would go nowhere. */
  it("is dead where the layout has said nothing about the supply", async () => {
    const header = await band({ ...LOADED, power: null });
    const button = header.renderRoot.querySelector<HTMLButtonElement>("button.chosen")!;
    expect(button.disabled).toBe(true);
    expect(button.title).toBe("no railroad is running to ask");
  });

  it("puts the list up when the press lands outside it", async () => {
    const header = await listing(await band(LOADED));
    header.renderRoot.querySelector(".dismiss")!.dispatchEvent(new Event("pointerdown"));
    await header.updateComplete;
    expect(header.renderRoot.querySelector("menu.drawings")).toBeNull();
  });
});

describe("what the band marks as unsaved", () => {
  /** The dot is the whole indicator: no button's disabled state has to be
   *  read to see that a drawing has edits in it (#84). */
  it("marks a drawing with edits in it", async () => {
    const header = await band({ drawing: "reversing-loops", unsaved: true });
    expect(header.renderRoot.querySelector(".unsaved")).not.toBeNull();
  });

  it("marks nothing once the drawing is saved", async () => {
    const header = await band({ drawing: "reversing-loops", unsaved: false });
    expect(header.renderRoot.querySelector(".unsaved")).toBeNull();
  });

  /** The mark carries its meaning in a label as well as in ink, a dot being no
   *  use to a reader that cannot see it. */
  it("labels the dot rather than leaving it a glyph", async () => {
    const header = await band({ drawing: "reversing-loops", unsaved: true });
    const dot = header.renderRoot.querySelector(".unsaved")!;
    expect(dot.getAttribute("role")).toBe("img");
    expect(dot.getAttribute("aria-label")).toBe("unsaved");
  });
});

describe("the status the band takes over", () => {
  /** A region with room in it rather than a string: per-container and
   *  hardware reachability belong beside the store and the broker, and the
   *  slot is where `2a-docker` puts them (#167). */
  it("gathers what is answering into one area with room in it", async () => {
    const header = await band({
      joined: true,
      linked: true,
      power: "on",
      derives: false,
      trouble: "the store is not answering",
    });
    const health = header.renderRoot.querySelector(".health")!;
    expect([...health.querySelectorAll("span")].map((one) => one.className)).toEqual([
      "refused",
      "trouble",
      "link joined",
      "power on",
      "session",
    ]);
    expect(health.querySelector("slot[name=health]")).not.toBeNull();
  });

  /** The store not answering is not one of the author's mistakes, so it
   *  reads here rather than on the drawing (#84). */
  it("reads the trouble the page is in", async () => {
    const header = await band({ trouble: "the store is not answering" });
    expect(reads(header, ".trouble")).toBe("the store is not answering");
  });

  it("says nothing where there is no trouble", async () => {
    expect(reads(await band(), ".trouble")).toBeNull();
  });

  it("says whether the broker is answering a joined session", async () => {
    expect(reads(await band({ joined: true, linked: true }), ".link")).toBe(
      "connected",
    );
    expect(reads(await band({ joined: true, linked: false }), ".link")).toBe(
      "not connected",
    );
  });

  /** With no session joined there is no broker to be answering. */
  it("says nothing about a broker off a joined session", async () => {
    expect(reads(await band({ linked: true }), ".link")).toBeNull();
  });

  /** Which of the two it is, and not only that something is wrong: the
   *  person recovering clears an emergency stop or switches a supply back on,
   *  which are different actions (ADR-0041). It is also the reason the bar's
   *  GO is greyed beside it. */
  it("says whether the rails have power, and which way they have not", async () => {
    expect(reads(await band({ power: "on" }), ".power")).toBe("power on");
    expect(reads(await band({ power: "off" }), ".power")).toBe("power off");
    expect(reads(await band({ power: "stopped" }), ".power")).toBe("emergency stop");
  });

  /** With no session joined nothing has said, and a drawing has no rails to
   *  have power. */
  it("says nothing about power off a joined session", async () => {
    expect(reads(await band({ power: null }), ".power")).toBeNull();
  });

  /** The session clock: elapsed time on the page's own clock, until a fast
   *  clock derived from the railroad's configuration replaces it (ADR-0047).
   *  A view reads a clock for scenery, never for control (ADR-0009). */
  it("runs a session clock while a session is joined", async () => {
    vi.useFakeTimers();
    try {
      const header = await band({ joined: true });
      expect(reads(header, ".session")).toBe("session 00:00");
      vi.advanceTimersByTime(65_000);
      await header.updateComplete;
      expect(reads(header, ".session")).toBe("session 01:05");
    } finally {
      vi.useRealTimers();
    }
  });

  /** With no session joined there is no session to time, and a drawing that
   *  nothing is running on never has one. */
  it("shows no session clock off a joined session", async () => {
    expect(reads(await band(), ".session")).toBeNull();
  });
});

describe("whether the drawing derives", () => {
  /** The coarse counterpart to the marks on the canvas (ADR-0024): one
   *  indicator, no fault named and nothing counted. */
  it("marks a drawing derivation refused", async () => {
    expect(reads(await band({ drawing: "reversing-loops", derives: false }), ".refused")).toBe(
      "does not derive",
    );
  });

  it("is clean while the drawing derives", async () => {
    expect(reads(await band({ drawing: "reversing-loops", derives: true }), ".refused")).toBeNull();
  });

  /** A page with nothing to say about derivation — the panel — says nothing. */
  it("is clean where nothing said otherwise", async () => {
    expect(reads(await band(), ".refused")).toBeNull();
  });

  /** One is the author's to fix and the other is not, so neither stands in for
   *  the other and both can show at once. */
  it("is a mark of its own, beside the store not answering", async () => {
    const header = await band({
      derives: false,
      trouble: "the store is not answering",
    });
    expect(reads(header, ".refused")).toBe("does not derive");
    expect(reads(header, ".trouble")).toBe("the store is not answering");
  });
});

/**
 * ON, STOP and OFF (ADR-0051). They stand beside the reading they act on,
 * because track power is the whole railroad's and no document's, and each
 * names where the supply should stand rather than asking for a change.
 */
describe("commanding the supply", () => {
  /** The three presses, in the order the band draws them. */
  function presses(header: TcHeader): HTMLButtonElement[] {
    return [...header.renderRoot.querySelectorAll<HTMLButtonElement>("button.press")];
  }

  /** What was asked of the supply while `act` ran. */
  function asking(header: TcHeader, act: () => void): string[] {
    const heard: string[] = [];
    header.addEventListener("power-wanted", (event) => {
      heard.push((event as CustomEvent<string>).detail);
    });
    act();
    return heard;
  }

  /** A band on a joined session with the broker answering. */
  const LIVE = { joined: true, linked: true };

  it("offers ON, STOP and OFF on a joined session", async () => {
    const header = await band(LIVE);
    expect(presses(header).map((one) => one.textContent!.trim())).toEqual([
      "ON",
      "STOP",
      "OFF",
    ]);
  });

  /** No session is no railroad to command, and a drawing has no rails. */
  it("offers nothing off a joined session", async () => {
    expect(presses(await band()).length).toBe(0);
  });

  /** A broker that is not answering would swallow the press, so the button
   *  is dead rather than pretending it landed. Dead and not hidden: the row
   *  must not move under the hand. */
  it("is dead while the broker is not answering", async () => {
    const header = await band({ joined: true, linked: false });
    expect(presses(header).map((one) => one.disabled)).toEqual([true, true, true]);
  });

  /** One click and no dialog. An emergency stop that asks "are you sure?" is
   *  not one, and `stopped` is cheap to recover from. */
  it("asks for an emergency stop on one click, with nothing in the way", async () => {
    const header = await band(LIVE);
    const heard = asking(header, () => presses(header)[1]!.click());
    expect(heard).toEqual(["stopped"]);
    expect(header.renderRoot.querySelector("sl-dialog")).toBeNull();
  });

  it("asks for power and for the supply to go", async () => {
    const header = await band(LIVE);
    expect(asking(header, () => presses(header)[0]!.click())).toEqual(["on"]);
    expect(asking(header, () => presses(header)[2]!.click())).toEqual(["off"]);
  });

  /** None is greyed by the value it would write: each names where the supply
   *  should stand, so a press that agrees with where it stands is not a
   *  race. */
  it("offers every press whatever the supply is doing", async () => {
    for (const power of ["on", "stopped", "off"] as const) {
      const header = await band({ ...LIVE, power });
      expect(presses(header).map((one) => one.disabled)).toEqual([false, false, false]);
    }
  });

  /** The drain is outstanding, so the button says what it is waiting for.
   *  A drain that never lands leaves the railroad powered, and a button
   *  still reading OFF would say the opposite. */
  it("says the drain is outstanding rather than that the supply has gone", async () => {
    const header = await band({ ...LIVE, draining: true });
    const off = presses(header)[2]!;
    expect(off.textContent!.trim()).toBe("DRAINING…");
    expect(off.disabled).toBe(true);
    expect(off.title).toBe("waiting for the run to drain");
  });

  /** ON is the way out of a wait, so it keeps its word and stays live. */
  it("leaves ON and STOP alive while the drain is outstanding", async () => {
    const header = await band({ ...LIVE, draining: true });
    const [on, stop] = presses(header);
    expect([on!.disabled, stop!.disabled]).toEqual([false, false]);
    expect(on!.textContent!.trim()).toBe("ON");
  });
});

/** Views are a list with one current entry, drawn as one icon-button each
 *  with the current one marked — the selector ADR-0038 said a third view
 *  would make of the toggle two of them were. */
describe("the view selector", () => {
  /** The list is what the views are, so every one of them has a button and
   *  the current one is marked rather than missing. */
  it("offers every view the app has, in the order the list has them", async () => {
    const buttons = views(await band({ view: "run" }));
    expect(buttons.map((one) => one.getAttribute("aria-label"))).toEqual(
      VIEWS.map((view) => view.label),
    );
  });

  it("marks the one that is current and no other", async () => {
    for (const view of VIEWS) {
      const marked = views(await band({ view: view.id }))
        .filter((one) => one.classList.contains("current"))
        .map((one) => one.dataset["view"]);
      expect(marked).toEqual([view.id]);
    }
  });

  it("asks for the view whose button was pressed", async () => {
    const header = await band({ view: "run" });
    const heard: string[] = [];
    header.addEventListener("view-wanted", (event) => {
      heard.push((event as CustomEvent<string>).detail);
    });
    for (const button of views(header)) button.click();
    expect(heard).toEqual(VIEWS.map((view) => view.id));
  });
});
