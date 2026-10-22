/**
 * What a widget shows and sends on a run (ADR-0087, #929): a text row's ANSI
 * codes read as bold and three colours, a toggle's position read off its row,
 * and what a press on a button or a toggle publishes.
 *
 * No DOM. The run view drawing them and the session carrying the press are
 * `run-widgets.test.ts`.
 */

import { describe, expect, it } from "vitest";

import type { WidgetSpec } from "../src/model/drawing.js";
import { ansi, togglePosition, widgetPress } from "../src/model/widgets.js";

const ESC = "\x1b";

describe("a text row's ANSI codes", () => {
  it("leaves plain text alone", () => {
    expect(ansi("0.4 A")).toEqual([{ text: "0.4 A", bold: false, colour: null }]);
  });

  it("reads 1 as bold and 22 as its end", () => {
    expect(ansi(`a${ESC}[1mb${ESC}[22mc`)).toEqual([
      { text: "a", bold: false, colour: null },
      { text: "b", bold: true, colour: null },
      { text: "c", bold: false, colour: null },
    ]);
  });

  it.each([
    [31, "red"],
    [91, "red"],
    [33, "amber"],
    [93, "amber"],
    [32, "green"],
    [92, "green"],
  ] as const)("reads %i as %s and 39 as the colour's end", (code, colour) => {
    expect(ansi(`${ESC}[${code}mhot${ESC}[39m cold`)).toEqual([
      { text: "hot", bold: false, colour },
      { text: " cold", bold: false, colour: null },
    ]);
  });

  it("keeps bold through a colour's end and the colour through bold's", () => {
    expect(ansi(`${ESC}[1;31mA${ESC}[39mB${ESC}[31;22mC`)).toEqual([
      { text: "A", bold: true, colour: "red" },
      { text: "B", bold: true, colour: null },
      { text: "C", bold: false, colour: "red" },
    ]);
  });

  it("resets everything on 0, and on no code at all", () => {
    expect(ansi(`${ESC}[1;32mA${ESC}[0mB${ESC}[1;32mC${ESC}[mD`)).toEqual([
      { text: "A", bold: true, colour: "green" },
      { text: "B", bold: false, colour: null },
      { text: "C", bold: true, colour: "green" },
      { text: "D", bold: false, colour: null },
    ]);
  });

  it("removes any other SGR code, an extended colour's arguments with it", () => {
    expect(ansi(`${ESC}[4;34mA${ESC}[38;5;0mB${ESC}[38;2;0;0;0;1mC`)).toEqual([
      { text: "AB", bold: false, colour: null },
      { text: "C", bold: true, colour: null },
    ]);
  });

  it("removes every other escape sequence", () => {
    const text = `${ESC}[2Ja${ESC}[1Kb${ESC}]0;title\x07c${ESC}(Bd${ESC}`;
    expect(ansi(text)).toEqual([{ text: "abcd", bold: false, colour: null }]);
  });
});

describe("a toggle", () => {
  const LIGHTS: WidgetSpec = {
    kind: "toggle",
    at: [0, 0],
    on: '{"lights": true}',
    off: '{"lights": false}',
  };

  it.each([
    ['{"lights": true}', "on"],
    ['{"lights": false}', "off"],
    ["dim", null],
    [undefined, null],
  ] as const)("reads row %s as %s", (row, position) => {
    expect(togglePosition(LIGHTS, row)).toBe(position);
  });

  it("sends the other position's payload, retained", () => {
    expect(widgetPress("lights", LIGHTS, LIGHTS.on)).toEqual({
      topic: "tc49/ui/state/toggle/lights",
      payload: LIGHTS.off,
      retain: true,
    });
    expect(widgetPress("lights", LIGHTS, LIGHTS.off)).toEqual({
      topic: "tc49/ui/state/toggle/lights",
      payload: LIGHTS.on,
      retain: true,
    });
  });

  it.each([["dim"], [undefined]])("sends on where row %s is neither", (row) => {
    expect(widgetPress("lights", LIGHTS, row)?.payload).toBe(LIGHTS.on);
  });

  /** A default stands for the row until one arrives (#939). */
  it("shows its default with no row, and a press sends the other position", () => {
    const lit = { ...LIGHTS, default: "on" };
    expect(togglePosition(lit, undefined)).toBe("on");
    expect(widgetPress("lights", lit, undefined)?.payload).toBe(LIGHTS.off);
    expect(togglePosition({ ...LIGHTS, default: "off" }, undefined)).toBe("off");
    expect(togglePosition(lit, LIGHTS.off)).toBe("off");
  });
});

it("sends a button's payload as typed, not retained", () => {
  const horn: WidgetSpec = { kind: "button", at: [0, 0], payload: "toot toot" };
  expect(widgetPress("horn", horn, undefined)).toEqual({
    topic: "tc49/ui/button/horn",
    payload: "toot toot",
    retain: false,
  });
});

it("sends nothing for a text widget", () => {
  const text: WidgetSpec = { kind: "text", at: [0, 0] };
  expect(widgetPress("current", text, "0.4 A")).toBeNull();
});
