/**
 * New world: pick a preset, a seed, and the handful of dials worth touching.
 *
 * A preset is a set of overrides applied on top of the *default* config, so
 * "Tribal Wars, but 300 agents" is one request - which is why the sliders stay
 * live when a preset is selected rather than being replaced by it. Building on
 * defaults rather than on the running world matters: a bare reset rebuilds
 * from the current config, so inheriting it made the Axelrod preset a one-way
 * door with `tournament_mode` stuck on.
 *
 * Reset leaves the world paused at tick 0 so you can look at the island before
 * anything happens to it; "start immediately" is the usual choice.
 */

import { useEffect, useState } from 'react';

import { api } from '@/api/rest';
import type { Preset, WorldConfig } from '@/api/types';
import { useSimControls } from '@/app/useSimControls';
import { Button, Panel } from '@/ui/primitives';
import { useSimStore } from '@/state/simStore';

export interface ResetDialogProps {
  onClose: () => void;
}

interface Dial {
  key:
    | 'population'
    | 'scarcity'
    | 'age_years_per_day'
    | 'initial_tribes'
    | 'llm_agents'
    | 'mutation_rate';
  label: string;
  hint: string;
  min: number;
  max: number;
  step: number;
}

const DIALS: Dial[] = [
  {
    key: 'population',
    label: 'Population',
    hint: 'The island comfortably feeds a few hundred.',
    min: 10,
    max: 600,
    step: 10,
  },
  {
    key: 'scarcity',
    label: 'Scarcity',
    hint: 'Above 1 means fewer resources. Winter is harsher still.',
    min: 0.4,
    max: 3,
    step: 0.1,
  },
  {
    key: 'age_years_per_day',
    label: 'Ageing speed',
    hint: 'Years lived per day. 3 holds the population steady; 4 and above thins it.',
    min: 0.5,
    max: 8,
    step: 0.5,
  },
  {
    key: 'initial_tribes',
    label: 'Starting tribes',
    hint: 'Formed at build time, on contested ground. 0 lets them emerge.',
    min: 0,
    max: 8,
    step: 1,
  },
  {
    key: 'llm_agents',
    label: 'Deliberative agents',
    hint: 'They hold goals and speak. Works without a model installed.',
    min: 0,
    max: 16,
    step: 1,
  },
  {
    key: 'mutation_rate',
    label: 'Strategy mutation',
    hint: 'How often a child plays something its parents did not.',
    min: 0,
    max: 0.3,
    step: 0.01,
  },
];

