/**
 * Render quality and viewer preferences.
 *
 * Quality is one dial that drives several knobs at once (shadows,
 * postprocessing, pixel ratio) so "it runs badly" has a single fix.
 */

import { create } from 'zustand';

export type Quality = 'low' | 'med' | 'high';

export interface QualityProfile {
  shadows: boolean;
  postprocessing: boolean;
  /** `[min, max]` device pixel ratio handed to the R3F canvas. */
  dpr: [number, number];
  /** Max agents drawn with full detail; the rest fall back to simple bodies. */
  detailedAgents: number;
}

export const QUALITY_PROFILES: Record<Quality, QualityProfile> = {
  low: { shadows: false, postprocessing: false, dpr: [0.75, 1], detailedAgents: 0 },
  med: { shadows: true, postprocessing: false, dpr: [1, 1.5], detailedAgents: 200 },
  high: { shadows: true, postprocessing: true, dpr: [1, 2], detailedAgents: 1000 },
};

export interface SettingsStoreState {
  quality: Quality;
  showFps: boolean;
  setQuality: (quality: Quality) => void;
  toggleFps: () => void;
  profile: () => QualityProfile;
}

export const useSettingsStore = create<SettingsStoreState>((set, get) => ({
  quality: 'med',
  showFps: true,
  setQuality: (quality) => set({ quality }),
  toggleFps: () => set({ showFps: !get().showFps }),
  profile: () => QUALITY_PROFILES[get().quality],
}));
