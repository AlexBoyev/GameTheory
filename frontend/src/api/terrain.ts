/**
 * Fetching and decoding the backend heightmap.
 *
 * The backend owns terrain from Phase 2 on. It arrives once per world as
 * base64 Float32 heights plus a uint8 biome map, and is wrapped in the same
 * `IslandSampler` interface the browser-side noise island used - so the mesh,
 * the agents and the camera all keep asking one question: how high is here.
 */

import type { IslandSampler } from '@/lib/terrain';

export interface TerrainPayload {
  size: number;
  resolution: number;
  water_level: number;
  max_height: number;
  heights_b64: string;
  biomes_b64: string;
  biome_names: string[];
}

export interface TerrainGrid {
  size: number;
  resolution: number;
  waterLevel: number;
  maxHeight: number;
  heights: Float32Array;
  biomes: Uint8Array;
  biomeNames: string[];
}

function decodeBase64(encoded: string): Uint8Array {
  const binary = atob(encoded);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

export function decodeTerrain(payload: TerrainPayload): TerrainGrid {
  const heightBytes = decodeBase64(payload.heights_b64);
  const biomes = decodeBase64(payload.biomes_b64);
  // The buffer is a fresh copy, so viewing it as Float32 is safe and free.
  const heights = new Float32Array(
    heightBytes.buffer,
    heightBytes.byteOffset,
    heightBytes.byteLength / 4,
  );

  return {
    size: payload.size,
    resolution: payload.resolution,
    waterLevel: payload.water_level,
    maxHeight: payload.max_height,
    heights,
    biomes,
    biomeNames: payload.biome_names,
  };
}

export async function fetchTerrain(): Promise<TerrainGrid> {
  const response = await fetch('/api/world/terrain');
  if (!response.ok) {
    throw new Error(`terrain request failed: ${response.status}`);
  }
  return decodeTerrain((await response.json()) as TerrainPayload);
}

/** Wrap a decoded grid in the sampler interface the scene expects. */
export function createGridSampler(grid: TerrainGrid): IslandSampler {
  const { resolution, size, maxHeight, waterLevel, heights, biomes, biomeNames } = grid;
  const half = size / 2;
  const step = size / (resolution - 1);
  const waterHeight = waterLevel;

  const indexAt = (x: number, z: number): number => {
    const col = Math.min(resolution - 1, Math.max(0, Math.round((x + half) / step)));
    const row = Math.min(resolution - 1, Math.max(0, Math.round((z + half) / step)));
    return row * resolution + col;
  };

  /** Bilinear height, so agents walking between cells do not step up stairs. */
  const heightAt = (x: number, z: number): number => {
    const gridX = Math.min(resolution - 1, Math.max(0, (x + half) / step));
    const gridZ = Math.min(resolution - 1, Math.max(0, (z + half) / step));
    const x0 = Math.floor(gridX);
    const z0 = Math.floor(gridZ);
    const x1 = Math.min(resolution - 1, x0 + 1);
    const z1 = Math.min(resolution - 1, z0 + 1);
    const fx = gridX - x0;
    const fz = gridZ - z0;

    const h00 = heights[z0 * resolution + x0] ?? 0;
    const h10 = heights[z0 * resolution + x1] ?? 0;
    const h01 = heights[z1 * resolution + x0] ?? 0;
    const h11 = heights[z1 * resolution + x1] ?? 0;

    const top = h00 + (h10 - h00) * fx;
    const bottom = h01 + (h11 - h01) * fx;
    return top + (bottom - top) * fz;
  };

  return {
    params: { size, maxHeight, waterLevel: waterLevel / maxHeight, seed: 0, falloff: 0 },
    heightAt,
    normalisedAt: (x, z) => (maxHeight > 0 ? heightAt(x, z) / maxHeight : 0),
    isWater: (x, z) => heightAt(x, z) < waterHeight,
    biomeAt: (x, z) => biomeNames[biomes[indexAt(x, z)] ?? 0] ?? null,
  };
}
