// @vitest-environment happy-dom

/**
 * The band across the top of both pages: what is open, which mode it is being
 * looked at in, and the status that is nobody's mistake — the store not
 * answering, the bridge, the tick.
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

describe("what the band names", () => {
  it("names the drawing that is open", async () => {
    expect(reads(await band({ drawing: "gotthard" }), ".drawing")).toBe("gotthard");
  });

  it("says plainly when none is open", async () => {
    expect(reads(await band(), ".drawing")).toBe("no drawing");
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

describe("which mode the band says you are in", () => {
  it("says the editor", async () => {
    expect(reads(await band({ mode: "editor" }), ".mode")).toBe("editor");
  });

  /** Replay and live are exclusive (ADR-0016), and which one you are in was
   *  inferrable only from whichever select was last touched. */
  it("tells replay from live from nothing joined", async () => {
    expect(reads(await band({ mode: "replay" }), ".mode")).toBe("replay");
    expect(reads(await band({ mode: "live" }), ".mode")).toBe("live");
    expect(reads(await band({ mode: "unjoined" }), ".mode")).toBe("nothing joined");
  });

  /** A replay reads a file, and the file's name is what says which run is on
   *  screen; the railroad's name says only which railroad. */
  it("names the trace a replay is reading", async () => {
    const header = await band({ mode: "replay", trace: "gotthard.jsonl" });
    expect(reads(header, ".trace")).toBe("gotthard.jsonl");
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

  it("says whether the bridge is answering a live session", async () => {
    expect(reads(await band({ mode: "live", linked: true }), ".link")).toBe("connected");
    expect(reads(await band({ mode: "live", linked: false }), ".link")).toBe(
      "not connected",
    );
  });

  /** A replay has no bridge to be answering, and neither has the editor. */
  it("says nothing about a bridge off a live session", async () => {
    expect(reads(await band({ mode: "replay", linked: true }), ".link")).toBeNull();
    expect(reads(await band({ mode: "editor", linked: true }), ".link")).toBeNull();
  });

  it("stamps the tick, and a dash before the first one", async () => {
    expect(reads(await band({ mode: "replay", tick: 7 }), ".tick")).toBe("tick 7");
    expect(reads(await band({ mode: "replay", tick: null }), ".tick")).toBe("—");
  });

  /** The editor has no clock: a drawing is not a run. */
  it("stamps no tick in the editor", async () => {
    expect(reads(await band({ mode: "editor", tick: 7 }), ".tick")).toBeNull();
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
  it("sends the editor to the panel", async () => {
    const other = (await band({ mode: "editor" })).renderRoot.querySelector("a.other")!;
    expect(other.getAttribute("href")).toBe("/panel.html");
    expect(other.textContent!.trim()).toBe("panel");
  });

  it("sends the panel to the editor, in every one of its modes", async () => {
    for (const mode of ["replay", "live", "unjoined"] as const) {
      const other = (await band({ mode })).renderRoot.querySelector("a.other")!;
      expect(other.getAttribute("href")).toBe("/");
      expect(other.textContent!.trim()).toBe("editor");
    }
  });
});
