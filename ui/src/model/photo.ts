/**
 * A picture file made a model's photo (ui/STOCK.md#a-models-photo, #978).
 *
 * A file dropped on the photo frame or chosen with **Choose file…** is
 * whatever the person had: a phone's 4000-pixel JPEG, a PNG, a screenshot. The
 * browser decodes it and it is written again as a JPEG **at most 1600 px
 * wide, quality 0.88, never cropped** — a car is wide and low, and the photo
 * is shown whole (`object-fit: contain`), so nothing here decides what part of
 * it matters. The store takes a photo under `image/jpeg` and nothing else
 * (#630).
 *
 * One function, `toJpeg`, so a test can replace it: there is no canvas to
 * decode with in a test's DOM, and what the screen does with the answer is
 * what is under test there. A picture the camera takes is not this: its bytes
 * go to the store as they are (`takePicture`).
 */

import { shows, type Picture } from "./store.js";

/** What a file that is not an image is answered with. */
export const NOT_A_PICTURE = "That file is not a picture.";

/** What an image the browser cannot decode is answered with — HEIC, on most
 *  desktops. */
export const UNREADABLE = "This browser cannot read that picture. Try a JPEG or PNG.";

/** The widest a photo is written: wider than any frame it is shown in. */
export const WIDEST = 1600;

/** The JPEG quality it is written at. */
export const QUALITY = 0.88;

/** Whether a file says it is an image at all, which is asked before the
 *  browser is asked to decode it. */
export function isPicture(file: Blob): boolean {
  return file.type.startsWith("image/");
}

/** The size a picture is written at: as it is where it is no wider than
 *  `WIDEST`, and scaled down whole to that width where it is. */
export function fitted(width: number, height: number): { width: number; height: number } {
  const scale = Math.min(1, WIDEST / width);
  return { width: Math.round(width * scale), height: Math.round(height * scale) };
}

/** A picture file decoded by the browser and written again as the JPEG the
 *  store keeps, with somewhere to show it from until Save writes it. Rejects
 *  with `UNREADABLE` where the browser cannot decode it. */
export async function toJpeg(file: Blob): Promise<Picture> {
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    throw new Error(UNREADABLE);
  }
  const { width, height } = fitted(bitmap.width, bitmap.height);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (context === null) throw new Error(UNREADABLE);
  context.drawImage(bitmap, 0, 0, width, height);
  bitmap.close();
  const blob = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, "image/jpeg", QUALITY),
  );
  if (blob === null) throw new Error(UNREADABLE);
  const jpeg = new Uint8Array(await blob.arrayBuffer());
  return { jpeg, shown: shows(jpeg) };
}
