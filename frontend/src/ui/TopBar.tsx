/**
 * The always-visible status strip: are we connected, what time is it in the
 * simulation, and where are the panels.
 */

import type { ConnectionStatus } from '@/api/types';
import { useSimStore } from '@/state/simStore';
import { useUiStore } from '@/state/uiStore';

const STATUS_STYLE: Record<ConnectionStatus, { dot: string; label: string }> = {
  idle: { dot: 'bg-slate-400', label: 'idle' },
  connecting: { dot: 'bg-amber-400 animate-pulse', label: 'connecting' },
  open: { dot: 'bg-emerald-400', label: 'live' },
  reconnecting: { dot: 'bg-amber-500 animate-pulse', label: 'reconnecting' },
  closed: { dot: 'bg-rose-500', label: 'disconnected' },
};

function Stat({ label, value }: { label: string; value: string }): React.ReactElement {
  return (
    <div className="flex flex-col leading-tight">
      <span className="text-[10px] uppercase tracking-wider text-slate-400">{label}</span>
      <span className="font-mono text-sm tabular-nums text-slate-100">{value}</span>
    </div>
  );
}

function formatClock(timeOfDay: number): string {
  const totalMinutes = Math.floor(timeOfDay * 24 * 60);
  const hours = String(Math.floor(totalMinutes / 60)).padStart(2, '0');
  const minutes = String(totalMinutes % 60).padStart(2, '0');
  return `${hours}:${minutes}`;
}

function formatSpeed(speed: number, status: string): string {
  if (status === 'paused') return 'paused';
  return speed < 0 ? 'MAX' : `${speed}x`;
}

export function TopBar(): React.ReactElement {
  const connection = useSimStore((state) => state.connection);
  const tick = useSimStore((state) => state.tick);
  const status = useSimStore((state) => state.status);
  const speed = useSimStore((state) => state.speed);
  const day = useSimStore((state) => state.day);
  const season = useSimStore((state) => state.season);
  const timeOfDay = useSimStore((state) => state.timeOfDay);
  const isNight = useSimStore((state) => state.isNight);
  const population = useSimStore((state) => state.population);
  const seed = useSimStore((state) => state.seed);

  const feedOpen = useUiStore((state) => state.eventFeedOpen);
  const toggle = useUiStore((state) => state.toggle);

  const indicator = STATUS_STYLE[connection];

  return (
    <header className="pointer-events-none absolute inset-x-0 top-0 z-10 flex justify-center p-3">
      <div className="pointer-events-auto flex flex-wrap items-center gap-4 rounded-2xl bg-slate-900/85 px-4 py-2.5 shadow-lg ring-1 ring-white/10 backdrop-blur">
        <div className="flex items-center gap-2">
          <span className={`h-2.5 w-2.5 rounded-full ${indicator.dot}`} />
          <span className="text-sm font-medium text-slate-200">Game Theory</span>
          <span className="text-xs text-slate-400">{indicator.label}</span>
        </div>

        <div className="h-6 w-px bg-white/10" />

        <Stat label="tick" value={tick.toLocaleString()} />
        <Stat label="speed" value={formatSpeed(speed, status)} />
        <Stat label="day" value={`${day + 1} · ${season}`} />
        <Stat label="clock" value={`${formatClock(timeOfDay)}${isNight ? ' 🌙' : ' ☀'}`} />
        <Stat label="agents" value={String(population)} />
        <Stat label="seed" value={String(seed)} />

        <div className="h-6 w-px bg-white/10" />

        <button
          type="button"
          onClick={() => toggle('eventFeedOpen')}
          title="Event log"
          className={`rounded-lg px-2 py-1.5 text-xs transition ${
            feedOpen ? 'bg-white/20 text-slate-100' : 'text-slate-400 hover:bg-white/10'
          }`}
        >
          📜 Log
        </button>
        <button
          type="button"
          onClick={() => toggle('helpOpen')}
          title="What am I watching? (?)"
          className="rounded-lg bg-sky-500/20 px-2 py-1.5 text-xs text-sky-200 transition hover:bg-sky-500/35"
        >
          ? Help
        </button>
      </div>
    </header>
  );
}
