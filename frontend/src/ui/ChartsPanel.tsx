/**
 * The charts (SPEC section 10): what the society is doing over time.
 *
 * Four questions, in order of how much they tell you: is the population
 * surviving, which strategies are winning, is anyone cooperating, and is the
 * food piling up with a few agents.
 */

import { useMemo } from 'react';

import type { MetricPoint } from '@/api/types';
import { Chart, type ChartSeries } from '@/ui/Chart';
import { Empty, Panel } from '@/ui/primitives';
import { useSocietyStore } from '@/state/societyStore';
import { useUiStore } from '@/state/uiStore';

/** Stable colour per strategy, so a line means the same thing every run. */
const STRATEGY_COLOURS: Record<string, string> = {
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

const GAME_COLOURS: Record<string, string> = {
  prisoners_dilemma: '#60a5fa',
  stag_hunt: '#4ade80',
  hawk_dove: '#f87171',
  ultimatum: '#a78bfa',
  public_goods: '#facc15',
};

function seriesFrom(
  points: MetricPoint[],
  keys: string[],
  pick: (point: MetricPoint, key: string) => number | undefined,
  colours: Record<string, string>,
): ChartSeries[] {
  return keys.map((key) => ({
    label: key,
    colour: colours[key] ?? '#94a3b8',
    values: points.map((point) => pick(point, key) ?? null),
  }));
}

export function ChartsPanel(): React.ReactElement {
  const points = useSocietyStore((state) => state.metrics);
  const close = useUiStore((state) => state.set);

  const ticks = useMemo(() => points.map((point) => point.tick), [points]);

  const strategyKeys = useMemo(() => {
    const seen = new Set<string>();
    for (const point of points)
      for (const key of Object.keys(point.by_strategy ?? {})) seen.add(key);
    return [...seen].sort();
  }, [points]);

  const gameKeys = useMemo(() => {
    const seen = new Set<string>();
    for (const point of points) {
      for (const key of Object.keys(point.cooperation_by_game ?? {})) seen.add(key);
    }
    return [...seen].sort();
  }, [points]);

  const population = useMemo<ChartSeries[]>(
    () => [
      {
        label: 'alive',
        colour: '#e2e8f0',
        values: points.map((point) => point.population),
      },
    ],
    [points],
  );

  const strategies = useMemo(
    () =>
      seriesFrom(
        points,
        strategyKeys,
        (point, key) => point.by_strategy?.[key] ?? 0,
        STRATEGY_COLOURS,
      ),
    [points, strategyKeys],
  );

  const cooperation = useMemo(
    () =>
      seriesFrom(points, gameKeys, (point, key) => point.cooperation_by_game?.[key], GAME_COLOURS),
    [points, gameKeys],
  );

  const inequality = useMemo<ChartSeries[]>(
    () => [
      { label: 'food Gini', colour: '#fbbf24', values: points.map((p) => p.food_gini ?? 0) },
      {
        label: 'trust density',
        colour: '#4ade80',
        values: points.map((p) => p.trust_density ?? 0),
      },
    ],
    [points],
  );

  const latest = points.at(-1);

  return (
    <Panel
      title="Charts"
      badge={`${points.length} samples`}
      onClose={() => close('chartsOpen', false)}
      className="max-h-[calc(100vh-11rem)] w-80"
    >
      {points.length < 2 ? (
        <Empty>
          Metrics are sampled every 100 ticks. Let it run - or press a higher speed - and the charts
          will fill in.
        </Empty>
      ) : (
        <div className="space-y-1 pt-1">
          <Chart title="Population" ticks={ticks} series={population} />
          <Chart title="Strategy shares" ticks={ticks} series={strategies} height={130} />
          <Chart
            title="Cooperation rate by game"
            ticks={ticks}
            series={cooperation}
            range={[0, 1]}
          />
          <Chart title="Food inequality & trust" ticks={ticks} series={inequality} range={[0, 1]} />

          {latest && (
            <dl className="grid grid-cols-2 gap-x-3 gap-y-0.5 px-3 pb-3 pt-1 text-[11px]">
              {Object.entries(latest.extra ?? {}).map(([key, value]) => (
                <div key={key} className="flex justify-between gap-2">
                  <dt className="text-slate-400">{key.replace(/_/g, ' ')}</dt>
                  <dd className="font-mono tabular-nums text-slate-200">{Math.round(value)}</dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      )}
    </Panel>
  );
}
