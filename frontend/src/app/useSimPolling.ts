/**
 * Keeps the UI honest about state it cannot infer from frames.
 *
 * Two reasons this exists rather than reading everything off the socket:
 *
 * * the measured tick rate lives on `GET /api/sim/state`, not in a frame;
 * * the simulation can be driven from outside this tab - `curl`, the Swagger
 *   page at `/docs`, a second browser window - and the controls should show
 *   what the engine is actually doing, not what this tab last asked for.
 */

import { useEffect } from 'react';

import { api } from '@/api/rest';
import { useSimStore } from '@/state/simStore';

const POLL_MS = 1000;

export function useSimPolling(enabled = true): void {
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const poll = async (): Promise<void> => {
      try {
        const state = await api.getState();
        if (!cancelled) {
          useSimStore.setState({
            status: state.status,
            speed: state.speed,
            ticksPerSecond: state.ticks_per_second,
            isNight: state.is_night,
            seed: state.seed,
            population: state.population,
          });
        }
      } catch {
        // The connection banner already reports a dead backend.
      }
      if (!cancelled) timer = setTimeout(() => void poll(), POLL_MS);
    };

    void poll();
    return () => {
      cancelled = true;
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [enabled]);
}
