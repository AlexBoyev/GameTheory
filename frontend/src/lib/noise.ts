/**
 * Deterministic value noise with smooth interpolation.
 *
 * Phase 1 only: the island you see is generated in the browser so the scene
 * has something to render before the backend owns terrain. From Phase 2 the
 * heightmap comes from `GET /api/world/terrain` and this file is used only by
 * tests and by the minimap placeholder.
 */

import { smoothstep } from '@/lib/math';

/** Stable 2D hash in `[0, 1)` - no `Math.random`, so the island never jitters. */
function hash2(x: number, y: number, seed: number): number {
  let h = x * 374761393 + y * 668265263 + seed * 2246822519;
  h = (h ^ (h >>> 13)) * 1274126177;
  h = h ^ (h >>> 16);
  return (h >>> 0) / 4294967296;
}

/** Bilinearly smoothed value noise at `(x, y)`. */
export function valueNoise2(x: number, y: number, seed: number): number {
  const xi = Math.floor(x);
  const yi = Math.floor(y);
  const tx = smoothstep(x - xi);
  const ty = smoothstep(y - yi);

  const n00 = hash2(xi, yi, seed);
  const n10 = hash2(xi + 1, yi, seed);
  const n01 = hash2(xi, yi + 1, seed);
  const n11 = hash2(xi + 1, yi + 1, seed);

  const top = n00 + (n10 - n00) * tx;
  const bottom = n01 + (n11 - n01) * tx;
  return top + (bottom - top) * ty;
}

export interface FbmOptions {
  octaves?: number;
  frequency?: number;
  lacunarity?: number;
  gain?: number;
}

/** Fractal Brownian motion in `[0, 1]`. */
export function fbm2(x: number, y: number, seed: number, options: FbmOptions = {}): number {
  const { octaves = 5, frequency = 1, lacunarity = 2, gain = 0.5 } = options;
  let amplitude = 1;
  let total = 0;
  let normalisation = 0;
  let f = frequency;

  for (let octave = 0; octave < octaves; octave += 1) {
    total += valueNoise2(x * f, y * f, seed + octave * 101) * amplitude;
    normalisation += amplitude;
    amplitude *= gain;
    f *= lacunarity;
  }
  return normalisation > 0 ? total / normalisation : 0;
}
