/**
 * The population-to-speed curve the new-world dialog quotes.
 *
 * It exists so the dialog can warn you before you build a 400-agent island
 * and press 25x, which is three to five times what the engine can deliver.
 * A hint that lies would be worse than no hint, so the measured points have
 * to come back out of it unchanged and it has to stay monotonic in between.
 */

import { describe, expect, it } from 'vitest';

import { populationHint, speedCeiling } from '@/lib/capacity';

describe('speedCeiling', () => {
  it('returns the measured points', () => {
    expect(speedCeiling(100)).toBeCloseTo(35);
    expect(speedCeiling(150)).toBeCloseTo(23);
    expect(speedCeiling(300)).toBeCloseTo(10);
    expect(speedCeiling(500)).toBeCloseTo(5);
  });

  it('interpolates between them', () => {
    const between = speedCeiling(225);

    expect(between).toBeLessThan(23);
    expect(between).toBeGreaterThan(10);
  });

  it('never promises more to a bigger island', () => {
    let previous = Infinity;
    for (let population = 10; population <= 600; population += 10) {
      const ceiling = speedCeiling(population);
      expect(ceiling).toBeLessThanOrEqual(previous + 1e-9);
      previous = ceiling;
    }
  });

  it('holds the small end flat rather than promising absurd speeds', () => {
    // Ten agents are not 35x faster than a hundred: MAX exists for that, and
    // quoting 350x in a hint would be a number nobody could act on.
    expect(speedCeiling(10)).toBe(35);
    expect(speedCeiling(50)).toBe(35);
  });

  it('keeps falling past the measured range', () => {
    expect(speedCeiling(600)).toBeLessThan(5);
    expect(speedCeiling(600)).toBeGreaterThan(0);
  });
});

describe('populationHint', () => {
  it('quotes a speed the reader can act on', () => {
    expect(populationHint(300)).toContain('10x');
    expect(populationHint(500)).toContain('5x');
  });
});
