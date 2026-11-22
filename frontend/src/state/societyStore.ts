/**
 * Tribes, huts, the trust graph and the metrics series.
 *
 * All of it is polled rather than streamed. These things change on the scale
 * of sim-minutes - a tribe forms, a hut goes up, a chart gains a point - so
 * putting them in a 20 Hz frame would be almost entirely repetition.
 */

import { create } from 'zustand';

import type { AgentSummary, LlmStatus, MetricPoint, Shelter, Tribe, TrustEdge } from '@/api/types';

export interface SocietyStoreState {
  tribes: Tribe[];
  shelters: Shelter[];
  trustEdges: TrustEdge[];
  /** Edges above the threshold before truncation, so the UI can say "of N". */
  trustTotal: number;
  metrics: MetricPoint[];
  /**
   * Last known state of the deliberative layer, or null before the first poll.
   *
   * Lives here rather than in the LLM panel so the warning banner does not
   * depend on that panel being open - the whole point of it is to be seen
   * when you have not gone looking.
   */
  llm: LlmStatus | null;
  /**
   * `agent id -> name`, for the name-tag overlay.
   *
   * Frames carry ids and nothing else - a name per agent per frame would be
   * most of the payload - so the names are polled separately and slowly.
   * Names never change, so a stale entry is only ever a missing one.
   */
  names: Map<number, string>;

  setTribes: (tribes: Tribe[]) => void;
  setShelters: (shelters: Shelter[]) => void;
  setTrust: (edges: TrustEdge[], total: number) => void;
  setMetrics: (points: MetricPoint[]) => void;
  setLlm: (status: LlmStatus) => void;
  setNames: (agents: AgentSummary[]) => void;
  tribeById: (id: number | null | undefined) => Tribe | undefined;
  reset: () => void;
}

export const useSocietyStore = create<SocietyStoreState>((set, get) => ({
  tribes: [],
  shelters: [],
  trustEdges: [],
  trustTotal: 0,
  metrics: [],
  llm: null,
  names: new Map<number, string>(),

  setTribes: (tribes) => set({ tribes }),
  setShelters: (shelters) => set({ shelters }),
  setTrust: (trustEdges, trustTotal) => set({ trustEdges, trustTotal }),
  setMetrics: (metrics) => set({ metrics }),
  setLlm: (llm) => set({ llm }),
  setNames: (agents) =>
    set({ names: new Map(agents.map((agent) => [agent.id, agent.name])) }),
  tribeById: (id) =>
    id === null || id === undefined ? undefined : get().tribes.find((tribe) => tribe.id === id),
  // `llm` is deliberately kept: the provider does not change because the
  // world was rebuilt.
  reset: () =>
    set({
      tribes: [],
      shelters: [],
      trustEdges: [],
      trustTotal: 0,
      metrics: [],
      names: new Map<number, string>(),
    }),
}));
