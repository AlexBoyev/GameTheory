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
        ...series.map((entry) => ({
          label: entry.label,
          stroke: entry.colour,
          width: 1.6,
          points: { show: false },
        })),
      ],
    };

    const data: uPlot.AlignedData = [ticks, ...series.map((entry) => entry.values)];
    const plot = new uPlot(options, data, host);
    plotRef.current = plot;

    const resize = (): void => plot.setSize({ width: host.clientWidth || 280, height });
    window.addEventListener('resize', resize);

    return () => {
      window.removeEventListener('resize', resize);
      plot.destroy();
      plotRef.current = null;
    };
    // Rebuilt wholesale when the shape of the data changes; uPlot is cheap
    // enough to recreate at this cadence and it keeps the code honest.
  }, [ticks, series, height, range]);

  return (
    <div className="px-2 pb-2">
      <p className="px-1 pb-0.5 text-[10px] uppercase tracking-wide text-slate-400">{title}</p>
      <div ref={hostRef} className="w-full" />
    </div>
  );
}
