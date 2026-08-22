// @vitest-environment happy-dom

/**
 * The band across the top of both pages: what is open, and the status that is
 * nobody's mistake — the store not answering, the bridge, the boundary.
 *
 * A DOM test, the whole of the behaviour being what the component renders,
 * as `tc-menu`'s is.
 */

import { describe, expect, it } from "vitest";

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

/** A band with three railroads to pick from and one of them loaded. */
const LOADED = { drawing: "gotthard", drawings: ["crossover-yard", "gotthard", "otira"] };

describe("what the band names", () => {
  it("names the railroad that is loaded", async () => {
    expect(reads(await band({ drawing: "gotthard" }), ".drawing")).toBe("gotthard");
  });

  it("says plainly when none is", async () => {
    expect(reads(await band(), ".drawing")).toBe("no railroad");
  });
});

/** Which railroad is loaded is the whole system's, both views being of it, so
 *  the control that changes it is the band's and not a menu on one view's bar
 *  (#167, ADR-0038). */
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
      ["gotthard", "✓"],
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

  /** The tick says which railroad is loaded, and that is all it says:
   *  re-reading it would throw away whatever has been drawn since (#101). The
   *  rule moves here whole from `File ▸ Open`. */
  it("asks for nothing when the loaded railroad is chosen", async () => {
    const header = await listing(await band(LOADED));
    const heard = await asked(header, async () => {
      await choose(header, "gotthard");
    });
    expect(heard).toEqual([]);
    expect(header.renderRoot.querySelector("menu.drawings")).toBeNull();
  });

  /** A list of nothing is an empty box that looks broken — the lesson the
   *  right-click menu already learnt (tc-menu). */
  it("is dead where the store has nothing to list", async () => {
    const header = await band({ drawings: [] });
    const button = header.renderRoot.querySelector<HTMLButtonElement>("button.chosen")!;
    expect(button.disabled).toBe(true);
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
    const header = await band({ drawing: "gotthard", unsaved: true });
    expect(header.renderRoot.querySelector(".unsaved")).not.toBeNull();
  });

  it("marks nothing once the drawing is saved", async () => {
    const header = await band({ drawing: "gotthard", unsaved: false });
    expect(header.renderRoot.querySelector(".unsaved")).toBeNull();
  });

  /** The mark carries its meaning in a label as well as in ink, a dot being no
   *  use to a reader that cannot see it. */
  it("labels the dot rather than leaving it a glyph", async () => {
    const header = await band({ drawing: "gotthard", unsaved: true });
    const dot = header.renderRoot.querySelector(".unsaved")!;
    expect(dot.getAttribute("role")).toBe("img");
    expect(dot.getAttribute("aria-label")).toBe("unsaved");
  });
});

describe("the status the band takes over", () => {
  /** The store not answering is not one of the author's mistakes, so it
   *  reads here rather than on the drawing (#84). */
  it("reads the trouble the page is in", async () => {
    const header = await band({ trouble: "the store is not answering" });
    expect(reads(header, ".trouble")).toBe("the store is not answering");
  });

  it("says nothing where there is no trouble", async () => {
    expect(reads(await band(), ".trouble")).toBeNull();
  });

  it("says whether the bridge is answering a joined session", async () => {
    expect(reads(await band({ joined: true, linked: true }), ".link")).toBe(
      "connected",
    );
    expect(reads(await band({ joined: true, linked: false }), ".link")).toBe(
      "not connected",
    );
  });

  /** With no session joined there is no bridge to be answering, and the
   *  editor never has one. */
  it("says nothing about a bridge off a joined session", async () => {
    expect(reads(await band({ mode: "run", linked: true }), ".link")).toBeNull();
    expect(reads(await band({ mode: "editor", linked: true }), ".link")).toBeNull();
  });

  it("stamps the boundary, and a dash before the first one", async () => {
    expect(reads(await band({ mode: "run", boundary: 7 }), ".boundary")).toBe(
      "boundary 7",
    );
    expect(reads(await band({ mode: "run", boundary: null }), ".boundary")).toBe("—");
  });

  /** The editor has no clock: a drawing is not a run. */
  it("stamps no boundary in the editor", async () => {
    expect(reads(await band({ mode: "editor", boundary: 7 }), ".boundary")).toBeNull();
  });
});

describe("whether the drawing derives", () => {
  /** The coarse counterpart to the marks on the canvas (ADR-0024): one
   *  indicator, no fault named and nothing counted. */
  it("marks a drawing derivation refused", async () => {
    expect(reads(await band({ drawing: "gotthard", derives: false }), ".refused")).toBe(
      "does not derive",
    );
  });

  it("is clean while the drawing derives", async () => {
    expect(reads(await band({ drawing: "gotthard", derives: true }), ".refused")).toBeNull();
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

describe("the way to the other page", () => {
  it("sends the editor to the run view", async () => {
    const other = (await band({ mode: "editor" })).renderRoot.querySelector("a.other")!;
    expect(other.getAttribute("href")).toBe("/panel.html");
    expect(other.textContent!.trim()).toBe("run");
  });

  it("sends the run view to the editor", async () => {
    const other = (await band({ mode: "run" })).renderRoot.querySelector("a.other")!;
    expect(other.getAttribute("href")).toBe("/");
    expect(other.textContent!.trim()).toBe("editor");
  });
});
