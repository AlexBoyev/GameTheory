/**
 * The LLM monitor (SPEC 9.4): what the deliberative layer is actually doing.
 *
 * The point of this panel is honesty. "LLM minds" is the easiest thing in the
 * project to fake, so this shows the provider, whether it is reachable, the
 * real call count, the failure rate, and the last prompts and replies. If it
 * says `mock`, nothing is talking to a model - which is the normal, intended
 * state when Ollama is not installed.
 */

import { useCallback, useEffect, useState } from 'react';

import { api } from '@/api/rest';
import type { LlmCall, LlmStats, LlmStatus } from '@/api/types';
import { Button, Empty, Panel, Row } from '@/ui/primitives';
import { useUiStore } from '@/state/uiStore';

const POLL_MS = 2000;

const SPEED_POLICIES = ['off', 'reduced', 'full'] as const;
type SpeedPolicy = (typeof SPEED_POLICIES)[number];

function health(status: LlmStatus | null): { label: string; tone: string } {
  if (!status) return { label: 'unknown', tone: 'text-slate-500' };
  if (!status.enabled) return { label: 'off', tone: 'text-slate-500' };
  if (status.circuit_open) return { label: 'circuit open', tone: 'text-rose-300' };
  if (status.provider === 'mock') return { label: 'mock plans', tone: 'text-amber-300' };
  if (status.reachable === false) return { label: 'unreachable', tone: 'text-rose-300' };
  if (status.reachable === null) return { label: 'not probed', tone: 'text-slate-400' };
  return { label: 'live', tone: 'text-emerald-300' };
}

function CallRow({ call }: { call: LlmCall }): React.ReactElement {
  const [open, setOpen] = useState(false);
  return (
    <li className="border-b border-white/5 px-3 py-1.5 last:border-0">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-baseline gap-2 text-left"
      >
        <span className={call.ok ? 'text-emerald-400' : 'text-rose-400'}>{call.ok ? '+' : '!'}</span>
        <span className="font-mono text-[10px] text-slate-400">#{call.agent_id}</span>
        <span className="text-[11px] text-slate-300">{call.kind}</span>
        {call.cached && <span className="text-[10px] text-sky-300">cached</span>}
        <span className="ml-auto font-mono text-[10px] tabular-nums text-slate-500">
          {call.latency_s > 0 ? `${call.latency_s.toFixed(2)}s` : '-'}
        </span>
      </button>
      {call.error && <p className="pl-6 text-[10px] text-rose-300">{call.error}</p>}
      {open && (
        <div className="space-y-1 pl-6 pt-1">
          <p className="text-[10px] uppercase tracking-wide text-slate-500">prompt</p>
          <pre className="max-h-32 overflow-auto whitespace-pre-wrap break-words rounded bg-black/30 p-2 text-[10px] text-slate-400">
            {call.prompt_preview || '(empty)'}
          </pre>
          <p className="text-[10px] uppercase tracking-wide text-slate-500">reply</p>
          <pre className="max-h-32 overflow-auto whitespace-pre-wrap break-words rounded bg-black/30 p-2 text-[10px] text-slate-400">
            {call.response_preview || '(empty)'}
          </pre>
        </div>
      )}
    </li>
  );
}

