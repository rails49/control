/**
 * The camera car's live picture, read off the `camera` app's route
 * (ADR-0082, ui/THROTTLE.md).
 *
 * Read with `fetch` rather than drawn as `<img src>`, because an image tells
 * the page nothing once its first frame is in: a multipart stream that ends,
 * or stays open and sends nothing, fires no `error`, and the last frame would
 * stay on screen as if live ([#950](https://github.com/rails49/control/issues/950)).
 * Reading the body itself, the page knows when either happens.
 */

/** How long the picture may go without a frame before it counts as lost. A
 *  camera that is streaming sends several a second, and the camera app gives
 *  up on one silent this long (`SILENCE_S`). */
export const STALL_MS = 5000;

/** A stream being read: the route, and how to stop reading it. */
export interface Watching {
  url: string;
  stop: () => void;
}

/**
 * Read the stream at `url`: `shown` with each JPEG it carries, and `lost`
 * once where the answer is not a 200, the fetch fails, the body ends, or no
 * frame comes for `STALL_MS`. `stop` ends the read and calls neither again.
 */
export function watchPicture(
  url: string,
  shown: (jpeg: Blob) => void,
  lost: () => void,
): Watching {
  const aborted = new AbortController();
  let stall: ReturnType<typeof setTimeout> | null = null;
  let over = false;
  const end = (failed: boolean): void => {
    if (over) return;
    over = true;
    if (stall !== null) clearTimeout(stall);
    aborted.abort();
    if (failed) lost();
  };
  const waiting = (): void => {
    if (stall !== null) clearTimeout(stall);
    stall = setTimeout(() => end(true), STALL_MS);
  };
  waiting();
  void (async () => {
    try {
      const response = await fetch(url, { signal: aborted.signal });
      if (!response.ok || response.body === null) return end(true);
      for await (const jpeg of jpegs(response.body)) {
        if (over) return;
        waiting();
        shown(new Blob([jpeg as Uint8Array<ArrayBuffer>], { type: "image/jpeg" }));
      }
    } catch {
      // Aborted, or the connection failed: either way the read is over.
    }
    end(true);
  })();
  return { url, stop: () => end(false) };
}

const BLANK = new Uint8Array([13, 10, 13, 10]);

/** The JPEGs of a body laid out as `multipart/x-mixed-replace`, as the
 *  camera app writes it, each part carrying its `Content-Length`. Ends at the
 *  end of the body and at a part with no length. */
export async function* jpegs(body: ReadableStream<Uint8Array>): AsyncGenerator<Uint8Array> {
  const reader = body.getReader();
  let held = new Uint8Array(0);
  for (;;) {
    const headers = find(held, BLANK);
    if (headers >= 0) {
      const start = headers + BLANK.length;
      const said = /content-length:\s*(\d+)/i.exec(
        new TextDecoder("latin1").decode(held.subarray(0, headers)),
      );
      if (said === null) return;
      const end = start + Number(said[1]);
      if (held.length >= end) {
        yield held.slice(start, end);
        held = held.slice(end);
        continue;
      }
    }
    const { done, value } = await reader.read();
    if (done) return;
    const more = new Uint8Array(held.length + value.length);
    more.set(held);
    more.set(value, held.length);
    held = more;
  }
}

/** Where `needle` first starts in `bytes`, or -1. */
function find(bytes: Uint8Array, needle: Uint8Array): number {
  outer: for (let i = 0; i + needle.length <= bytes.length; i++) {
    for (let j = 0; j < needle.length; j++) {
      if (bytes[i + j] !== needle[j]) continue outer;
    }
    return i;
  }
  return -1;
}
