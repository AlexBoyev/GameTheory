/**
 * Overlay toggles, as buttons rather than keys you have to know about.
 *
 * Toggles that need data the simulation does not produce yet are shown
 * disabled with the phase that turns them on, rather than hidden (which makes
 * the roadmap invisible) or live but inert (which makes the UI feel broken).
 */

import { useUiStore, type ToggleKey } from '@/state/uiStore';

interface OverlayToggle {
  key: ToggleKey;
  label: string;
  icon: string;
  shortcut: string;
  /** Set when the overlay has nothing to draw yet. */
  needsPhase?: number;
}

const TOGGLES: OverlayToggle[] = [
  { key: 'showTrustLines', label: 'Trust lines', icon: '🔗', shortcut: 't' },
  { key: 'showTerritories', label: 'Territories', icon: '🏕️', shortcut: 'g' },
  { key: 'chartsOpen', label: 'Charts', icon: '📈', shortcut: 'c' },
  { key: 'showHeatmap', label: 'Heatmap', icon: '🔥', shortcut: 'h', needsPhase: 6 },
  { key: 'showNames', label: 'Names', icon: '🏷️', shortcut: 'n', needsPhase: 6 },
  { key: 'showSpeechBubbles', label: 'Speech', icon: '💬', shortcut: 'b' },
  { key: 'llmPanelOpen', label: 'LLM minds', icon: '🧠', shortcut: 'm' },
  { key: 'godPanelOpen', label: 'God tools', icon: '⚡', shortcut: 'k' },
  { key: 'minimapOpen', label: 'Minimap', icon: '🗺️', shortcut: 'o' },
];

export function OverlayBar(): React.ReactElement {
  const state = useUiStore();
  const toggle = useUiStore((store) => store.toggle);

  return (
    <div className="pointer-events-auto flex flex-col gap-1 rounded-2xl bg-slate-900/85 p-1.5 shadow-lg ring-1 ring-white/10 backdrop-blur">
      <span className="px-1 pt-0.5 text-[9px] uppercase tracking-wider text-slate-500">
        Overlays
      </span>
      {TOGGLES.map((entry) => {
        const active = state[entry.key];
        const pending = entry.needsPhase !== undefined;
        const title = pending
          ? `${entry.label} (${entry.shortcut}) - needs Phase ${entry.needsPhase} data`
          : `${entry.label} (${entry.shortcut})`;

        return (
          <button
            key={entry.key}
            type="button"
            title={title}
            disabled={pending}
            onClick={() => toggle(entry.key)}
            className={`flex items-center gap-1.5 rounded-lg px-2 py-1 text-left text-[11px] transition disabled:cursor-not-allowed disabled:opacity-35 ${
              active && !pending
                ? 'bg-emerald-500/90 text-slate-900'
                : 'text-slate-300 hover:bg-white/10'
            }`}
          >
            <span className="w-4 text-center">{entry.icon}</span>
            <span className="flex-1">{entry.label}</span>
            <kbd className="rounded bg-white/10 px-1 font-mono text-[9px] text-slate-400">
              {entry.shortcut}
            </kbd>
          </button>
        );
      })}
      <button
        type="button"
        title="What am I watching? (?)"
        onClick={() => toggle('helpOpen')}
        className="flex items-center gap-1.5 rounded-lg bg-sky-500/20 px-2 py-1 text-left text-[11px] text-sky-200 transition hover:bg-sky-500/35"
      >
        <span className="w-4 text-center">?</span>
        <span className="flex-1">Help</span>
        <kbd className="rounded bg-white/10 px-1 font-mono text-[9px] text-sky-300">?</kbd>
      </button>
    </div>
  );
}
