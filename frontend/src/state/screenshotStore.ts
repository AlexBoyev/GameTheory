/**
 * A one-shot request to save a PNG.
 *
 * The button is in the 2D overlay and the renderer is inside the Canvas, so
 * they cannot call each other directly. This is the smallest possible seam:
 * the button raises a flag, the in-scene `Screenshotter` honours it on the
 * next frame and reports whether the browser allowed it.
 */

import { create } from 'zustand';

export interface ScreenshotStoreState {
  requested: boolean;
  /** Null until a shot has been attempted; false when the browser refused. */
  lastSucceeded: boolean | null;

  request: () => void;
  resolve: (succeeded: boolean) => void;
}

export const useScreenshotStore = create<ScreenshotStoreState>((set) => ({
  requested: false,
  lastSucceeded: null,
  request: () => set({ requested: true }),
  resolve: (succeeded) => set({ requested: false, lastSucceeded: succeeded }),
}));
