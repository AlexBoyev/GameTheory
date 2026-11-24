/**
 * The URL is part of the UI.
 *
 * What you are looking at - the selected agent, which panels are open, the
 * speed - lives in the query string, so a link restores the view and `?speed=10`
 * starts a world already running. Applied once on load, then kept in sync with
 * `replaceState` so it never pollutes the back button.
 */

import { useEffect, useRef } from 'react';

import { useSimControls } from '@/app/useSimControls';
import { useSelectionStore } from '@/state/selectionStore';
import { useSimStore } from '@/state/simStore';
import { useUiStore } from '@/state/uiStore';

export function useUrlState(): void {
  const controls = useSimControls();
  const applied = useRef(false);

  const selectedAgentId = useSelectionStore((state) => state.selectedAgentId);
  const eventFeedOpen = useUiStore((state) => state.eventFeedOpen);
  const helpOpen = useUiStore((state) => state.helpOpen);
  const menuOpen = useUiStore((state) => state.menuOpen);
  const started = useUiStore((state) => state.started);
  const speed = useSimStore((state) => state.speed);
  const status = useSimStore((state) => state.status);

  // --- read, once
  useEffect(() => {
    if (applied.current) return;
    applied.current = true;

    const params = new URLSearchParams(window.location.search);

    const agent = params.get('agent');
    if (agent !== null && agent !== '' && Number.isFinite(Number(agent))) {
      useSelectionStore.getState().select(Number(agent));
      if (params.get('follow') === '1') useSelectionStore.getState().setFollowing(true);
    }

    const panels = (params.get('panels') ?? 'log').split(',');
    useUiStore.getState().set('eventFeedOpen', panels.includes('log'));
    if (params.get('help') === '1') useUiStore.getState().set('helpOpen', true);

    const requested = params.get('speed');
    if (requested !== null && Number.isFinite(Number(requested))) {
      // A link copied from a running world carries its speed and no
      // `paused`, so it should land running: the backend now boots paused
      // and waits to be asked, which would otherwise make every shared link
      // open on a frozen island.
      void controls.setSpeed(Number(requested)).then(() => controls.play());
    }
    if (params.get('paused') === '1') void controls.pause();
  }, [controls]);

  // --- write, on change
  useEffect(() => {
    if (!applied.current) return;
    const params = new URLSearchParams();

    if (selectedAgentId !== null) params.set('agent', String(selectedAgentId));
    const panels = eventFeedOpen ? ['log'] : [];
    if (panels.length > 0) params.set('panels', panels.join(','));
    if (helpOpen) params.set('help', '1');
    // A link copied from a running world should land in that world, not on
    // the front screen - the menu pauses, and a shared link that stops the
    // simulation is a worse link.
    if (started) params.set('menu', '0');
    if (status === 'paused' && !menuOpen) params.set('paused', '1');
    else params.set('speed', String(speed));

    const query = params.toString();
    window.history.replaceState(null, '', query ? `?${query}` : window.location.pathname);
  }, [selectedAgentId, eventFeedOpen, helpOpen, speed, status, started, menuOpen]);
}
