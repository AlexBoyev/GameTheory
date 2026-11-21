/**
 * Measures the render loop from inside it.
 *
 * Reports twice a second rather than every frame: a counter that re-renders
 * React sixty times a second is measuring itself.
 */

import { useFrame, useThree } from '@react-three/fiber';
import { useRef } from 'react';

import { usePerfStore } from '@/state/perfStore';
import { simState } from '@/state/simStore';

const REPORT_INTERVAL_MS = 500;

export function PerfProbe(): null {
  const gl = useThree((three) => three.gl);
  const frames = useRef(0);
  // Seeded on the first frame rather than at render time: reading the clock
  // during render is impure, and the first window is measured anyway.
  const since = useRef(0);
  const lastSimFrames = useRef(0);

  useFrame(() => {
    frames.current += 1;
    const now = performance.now();
    if (since.current === 0) {
      since.current = now;
      return;
    }
    const elapsed = now - since.current;
    if (elapsed < REPORT_INTERVAL_MS) return;

    const simFrames = simState().framesReceived;
    usePerfStore.getState().report({
      fps: Math.round((frames.current * 1000) / elapsed),
      drawCalls: gl.info.render.calls,
      triangles: gl.info.render.triangles,
      framesPerSecond: Math.round(((simFrames - lastSimFrames.current) * 1000) / elapsed),
    });

    frames.current = 0;
    lastSimFrames.current = simFrames;
    since.current = now;
  });

  return null;
}