export function LlmPanel(): React.ReactElement {
  const close = useUiStore((state) => state.set);
  const [status, setStatus] = useState<LlmStatus | null>(null);
  const [stats, setStats] = useState<LlmStats | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async (): Promise<void> => {
    const [nextStatus, nextStats] = await Promise.all([api.llmStatus(), api.llmStats()]);
    setStatus(nextStatus);
    setStats(nextStats);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const tick = async (): Promise<void> => {
      try {
        if (!cancelled) await refresh();
      } catch {
        // The connection banner already covers a dead backend.
      }
    };
    void tick();
    const timer = setInterval(() => void tick(), POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [refresh]);

  const apply = useCallback(
    async (change: Parameters<typeof api.putLlmSettings>[0]): Promise<void> => {
      setBusy(true);
      try {
        setStatus(await api.putLlmSettings(change));
        await refresh();
      } catch {
        // Leave the previous status on screen rather than blanking it.
      } finally {
        setBusy(false);
      }
    },
    [refresh],
  );

  const state = health(status);
  const recent = stats?.recent ?? [];
  const policy = (status?.high_speed_policy ?? 'reduced') as SpeedPolicy;

  return (
    <Panel
      title="LLM minds"
      badge={status ? `${status.provider} · ${status.model}` : 'loading'}
      onClose={() => close('llmPanelOpen', false)}
      className="max-h-[calc(100vh-11rem)] w-80"
    >
      <div className="space-y-2 p-3">
        <div className="flex items-center gap-2">
          <span className={`text-xs font-semibold ${state.tone}`}>{state.label}</span>
          <span className="ml-auto flex gap-1">
            <Button
              onClick={() => void apply({ enabled: !(status?.enabled ?? true) })}
              active={status?.enabled ?? false}
              disabled={busy}
              title="Switch deliberation on or off"
            >
              {status?.enabled ? 'on' : 'off'}
            </Button>
          </span>
        </div>

        {status?.provider === 'mock' && (
          <p className="rounded-lg bg-amber-500/10 p-2 text-[10px] leading-relaxed text-amber-200">
            Plans are coming from the built-in mock, not a language model. Install Ollama and
            switch provider below to use a real one - everything else works either way.
          </p>
        )}
        {status?.circuit_open && (
          <p className="rounded-lg bg-rose-500/10 p-2 text-[10px] leading-relaxed text-rose-200">
            Too many failures in a row, so calls are suspended for a cooldown. Agents are running
            on utility AI until it closes.
          </p>
        )}

        <div className="flex gap-1">
          {(['mock', 'ollama'] as const).map((name) => (
            <Button
              key={name}
              onClick={() => void apply({ provider: name })}
              active={status?.provider === name}
              disabled={busy}
              title={name === 'ollama' ? 'Needs a local Ollama daemon' : 'In-process, no install'}
            >
              {name}
            </Button>
          ))}
          <span className="ml-auto flex gap-1">
            {SPEED_POLICIES.map((name) => (
              <Button
                key={name}
                onClick={() => void apply({ high_speed_policy: name })}
                active={policy === name}
                disabled={busy}
                title={`At high speed: ${name}`}
                tone="quiet"
              >
                {name}
              </Button>
            ))}
          </span>
        </div>

        <dl className="pt-1">
          <Row label="deliberating agents" value={status?.max_agents ?? '-'} />
          <Row
            label="min interval"
            value={status ? `${status.min_interval_sim_s}s sim` : '-'}
          />
          <Row label="queue" value={status?.queue_depth ?? 0} />
          <Row label="calls" value={stats?.calls ?? 0} />
          <Row label="cache hits" value={stats?.cache_hits ?? 0} />
          <Row
            label="failures"
            value={
              stats ? `${stats.failures} (${Math.round(stats.failure_rate * 100)}%)` : '-'
            }
          />
          <Row label="timeouts" value={stats?.timeouts ?? 0} />
          <Row
            label="refused by limits"
            value={stats?.refusals ?? 0}
            title="Rate limit or open circuit - not a provider failure"
          />
          <Row
            label="avg latency"
            value={stats ? `${stats.avg_latency_s.toFixed(2)}s` : '-'}
          />
          <Row label="prompt tokens (est)" value={stats?.prompt_tokens_estimate ?? 0} />
        </dl>
      </div>

      <h3 className="border-y border-white/10 px-3 py-1 text-[10px] uppercase tracking-wider text-slate-400">
        Recent calls
      </h3>
      {recent.length > 0 ? (
        <ul>
          {recent.map((call, index) => (
            <CallRow key={`${call.agent_id}-${index}`} call={call} />
          ))}
        </ul>
      ) : (
        <Empty>No calls yet. Deliberation happens every few sim-seconds per agent.</Empty>
      )}
    </Panel>
  );
}
