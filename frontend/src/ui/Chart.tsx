/**
 * A thin uPlot wrapper: one small, fast line chart.
 *
 * uPlot rather than a React charting library because these redraw on a timer
 * with hundreds of points and must not cost the render loop anything.
 */

import { useEffect, useRef } from 'react';
import uPlot from 'uplot';

import 'uplot/dist/uPlot.min.css';

export interface ChartSeries {
  label: string;
  colour: string;
  values: (number | null)[];
}

export interface ChartProps {
  title: string;
  /** Shared x axis - sim ticks. */
  ticks: number[];
  series: ChartSeries[];
  height?: number;
  /** Clamp the y axis, for rates that are always 0..1. */
  range?: [number, number];
}

export function Chart({
  title,
  ticks,
  series,
  height = 110,
  range,
}: ChartProps): React.ReactElement {
  const hostRef = useRef<HTMLDivElement>(null);
  const plotRef = useRef<uPlot | null>(null);

  // The *shape* of the chart: how many lines and what they are called. Only
  // a change here needs a new plot; new samples do not.
  const shape = series.map((entry) => `${entry.label}:${entry.colour}`).join('|');

  // The newest series, readable from the creation effect without making it
  // depend on an array that is rebuilt on every poll. Synced in an effect
  // rather than during render, which the React compiler rules forbid.
  const seriesRef = useRef(series);
  useEffect(() => {
    seriesRef.current = series;
  }, [series]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    const options: uPlot.Options = {
      width: host.clientWidth || 280,
      height,
      padding: [8, 8, 0, 0],
      legend: { show: series.length > 1, live: false },
      cursor: { show: true, y: false },
      scales: {
        x: { time: false },
        ...(range ? { y: { range } } : {}),
      },
      axes: [
        {
          stroke: '#64748b',
          grid: { stroke: 'rgba(148,163,184,0.12)' },
          ticks: { stroke: 'rgba(148,163,184,0.2)' },
          font: '10px system-ui',
          size: 24,
        },
        {
          stroke: '#64748b',
          grid: { stroke: 'rgba(148,163,184,0.12)' },
          ticks: { stroke: 'rgba(148,163,184,0.2)' },
          font: '10px system-ui',
          size: 34,
        },
      ],
      series: [
        {},
        ...seriesRef.current.map((entry) => ({
          label: entry.label,
          stroke: entry.colour,
          width: 1.6,
          points: { show: false },
        })),
      ],
    };

    const plot = new uPlot(options, [[]] as unknown as uPlot.AlignedData, host);
    plotRef.current = plot;

    const resize = (): void => plot.setSize({ width: host.clientWidth || 280, height });
    window.addEventListener('resize', resize);

    return () => {
      window.removeEventListener('resize', resize);
      plot.destroy();
      plotRef.current = null;
    };
    // Rebuilt only when the shape changes. It used to depend on `ticks` and
    // `series` too, which are fresh arrays on every poll, so the whole plot
    // was destroyed and recreated every three seconds - the canvas flashed
    // and the axes re-laid themselves out, which is the "jumping" you see
    // when you watch the charts. Samples go in through `setData` below.
  }, [shape, height, range, series.length]);

  useEffect(() => {
    const plot = plotRef.current;
    if (!plot) return;
    plot.setData([ticks, ...series.map((entry) => entry.values)] as uPlot.AlignedData);
  }, [ticks, series]);

  return (
    <div className="px-2 pb-2">
      <p className="px-1 pb-0.5 text-[10px] uppercase tracking-wide text-slate-400">{title}</p>
      <div ref={hostRef} className="w-full" />
    </div>
  );
}
