/**
 * The island sampler: one source of truth for "how high is the ground here".
 *
 * Terrain and agents must agree, or beans float and sink. Phase 3 swaps the
 * noise for the backend heightmap behind this same interface.
 */

import { fbm2 } from '@/lib/noise';
import { clamp01, smoothstep } from '@/lib/math';

export interface IslandParams {
  /** World extent; the island spans `-size/2 .. size/2` on both axes. */
  size: number;
  maxHeight: number;
  /** Fraction of `maxHeight` below which terrain counts as water. */
  waterLevel: number;
  seed: number;
  falloff?: number;
}

export interface IslandSampler {
  readonly params: Required<IslandParams>;
  /** Height in world units at `(x, z)`. */
  heightAt(x: number, z: number): number;
  /** Normalised height in `[0, 1]` at `(x, z)`. */
  normalisedAt(x: number, z: number): number;
  /** True where the ground is below the water line. */
  isWater(x: number, z: number): boolean;
  /** Biome name at `(x, z)`, when the sampler knows one (backend terrain). */
  biomeAt?(x: number, z: number): string | null;
}

const NOISE_SCALE = 2.6;

export function createIslandSampler(params: IslandParams): IslandSampler {
  const resolved: Required<IslandParams> = { falloff: 2.2, ...params };
  const half = resolved.size / 2;
  const waterHeight = resolved.waterLevel * resolved.maxHeight;

  function normalisedAt(x: number, z: number): number {
    // Radial falloff turns a noise field into an island with water at the edges.
    const distance = Math.hypot(x / half, z / half);
    const mask = 1 - smoothstep(Math.pow(clamp01(distance), resolved.falloff));
    const noise = fbm2(
      (x / resolved.size) * NOISE_SCALE,
      (z / resolved.size) * NOISE_SCALE,
      resolved.seed,
      {
        octaves: 5,
      },
    );
    // Bias upwards in the middle so the centre is land, not a lake.
    return clamp01(noise * 0.75 + 0.3) * mask;
  }

  return {
    params: resolved,
    normalisedAt,
    heightAt(x, z) {
      return normalisedAt(x, z) * resolved.maxHeight;
    },
    isWater(x, z) {
      return normalisedAt(x, z) * resolved.maxHeight < waterHeight;
    },
  };
}
