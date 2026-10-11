// @vitest-environment happy-dom

/**
 * The band across the top of both pages: what is open, and the status that is
 * nobody's mistake — the store not answering, the broker, the session clock.
 *
 * A DOM test, the whole of the behaviour being what the component renders,
 * as `tc-menu`'s is.
 */

import { describe, expect, it, vi } from "vitest";

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

/** Which railroad is loaded is the whole system's, both views being of it, so
 *  the name reads in the band and not on a view's bar (#167, ADR-0038). */
describe("what the band names", () => {
  it("names the railroad that is loaded", async () => {
    expect(reads(await band({ drawing: "reversing-loops" }), ".drawing")).toBe(
      "reversing-loops",
    );
  });

  it("says plainly when none is", async () => {
    expect(reads(await band(), ".drawing")).toBe("no railroad loaded");
  });
});

/** Loading another railroad, and backup, are the settings dialog's, behind a
 *  gear on the band (ADR-0072). The name says which is loaded and is not
 *  pressed. */
describe("the way into settings", () => {
  function gear(header: TcHeader): HTMLButtonElement | null {
    return header.renderRoot.querySelector<HTMLButtonElement>("button.settings");
  }

  it("has no picker: the name is text", async () => {
    const header = await band({ drawing: "reversing-loops", power: "off" });
    expect(header.renderRoot.querySelector(".drawing")!.closest("button")).toBeNull();
    expect(header.renderRoot.querySelector("menu")).toBeNull();
  });

  it("asks for settings when the gear is pressed", async () => {
    const header = await band();
    let wanted = 0;
    header.addEventListener("settings-wanted", () => {
      wanted += 1;
    });
    gear(header)!.click();
    expect(wanted).toBe(1);
    expect(gear(header)!.title).toBe("Settings");
  });

  /** A new box has no railroad loaded and no session to join, and the gear
   *  is where its first railroad is loaded from. */
  it("is the last thing on the band with no session joined", async () => {
    const header = await band();
    const pressed = [...header.renderRoot.querySelectorAll("button")];
    expect(pressed.at(-1)).toBe(gear(header));
  });

  it("sits before ON", async () => {
    const header = await band({ joined: true, linked: true });
    const pressed = [...header.renderRoot.querySelectorAll("button")];
    const on = pressed.find((one) => one.textContent!.trim() === "ON")!;
    expect(pressed.indexOf(gear(header)!)).toBe(pressed.indexOf(on) - 1);
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
      fault: "district B tripped",
    });
    const health = header.renderRoot.querySelector(".health")!;
    expect([...health.querySelectorAll("span")].map((one) => one.className)).toEqual([
      "refused",
      "trouble",
      "fault",
      "session",
    ]);
    expect(health.querySelector("slot[name=health]")).not.toBeNull();
  });

  /**
   * Nothing that is going right reads here (#517). A band whose status line is
   * always full is one nobody reads, so the entry that matters is not seen
   * either.
   *
   * The whole of the ordinary case: a session joined, the broker answering, the
   * rails live, the drawing deriving, and trains standing on the layout. Only
   * the session clock is drawn.
   */
  it("says nothing at all while everything is going right", async () => {
    const header = await band({
      joined: true,
      linked: true,
      power: "on",
      derives: true,
      frozen: false,
      fault: null,
    });
    const health = header.renderRoot.querySelector(".health")!;
    expect([...health.querySelectorAll("span")].map((one) => one.className)).toEqual([
      "session",
    ]);
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

  /** The link has no word of its own at all (#517): connected is the ordinary
   *  case, and not connected is a sentence in `trouble` that names the broker
   *  and asks whether the bus is running (`tc-panel.ts`). Two entries saying
   *  one thing, one of them with nothing a person could act on in it. */
  it("says nothing of its own about the broker either way", async () => {
    for (const linked of [true, false]) {
      const header = await band({ joined: true, linked });
      expect(header.renderRoot.querySelector(".link")).toBeNull();
    }
  });

  /** Track power reads as the mark on the press that names where it stands
   *  (#517), not as a word beside three buttons saying the same thing. */
  it("says nothing of its own about power", async () => {
    for (const power of ["on", "off", "stopped", null] as const) {
      const header = await band({ joined: true, linked: true, power });
      expect(header.renderRoot.querySelector(".power")).toBeNull();
    }
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
 * What the hardware says is wrong with the supply, in its own words
 * (BUS.md, device vocabulary; #602).
 *
 * A fault and not a reading of the supply: a command station that cuts one
 * district by itself goes on reporting the railroad as powered, and a district
 * reaches no topic of its own, so the sentence the hardware publishes is the
 * whole of what says a trip is standing
 * ([ADR-0050](../../docs/adr/0050-broken-hardware-is-reported-never-worked-around.md)).
 * The mark on the presses says where the supply stands and cannot say this —
 * since #585 a marked OFF wears the plain mark, so a dark railroad reads as
 * one at rest.
 */
describe("a fault the hardware reports", () => {
  it("says what the hardware said", async () => {
    const header = await band({ joined: true, fault: "district B tripped" });
    expect(reads(header, ".fault")).toBe("district B tripped");
  });

  /** The reading and the fault are two things, and the loud one is the fault:
   *  a trip while the other districts are powered is a railroad that looks
   *  entirely well. */
  it("shows whichever way the supply stands", async () => {
    for (const power of ["on", "stopped", "off"] as const) {
      const header = await band({
        joined: true,
        linked: true,
        power,
        fault: "district B tripped",
      });
      expect(reads(header, ".fault")).toBe("district B tripped");
    }
  });

  it("says nothing where the hardware reports none", async () => {
    expect(reads(await band({ joined: true, power: "on" }), ".fault")).toBeNull();
  });

  /** One is the app's and the other is the railroad's, so neither stands in
   *  for the other and both can show at once — a participant that has lost
   *  its station says so on the row while the broker is still answering. */
  it("is a mark of its own, beside the trouble the app is in", async () => {
    const header = await band({
      trouble: "the store is not answering",
      fault: "no station on /dev/ttyACM0",
    });
    expect(reads(header, ".trouble")).toBe("the store is not answering");
    expect(reads(header, ".fault")).toBe("no station on /dev/ttyACM0");
  });

  /** It is the whole sentence the hardware published, so a long one is read
   *  by hovering rather than guessed at from what the band had room for. */
  it("carries the sentence as its own title", async () => {
    const header = await band({ fault: "district B tripped" });
    expect(header.renderRoot.querySelector(".fault")!.getAttribute("title")).toBe(
      "district B tripped",
    );
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

  /**
   * Where the supply stands, marked on the press that names it (#517).
   *
   * The three buttons are the reading as well as the presses, which is what
   * lets the status line drop the word that used to repeat one of them. The
   * mark is the rail's mark on the current view: the list is what the supply
   * can be doing and the current one is one of them.
   */
  it("marks the press the supply is standing at, and no other", async () => {
    for (const power of ["on", "stopped", "off"] as const) {
      const header = await band({ ...LIVE, power });
      const marked = presses(header)
        .filter((one) => one.classList.contains("at"))
        .map((one) => one.textContent!.trim());
      expect(marked).toEqual([{ on: "ON", stopped: "STOP", off: "OFF" }[power]]);
    }
  });

  /** The marked press says which of the two ways of standing still it is, the
   *  words the status line used to carry: an emergency stop is cleared and a
   *  supply that is off is switched back on, which are different actions by a
   *  person (ADR-0041). */
  it("names the state on the press that is standing at it", async () => {
    const said: string[] = [];
    for (const power of ["on", "stopped", "off"] as const) {
      const header = await band({ ...LIVE, power });
      said.push(presses(header).find((one) => one.classList.contains("at"))!.title);
    }
    expect(said).toEqual(["power on", "emergency stop", "power off"]);
  });

  /** With nothing said about the supply there is nothing to mark. */
  it("marks none of them before the layout has said", async () => {
    const header = await band({ joined: true, linked: true, power: null });
    expect(presses(header).some((one) => one.classList.contains("at"))).toBe(false);
  });

  /** ON is the way out of a wait, so it keeps its word and stays live. */
  it("leaves ON and STOP alive while the drain is outstanding", async () => {
    const header = await band({ ...LIVE, draining: true });
    const [on, stop] = presses(header);
    expect([on!.disabled, stop!.disabled]).toEqual([false, false]);
    expect(on!.textContent!.trim()).toBe("ON");
  });
});
