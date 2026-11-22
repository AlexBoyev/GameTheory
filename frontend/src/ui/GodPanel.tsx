/**
 * God tools (SPEC 9.4): the observer's hands.
 *
 * Every tool lands *somewhere*, and the obvious somewhere is wherever you are
 * looking - so the local ones use the selected agent's position when there is
 * one and the island's middle otherwise, and say which in the result line.
 * That beats making the user type coordinates for a toy.
 *
 * Smite is deliberately separated and only enabled with an agent selected:
 * it is the one tool that cannot be undone by waiting.
 */

import { useCallback, useState } from 'react';

import { api } from '@/api/rest';
import type { GodAction, GodRequest, Snapshot } from '@/api/types';
import { Button, Empty, Panel, Row } from '@/ui/primitives';
import { useSelectionStore } from '@/state/selectionStore';
import { useSimStore } from '@/state/simStore';
import { useUiStore } from '@/state/uiStore';

interface Tool {
  action: GodAction;
  label: string;
  icon: string;
  hint: string;
  /** Extra payload beyond the position. */
  payload?: GodRequest;
  tone?: 'default' | 'danger';
}

const TOOLS: Tool[] = [
  {
    action: 'drop_food',
    label: 'Drop food',
    icon: '🫐',
    hint: 'Scatter bushes - the simplest way to end a famine.',
    payload: { amount: 40, radius: 20 },
  },
  {
    action: 'bounty',
    label: 'Good season',
    icon: '🌱',
    hint: 'Refill every patch nearby and speed up its regrowth.',
    payload: { radius: 60 },
  },
  {
    action: 'drought',
    label: 'Drought',
    icon: '🏜️',
    hint: 'Dry up the water for miles. Agents never plan around water - until now.',
    // Island-wide, because water only exists on the shore: a 60-unit drought
    // centred anywhere inland finds nothing and reports "0 watering spots",
    // which reads as a broken button rather than a bad choice of radius.
    payload: { radius: 400 },
    tone: 'danger',
  },
  {
    action: 'plague',
    label: 'Plague',
    icon: '🦠',
    hint: 'Hurt everyone nearby. Lethal for the weak, survivable for the rest.',
    payload: { radius: 40, amount: 55 },
    tone: 'danger',
  },
];

const STRATEGIES = [
  'TitForTat',
  'AlwaysDefect',
  'AlwaysCooperate',
  'Grudger',
  'Opportunist',
] as const;

