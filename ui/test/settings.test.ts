/**
 * When the settings dialog's railroad part is refused, with no DOM (#733,
 * #737).
 *
 * The first condition that holds is the reason, so each row of the table is
 * checked with every row below it also holding: the order is the claim.
 */

import { describe, expect, it } from "vitest";

import {
  arrived,
  boxRefusal,
  copyRefusal,
  Drain,
  gapChange,
  pointGapOf,
  refusal,
  restoreRefusal,
} from "../src/model/settings.js";
import type { Backup } from "../src/model/store.js";

describe("why the railroad part is refused", () => {
  it("is refused while the layout has not said which railroad is loaded", () => {
    expect(refusal(null, "on", "the drawing")).toBe(
      "the layout has not said which railroad is loaded",
    );
    expect(refusal(null, "off", null)).toBe(
      "the layout has not said which railroad is loaded",
    );
  });

  it("is refused while a railroad is loaded and the layout has not said the supply", () => {
    expect(refusal("otira", null, "the roster")).toBe(
      "the layout has not said whether the track has power",
    );
  });

  /** The press drains the track itself (ADR-0085, decision 5). */
  it.each(["on", "draining"] as const)("is open while the track reads %s", (power) => {
    expect(refusal("otira", power, null)).toBeNull();
  });

  it("is refused over unsaved edits, naming what holds them", () => {
    expect(refusal("otira", "off", "the drawing")).toBe(
      "the drawing has unsaved edits — save first",
    );
    expect(refusal("", null, "the roster")).toBe(
      "the roster has unsaved edits — save first",
    );
  });

  it("is open with the track dead and nothing unsaved", () => {
    expect(refusal("otira", "off", null)).toBeNull();
  });

  /** A binding with nothing loaded reads no supply, and the first railroad on
   *  a new box is loaded from the dialog (ADR-0072, decision 6). */
  it("is open with no railroad loaded, whatever the supply has said", () => {
    expect(refusal("", null, null)).toBeNull();
  });
});

/** Copy loaded as… waits on everything a load does, and then on there being a
 *  loaded railroad to copy (#737). */
describe("why Copy loaded as… is refused", () => {
  it("is refused for the railroad part's reason first", () => {
    expect(copyRefusal(null, "off", null)).toBe(
      "the layout has not said which railroad is loaded",
    );
    expect(copyRefusal("otira", null, null)).toBe(
      "the layout has not said whether the track has power",
    );
    expect(copyRefusal("", "off", "the roster")).toBe(
      "the roster has unsaved edits — save first",
    );
  });

  it("is refused with no railroad loaded, there being nothing to copy", () => {
    expect(copyRefusal("", null, null)).toBe("no railroad is loaded to copy");
  });

  it("is open with a railroad loaded, the track dead and nothing unsaved", () => {
    expect(copyRefusal("otira", "off", null)).toBeNull();
  });
});

/** Turning the box off waits on the track being dead, a stop included, and on
 *  the layout having said so (#745). */
describe("why turning the box off is refused", () => {
  it("is refused while the layout has not said whether the track has power", () => {
    expect(boxRefusal(null)).toBe("the layout has not said whether the track has power");
  });

  it.each(["on", "draining", "off"] as const)("is open while the track reads %s", (power) => {
    expect(boxRefusal(power)).toBeNull();
  });
});

/** A restore waits while the physical layout could come to disagree with the
 *  store (#688), and while the page has not heard which railroad it runs
 *  (#759). */
describe("why a restore is refused", () => {
  const holding: Backup = { commit: "a1", said: "", when: "", railroads: ["otira"] };
  const without: Backup = { commit: "b2", said: "", when: "", railroads: ["mainline"] };

  it.each(["on", "draining", "off", null] as const)(
    "is refused while the layout has not said which railroad is loaded, power %s",
    (power) => {
      expect(restoreRefusal(null, power, holding)).toBe(
        "the layout has not said which railroad is loaded",
      );
      expect(restoreRefusal(null, power, undefined)).toBe(
        "the layout has not said which railroad is loaded",
      );
    },
  );

  it("is refused while a railroad is loaded and the layout has not said the supply", () => {
    expect(restoreRefusal("otira", null, holding)).toBe(
      "the layout has not said whether the track has power",
    );
    expect(restoreRefusal("otira", null, without)).toBe(
      "the layout has not said whether the track has power",
    );
  });

  /** The press drains the track itself (ADR-0085, decision 5). */
  it.each(["on", "draining"] as const)("is open while the track reads %s", (power) => {
    expect(restoreRefusal("otira", power, holding)).toBeNull();
  });

  it("is refused for a backup without the loaded railroad", () => {
    expect(restoreRefusal("otira", "off", without)).toBe(
      "this backup has no otira — load another railroad first",
    );
  });

  it("is open with the track dead and a backup holding the railroad, or none picked", () => {
    expect(restoreRefusal("otira", "off", holding)).toBeNull();
    expect(restoreRefusal("otira", "off", undefined)).toBeNull();
  });

  /** With nothing loaded there is no run to drift from, and any backup will
   *  do (#697). */
  it.each(["on", "draining", "off", null] as const)(
    "is open with no railroad loaded, power %s, whatever the backup holds",
    (power) => {
      expect(restoreRefusal("", power, holding)).toBeNull();
      expect(restoreRefusal("", power, without)).toBeNull();
      expect(restoreRefusal("", power, undefined)).toBeNull();
    },
  );
});

