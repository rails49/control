import { describe, expect, it } from "vitest";

import { jpegs } from "../src/model/picture.js";

const encoder = new TextEncoder();

/** One part as the camera app writes it (`src/tc49/camera/face.py`). */
function part(jpeg: Uint8Array): Uint8Array {
  const head = encoder.encode(
    `--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ${jpeg.length}\r\n\r\n`,
  );
  return joined(head, jpeg, encoder.encode("\r\n"));
}

function joined(...pieces: Uint8Array[]): Uint8Array {
  const all = new Uint8Array(pieces.reduce((n, piece) => n + piece.length, 0));
  let at = 0;
  for (const piece of pieces) {
    all.set(piece, at);
    at += piece.length;
  }
  return all;
}

/** A body that arrives in `size`-byte chunks, as a network splits it. */
function body(bytes: Uint8Array, size: number): ReadableStream<Uint8Array> {
  let at = 0;
  return new ReadableStream({
    pull(controller) {
      if (at >= bytes.length) return controller.close();
      controller.enqueue(bytes.slice(at, at + size));
      at += size;
    },
  });
}

async function read(stream: ReadableStream<Uint8Array>): Promise<number[][]> {
  const got: number[][] = [];
  for await (const jpeg of jpegs(stream)) got.push([...jpeg]);
  return got;
}

describe("the camera app's stream, read", () => {
  const one = new Uint8Array([0xff, 0xd8, 13, 10, 13, 10, 0xff, 0xd9]);
  const two = new Uint8Array([0xff, 0xd8, 2, 0xff, 0xd9]);
  const sent = joined(part(one), part(two), encoder.encode("--frame--\r\n"));

  it.each([1, 3, 1000])("yields each JPEG unchanged, in %i-byte chunks", async (size) => {
    expect(await read(body(sent, size))).toEqual([[...one], [...two]]);
  });

  it("ends at a part with no length", async () => {
    const bare = encoder.encode("--frame\r\nContent-Type: image/jpeg\r\n\r\n");
    expect(await read(body(joined(part(one), bare, part(two)), 7))).toEqual([[...one]]);
  });
});
