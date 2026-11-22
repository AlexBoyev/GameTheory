/**
 * Where the camera is looking, for the minimap.
 *
 * Written from inside the render loop and read by one small canvas, so it is
 * deliberately *not* reactive: a store that re-rendered React sixty times a
 * second to move a triangle would cost more than the minimap is worth. The
 * minimap reads it with `cameraState()` on its own redraw timer.
 */

import { create } from 'zustand';

export interface CameraStoreState {
  /** The point the camera orbits, in world units. */
  x: number;
  z: number;
  /** Compass heading of the view direction, in radians. */
  heading: number;
  /** Distance from the target, which stands in for how much is on screen. */
  distance: number;

  report: (x: number, z: number, heading: number, distance: number) => void;
}

export const useCameraStore = create<CameraStoreState>((set) => ({
  x: 0,
  z: 0,
  heading: 0,
  distance: 80,
  report: (x, z, heading, distance) => set({ x, z, heading, distance }),
}));

/** Non-reactive read, for code running inside the render loop or on a timer. */
export const cameraState = (): CameraStoreState => useCameraStore.getState();
