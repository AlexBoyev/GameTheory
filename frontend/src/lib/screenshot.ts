/**
 * Naming a screenshot.
 *
 * The capture itself lives in `scene/Screenshotter`, which has the renderer:
 * reading the canvas from the DOM would need `preserveDrawingBuffer`, and
 * that costs every frame rather than only the one being saved.
 */

/** Filename with a sortable timestamp, so a run's shots stay in order. */
export function screenshotName(tick: number, now: Date = new Date()): string {
  const stamp = now.toISOString().replace(/[:.]/g, '-').slice(0, 19);
  return `gametheory-${stamp}-tick${tick}.png`;
}
