/**
 * The README's *What is where* names every module under `src/` (#879).
 *
 * The block is the map a person reads before opening a file, and a module
 * added without a line there is one the map does not show. Nothing else
 * notices: the compiler reads imports, not the README. So every `.ts` file
 * under `src/` is checked to be named in the block, under its own directory.
 *
 * A component's `*.styles.ts` is the `<component>.styles.ts` line's, and the
 * `*.generated.ts` files have their own two lines whatever their name, so
 * neither kind needs a line of its own.
 */

import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const UI = new URL("../", import.meta.url);

/** Every `.ts` file under `src/`, as a path from `ui/`. */
function modules(): string[] {
  const src = fileURLToPath(new URL("src/", UI));
  return readdirSync(src, { recursive: true, encoding: "utf8" })
    .filter((path) => path.endsWith(".ts"))
    .map((path) => `src/${path.split("\\").join("/")}`)
    .sort();
}

/** Every path the *What is where* block names: an entry's first word, under
 *  the directories its indentation puts it in. A continuation line's first
 *  word is named as well, which is harmless: it is no file name. */
function named(): Set<string> {
  const readme = readFileSync(new URL("README.md", UI), "utf8");
  const block = /## What is where\n+```\n([\s\S]*?)```/.exec(readme);
  if (!block) throw new Error("README.md has no *What is where* block");
  const paths = new Set<string>();
  const parents: { indent: number; path: string }[] = [];
  for (const line of block[1]!.split("\n")) {
    const entry = /^( *)(\S+)/.exec(line);
    if (!entry) continue;
    const indent = entry[1]!.length;
    while (parents.length && parents.at(-1)!.indent >= indent) parents.pop();
    const path = parents.map((p) => p.path).join("") + entry[2]!;
    paths.add(path);
    if (path.endsWith("/")) parents.push({ indent, path: entry[2]! });
  }
  return paths;
}

describe("README's What is where", () => {
  it("names every module under src/", () => {
    const map = named();
    const missing = modules().filter(
      (path) =>
        !path.endsWith(".styles.ts") &&
        !path.endsWith(".generated.ts") &&
        !map.has(path),
    );
    expect(missing).toEqual([]);
  });
});
