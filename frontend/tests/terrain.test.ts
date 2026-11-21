import { describe, expect, it } from 'vitest';

import { createGridSampler, decodeTerrain, type TerrainPayload } from '@/api/terrain';

const RESOLUTION = 4;
const MAX_HEIGHT = 10;
const SIZE = 30;

/** Build a payload whose height rises left to right, with water on the left. */
function payload(): TerrainPayload {
  const heights = new Float32Array(RESOLUTION * RESOLUTION);
  const biomes = new Uint8Array(RESOLUTION * RESOLUTION);
  for (let row = 0; row < RESOLUTION; row += 1) {
    for (let col = 0; col < RESOLUTION; col += 1) {
      const index = row * RESOLUTION + col;
      heights[index] = col * 3; // 0, 3, 6, 9
      biomes[index] = col === 0 ? 0 : 2; // water, then meadow
    }
  }
  const toBase64 = (bytes: Uint8Array): string =>
    btoa(String.fromCharCode(...Array.from(bytes)));

  return {
    size: SIZE,
    resolution: RESOLUTION,
    water_level: 1.5,
    max_height: MAX_HEIGHT,
    heights_b64: toBase64(new Uint8Array(heights.buffer)),
    biomes_b64: toBase64(biomes),
    biome_names: ['water', 'beach', 'meadow'],
  };
}

describe('decodeTerrain', () => {
  it('decodes base64 into the promised array sizes', () => {
    const grid = decodeTerrain(payload());

    expect(grid.heights).toHaveLength(RESOLUTION * RESOLUTION);
    expect(grid.biomes).toHaveLength(RESOLUTION * RESOLUTION);
    expect(grid.resolution).toBe(RESOLUTION);
    expect(grid.maxHeight).toBe(MAX_HEIGHT);
  });

  it('preserves the height values', () => {
    const grid = decodeTerrain(payload());

    expect(Array.from(grid.heights.slice(0, 4))).toEqual([0, 3, 6, 9]);
  });
});

describe('createGridSampler', () => {
  const sampler = createGridSampler(decodeTerrain(payload()));
  const half = SIZE / 2;

  it('samples the corners of the grid', () => {
    expect(sampler.heightAt(-half, -half)).toBeCloseTo(0, 5);
    expect(sampler.heightAt(half, -half)).toBeCloseTo(9, 5);
  });

  it('interpolates between cells instead of stepping', () => {
    const step = SIZE / (RESOLUTION - 1);
    const midway = sampler.heightAt(-half + step / 2, -half);

    expect(midway).toBeGreaterThan(0);
    expect(midway).toBeLessThan(3);
    expect(midway).toBeCloseTo(1.5, 5);
  });

  it('reports normalised height against max_height', () => {
    expect(sampler.normalisedAt(half, -half)).toBeCloseTo(0.9, 5);
  });

  it('knows where the water is', () => {
    expect(sampler.isWater(-half, -half)).toBe(true);
    expect(sampler.isWater(half, -half)).toBe(false);
  });

  it('exposes biome names for terrain colouring', () => {
    expect(sampler.biomeAt?.(-half, -half)).toBe('water');
    expect(sampler.biomeAt?.(half, half)).toBe('meadow');
  });

  it('clamps queries outside the island', () => {
    expect(sampler.heightAt(-1000, -1000)).toBeCloseTo(0, 5);
    expect(Number.isFinite(sampler.heightAt(1000, 1000))).toBe(true);
  });
});
