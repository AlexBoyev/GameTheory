/**
 * Samples the event log at human speed instead of socket speed.
 *
 * The feed used to subscribe straight to the store, so every `events`
 * envelope re-rendered the whole list - twenty times a second at MAX speed,
 * with hundreds of rows. That cost the render loop everything: measured at
 * MAX, the canvas ran at 1 fps with the log open and 66 fps with it closed.
 *
 * Nobody can read a log that updates twenty times a second, so it is sampled
 * four times a second instead. The store keeps the full history for filters;
 * only the rendered slice is throttled.
 */

import { useEffect, useState } from 'react';

import type { EventItem } from '@/api/types';
import { useSimStore } from '@/state/simStore';

export const FEED_SAMPLE_MS = 250;

export function useThrottledEvents(limit: number): EventItem[] {
  const [rows, setRows] = useState<EventItem[]>([]);

  useEffect(() => {
    const sample = (): void => setRows(useSimStore.getState().events.slice(0, limit));
    const timer = setInterval(sample, FEED_SAMPLE_MS);
    return () => clearInterval(timer);
  }, [limit]);

  return rows;
}
