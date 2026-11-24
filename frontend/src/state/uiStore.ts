/** Panel visibility and scene overlays (SPEC 9.3, 9.4). */

import { create } from 'zustand';

/**
 * Whether to show the front screen, decided before the store exists.
 *
 * Read here rather than in a `useEffect` because the menu pauses the world
 * when it opens: applying `?menu=0` a tick later would pause and immediately
 * unpause, which a deep link or a screenshot run should never do.
 */
function menuWanted(): boolean {
  if (typeof window === 'undefined') return true;
  return new URLSearchParams(window.location.search).get('menu') !== '0';
}

export interface UiStoreState {
  chartsOpen: boolean;
  eventFeedOpen: boolean;
  llmPanelOpen: boolean;
  godPanelOpen: boolean;
  minimapOpen: boolean;
  helpOpen: boolean;
  resetOpen: boolean;
  /** The front screen. Open on arrival; Escape brings it back. */
  menuOpen: boolean;
  /** False until the first Start, which is what makes the button say Resume. */
  started: boolean;

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
  godPanelOpen: false,
  // On by default: it is the only way to see the whole island at once.
  minimapOpen: true,
  helpOpen: false,
  resetOpen: false,
  menuOpen: menuWanted(),
  started: !menuWanted(),

  showTrustLines: false,
  showTerritories: false,
  showHeatmap: false,
  showNames: false,
  showSpeechBubbles: true,

  toggle: (key) => set((state) => ({ [key]: !state[key] })),
  set: (key, value) => set({ [key]: value }),
}));
