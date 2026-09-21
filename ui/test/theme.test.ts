// @vitest-environment happy-dom

/**
 * Which Shoelace theme the page wears (#547).
 *
 * Both themes are linked and the operating system decides, with no toggle in
 * the page (LOOK.md, ADR-0003). Shoelace's dark theme hangs off a class rather
 * than a query of its own, so the query is read here and the class is the
 * whole of what this module does; a test is worth having because the class
 * name is a string in someone else's stylesheet and nothing else would notice
 * it going wrong.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { followTheSystem } from "../src/ui/theme.js";

/** The preference, and a way to change it: happy-dom answers `matchMedia`
 *  with a list that never changes, and what is under test is a page that
 *  follows one that does. */
function preferring(dark: boolean) {
  const listeners: (() => void)[] = [];
  const query = {
    matches: dark,
    addEventListener: (_: string, listener: () => void) =>
      listeners.push(listener),
  };
  vi.spyOn(window, "matchMedia").mockReturnValue(
    query as unknown as MediaQueryList,
  );
  return (now: boolean) => {
    query.matches = now;
    for (const listener of listeners) listener();
  };
}

afterEach(() => {
  vi.restoreAllMocks();
  document.documentElement.className = "";
});

describe("the theme the page wears", () => {
  it("is the light one with nothing said", () => {
    preferring(false);
    followTheSystem();
    expect(document.documentElement.classList.contains("sl-theme-dark")).toBe(
      false,
    );
  });

  it("is the dark one where the system asks for dark", () => {
    preferring(true);
    followTheSystem();
    expect(document.documentElement.classList.contains("sl-theme-dark")).toBe(
      true,
    );
  });

  /** A page left open on a machine that turns dark at sunset. Nothing reloads
   *  it, so the preference changing is the only thing there is to follow. */
  it("follows the preference changing under an open page", () => {
    const now = preferring(false);
    followTheSystem();
    now(true);
    expect(document.documentElement.classList.contains("sl-theme-dark")).toBe(
      true,
    );
    now(false);
    expect(document.documentElement.classList.contains("sl-theme-dark")).toBe(
      false,
    );
  });
});
