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
  committed,
  Drain,
  percentOf,
  pickRefusal,
  refusal,
  reheard,
  restoreRefusal,
  SETTING_FIELDS,
  SETTINGS_UNHEARD,
  settingChange,
  settingsOf,
  shownIn,
  type LayoutSettings,
  type SettingField,
  type SettingsChange,
} from "../src/model/settings.js";
import type { Backup } from "../src/model/store.js";

describe("why the railroad part is refused", () => {
  it("is refused while the layout has not said which railroad is loaded", () => {
    expect(refusal(null, "on")).toBe(
      "the layout has not said which railroad is loaded",
    );
    expect(refusal(null, "off")).toBe(
      "the layout has not said which railroad is loaded",
    );
  });

  it("is refused while a railroad is loaded and the layout has not said the supply", () => {
    expect(refusal("otira", null)).toBe(
      "the layout has not said whether the track has power",
    );
  });

  /** The press drains the track itself (ADR-0085, decision 5). */
  it.each(["on", "draining"] as const)("is open while the track reads %s", (power) => {
    expect(refusal("otira", power)).toBeNull();
  });

  /** Unsaved edits refuse nothing: the app saves them before the load
   *  (#1233). */
  it("is open with the track dead", () => {
    expect(refusal("otira", "off")).toBeNull();
  });

  /** A binding with nothing loaded reads no supply, and the first railroad on
   *  a new box is loaded from the dialog (ADR-0072, decision 6). */
  it("is open with no railroad loaded, whatever the supply has said", () => {
    expect(refusal("", null)).toBeNull();
  });
});

/** Copy loaded as… waits on everything a load does, and then on there being a
 *  loaded railroad to copy (#737). */
describe("why Copy loaded as… is refused", () => {
  it("is refused for the railroad part's reason first", () => {
    expect(copyRefusal(null, "off")).toBe(
      "the layout has not said which railroad is loaded",
    );
    expect(copyRefusal("otira", null)).toBe(
      "the layout has not said whether the track has power",
    );
  });

  it("is refused with no railroad loaded, there being nothing to copy", () => {
    expect(copyRefusal("", null)).toBe("no railroad is loaded to copy");
  });

  it("is open with a railroad loaded and the track dead", () => {
    expect(copyRefusal("otira", "off")).toBeNull();
  });
});

/** Turning the box off waits on the track being dead, a stop included, and on
 *  the layout having said so (#745). */
describe("why a pick from the list is refused", () => {
  it("is refused for what refuses the railroad part, first", () => {
    expect(pickRefusal(null, "off", true)).toBe(
      "the layout has not said which railroad is loaded",
    );
  });

  it("is refused while the page holds a drawing with no railroad", () => {
    expect(pickRefusal("", null, true)).toBe(
      "the drawing has no railroad — press New to keep it",
    );
  });

  it("is open with no railroad loaded and no drawing on the page", () => {
    expect(pickRefusal("", null, false)).toBeNull();
  });
});

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

/** The row as `layout` writes it, every field readable. */
const ROW = {
  at: 1,
  point_gap: 0.5,
  speeds: { clear: 0.6, caution: 0.07 },
  throttle_silence: 5,
  sensor_silence: 3,
  arrival_allowance: 60,
};

/** `ROW` as the dialog reads it. */
const HEARD: LayoutSettings = {
  pointGap: 0.5,
  speeds: { clear: 0.6, caution: 0.07 },
  throttleSilence: 5,
  sensorSilence: 3,
  arrivalAllowance: 60,
};

/** Each field of the setting tabs, as a commit in it is answered (#1128,
 *  #1134, #1149, #1192): the row's own value as typed, the row with the field
 *  unreadable, the sentences it refuses with, values outside its bounds,
 *  and values in range with the exact payload each sends. */
const FIELDS: Record<
  SettingField,
  {
    own: string;
    unreadable: LayoutSettings;
    number: string;
    range: string;
    outside: string[];
    sent: [string, SettingsChange][];
  }
