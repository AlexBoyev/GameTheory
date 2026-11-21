/**
 * All the 2D furniture, laid out around the canvas.
 *
 * Panels sit in a non-interactive overlay and opt back into pointer events
 * themselves, so the island stays draggable everywhere they are not.
 */

import { ChartsPanel } from '@/ui/ChartsPanel';
import { ControlBar } from '@/ui/ControlBar';
import { EventFeed } from '@/ui/EventFeed';
import { HelpOverlay } from '@/ui/HelpOverlay';
import { HoverTooltip } from '@/ui/HoverTooltip';
import { Inspector } from '@/ui/Inspector';
import { OverlayBar } from '@/ui/OverlayBar';
import { TopBar } from '@/ui/TopBar';
import { useSimStore } from '@/state/simStore';
import { useUiStore } from '@/state/uiStore';

/** Where the API lives, for the copy-pasteable examples in the help panel. */
function backendOrigin(): string {
  const configured: unknown = import.meta.env.VITE_BACKEND_URL;
  if (typeof configured === 'string' && configured.length > 0) return configured;
  return window.location.origin;
}

function ConnectionNotice(): React.ReactElement | null {
  const connection = useSimStore((state) => state.connection);
  const frames = useSimStore((state) => state.framesReceived);

  if (connection === 'open' && frames > 0) return null;

  const message =
    connection === 'open'
      ? 'Connected - waiting for the first frame...'
      : connection === 'reconnecting'
        ? 'Lost the backend. Reconnecting...'
        : connection === 'closed'
          ? 'Disconnected.'
          : 'Connecting to the simulation...';

  return (
    <div className="pointer-events-none absolute inset-x-0 top-24 z-20 flex justify-center">
      <div className="rounded-full bg-slate-900/85 px-4 py-2 text-xs text-slate-300 ring-1 ring-white/10 backdrop-blur">
        {message}
        {connection !== 'open' && (
          <span className="ml-2 text-slate-500">is the backend running?</span>
        )}
      </div>
    </div>
  );
}

export function Hud(): React.ReactElement {
  const helpOpen = useUiStore((state) => state.helpOpen);
  const feedOpen = useUiStore((state) => state.eventFeedOpen);
  const chartsOpen = useUiStore((state) => state.chartsOpen);
  const setHelp = useUiStore((state) => state.set);

  return (
    <div className="pointer-events-none absolute inset-0">
      <TopBar />
      <ConnectionNotice />

      {/* Side panels: log on the left, inspector on the right. */}
      <div className="absolute inset-x-0 top-20 bottom-20 flex items-start justify-between px-3">
        <div className="pointer-events-none flex flex-col gap-3">
          {feedOpen && <EventFeed />}
          {chartsOpen && <ChartsPanel />}
        </div>
        <div className="pointer-events-none flex items-start gap-3">
          <Inspector />
          <OverlayBar />
        </div>
      </div>

      <ControlBar />
      <HoverTooltip />

      {helpOpen && (
        <HelpOverlay onClose={() => setHelp('helpOpen', false)} backendOrigin={backendOrigin()} />
      )}
    </div>
  );
}
