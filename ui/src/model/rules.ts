/**
 * The rules the store enforces over a document, said once for the browser.
 *
 * Each is a transcription of the Python the store checks with, cited in the
 * doc comment above it. They are transcribed rather than generated: the
 * reasoning is in #490, and what matters here is that the transcription
 * happens once. A rule restated per screen drifts one screen at a time, and a
 * screen that forgot to restate it lets a value through that the store then
 * answers with a 400 — which is a refusal read across the network rather than
 * beside the field it was typed in (ADR-0023).
 */

/** What the drawing schema takes as a name: not empty, and without the `.`
 *  that separates a symbol from its pin or the `/` that separates a path
 *  (`tc49.lib.layout.check_name`). */
export function isName(name: string): boolean {
  return name !== "" && !name.includes(".") && !name.includes("/");
}
