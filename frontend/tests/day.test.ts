import { beforeEach, describe, expect, it } from 'vitest';

import type { DayData, Envelope } from '@/api/types';
import { useSimStore } from '@/state/simStore';

function dayEnvelope(day: number, headline = 'War: 1 declaration between tribes'): Envelope {
  const data: DayData = {
    day,
    season: 'spring',
    headline,
    lines: ['156 fights, 625 rumours, 12 trades', '118 alive (-2 overnight)'],
    counts: { combat: 156, gossip: 625 },
  };
  return { type: 'day', tick: day * 2400, data: data as unknown as Record<string, unknown> };
}

function frame(tick: number, skip: number): Envelope {
  return {
    type: 'frame',
    tick,
    data: {
      stride: 7,
      agents: [],
      tod: 0.5,
      status: 'paused',
      speed: 1,
      day: 0,
      season: 'spring',
      skip,
    },
  };
}

describe('the day card', () => {
  beforeEach(() => {
    useSimStore.setState({ dayReport: null, skipRemaining: 0 });
  });

  it('is held until something takes it down', () => {
    useSimStore.getState().ingest(dayEnvelope(3));

    const report = useSimStore.getState().dayReport;
    expect(report?.day).toBe(3);
    expect(report?.headline).toContain('War');

    useSimStore.getState().dismissDay();
    expect(useSimStore.getState().dayReport).toBeNull();
  });

  it('is replaced by the newer day rather than queued behind it', () => {
    // At MAX speed a day lands every fifteen seconds, which is faster than
    // a card's ten-second life if they stacked. The newest is the true one.
    useSimStore.getState().ingest(dayEnvelope(3));
    useSimStore.getState().ingest(dayEnvelope(4, '2 chiefs overthrown'));

    expect(useSimStore.getState().dayReport?.day).toBe(4);
    expect(useSimStore.getState().dayReport?.headline).toContain('chiefs');
  });
});

describe('skip progress', () => {
  beforeEach(() => {
    useSimStore.setState({ skipRemaining: 0 });
  });

  it('comes off the frame stream, not just the one-second poll', () => {
    // A day-long skip takes tens of seconds; a bar that moves once a second
    // reads as stuck. Frames arrive twenty times a second.
    useSimStore.getState().ingest(frame(100, 2300));
    expect(useSimStore.getState().skipRemaining).toBe(2300);

    useSimStore.getState().ingest(frame(2400, 0));
    expect(useSimStore.getState().skipRemaining).toBe(0);
  });

  it('treats a frame with no skip field as no skip in progress', () => {
    useSimStore.setState({ skipRemaining: 500 });
    const stale: Envelope = {
      type: 'frame',
      tick: 1,
      data: {
        stride: 7,
        agents: [],
        tod: 0.5,
        status: 'running',
        speed: 1,
        day: 0,
        season: 'spring',
      },
    };

    useSimStore.getState().ingest(stale);

    expect(useSimStore.getState().skipRemaining).toBe(0);
  });
});
