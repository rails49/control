/**
 * The roster document's calls: which route each one asks, and what it makes of
 * the answer (#388).
 *
 * At the client rather than through the screen that now edits them
 * (`test/making.test.ts`): what is under test is that the document's route and
 * the run views' derived one are two routes — `GET` and `PUT` on
 * `/rosters/<railroad>` are inverses over the file, and
 * `/rosters/<railroad>/trains` is what the panel and the throttle read.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { RosterDoc } from "../src/model/store.js";
import { readRoster, readTrains, saveRoster } from "../src/model/store.js";

/** A car for each of the two Krokodils, and a rake of anonymous hoppers behind
 *  one of them: `cars` holds what there is something to say about, and the
 *  hoppers are named by their model where they are used (ADR-0061). */
const OVAL: RosterDoc = {
  roster: "oval",
  cars: {
    "krokodil-a": { model: "arnold-ce68", addr: "3" },
    "krokodil-b": { model: "arnold-ce68", addr: "4" },
  },
  trains: {
    ore: {
      cars: [{ car: "krokodil-a" }, { model: "hopper" }, { model: "hopper" }],
    },
    shunt: { cars: [{ car: "krokodil-b", orientation: "reverse" }] },
  },
};

interface Asked {
  path: string;
  method: string;
  body: unknown;
}

const asked: Asked[] = [];
let answer: { ok: boolean; body: unknown } = { ok: true, body: {} };
let real: typeof globalThis.fetch;

beforeEach(() => {
  real = globalThis.fetch;
  asked.length = 0;
  globalThis.fetch = ((path: string, init?: RequestInit) => {
    asked.push({
      path,
      method: init?.method ?? "GET",
      body: init?.body === undefined ? undefined : JSON.parse(String(init.body)),
    });
    return Promise.resolve({
      ok: answer.ok,
      json: () => Promise.resolve(answer.body),
    } as unknown as Response);
  }) as unknown as typeof fetch;
});

afterEach(() => {
  globalThis.fetch = real;
});

describe("a railroad's roster", () => {
  it("reads the document at the railroad's own path", async () => {
    answer = { ok: true, body: OVAL };
    expect(await readRoster("oval")).toEqual(OVAL);
    expect(asked).toEqual([{ path: "/rosters/oval", method: "GET", body: undefined }]);
  });

  it("reads a railroad that owns nothing as the empty document", async () => {
    // A drawing saved this morning has no roster file beside it, and that is
    // what the screen writing the first car draws itself from.
    answer = { ok: true, body: { roster: "oval", cars: {}, trains: {} } };
    expect(await readRoster("oval")).toEqual({
      roster: "oval",
      cars: {},
      trains: {},
    });
  });

  it("saves it under the railroad the document names itself for", async () => {
    answer = { ok: true, body: { saved: "oval" } };
    await saveRoster(OVAL);
    expect(asked).toEqual([{ path: "/rosters/oval", method: "PUT", body: OVAL }]);
  });

  it("saves the whole document, so a car left out is a car removed", async () => {
    answer = { ok: true, body: { saved: "oval" } };
    await saveRoster({ ...OVAL, cars: { "krokodil-a": { model: "arnold-ce68" } } });
    expect((asked[0]!.body as RosterDoc).cars).toEqual({
      "krokodil-a": { model: "arnold-ce68" },
    });
  });

  it("throws what the store said where a roster does not validate", async () => {
    // Strict, unlike a drawing: there is no picture to look at, so nothing is
    // written and there is one thing to report and nothing to undo.
    answer = { ok: false, body: { error: "roster 'oval': names unknown model …" } };
    await expect(saveRoster(OVAL)).rejects.toThrow("names unknown model");
  });

  it("reads the derived trains at a path below the document", async () => {
    answer = { ok: true, body: { roster: "oval", trains: { ore: { length: 722 } } } };
    expect(await readTrains("oval")).toEqual({
      roster: "oval",
      trains: { ore: { length: 722 } },
    });
    expect(asked[0]!.path).toBe("/rosters/oval/trains");
  });

  it("encodes a railroad whose name needs it, on both routes", async () => {
    answer = { ok: true, body: OVAL };
    await readRoster("east & west");
    await readTrains("east & west");
    expect(asked.map((one) => one.path)).toEqual([
      "/rosters/east%20%26%20west",
      "/rosters/east%20%26%20west/trains",
    ]);
  });
});