> = {
  gap: {
    own: "0.50",
    unreadable: { ...HEARD, pointGap: null },
    number: "the time between point commands is a number of seconds",
    range: "the time between point commands is from 0 to 5 seconds",
    outside: ["7", "-0.1", "5.01"],
    sent: [
      ["1.2", { point_gap: 1.2 }],
      ["0", { point_gap: 0 }],
      [" 5 ", { point_gap: 5 }],
      ["0.25", { point_gap: 0.25 }],
    ],
  },
  clear: {
    own: "60",
    unreadable: { ...HEARD, speeds: { clear: null, caution: null } },
    number: "the speed at clear is a number, in percent",
    range: "the speed at clear is from 1 to 100 percent",
    outside: ["0", "0.5", "101", "-3"],
    sent: [
      [" 100 ", { speeds: { clear: 1 } }],
      ["1", { speeds: { clear: 0.01 } }],
      ["45.5", { speeds: { clear: 0.455 } }],
    ],
  },
  caution: {
    own: "7",
    unreadable: { ...HEARD, speeds: { clear: null, caution: null } },
    number: "the speed at caution is a number, in percent",
    range: "the speed at caution is from 1 to 100 percent",
    outside: ["0", "0.5", "101", "-3"],
    sent: [["45", { speeds: { caution: 0.45 } }]],
  },
  silence: {
    own: "5",
    unreadable: { ...HEARD, throttleSilence: null },
    number: "how long a throttle may go silent is a number of seconds",
    range: "how long a throttle may go silent is from 2 to 60 seconds",
    outside: ["1", "1.9", "61", "0"],
    sent: [
      ["10", { throttle_silence: 10 }],
      ["2", { throttle_silence: 2 }],
      ["60", { throttle_silence: 60 }],
    ],
  },
  sensorSilence: {
    own: "3",
    unreadable: { ...HEARD, sensorSilence: null },
    number: "how long a sensor may go unheard is a number of seconds",
    range: "how long a sensor may go unheard is from 2 to 60 seconds",
    outside: ["1", "1.9", "61", "0"],
    sent: [
      ["10", { sensor_silence: 10 }],
      ["2", { sensor_silence: 2 }],
      ["60", { sensor_silence: 60 }],
    ],
  },
  arrivalAllowance: {
    own: "60",
    unreadable: { ...HEARD, arrivalAllowance: null },
    number: "how long a move may take to arrive is a number of seconds",
    range: "how long a move may take to arrive is from 5 to 600 seconds",
    outside: ["4", "601", "4.9", "0"],
    sent: [
      ["5", { arrival_allowance: 5 }],
      ["600", { arrival_allowance: 600 }],
      ["90", { arrival_allowance: 90 }],
    ],
  },
};

describe("a table entry for every field", () => {
  it("is what the cases below cover", () => {
    expect(Object.keys(SETTING_FIELDS).sort()).toEqual(Object.keys(FIELDS).sort());
  });
});

describe.each(Object.keys(SETTING_FIELDS) as SettingField[])(
  "what a commit in %s does",
  (field) => {
    const cases = FIELDS[field];

    it("sends nothing while the layout has not said its settings", () => {
      expect(settingChange(field, cases.sent[0]![0], null)).toEqual({
        refused: "the layout has not said its settings",
      });
    });

    it("sends nothing where the row's value for it is unreadable", () => {
      expect(settingChange(field, cases.sent[0]![0], cases.unreadable)).toEqual({
        refused: SETTINGS_UNHEARD,
      });
    });

    it("refuses what is not a number", () => {
      for (const typed of ["", " ", "fast", "abc", "Infinity", "1,2"]) {
        expect(settingChange(field, typed, HEARD)).toEqual({ refused: cases.number });
      }
    });

    it("refuses a value outside its bounds", () => {
      for (const typed of cases.outside) {
        expect(settingChange(field, typed, HEARD)).toEqual({ refused: cases.range });
      }
    });

    it("sends nothing for the value the row already says", () => {
      expect(settingChange(field, cases.own, HEARD)).toBeNull();
    });

    it("sends a value in range alone, the ends included", () => {
      for (const [typed, sent] of cases.sent) {
        expect(settingChange(field, typed, HEARD)).toEqual({ sent });
      }
    });
  },
);

describe("a speed in percent", () => {
  it("is the fraction times 100, without the float's tail", () => {
    expect(percentOf(0.6)).toBe(60);
    expect(percentOf(0.07)).toBe(7);
    expect(percentOf(0.455)).toBe(45.5);
  });
});

