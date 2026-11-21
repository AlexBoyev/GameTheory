/**
 * Tribes, huts, the trust graph and the metrics series.
 *
 * All of it is polled rather than streamed. These things change on the scale
 * of sim-minutes - a tribe forms, a hut goes up, a chart gains a point - so
 * putting them in a 20 Hz frame would be almost entirely repetition.
 */

import { create } from 'zustand';

import type { MetricPoint, Shelter, Tribe, TrustEdge } from '@/api/types';

export interface SocietyStoreState {
  tribes: Tribe[];
  shelters: Shelter[];
  trustEdges: TrustEdge[];
  /** Edges above the threshold before truncation, so the UI can say "of N". */
  trustTotal: number;
  metrics: MetricPoint[];

  setTribes: (tribes: Tribe[]) => void;
  setShelters: (shelters: Shelter[]) => void;
  setTrust: (edges: TrustEdge[], total: number) => void;
  setMetrics: (points: MetricPoint[]) => void;
  tribeById: (id: number | null | undefined) => Tribe | undefined;
  reset: () => void;
}

export const useSocietyStore = create<SocietyStoreState>((set, get) => ({
  tribes: [],
  shelters: [],
  trustEdges: [],
  trustTotal: 0,
  metrics: [],

  setTribes: (tribes) => set({ tribes }),
  setShelters: (shelters) => set({ shelters }),
  setTrust: (trustEdges, trustTotal) => set({ trustEdges, trustTotal }),
  setMetrics: (metrics) => set({ metrics }),
  tribeById: (id) =>
    id === null || id === undefined ? undefined : get().tribes.find((tribe) => tribe.id === id),
  reset: () => set({ tribes: [], shelters: [], trustEdges: [], trustTotal: 0, metrics: [] }),
}));
