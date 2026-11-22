import { describe, expect, it } from 'vitest';

import { screenshotName } from '@/lib/screenshot';

describe('screenshot names', () => {
  const when = new Date('2026-11-22T17:45:09.123Z');

  it('sorts chronologically and says which tick it caught', () => {
    expect(screenshotName(4210, when)).toBe('gametheory-2026-11-22T17-45-09-tick4210.png');
  });

  it('contains nothing a filesystem would object to', () => {
    expect(screenshotName(1, when)).not.toMatch(/[:*?"<>|]/);
  });

  it('orders by name the way it orders by time', () => {
    const earlier = screenshotName(1, new Date('2026-11-22T10:00:00Z'));
    const later = screenshotName(1, new Date('2026-11-22T11:00:00Z'));

    expect([later, earlier].sort()).toEqual([earlier, later]);
  });
});
