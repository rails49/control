// @vitest-environment happy-dom

/**
 * Widgets on a run, end to end through the app (ADR-0087, #929, #939): the run
 * view draws each as its face alone, a text widget shows its row, a toggle its
 * position, and a click on a button or a toggle publishes its payload raw.
 *
 * What a row means and what a press sends are `widget-run.test.ts`; this is
 * the walk from the broker's side to the sheet and back. happy-dom's
 * `getScreenCTM` is the identity, so a client pixel reads as a grid square.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-app.js";
import type { Drawing } from "../src/model/drawing.js";
import type { Point } from "../src/model/geometry.js";
import type { TcApp } from "../src/ui/tc-app.js";
import { power, serving, settled, surface } from "./support/shell.js";
import {
  Broker,
  brokering,
  DERIVES,
  joined,
  said,
  STOCK,
  stored,
  unbrokered,
} from "./support/session.js";

const ESC = "\x1b";

const TEXT = "tc49/ui/state/text/current";
const TOGGLE = "tc49/ui/state/toggle/lights";
const BUTTON = "tc49/ui/button/horn";

/** The toy railroad with a widget of each kind below its two blocks. */
function withWidgets(name: string): Drawing {
  return {
    ...stored(name),
    widgets: {
      current: { kind: "text", at: [0, 4], default: "no reading" },
      lights: {
        kind: "toggle",
        at: [0, 6],
        on: '{"lights": true}',
        off: '{"lights": false}',
      },
      horn: { kind: "button", at: [4, 6], payload: "toot toot" },
    },
  };
}

/** The middle of each widget, which is where a click lands. */
const MIDDLE: Record<string, Point> = {
  lights: { x: 1, y: 6.5 },
  horn: { x: 4.5, y: 6.5 },
};

beforeEach(() => {
  brokering();
  serving({
    drawings: ["toy"],
    rosterOf: () => STOCK,
    read: withWidgets,
    review: () => Promise.resolve(DERIVES),
  });
});

afterEach(unbrokered);

/** The widget's group on the run view's sheet. */
function widget(shell: TcApp, name: string): Element {
  return surface(shell).querySelector(`[data-widget="${name}"]`)!;
}

/** The words a widget shows. */
function words(shell: TcApp, name: string): string {
  return widget(shell, name).querySelector(".widget-text")!.textContent!.trim();
}

/** A toggle's position: `on`, `off`, or `null` where it shows neither. */
function lamp(shell: TcApp, name: string): string | null {
  const track = widget(shell, name).querySelector(".widget-track")!.classList;
  return track.contains("on") ? "on" : track.contains("off") ? "off" : null;
}

/** A row on a widget's topic, raw, as a script writes it. */
async function writes(shell: TcApp, topic: string, payload: string): Promise<void> {
  Broker.last!.saysRaw(topic, payload);
  await settled(shell);
}

/** A click on a widget, the way a pointer makes one. */
async function clicks(shell: TcApp, name: string): Promise<void> {
  const at = MIDDLE[name]!;
  for (const type of ["pointerdown", "pointerup"]) {
    surface(shell).dispatchEvent(
      new PointerEvent(type, { bubbles: true, clientX: at.x, clientY: at.y }),
    );
  }
  await settled(shell);
}

/** What the page published on the widget topics, as it went out. */
function sent(): { topic: string; payload: string; retain?: true }[] {
  return Broker.last!.published.filter(({ topic }) => topic.startsWith("tc49/ui/"));
}

it("draws every widget as its face at its place", async () => {
  const shell = await joined();
  const text = widget(shell, "current").querySelector(".widget-text")!;
  expect(["x", "y"].map((one) => text.getAttribute(one))).toEqual(["0.5", "4.5"]);
  const track = widget(shell, "lights").querySelector(".widget-track")!;
  expect(["x", "y"].map((one) => track.getAttribute(one))).toEqual(["0.1", "6.2"]);
  const ring = widget(shell, "horn").querySelector(".widget-ring")!;
  expect(["cx", "cy"].map((one) => ring.getAttribute(one))).toEqual(["4.5", "6.5"]);
});