export function GodPanel(): React.ReactElement {
  const close = useUiStore((state) => state.set);
  const selectedId = useSelectionStore((state) => state.selectedAgentId);
  const tick = useSimStore((state) => state.tick);
  const [log, setLog] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [strategy, setStrategy] = useState<string>(STRATEGIES[0]);
  const [deliberative, setDeliberative] = useState(false);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);

  const note = useCallback((line: string): void => {
    setLog((current) => [line, ...current].slice(0, 6));
  }, []);

  /** Where a local tool lands: the selected agent, else the middle. */
  const target = useCallback((): { payload: GodRequest; where: string } => {
    const agent = selectedId;
    if (agent === null) return { payload: {}, where: 'the middle of the island' };
    const frame = useSimStore.getState().currentFrame;
    if (frame && frame.stride > 0) {
      const total = Math.floor(frame.agents.length / frame.stride);
      for (let index = 0; index < total; index += 1) {
        const offset = index * frame.stride;
        if (frame.agents[offset] === agent) {
          return {
            payload: { x: frame.agents[offset + 1] ?? 0, z: frame.agents[offset + 2] ?? 0 },
            where: `agent #${agent}`,
          };
        }
      }
    }
    return { payload: {}, where: 'the middle of the island' };
  }, [selectedId]);

  const run = useCallback(
    async (tool: Tool): Promise<void> => {
      setBusy(true);
      try {
        const { payload, where } = target();
        const result = await api.god(tool.action, { ...tool.payload, ...payload });
        note(`${tool.label} at ${where}: ${result.detail || `${result.affected} affected`}`);
      } catch (error) {
        note(`${tool.label} failed: ${String(error)}`);
      } finally {
        setBusy(false);
      }
    },
    [note, target],
  );

  const spawn = useCallback(async (): Promise<void> => {
    setBusy(true);
    try {
      const { payload } = target();
      const result = await api.god('spawn_agent', {
        ...payload,
        strategy,
        brain_type: deliberative ? 'llm' : 'utility',
      });
      note(`Spawned: ${result.detail}`);
    } finally {
      setBusy(false);
    }
  }, [deliberative, note, strategy, target]);

  const smite = useCallback(async (): Promise<void> => {
    if (selectedId === null) return;
    setBusy(true);
    try {
      const result = await api.god('smite', { agent_id: selectedId });
      note(`Smite: ${result.detail}`);
    } finally {
      setBusy(false);
    }
  }, [note, selectedId]);

  const refreshSnapshots = useCallback(async (): Promise<void> => {
    try {
      setSnapshots(await api.snapshots());
    } catch {
      setSnapshots([]);
    }
  }, []);

  const save = useCallback(async (): Promise<void> => {
    setBusy(true);
    try {
      const meta = await api.saveSnapshot(`tick ${tick}`);
      note(`Saved "${meta.label}" (${Math.round((meta.size_bytes ?? 0) / 1024)} kB)`);
      await refreshSnapshots();
    } finally {
      setBusy(false);
    }
  }, [note, refreshSnapshots, tick]);

  const load = useCallback(
    async (snapshot: Snapshot): Promise<void> => {
      setBusy(true);
      try {
        const result = await api.loadSnapshot(snapshot.id);
        note(`Loaded "${snapshot.label}": ${result.detail}`);
      } finally {
        setBusy(false);
      }
    },
    [note],
  );

  return (
    <Panel
      title="God tools"
      badge={selectedId === null ? 'centre' : `at #${selectedId}`}
      onClose={() => close('godPanelOpen', false)}
      className="max-h-[calc(100vh-11rem)] w-72"
    >
      <div className="space-y-3 p-3">
        <p className="text-[10px] leading-relaxed text-slate-400">
          Local tools land on the selected agent, or the middle of the island when nothing is
          selected. Everything you do here shows up in the event feed.
        </p>

        <div className="grid grid-cols-2 gap-1">
          {TOOLS.map((tool) => (
            <Button
              key={tool.action}
              onClick={() => void run(tool)}
              disabled={busy}
              title={tool.hint}
              tone={tool.tone === 'danger' ? 'danger' : 'default'}
            >
              <span className="mr-1">{tool.icon}</span>
              {tool.label}
            </Button>
          ))}
        </div>

        <div className="space-y-1 rounded-lg bg-slate-800/60 p-2">
          <p className="text-[10px] uppercase tracking-wide text-slate-400">Spawn an agent</p>
          <select
            value={strategy}
            onChange={(event) => setStrategy(event.target.value)}
            aria-label="Strategy"
            className="w-full rounded bg-slate-900 px-2 py-1 text-[11px] text-slate-100 outline-none ring-1 ring-white/10"
          >
            {STRATEGIES.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-2 text-[10px] text-slate-300">
            <input
              type="checkbox"
              checked={deliberative}
              onChange={(event) => setDeliberative(event.target.checked)}
              className="accent-emerald-400"
            />
            Deliberative (holds goals, speaks)
          </label>
          <Button onClick={() => void spawn()} disabled={busy}>
            ✨ Spawn
          </Button>
        </div>

        <div className="space-y-1 rounded-lg bg-rose-500/5 p-2 ring-1 ring-rose-400/20">
          <p className="text-[10px] uppercase tracking-wide text-rose-200/80">
            Cannot be undone by waiting
          </p>
          <Button
            onClick={() => void smite()}
            disabled={busy || selectedId === null}
            tone="danger"
            title={selectedId === null ? 'Select an agent first' : `Kill agent #${selectedId}`}
          >
            ⚡ Smite {selectedId === null ? '(select someone)' : `#${selectedId}`}
          </Button>
        </div>

        <div className="space-y-1 rounded-lg bg-slate-800/60 p-2">
          <div className="flex items-center gap-1">
            <p className="flex-1 text-[10px] uppercase tracking-wide text-slate-400">Snapshots</p>
            <Button onClick={() => void save()} disabled={busy} title="Save the world as it is">
              💾 Save
            </Button>
            <Button onClick={() => void refreshSnapshots()} tone="quiet" title="Refresh the list">
              ↻
            </Button>
          </div>
          {snapshots.length === 0 ? (
            <p className="text-[10px] text-slate-500">
              None loaded. Save one, or press ↻ to list what is stored.
            </p>
          ) : (
            <ul className="space-y-0.5">
              {snapshots.slice(0, 6).map((snapshot) => (
                <li key={snapshot.id}>
                  <button
                    type="button"
                    onClick={() => void load(snapshot)}
                    disabled={busy}
                    className="flex w-full items-baseline gap-2 rounded px-1 py-0.5 text-left text-[11px] text-slate-300 transition hover:bg-white/10 disabled:opacity-40"
                  >
                    <span className="flex-1 truncate">{snapshot.label}</span>
                    <span className="font-mono text-[10px] tabular-nums text-slate-500">
                      t{snapshot.tick} · {snapshot.population}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <h3 className="border-y border-white/10 px-3 py-1 text-[10px] uppercase tracking-wider text-slate-400">
        What you did
      </h3>
      {log.length === 0 ? (
        <Empty>Nothing yet. Interventions are reported here and in the feed.</Empty>
      ) : (
        <ul className="space-y-0.5 p-3 pt-2">
          {log.map((line, index) => (
            <li key={`${line}-${index}`} className="text-[11px] text-slate-400">
              {line}
            </li>
          ))}
        </ul>
      )}
      <div className="px-3 pb-3">
        <Row label="tick" value={tick} />
      </div>
    </Panel>
  );
}
