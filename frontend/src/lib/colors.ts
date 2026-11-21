/** The pastel palette (SPEC 9.2). Soft, warm, low contrast - never neon. */

import { remap } from '@/lib/math';

/** Tribe colours, indexed by tribe id; `-1` (no tribe) uses `NO_TRIBE_COLOR`. */
export const TRIBE_COLORS = [
  '#e8a6a6',
  '#a6c8e8',
  '#b6e0a6',
  '#e8d2a6',
  '#c9a6e8',
  '#a6e8d8',
  '#e8bda6',
  '#bfbfe8',
] as const;

export const NO_TRIBE_COLOR = '#dcd3c4';

export const BIOME_COLORS = {
  water: '#86c5de',
  beach: '#f2e3c4',
  meadow: '#c7e3a8',
  forest: '#8fc08a',
  hills: '#cbbf9b',
  peaks: '#efeae2',
} as const satisfies Record<string, string>;

/** Colour for a biome name from the `hello` legend; unknown names read as land. */
export function biomeColor(name: string): string {
  return name in BIOME_COLORS
    ? BIOME_COLORS[name as keyof typeof BIOME_COLORS]
    : BIOME_COLORS.meadow;
}

export function tribeColor(tribeId: number): string {
  if (tribeId < 0) return NO_TRIBE_COLOR;
  return TRIBE_COLORS[tribeId % TRIBE_COLORS.length] ?? NO_TRIBE_COLOR;
}

/** Blend two hex colours; `alpha` 0 returns `a`, 1 returns `b`. */
export function mixHex(a: string, b: string, alpha: number): string {
  const parse = (hex: string): [number, number, number] => {
    const value = Number.parseInt(hex.replace('#', ''), 16);
    return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
  };
  const [ar, ag, ab] = parse(a);
  const [br, bg, bb] = parse(b);
  const to = (from: number, target: number): number =>
    Math.round(from + (target - from) * Math.max(0, Math.min(1, alpha)));
  const channels = [to(ar, br), to(ag, bg), to(ab, bb)];
  return `#${channels.map((c) => c.toString(16).padStart(2, '0')).join('')}`;
}

/**
 * Terrain colour by normalised height: water, beach, meadow, forest, hills,
 * peaks - with short blends so the island reads as one smooth surface.
 */
export function terrainColorAt(normalisedHeight: number, waterLevel: number): string {
  const h = normalisedHeight;
  if (h < waterLevel) return BIOME_COLORS.water;
  const land = remap(h, waterLevel, 1, 0, 1);
  if (land < 0.08) return mixHex(BIOME_COLORS.water, BIOME_COLORS.beach, land / 0.08);
  if (land < 0.18) return BIOME_COLORS.beach;
  if (land < 0.34) return mixHex(BIOME_COLORS.beach, BIOME_COLORS.meadow, (land - 0.18) / 0.16);
  if (land < 0.56) return mixHex(BIOME_COLORS.meadow, BIOME_COLORS.forest, (land - 0.34) / 0.22);
  if (land < 0.78) return mixHex(BIOME_COLORS.forest, BIOME_COLORS.hills, (land - 0.56) / 0.22);
  return mixHex(BIOME_COLORS.hills, BIOME_COLORS.peaks, (land - 0.78) / 0.22);
}

/** Sun colour over the day: warm at dawn/dusk, white at noon, blue at night. */
export function sunColorAt(timeOfDay: number): string {
  if (timeOfDay < 0.22 || timeOfDay >= 0.86) return '#6f86c9';
  if (timeOfDay < 0.32) return mixHex('#6f86c9', '#ffd2a1', (timeOfDay - 0.22) / 0.1);
  if (timeOfDay < 0.44) return mixHex('#ffd2a1', '#fff6e2', (timeOfDay - 0.32) / 0.12);
  if (timeOfDay < 0.68) return '#fff6e2';
  if (timeOfDay < 0.8) return mixHex('#fff6e2', '#ffc49b', (timeOfDay - 0.68) / 0.12);
  return mixHex('#ffc49b', '#6f86c9', (timeOfDay - 0.8) / 0.06);
}
