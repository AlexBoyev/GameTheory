/**
 * All the 2D furniture, laid out around the canvas.
 *
 * Panels sit in a non-interactive overlay and opt back into pointer events
 * themselves, so the island stays draggable everywhere they are not.
 */

import { ChartsPanel } from '@/ui/ChartsPanel';
import { ControlBar } from '@/ui/ControlBar';
import { EventFeed } from '@/ui/EventFeed';
import { GodPanel } from '@/ui/GodPanel';
import { HelpOverlay } from '@/ui/HelpOverlay';
import { HoverTooltip } from '@/ui/HoverTooltip';
import { Inspector } from '@/ui/Inspector';
import { Minimap } from '@/ui/Minimap';
import { LlmPanel } from '@/ui/LlmPanel';
import { OverlayBar } from '@/ui/OverlayBar';
import { TopBar } from '@/ui/TopBar';
import { TournamentPanel } from '@/ui/TournamentPanel';
import { useSimStore } from '@/state/simStore';
import { useSocietyStore } from '@/state/societyStore';
import { useUiStore } from '@/state/uiStore';

/** Where the API lives, for the copy-pasteable examples in the help panel. */
function backendOrigin(): string {
  const configured: unknown = import.meta.env.VITE_BACKEND_URL;
  if (typeof configured === 'string' && configured.length > 0) return configured;
  return window.location.origin;
}

function LlmNotice(): React.ReactElement | null {
  const llm = useSocietyStore((state) => state.llm);
  const open = useUiStore((state) => state.set);

  // Nothing to warn about when the mock is serving: that is the documented
  // default, and the LLM panel explains it in full.
  if (!llm || !llm.enabled || llm.provider === 'mock') return null;
  if (!llm.circuit_open && llm.reachable !== false) return null;

  const message = llm.circuit_open
    ? `${llm.provider} failed repeatedly - deliberation is paused`
    : `${llm.provider} is not reachable at its configured URL`;

  return (
    <div className="pointer-events-none absolute inset-x-0 top-14 z-20 flex justify-center">
      <button
        type="button"
        onClick={() => open('llmPanelOpen', true)}
        className="pointer-events-auto rounded-full bg-rose-500/20 px-4 py-1.5 text-xs text-rose-100 ring-1 ring-rose-400/40 backdrop-blur transition hover:bg-rose-500/30"
      >
        {message}
        <span className="ml-2 text-rose-200/70">
          agents are still acting on utility AI - details
        </span>
      </button>
    </div>
  );
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
  const llmOpen = useUiStore((state) => state.llmPanelOpen);
  const godOpen = useUiStore((state) => state.godPanelOpen);
  const minimapOpen = useUiStore((state) => state.minimapOpen);
  const setHelp = useUiStore((state) => state.set);

  return (
    <div className="pointer-events-none absolute inset-0">
      <TopBar />
      <ConnectionNotice />
      <LlmNotice />

      {/* Side panels: log on the left, inspector on the right. */}
      <div className="absolute inset-x-0 top-20 bottom-20 flex items-start justify-between px-3">
        <div className="pointer-events-none flex flex-col gap-3">
          {feedOpen && <EventFeed />}
          {chartsOpen && <ChartsPanel />}
          {llmOpen && <LlmPanel />}
          {godOpen && <GodPanel />}
          <TournamentPanel />
        </div>
        <div className="pointer-events-none flex items-start gap-3">
          <Inspector />
          <div className="pointer-events-none flex flex-col items-end gap-3">
            <OverlayBar />
            {minimapOpen && <Minimap />}
          </div>
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