export function ResetDialog({ onClose }: ResetDialogProps): React.ReactElement {
  const controls = useSimControls();
  const currentConfig = useSimStore((state) => state.config);
  const currentSeed = useSimStore((state) => state.seed);

  const [seed, setSeed] = useState(String(currentSeed));
  const [preset, setPreset] = useState<string | null>(null);
  const [autostart, setAutostart] = useState(true);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [defaults, setDefaults] = useState<WorldConfig | null>(null);
  const [busy, setBusy] = useState(false);
  const [dials, setDials] = useState<Record<Dial['key'], number>>({
    population: currentConfig?.population ?? 120,
    scarcity: currentConfig?.scarcity ?? 1,
    age_years_per_day: currentConfig?.age_years_per_day ?? 3,
    initial_tribes: currentConfig?.initial_tribes ?? 0,
    llm_agents: currentConfig?.llm_agents ?? 4,
    mutation_rate: currentConfig?.mutation_rate ?? 0.05,
  });

  useEffect(() => {
    void api
      .presets()
      .then(setPresets)
      .catch(() => setPresets([]));
    // The base a new world is built on. Not the *current* config: a bare
    // reset rebuilds from that, so picking Axelrod once would leave
    // `tournament_mode` on with no way back.
    void api
      .getDefaults()
      .then(setDefaults)
      .catch(() => setDefaults(null));
  }, []);

  const submit = async (): Promise<void> => {
    setBusy(true);
    try {
      // Always from defaults, never from the running world: a preset is
      // overrides on top of defaults, and inheriting the current config would
      // carry a previous preset's settings into the new world.
      const base = defaults ?? currentConfig;
      const config: WorldConfig | undefined = base ? { ...base, ...dials } : undefined;
      await controls.reset({
        seed: Number(seed) || 0,
        ...(config ? { config } : {}),
        ...(preset ? { preset } : {}),
      });
      if (autostart) await controls.play();
      onClose();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="pointer-events-auto absolute inset-0 z-30 flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm">
      <Panel
        title="New world"
        onClose={onClose}
        className="max-h-[calc(100vh-4rem)] w-full max-w-lg"
      >
        <div className="space-y-3 p-3">
          <div>
            <p className="mb-1 text-[10px] uppercase tracking-wide text-slate-400">Preset</p>
            <div className="grid grid-cols-2 gap-1">
              <PresetButton
                name="Default island"
                description="The dials below, and nothing else."
                active={preset === null}
                onClick={() => setPreset(null)}
              />
              {presets.map((entry) => (
                <PresetButton
                  key={entry.id}
                  name={entry.name}
                  description={entry.description}
                  active={preset === entry.id}
                  onClick={() => setPreset(entry.id)}
                />
              ))}
            </div>
            {preset !== null && (
              <p className="mt-1 text-[10px] text-amber-200/80">
                A preset overrides the dials it cares about; the rest stay as set below.
              </p>
            )}
          </div>

          <div>
            <p className="mb-1 text-[10px] uppercase tracking-wide text-slate-400">Seed</p>
            <div className="flex gap-2">
              <input
                value={seed}
                onChange={(event) => setSeed(event.target.value)}
                inputMode="numeric"
                aria-label="Seed"
                className="min-w-0 flex-1 rounded-lg bg-slate-800 px-2 py-1.5 font-mono text-xs text-slate-100 outline-none ring-1 ring-white/10 focus:ring-emerald-400/60"
              />
              <Button onClick={() => setSeed(String(Math.floor(Math.random() * 100000)))}>
                🎲
              </Button>
            </div>
            <p className="mt-1 text-[10px] text-slate-500">
              Same seed, same world - to the bit, with deliberative agents off.
            </p>
          </div>

          {DIALS.map((dial) => (
            <div key={dial.key}>
              <div className="flex items-baseline justify-between">
                <p className="text-[10px] uppercase tracking-wide text-slate-400">{dial.label}</p>
                <span className="font-mono text-[11px] tabular-nums text-slate-200">
                  {dial.step < 1 ? dials[dial.key].toFixed(2) : dials[dial.key]}
                </span>
              </div>
              <input
                type="range"
                min={dial.min}
                max={dial.max}
                step={dial.step}
                value={dials[dial.key]}
                aria-label={dial.label}
                onChange={(event) =>
                  setDials((current) => ({ ...current, [dial.key]: Number(event.target.value) }))
                }
                className="w-full accent-emerald-400"
              />
              <p className="text-[10px] text-slate-500">{dial.hint}</p>
            </div>
          ))}

          <label className="flex items-center gap-2 text-[11px] text-slate-300">
            <input
              type="checkbox"
              checked={autostart}
              onChange={(event) => setAutostart(event.target.checked)}
              className="accent-emerald-400"
            />
            Start immediately (a new world is paused at tick 0)
          </label>

          <div className="flex justify-end gap-2 pt-1">
            <Button onClick={onClose} tone="quiet">
              Cancel
            </Button>
            <Button onClick={() => void submit()} disabled={busy} tone="danger">
              {busy ? 'Building...' : 'Build world'}
            </Button>
          </div>
        </div>
      </Panel>
    </div>
  );
}

function PresetButton({
  name,
  description,
  active,
  onClick,
}: {
  name: string;
  description: string;
  active: boolean;
  onClick: () => void;
}): React.ReactElement {
  return (
    <button
      type="button"
      onClick={onClick}
      title={description}
      className={`rounded-lg px-2 py-1.5 text-left text-[11px] transition ${
        active ? 'bg-emerald-500/90 text-slate-900' : 'bg-white/5 text-slate-200 hover:bg-white/15'
      }`}
    >
      <span className="block font-medium">{name}</span>
      <span className={`block truncate text-[10px] ${active ? 'text-slate-800' : 'text-slate-500'}`}>
        {description}
      </span>
    </button>
  );
}
