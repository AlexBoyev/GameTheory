/**
 * Every simulation control the UI can invoke, in one hook.
 *
 * The REST call is the source of truth: each one returns the new state, which
 * is written straight into the store so a button press is reflected before the
 * next frame arrives.
 */

import { useCallback } from 'react';

import { api } from '@/api/rest';
import type { SimState, WorldConfig } from '@/api/types';
import { useSimStore } from '@/state/simStore';

export const SPEED_PRESETS = [1, 2, 5, 10, 25, 50, -1] as const;

export function speedLabel(speed: number): string {
  return speed < 0 ? 'MAX' : `${speed}x`;
}

export interface SimControls {
  play: () => Promise<void>;
  pause: () => Promise<void>;
  toggle: () => Promise<void>;
  step: (n?: number) => Promise<void>;
  setSpeed: (multiplier: number) => Promise<void>;
  reset: (options: { seed?: number; config?: WorldConfig; preset?: string }) => Promise<void>;
}

export function useSimControls(): SimControls {
  const status = useSimStore((state) => state.status);

  const apply = useCallback((next: SimState) => {
    useSimStore.setState({
      status: next.status,
      speed: next.speed,
      tick: next.tick,
      seed: next.seed,
      population: next.population,
      day: next.day,
      season: next.season,
    });
  }, []);

  const play = useCallback(async () => apply(await api.start()), [apply]);
  const pause = useCallback(async () => apply(await api.pause()), [apply]);

  return {
    play,
    pause,
    toggle: useCallback(async () => {
      await (status === 'running' ? pause() : play());
    }, [status, pause, play]),
    step: useCallback(async (n = 1) => apply(await api.step(n)), [apply]),
    setSpeed: useCallback(
      async (multiplier: number) => apply(await api.setSpeed(multiplier)),
      [apply],
    ),
    reset: useCallback(
      async (options: { seed?: number; config?: WorldConfig; preset?: string }) =>
        apply(await api.reset(options)),
      [apply],
    ),
  };
}
