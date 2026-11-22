/**
 * Saving a PNG of the island.
 *
 * The canvas is found in the DOM rather than threaded down from the scene,
 * because the button lives in the 2D overlay and there is exactly one canvas.
 * It needs `preserveDrawingBuffer` on the WebGL context (set in `App`), or
 * the buffer is already cleared by the time we read it.
 */

/** Filename with a sortable timestamp, so a run's shots stay in order. */
export function screenshotName(tick: number, now: Date = new Date()): string {
  const stamp = now.toISOString().replace(/[:.]/g, '-').slice(0, 19);
  return `gametheory-${stamp}-tick${tick}.png`;
}

/**
 * Save the current frame as a PNG download.
 *
 * Returns false when there is no canvas or the browser refuses to export it,
 * so the caller can say so rather than appearing to do nothing.
 */
export function saveScreenshot(tick: number): boolean {
  const canvas = document.querySelector('canvas');
  if (!(canvas instanceof HTMLCanvasElement)) return false;

  let url: string;
  try {
    url = canvas.toDataURL('image/png');
  } catch {
    return false;
  }
  if (!url.startsWith('data:image/png') || url.length < 100) return false;

  const link = document.createElement('a');
  link.href = url;
  link.download = screenshotName(tick);
  link.click();
  return true;
}
