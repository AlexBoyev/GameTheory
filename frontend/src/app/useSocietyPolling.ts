/**
 * Polls the slow-moving half of the world.
 *
 * Split by cadence rather than by endpoint: huts and tribes change every few
 * sim-minutes, the trust graph is expensive to build and only matters when
 * its overlay is on, and metrics only gain a point every hundred ticks.
 * Polling each at its own rate keeps all of it off the frame budget.
 */

import { useEffect } from 'react';

import { api } from '@/api/rest';
import { useSocietyStore } from '@/state/societyStore';
import { useSimStore } from '@/state/simStore';
import { useUiStore } from '@/state/uiStore';

const SLOW_MS = 2000;
const TRUST_MS = 1500;
const METRICS_MS = 3000;
const LLM_MS = 4000;

/** Run `task` every `interval` ms until unmounted, skipping failures. */
function usePoll(task: () => Promise<void>, interval: number, enabled: boolean): void {
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const tick = async (): Promise<void> => {
      try {
        await task();
      } catch {
        // A failed poll is not worth surfacing; the connection banner covers
        // a genuinely dead backend.
      }
      if (!cancelled) timer = setTimeout(() => void tick(), interval);
    };

    timer = setTimeout(() => void tick(), interval);
    return () => {
      cancelled = true;
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [task, interval, enabled]);
}

export function useSocietyPolling(): void {
  const worldEpoch = useSimStore((state) => state.worldEpoch);
  const showTrust = useUiStore((state) => state.showTrustLines);
  const showTerritories = useUiStore((state) => state.showTerritories);
  const chartsOpen = useUiStore((state) => state.chartsOpen);

  // A new world invalidates everything we knew about the society.
  useEffect(() => {
    useSocietyStore.getState().reset();
  }, [worldEpoch]);

  usePoll(
    async () => {
      const [tribes, shelters] = await Promise.all([api.tribes(), api.shelters()]);
      useSocietyStore.getState().setTribes(tribes);
      useSocietyStore.getState().setShelters(shelters);
    },
    SLOW_MS,
    true,
  );

  usePoll(
    async () => {
      const graph = await api.trustGraph();
      useSocietyStore.getState().setTrust(graph.edges ?? [], graph.total ?? 0);
    },
    TRUST_MS,
    showTrust || showTerritories,
  );

  usePoll(
    async () => {
      const metrics = await api.metrics();
      useSocietyStore.getState().setMetrics(metrics.points ?? []);
    },
    METRICS_MS,
    chartsOpen,
  );

  // Always polled, panel open or not: an unreachable model is something the
  // user needs told, and it is one small request every four seconds.
  usePoll(
    async () => {
      useSocietyStore.getState().setLlm(await api.llmStatus());
    },
    LLM_MS,
    true,
  );
}
