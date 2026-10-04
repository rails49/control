/**
 * The catalogue calls: which route each one asks, and what it makes of the
 * answer (#392).
 *
 * At the client rather than through the screen that now writes them
 * (`test/making.test.ts`, `test/photos.test.ts`): what is under test is the
 * shape of the request — a model is the installation's and is addressed by its
 * own name, with no railroad in the path (ADR-0045) — and the unwrapping of
 * the answer.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { ModelDoc } from "../src/model/store.js";
import {
  photoUrl,
  readCatalogue,
  readModel,
  saveModel,
  savePhoto,
} from "../src/model/store.js";

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
  /** What the body was labelled, where the call labelled it: `sent` keeps a
   *  photo's bytes as they are, and the label is the whole of what says a body
   *  is a picture rather than a document. */
  type?: string;
}

const asked: Asked[] = [];
let answer: { ok: boolean; body: unknown } = { ok: true, body: {} };
let real: typeof globalThis.fetch;

beforeEach(() => {
  real = globalThis.fetch;
  asked.length = 0;
  globalThis.fetch = ((path: string, init?: RequestInit) => {
    const labelled = init?.headers as Record<string, string> | undefined;
    asked.push({
      path,
      method: init?.method ?? "GET",
      body: sent(init?.body),
      ...(labelled?.["Content-Type"] === undefined
        ? {}
        : { type: labelled["Content-Type"] }),
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

/** What a call carried, as the route takes it: a photo's own bytes, the one
 *  body here that is not a document, and the document everywhere else. */
function sent(body: BodyInit | null | undefined): unknown {
  if (body === undefined || body === null) return undefined;
  if (body instanceof Uint8Array) return body;
  return JSON.parse(String(body));
}

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
      {
        path: "/catalogue/sbb-re460",
        method: "PUT",
        body: RE460,
        type: "application/json",
      },
    ]);
  });

  /** The picture hangs below the model's document and is addressed by the
   *  model's own name, as the document is. Nothing on the document says
   *  whether there is one, so the route is the whole of the question (#630). */
  it("points at one model's photo below that model's own route", () => {
    expect(photoUrl("sbb-re460")).toBe("/catalogue/sbb-re460/photo");
  });

  /** A cache-buster and no part of the route: the store drops a query string,
   *  so this is the same picture asked for again rather than another one. */
  it("asks for the photo again under a version, and for nothing where none", () => {
    expect(photoUrl("sbb-re460", 2)).toBe("/catalogue/sbb-re460/photo?v=2");
    expect(photoUrl("sbb-re460", 0)).toBe("/catalogue/sbb-re460/photo");
  });

  /** The body is the JPEG itself, byte for byte, under `image/jpeg`: the one
   *  thing this app sends that is not a document (docs/SYSTEM.md). */
  it("saves a photo as the picture's own bytes", async () => {
    answer = { ok: true, body: { saved: "sbb-re460" } };
    const jpeg = new Uint8Array([0xff, 0xd8, 0xff, 0x2a]);

    await savePhoto("sbb-re460", jpeg);

    expect(asked).toEqual([
      {
        path: "/catalogue/sbb-re460/photo",
        method: "PUT",
        body: jpeg,
        type: "image/jpeg",
      },
    ]);
  });

  it("throws what the store said where a model does not validate", async () => {
    // The store writes nothing in that case, so there is one thing to report
    // and nothing to undo.
    answer = { ok: false, body: { error: "model 'sbb-re460': kind must be …" } };
    await expect(saveModel(RE460)).rejects.toThrow("kind must be");
  });
});
