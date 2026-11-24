/**
 * Wires the keyboard map in `lib/keybindings.ts` to actual behaviour.
 *
 * The map is data so the help overlay and these handlers cannot disagree
 * about what a key does.
 */

import { useEffect } from 'react';

import { useSimControls } from '@/app/useSimControls';
import { actionForKey, type ActionId } from '@/lib/keybindings';
import { useSelectionStore } from '@/state/selectionStore';
import { useUiStore } from '@/state/uiStore';

const SPEED_FOR: Partial<Record<ActionId, number>> = {
  speed1: 1,
  speed2: 2,
  speed5: 5,
  speed10: 10,
  speed25: 25,
  speed50: 50,
  speedMax: -1,
};

const OVERLAY_FOR: Partial<
  Record<
    ActionId,
    'showTrustLines' | 'showTerritories' | 'showHeatmap' | 'showNames' | 'showSpeechBubbles'
  >
> = {
  toggleTrustLines: 'showTrustLines',
  toggleTerritories: 'showTerritories',
  toggleHeatmap: 'showHeatmap',
  toggleNames: 'showNames',
  toggleSpeech: 'showSpeechBubbles',
};

export function useKeyboard(): void {
  const controls = useSimControls();

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      // Typing in a field is not a shortcut.
      const target = event.target;
      if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;

      const action = actionForKey(event.key);
      if (action === null) return;

      const speed = SPEED_FOR[action];
      if (speed !== undefined) {
        event.preventDefault();
        void controls.setSpeed(speed);
        return;
      }

      const overlay = OVERLAY_FOR[action];
      if (overlay !== undefined) {
        event.preventDefault();
        useUiStore.getState().toggle(overlay);
        return;
      }

      switch (action) {
        case 'togglePlay':
          event.preventDefault();
          void controls.toggle();
          break;
        case 'step':
          event.preventDefault();
          void controls.step(1);
          break;
        case 'reset':
          event.preventDefault();
          useUiStore.getState().toggle('resetOpen');
          break;
        case 'followSelected':
          event.preventDefault();
          useSelectionStore.getState().toggleFollow();
          break;
        case 'escapeBack': {
          // One key, walking outwards: close what is on top, then let go of
          // the agent, then stop the world. Pressing it twice from anywhere
          // should always end up at the menu.
          event.preventDefault();
          const ui = useUiStore.getState();
          const selection = useSelectionStore.getState();
          if (ui.helpOpen) ui.set('helpOpen', false);
          else if (ui.resetOpen) ui.set('resetOpen', false);
          else if (ui.menuOpen) {
            ui.set('menuOpen', false);
            void controls.play();
          } else if (selection.following) selection.setFollowing(false);
          else if (selection.selectedAgentId !== null) selection.clear();
          else {
            ui.set('menuOpen', true);
            void controls.pause();
          }
          break;
        }
        case 'toggleCharts':
          event.preventDefault();
          useUiStore.getState().toggle('chartsOpen');
          break;
        case 'toggleLog':
          event.preventDefault();
          useUiStore.getState().toggle('eventFeedOpen');
          break;
        case 'toggleLlm':
          event.preventDefault();
          useUiStore.getState().toggle('llmPanelOpen');
          break;
        case 'toggleGod':
          event.preventDefault();
          useUiStore.getState().toggle('godPanelOpen');
          break;
        case 'toggleMinimap':
          event.preventDefault();
          useUiStore.getState().toggle('minimapOpen');
          break;
        case 'toggleHelp':
          event.preventDefault();
          useUiStore.getState().toggle('helpOpen');
          break;
        default:
          break;
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [controls]);
}