/** A press that needs the track dead drains it and acts once it reads `off`
 *  (ADR-0085, decision 5). */
describe("a press held for a dead track", () => {
  function counted(): { drain: Drain; acts: () => number; act: () => void } {
    let count = 0;
    return { drain: new Drain(), acts: () => count, act: () => (count += 1) };
  }

  it("acts at once with the track dead, asking for nothing", () => {
    const { drain, acts, act } = counted();

    expect(drain.begin("off", act)).toBeNull();

    expect(acts()).toBe(1);
    expect(drain.waiting).toBe(false);
  });

  it("acts at once where the press does not wait on the supply", () => {
    const { drain, acts, act } = counted();

    expect(drain.begin(null, act)).toBeNull();

    expect(acts()).toBe(1);
  });

  it("asks for the drain from on, and acts once off is heard", () => {
    const { drain, acts, act } = counted();

    expect(drain.begin("on", act)).toBe("draining");
    expect(drain.waiting).toBe(true);
    drain.heard("on");
    drain.heard("draining");
    expect(acts()).toBe(0);
    drain.heard("off");

    expect(acts()).toBe(1);
    expect(drain.waiting).toBe(false);
    drain.heard("off");
    expect(acts()).toBe(1);
  });

  it("asks for nothing more while the track is already draining", () => {
    const { drain, acts, act } = counted();

    expect(drain.begin("draining", act)).toBeNull();
    drain.heard("off");

    expect(acts()).toBe(1);
  });

  it("acts on nothing once abandoned", () => {
    const { drain, acts, act } = counted();
    drain.begin("on", act);

    drain.abandon();
    drain.heard("off");

    expect(acts()).toBe(0);
    expect(drain.waiting).toBe(false);
  });

  /** ON pressed on the band ends the drain: the person changed their mind. */
  it("gives up where power reads on again after draining", () => {
    const { drain, acts, act } = counted();
    drain.begin("on", act);
    drain.heard("draining");

    drain.heard("on");
    drain.heard("off");

    expect(acts()).toBe(0);
    expect(drain.waiting).toBe(false);
  });

  it("keeps waiting while the supply goes unheard", () => {
    const { drain, acts, act } = counted();
    drain.begin("on", act);

    drain.heard(null);
    drain.heard("off");

    expect(acts()).toBe(1);
  });
});

/** When a pick has landed, so the dialog closes (#902): the page holds the
 *  drawing, the row names it, and the dispatcher has said its picture since
 *  — or the row says nothing was built, there being no dispatcher on it. */
describe("a pick that has landed", () => {
  const LANDED = { opened: "otira", railroad: "otira", built: true, allocated: true };

  it("has landed once all three hold", () => {
    expect(arrived("otira", LANDED)).toBe(true);
  });

  it("has not while the page holds another drawing, or none", () => {
    expect(arrived("otira", { ...LANDED, opened: "toy" })).toBe(false);
    expect(arrived("otira", { ...LANDED, opened: "" })).toBe(false);
  });

  it("has not while the row names another railroad, or has not said", () => {
    expect(arrived("otira", { ...LANDED, railroad: "toy" })).toBe(false);
    expect(arrived("otira", { ...LANDED, railroad: null })).toBe(false);
  });

  it("has not before the allocation, where the railroad was built", () => {
    expect(arrived("otira", { ...LANDED, allocated: false })).toBe(false);
  });

  it("has without the allocation, where the row says nothing was built", () => {
    expect(arrived("otira", { ...LANDED, built: false, allocated: false })).toBe(true);
  });
});

/** The Points tab's one field, the point gap (#1128): what a commit sends,
 *  and what refuses it. */
describe("what a committed point gap does", () => {
  it("sends nothing while the layout has not said its settings", () => {
    expect(gapChange("1.2", null)).toEqual({
      refused: "the layout has not said its settings",
    });
  });

  it("refuses what is not a number of seconds", () => {
    for (const typed of ["", " ", "fast", "Infinity", "1,2"]) {
      expect(gapChange(typed, 0.5)).toEqual({
        refused: "the time between point commands is a number of seconds",
      });
    }
  });

  it("refuses a gap below 0 or above 5 seconds", () => {
    for (const typed of ["7", "-0.1", "5.01"]) {
      expect(gapChange(typed, 0.5)).toEqual({
        refused: "the time between point commands is from 0 to 5 seconds",
      });
    }
  });

  it("sends a gap from 0 to 5 seconds, the ends included", () => {
    expect(gapChange("1.2", 0.5)).toEqual({ sent: 1.2 });
    expect(gapChange("0", 0.5)).toEqual({ sent: 0 });
    expect(gapChange(" 5 ", 0.5)).toEqual({ sent: 5 });
    expect(gapChange("0.25", 0.5)).toEqual({ sent: 0.25 });
  });

  it("sends nothing where the gap is the one the layout says", () => {
    expect(gapChange("0.5", 0.5)).toBeNull();
    expect(gapChange("0.50", 0.5)).toBeNull();
  });
});

describe("the point gap state/settings says", () => {
  it("reads point_gap in seconds", () => {
    expect(pointGapOf({ at: 3, point_gap: 0.8 })).toBe(0.8);
    expect(pointGapOf({ point_gap: 0 })).toBe(0);
  });

  it("reads none that layout could not have meant", () => {
    for (const payload of [{}, { point_gap: "1" }, { point_gap: -1 }, { point_gap: 6 }]) {
      expect(pointGapOf(payload)).toBeNull();
    }
  });
});
