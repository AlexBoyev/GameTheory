/** Panel visibility and scene overlays (SPEC 9.3, 9.4). */

import { create } from 'zustand';

export interface UiStoreState {
  chartsOpen: boolean;
  eventFeedOpen: boolean;
  llmPanelOpen: boolean;
  helpOpen: boolean;
  resetOpen: boolean;

  showTrustLines: boolean;
  showTerritories: boolean;
  showHeatmap: boolean;
  showNames: boolean;
  showSpeechBubbles: boolean;

  toggle: (key: ToggleKey) => void;
  set: (key: ToggleKey, value: boolean) => void;
}

export type ToggleKey = {
  [K in keyof UiStoreState]: UiStoreState[K] extends boolean ? K : never;
}[keyof UiStoreState];

export const useUiStore = create<UiStoreState>((set) => ({
  chartsOpen: false,
  // Open by default: a simulation you cannot read is just a screensaver.
  eventFeedOpen: true,
  llmPanelOpen: false,
  helpOpen: false,
  resetOpen: false,

  showTrustLines: false,
  showTerritories: false,
  showHeatmap: false,
  showNames: false,
  showSpeechBubbles: true,

  toggle: (key) => set((state) => ({ [key]: !state[key] })),
  set: (key, value) => set({ [key]: value }),
}));
