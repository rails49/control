/**
 * One train as `GET /rosters/<railroad>/trains` answers it, for a suite that
 * cares about some of its fields and not the rest.
 *
 * Every field is on the store's answer, so a fixture states them all; this
 * fills in the ones a suite leaves out as a train of `length` with nothing to
 * switch, no camera, no locomotive, no address and the colour orange.
 *
 * Tests only — nothing under `src` imports this.
 */

import type { TrainDoc } from "../../src/model/store.js";

export function trainDoc(length: number, more: Partial<TrainDoc> = {}): TrainDoc {
  return {
    length,
    functions: [],
    camera: false,
    locomotive: null,
    addresses: [],
    colour: "orange",
    ...more,
  };
}
