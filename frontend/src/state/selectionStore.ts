/** What the observer is looking at: hover, selection and where to fly. */

import { create } from 'zustand';

export interface FlyRequest {
  x: number;
  z: number;
}

export interface SelectionStoreState {
  selectedAgentId: number | null;
  hoveredAgentId: number | null;
  following: boolean;
  /** Set to ask the camera to fly somewhere; the rig clears it when it starts. */
  flyTarget: FlyRequest | null;

  select: (agentId: number | null) => void;
  hover: (agentId: number | null) => void;
  setFollowing: (following: boolean) => void;
  /** Follow the selection; with nobody selected this does nothing. */
  toggleFollow: () => void;
  requestFly: (x: number, z: number) => void;
  consumeFly: () => void;
  clear: () => void;
}

export const useSelectionStore = create<SelectionStoreState>((set, get) => ({
  selectedAgentId: null,
  hoveredAgentId: null,
  following: false,
  flyTarget: null,

  select: (agentId) =>
    set({ selectedAgentId: agentId, following: agentId === null ? false : get().following }),
  hover: (agentId) => set({ hoveredAgentId: agentId }),
  setFollowing: (following) => set({ following: following && get().selectedAgentId !== null }),
  toggleFollow: () => set({ following: get().selectedAgentId !== null && !get().following }),
  requestFly: (x, z) => set({ flyTarget: { x, z } }),
  consumeFly: () => set({ flyTarget: null }),
  clear: () => set({ selectedAgentId: null, hoveredAgentId: null, following: false }),
}));
