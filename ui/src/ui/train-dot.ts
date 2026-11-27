/**
 * The dot in a train's colour that the run view's roster and request list
 * put before a train's name, so a person can match a row to the train's
 * route (#1410). The colour is set on the dot as `--train`, `--train-<name>`
 * for a train in the trains read and `--hint` for one missing from it; the
 * stylesheet's one `.dot` rule paints it (`shared.styles.ts`).
 */

import { html, type TemplateResult } from "lit";

import type { TrainColour } from "../colour.generated.js";

export function dot(colour: TrainColour | undefined): TemplateResult {
  const value = colour === undefined ? "var(--hint)" : `var(--train-${colour})`;
  return html`<span class="dot" style=${`--train: ${value}`}></span>`;
}
