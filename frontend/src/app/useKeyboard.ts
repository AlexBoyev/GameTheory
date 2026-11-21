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
        case 'stopFollow':
          event.preventDefault();
          if (useUiStore.getState().helpOpen) useUiStore.getState().set('helpOpen', false);
          else if (useUiStore.getState().resetOpen) useUiStore.getState().set('resetOpen', false);
          else if (useSelectionStore.getState().following)
            useSelectionStore.getState().setFollowing(false);
          else useSelectionStore.getState().clear();
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