describe("a text widget", () => {
  it("shows its default with no row, then the row once one arrives", async () => {
    const shell = await joined();
    expect(words(shell, "current")).toBe("no reading");
    await writes(shell, TEXT, "0.4 A");
    expect(words(shell, "current")).toBe("0.4 A");
  });

  it("draws bold and colour as runs of their own, other codes removed", async () => {
    const shell = await joined();
    await writes(shell, TEXT, `${ESC}[1;31m2.1 A${ESC}[0m ${ESC}[4mok${ESC}[32m!`);
    const runs = [...widget(shell, "current").querySelectorAll("tspan")].map((run) => [
      run.textContent,
      run.getAttribute("class"),
    ]);
    expect(runs).toEqual([
      ["2.1 A", "bold red"],
      [" ok", ""],
      ["!", "green"],
    ]);
  });

  it("is its words alone, with no box to cut them", async () => {
    const shell = await joined();
    await writes(shell, TEXT, "a reading far longer than one square");
    expect(words(shell, "current")).toBe("a reading far longer than one square");
    expect(widget(shell, "current").querySelector("rect, svg")).toBeNull();
  });

  it("reads a raw row without disturbing any other", async () => {
    const shell = await joined();
    await said(shell, "tc49/layout/state/power", { power: "on" });
    await writes(shell, TOGGLE, '{"lights": true}');
    await writes(shell, TEXT, "{not json");
    await writes(shell, "tc49/ui/state/text/other", '{"power": "off"}');
    expect(words(shell, "current")).toBe("{not json");
    expect(lamp(shell, "lights")).toBe("on");
    expect(power(shell).state).toBe("on");
    // And the page still reads the rows after it.
    await said(shell, "tc49/layout/state/power", { power: "off" });
    expect(power(shell).state).toBe("off");
  });
});

describe("a toggle", () => {
  it.each([
    ['{"lights": true}', "on"],
    ['{"lights": false}', "off"],
    ["dim", null],
  ] as const)("shows row %s as %s", async (row, position) => {
    const shell = await joined();
    await writes(shell, TOGGLE, row);
    expect(lamp(shell, "lights")).toBe(position);
    expect(widget(shell, "lights").querySelector("text")).toBeNull();
  });

  it("shows neither with no row", async () => {
    const shell = await joined();
    expect(lamp(shell, "lights")).toBeNull();
  });

  it("publishes the other position's payload, retained", async () => {
    const shell = await joined();
    await writes(shell, TOGGLE, '{"lights": true}');
    await clicks(shell, "lights");
    expect(sent()).toEqual([{ topic: TOGGLE, payload: '{"lights": false}', retain: true }]);
  });

  it("publishes on where it shows neither position", async () => {
    const shell = await joined();
    await clicks(shell, "lights");
    await writes(shell, TOGGLE, "dim");
    await clicks(shell, "lights");
    expect(sent()).toEqual([
      { topic: TOGGLE, payload: '{"lights": true}', retain: true },
      { topic: TOGGLE, payload: '{"lights": true}', retain: true },
    ]);
  });
});

describe("a button", () => {
  it("shows no name and publishes its payload once a press, not retained", async () => {
    const shell = await joined();
    expect(widget(shell, "horn").querySelector("text")).toBeNull();
    await clicks(shell, "horn");
    expect(sent()).toEqual([{ topic: BUTTON, payload: "toot toot" }]);
  });
});

it("presses while track power is off", async () => {
  const shell = await joined();
  await said(shell, "tc49/layout/state/power", { power: "off" });
  await clicks(shell, "horn");
  await clicks(shell, "lights");
  expect(sent()).toEqual([
    { topic: BUTTON, payload: "toot toot" },
    { topic: TOGGLE, payload: '{"lights": true}', retain: true },
  ]);
});
