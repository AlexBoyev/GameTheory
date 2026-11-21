import { describe, expect, it } from 'vitest';

import { BACKOFF_BASE_MS, BACKOFF_MAX_MS, backoffDelay } from '@/api/ws';

describe('backoffDelay', () => {
  it('grows exponentially from the base delay', () => {
    const noJitter = () => 0.5;
    expect(backoffDelay(0, noJitter)).toBe(BACKOFF_BASE_MS);
    expect(backoffDelay(1, noJitter)).toBe(BACKOFF_BASE_MS * 2);
    expect(backoffDelay(3, noJitter)).toBe(BACKOFF_BASE_MS * 8);
  });

  it('caps so a dead backend is retried once every ten seconds, not faster', () => {
    expect(backoffDelay(50, () => 0.5)).toBe(BACKOFF_MAX_MS);
  });

  it('never returns less than the base delay, even with full negative jitter', () => {
    for (let attempt = 0; attempt < 12; attempt += 1) {
      expect(backoffDelay(attempt, () => 0)).toBeGreaterThanOrEqual(BACKOFF_BASE_MS);
    }
  });

  it('applies jitter so reconnecting tabs do not stampede', () => {
    const low = backoffDelay(5, () => 0);
    const high = backoffDelay(5, () => 1);
    expect(low).toBeLessThan(high);
  });
});
