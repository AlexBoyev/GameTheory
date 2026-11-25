import { describe, expect, it } from 'vitest';

import { humanDuration, paceSummary, secondsToDay, TICKS_PER_DAY } from '@/lib/eta';

describe('projecting how long the world will take', () => {
  it('answers the question the tps readout cannot', () => {
    // Measured on the default island: ~124 tps sustained at MAX.
    expect(secondsToDay(0, 10, 124)).toBeCloseTo((10 * TICKS_PER_DAY) / 124, 5);
    expect(humanDuration((10 * TICKS_PER_DAY) / 124)).toBe('3.2 min');
  });

  it('says nothing when there is nothing to say', () => {
    expect(secondsToDay(0, 10, 0), 'a paused world has no rate').toBeNull();
    expect(secondsToDay(30_000, 10, 124), 'day 10 is already behind us').toBeNull();
    expect(paceSummary(0, 0)).toBeNull();
  });

  it('quotes the next landmark day, not a fixed one', () => {
    expect(paceSummary(0, 124)).toContain('day 10 in');
    expect(paceSummary(12 * TICKS_PER_DAY, 124)).toContain('day 20 in');
    expect(paceSummary(60 * TICKS_PER_DAY, 124)).toContain('day 100 in');
  });

  it('scales its units to how long it actually is', () => {
    expect(humanDuration(45)).toBe('45 s');
    expect(humanDuration(200)).toBe('3.3 min');
    expect(humanDuration(3_600)).toBe('60 min');
    expect(humanDuration(9_000)).toBe('2.5 h');
  });
});
