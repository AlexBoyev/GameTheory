/**
 * Render-side performance counters.
 *
 * Kept in its own store, updated at most twice a second, so that reading
 * "what is my frame rate" never itself costs a re-render per frame.
 */

import { create } from 'zustand';

export interface PerfStoreState {
  fps: number;
  /** Draw calls in the last rendered frame - the number to watch. */
  drawCalls: number;
  triangles: number;
  /** Frames per second arriving from the simulation socket. */
  framesPerSecond: number;
  report: (sample: Omit<PerfStoreState, 'report'>) => void;
}

export const usePerfStore = create<PerfStoreState>((set) => ({
  fps: 0,
  drawCalls: 0,
  triangles: 0,
  framesPerSecond: 0,
  report: (sample) => set(sample),
}));