describe("what state/settings says", () => {
  it("reads every field of a full row", () => {
    expect(settingsOf(ROW)).toEqual(HEARD);
  });

  it("reads a field layout could not have meant as null, and only that field", () => {
    expect(settingsOf({ ...ROW, point_gap: 6 })).toEqual({ ...HEARD, pointGap: null });
    expect(settingsOf({ ...ROW, point_gap: "1" })).toEqual({ ...HEARD, pointGap: null });
    expect(settingsOf({ ...ROW, throttle_silence: 1 })).toEqual({
      ...HEARD,
      throttleSilence: null,
    });
    expect(settingsOf({ ...ROW, sensor_silence: 61 })).toEqual({ ...HEARD, sensorSilence: null });
  });

  it("reads the arrival allowance from 5 to 600 seconds, and nothing else (#1192)", () => {
    expect(settingsOf({ ...ROW, arrival_allowance: 60 }).arrivalAllowance).toBe(60);
    const { arrival_allowance: _, ...missing } = ROW;
    for (const row of [
      { ...ROW, arrival_allowance: 4 },
      { ...ROW, arrival_allowance: 601 },
      { ...ROW, arrival_allowance: "60" },
      missing,
    ]) {
      expect(settingsOf(row)).toEqual({ ...HEARD, arrivalAllowance: null });
    }
  });

  it("reads both speeds as null where speeds does not read", () => {
    for (const speeds of [
      undefined,
      null,
      { clear: 0.6 },
      { clear: 0, caution: 0.3 },
      { clear: 0.6, caution: 1.2 },
    ]) {
      expect(settingsOf({ ...ROW, speeds })).toEqual({
        ...HEARD,
        speeds: { clear: null, caution: null },
      });
    }
  });
});

/** The #1137 rule: a refused commit stays in its field beside the reason
 *  until a commit there is not refused or the row says a different value. */
describe("a refused commit", () => {
  it("shows the row's value, and nothing while the row is unheard", () => {
    expect(shownIn({}, "clear", HEARD)).toBe("60");
    expect(shownIn({}, "gap", null)).toBe("");
  });

  it("stays in its field, beside its reason, through the same commit again", () => {
    const first = committed({}, "silence", "1", HEARD);
    expect(first.sent).toBeNull();
    const again = committed(first.refusals, "silence", "1", HEARD);
    expect(again.sent).toBeNull();
    expect(shownIn(again.refusals, "silence", HEARD)).toBe("1");
    expect(again.refusals.silence?.reason).toBe(
      "how long a throttle may go silent is from 2 to 60 seconds",
    );
  });

  it("goes when a commit in its field is not refused", () => {
    const { refusals } = committed({}, "silence", "1", HEARD);
    const sent = committed(refusals, "silence", "10", HEARD);
    expect(sent).toEqual({ refusals: {}, sent: { throttle_silence: 10 } });
    expect(committed(refusals, "silence", "5", HEARD)).toEqual({ refusals: {}, sent: null });
  });

  it("goes when the row says a different value for its field, and not before", () => {
    const { refusals } = committed({}, "gap", "7", HEARD);
    expect(reheard(refusals, HEARD)).toBe(refusals);
    expect(reheard(refusals, { ...HEARD, sensorSilence: 10 })).toBe(refusals);
    const moved = reheard(refusals, { ...HEARD, pointGap: 1 });
    expect(moved).toEqual({});
    expect(shownIn(moved, "gap", { ...HEARD, pointGap: 1 })).toBe("1");
  });

  it("leaves another field's alone", () => {
    const silent = committed({}, "silence", "1", HEARD).refusals;
    const both = committed(silent, "sensorSilence", "1", HEARD).refusals;
    expect(Object.keys(both).sort()).toEqual(["sensorSilence", "silence"]);
    expect(committed(both, "sensorSilence", "10", HEARD).refusals).toEqual(silent);
    expect(shownIn(silent, "sensorSilence", HEARD)).toBe("3");
    const moved = reheard(both, { ...HEARD, sensorSilence: 10 });
    expect(moved).toEqual(silent);
  });
});
