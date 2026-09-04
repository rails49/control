/**
 * What a call to the store says when it does not come back with a document
 * (#411).
 *
 * Three ways to fail and three sets of words, decided once in `ask` so that
 * every screen shows the same thing: nothing answered, something answered that
 * is not the store's, and the store's own refusal. The third was the only one
 * the helper knew — it parsed every body as JSON before looking at the status
 * — so a proxy's 404 page reached a person as the parser's complaint, and the
 * screens above it told them to start a store that was up and answering
 * (#405).
 *
 * Driven through `readCatalogue` and `saveModel` because a caller has to run
 * for `ask` to run; nothing here is about the catalogue, which is
 * `test/catalogue.test.ts`.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { ModelDoc } from "../src/model/store.js";
import { readCatalogue, saveModel, Unanswered } from "../src/model/store.js";

const RE460: ModelDoc = { model: "sbb-re460", kind: "locomotive", length: 220 };

let real: typeof globalThis.fetch;

beforeEach(() => {
  real = globalThis.fetch;
});

afterEach(() => {
  globalThis.fetch = real;
});

/** What comes back from whatever answered, as `fetch` hands it over. */
function answers(response: Partial<Response> & { json?: () => Promise<unknown> }): void {
  globalThis.fetch = (() =>
    Promise.resolve(response as unknown as Response)) as unknown as typeof fetch;
}

/** A page from something in front of the store: a status, a content type
 *  saying HTML, and a body that will not parse as JSON. */
function page(status: number, statusText = ""): void {
  answers({
    ok: false,
    status,
    statusText,
    headers: new Headers({ "content-type": "text/html; charset=utf-8" }),
    json: () => Promise.reject(new SyntaxError("Unexpected token '<'")),
  });
}

/** The store's own answer: JSON, with the status it chose. */
function store(status: number, body: unknown): void {
  answers({
    ok: status < 400,
    status,
    statusText: "",
    headers: new Headers({ "content-type": "application/json" }),
    json: () => Promise.resolve(body),
  });
}

describe("a call that gets no answer at all", () => {
  it("names the store and the command that starts one", async () => {
    globalThis.fetch = (() =>
      Promise.reject(new TypeError("Failed to fetch"))) as unknown as typeof fetch;

    await expect(readCatalogue()).rejects.toThrow(
      "the store is not answering — run `tc49 serve`",
    );
  });

  it("is one a view reads again after", async () => {
    globalThis.fetch = (() =>
      Promise.reject(new TypeError("Failed to fetch"))) as unknown as typeof fetch;

    await expect(readCatalogue()).rejects.toBeInstanceOf(Unanswered);
  });
});

describe("an answer that is not the store's", () => {
  /** What #405 was: the proxy's route table was stale, so `GET /catalogue`
   *  came back as nginx's own 404 page. The store was up throughout. */
  it("says what was asked and what came back", async () => {
    page(404);

    await expect(readCatalogue()).rejects.toThrow("GET /catalogue answered 404");
  });

  it("adds the status text where the browser gives one", async () => {
    page(502, "Bad Gateway");

    await expect(readCatalogue()).rejects.toThrow(
      "GET /catalogue answered 502 Bad Gateway",
    );
  });

  /** The write, which is the same dialog's Create press: the path is the one
   *  the model was to be written at. */
  it("names a write by its own method and path", async () => {
    page(404);

    await expect(saveModel(RE460)).rejects.toThrow(
      "PUT /catalogue/sbb-re460 answered 404",
    );
  });

  /** It guesses at no cause. There is a proxy in front of a layout server and
   *  none in front of a laptop's store, and this side knows about neither. */
  it("says nothing about why", async () => {
    page(404);

    await expect(readCatalogue()).rejects.not.toThrow(/proxy|route table|tc49 serve/);
  });

  it("is one a view reads again after", async () => {
    page(404);

    await expect(readCatalogue()).rejects.toBeInstanceOf(Unanswered);
  });

  /** A body that parses as nothing is not the store's answer whatever the
   *  status is: a 200 from something else is still something else. */
  it("does not take a 200 that will not parse for an answer", async () => {
    answers({
      ok: true,
      status: 200,
      statusText: "OK",
      headers: new Headers({ "content-type": "text/html" }),
      json: () => Promise.reject(new SyntaxError("Unexpected token '<'")),
    });

    await expect(readCatalogue()).rejects.toThrow("GET /catalogue answered 200 OK");
  });

  /** A status the store did not put words on names the request, there being
   *  nothing else to say about it. */
  it("names the request where a status arrives with no words on it", async () => {
    store(500, {});

    await expect(readCatalogue()).rejects.toThrow("GET /catalogue answered 500");
  });
});

describe("the store's own refusal", () => {
  it("is shown in the store's words", async () => {
    store(400, { error: "model 'sbb-re460': kind must be one of …" });

    await expect(saveModel(RE460)).rejects.toThrow("kind must be one of");
  });

  /** Not something to try again: the store answered, and it will answer the
   *  same until what was sent changes. */
  it("is not one a view reads again after", async () => {
    store(400, { error: "model 'sbb-re460': kind must be one of …" });

    await expect(saveModel(RE460)).rejects.not.toBeInstanceOf(Unanswered);
  });
});
