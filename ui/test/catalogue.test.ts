/**
 * The catalogue calls: which route each one asks, and what it makes of the
 * answer (#392).
 *
 * At the client rather than through the screen that now writes them
 * (`test/making.test.ts`): what is under test is the shape of the request — a
 * model is the installation's and is addressed by its own name, with no
 * railroad in the path (ADR-0045) — and the unwrapping of the answer.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { ModelDoc } from "../src/model/store.js";
import { readCatalogue, readModel, saveModel } from "../src/model/store.js";

const RE460: ModelDoc = {
  model: "sbb-re460",
  kind: "locomotive",
  length: 220,
  manufacturer: "Roco",
  functions: { "0": { name: "headlights" } },
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

describe("the installation's catalogue", () => {
  it("reads every model it knows, by name and with no railroad named", async () => {
    answer = { ok: true, body: { models: { "sbb-re460": RE460 } } };
    expect(await readCatalogue()).toEqual({ "sbb-re460": RE460 });
    expect(asked).toEqual([{ path: "/catalogue", method: "GET", body: undefined }]);
  });

  it("reads an empty catalogue as no models rather than as a failure", async () => {
    // Which is a box nobody has written a model on yet, and the state the
    // screen that would write the first one draws itself in.
    answer = { ok: true, body: { models: {} } };
    expect(await readCatalogue()).toEqual({});
  });

  it("reads one model at the name it is filed under", async () => {
    answer = { ok: true, body: RE460 };
    expect(await readModel("sbb-re460")).toEqual(RE460);
    expect(asked[0]!.path).toBe("/catalogue/sbb-re460");
  });

  it("saves a model under the name the document gives itself", async () => {
    answer = { ok: true, body: { saved: "sbb-re460" } };
    await saveModel(RE460);
    expect(asked).toEqual([
      { path: "/catalogue/sbb-re460", method: "PUT", body: RE460 },
    ]);
  });

  it("throws what the store said where a model does not validate", async () => {
    // The store writes nothing in that case, so there is one thing to report
    // and nothing to undo.
    answer = { ok: false, body: { error: "model 'sbb-re460': kind must be …" } };
    await expect(saveModel(RE460)).rejects.toThrow("kind must be");
  });
});
