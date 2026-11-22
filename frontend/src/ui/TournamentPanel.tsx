/**
 * The Axelrod report (SPEC 5.3), shown only when a tournament is running.
 *
 * It appears by itself when you pick the Axelrod preset and disappears again
 * on any other world, because a standings table on an island would be an
 * empty box asking to be closed. The charts panel already draws the strategy
 * shares over time - this is the table that says *why* they moved.
 *
 * The one number worth watching is score per round: it starts near the
 * mutual-defection payoff and climbs towards the mutual-cooperation one as
 * the reciprocators take over. That rise is the finding.
 */

import { useEffect, useState } from 'react';

import { api } from '@/api/rest';
import type { Tournament } from '@/api/types';
import { Empty, Panel, Row } from '@/ui/primitives';
import { useSimStore } from '@/state/simStore';

const POLL_MS = 1500;

/** Stable colour per strategy, matching the charts panel. */
const COLOURS: Record<string, string> = {
  AlwaysCooperate: '#4ade80',
  AlwaysDefect: '#f87171',
  TitForTat: '#60a5fa',
  GenerousTFT: '#a78bfa',
  Grudger: '#fb923c',
  Pavlov: '#facc15',
  Detective: '#22d3ee',
  Random: '#94a3b8',
  Opportunist: '#f472b6',
  LLM: '#fde68a',
};

export function TournamentPanel(): React.ReactElement | null {
  const epoch = useSimStore((state) => state.worldEpoch);
  const [report, setReport] = useState<Tournament | null>(null);

  useEffect(() => {
    let cancelled = false;
    const tick = async (): Promise<void> => {
      try {
        const next = await api.tournament();
        if (!cancelled) setReport(next);
      } catch {
        // The connection banner covers a dead backend.
      }
    };
    void tick();
    const timer = setInterval(() => void tick(), POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
    // `epoch` changes on every new world, which is exactly when a tournament
    // starts or stops being the thing on screen.
  }, [epoch]);

  if (!report?.active) return null;

  const standings = report.standings ?? [];
  const members = standings.reduce((total, row) => total + row.members, 0) || 1;
  const best = standings[0]?.score_per_round ?? 1;
  const generations = report.generations ?? 0;
  const generation = report.generation ?? 0;

  return (
    <Panel
      title="Tournament"
      badge={
        report.finished
          ? `finished · ${generations} generations`
          : `generation ${generation + 1} of ${generations}`
      }
      className="w-72"
    >
      <div className="space-y-2 p-3">
        <p className="text-[10px] leading-relaxed text-slate-400">
          Round-robin iterated Prisoner&rsquo;s Dilemma, survival off. Each generation the
          population is resampled in proportion to what each strategy scored.
        </p>

        {!report.finished && (
          <div className="h-1 overflow-hidden rounded-full bg-white/10">
            <div
              className="h-full rounded-full bg-emerald-400/80"
              style={{
                width: `${Math.round((100 * (report.pairings_played ?? 0)) / Math.max(1, report.pairings_total ?? 1))}%`,
              }}
            />
          </div>
        )}

        {standings.length === 0 ? (
          <Empty>Waiting for the first pairings to finish.</Empty>
        ) : (
          <ol className="space-y-1">
            {standings.map((row, index) => (
              <li key={row.strategy}>
                <div className="flex items-baseline gap-2">
                  <span className="w-3 text-right font-mono text-[10px] text-slate-500">
                    {index + 1}
                  </span>
                  <span
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{ backgroundColor: COLOURS[row.strategy] ?? '#94a3b8' }}
                  />
                  <span className="flex-1 truncate text-[11px] text-slate-200">
                    {row.strategy}
                  </span>
                  <span className="font-mono text-[11px] tabular-nums text-slate-300">
                    {row.score_per_round.toFixed(2)}
                  </span>
                  <span
                    className="w-8 text-right font-mono text-[10px] tabular-nums text-slate-500"
                    title={`${row.members} of ${members} agents`}
                  >
                    {Math.round((100 * row.members) / members)}%
                  </span>
                </div>
                {/* Bar relative to the leader, so the gradient selection
                    actually works on is visible rather than implied. */}
                <div className="ml-7 mt-0.5 h-0.5 overflow-hidden rounded-full bg-white/5">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${Math.max(2, Math.round((100 * row.score_per_round) / Math.max(0.01, best)))}%`,
                      backgroundColor: COLOURS[row.strategy] ?? '#94a3b8',
                      opacity: 0.55,
                    }}
                  />
                </div>
              </li>
            ))}
          </ol>
        )}

        <dl className="pt-1">
          <Row label="score is" value="per round, not per agent" />
          <Row
            label="pairings this generation"
            value={`${report.pairings_played ?? 0} / ${report.pairings_total ?? 0}`}
          />
        </dl>
      </div>
    </Panel>
  );
}
