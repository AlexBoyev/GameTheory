/**
 * New world: pick a seed and a population, or take the dice.
 *
 * Reset leaves the world paused at tick 0 on purpose, so you can look at the
 * island before anything happens to it. "Start immediately" is the usual
 * choice, so it is checked by default.
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

export function ResetDialog({ onClose }: ResetDialogProps): React.ReactElement {
  const controls = useSimControls();
  const currentConfig = useSimStore((state) => state.config);
  const currentSeed = useSimStore((state) => state.seed);

  const [seed, setSeed] = useState(String(currentSeed));
  const [population, setPopulation] = useState(String(currentConfig?.population ?? 120));
  const [scarcity, setScarcity] = useState(String(currentConfig?.scarcity ?? 1));
  const [autostart, setAutostart] = useState(true);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void api
      .presets()
      .then(setPresets)
      .catch(() => setPresets([]));
  }, []);

  const submit = async (): Promise<void> => {
    setBusy(true);
    try {
      const base = currentConfig;
      const config: WorldConfig | undefined = base
        ? {
            ...base,
            population: Number(population) || base.population,
            scarcity: Number(scarcity) || base.scarcity,
          }
        : undefined;
      await controls.reset({ seed: Number(seed) || 0, ...(config ? { config } : {}) });
      if (autostart) await controls.play();
      onClose();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="pointer-events-auto absolute inset-0 z-30 flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm">
      <Panel title="New world" onClose={onClose} className="w-full max-w-md">
        <div className="space-y-3 p-3">
          <Field label="Seed" hint="Same seed, same world - to the bit.">
            <div className="flex gap-2">
              <input
                value={seed}
                onChange={(event) => setSeed(event.target.value)}
                inputMode="numeric"
                className="min-w-0 flex-1 rounded-lg bg-slate-800 px-2 py-1.5 font-mono text-xs text-slate-100 outline-none ring-1 ring-white/10 focus:ring-emerald-400/60"
              />
              <Button onClick={() => setSeed(String(Math.floor(Math.random() * 100000)))}>
                🎲
              </Button>
            </div>
          </Field>

          <Field label="Population" hint="The island comfortably feeds a few hundred.">
            <input
              value={population}
              onChange={(event) => setPopulation(event.target.value)}
              inputMode="numeric"
              className="w-full rounded-lg bg-slate-800 px-2 py-1.5 font-mono text-xs text-slate-100 outline-none ring-1 ring-white/10 focus:ring-emerald-400/60"
            />
          </Field>

          <Field label="Scarcity" hint="Above 1 means fewer resources. Winter is harsher still.">
            <input
              value={scarcity}
              onChange={(event) => setScarcity(event.target.value)}
              inputMode="decimal"
              className="w-full rounded-lg bg-slate-800 px-2 py-1.5 font-mono text-xs text-slate-100 outline-none ring-1 ring-white/10 focus:ring-emerald-400/60"
            />
          </Field>

          <label className="flex items-center gap-2 text-[11px] text-slate-300">
            <input
              type="checkbox"
              checked={autostart}
              onChange={(event) => setAutostart(event.target.checked)}
              className="accent-emerald-400"
            />
            Start immediately (reset leaves the world paused)
          </label>

          {presets.length > 0 && (
            <div className="rounded-lg bg-slate-800/60 p-2">
              <p className="mb-1 text-[10px] uppercase tracking-wide text-slate-400">
                Presets - values land in Phase 6
              </p>
              <ul className="space-y-0.5">
                {presets.map((preset) => (
                  <li key={preset.id} className="text-[11px] text-slate-400">
                    <span className="text-slate-200">{preset.name}</span> - {preset.description}
                  </li>
                ))}
              </ul>
            </div>
          )}

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

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint: string;
  children: React.ReactNode;
}): React.ReactElement {
  return (
    <div>
      <p className="mb-1 text-[10px] uppercase tracking-wide text-slate-400">{label}</p>
      {children}
      <p className="mt-1 text-[10px] text-slate-500">{hint}</p>
    </div>
  );
}
