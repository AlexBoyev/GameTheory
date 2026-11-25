/**
 * The title card that announces a day.
 *
 * A day is 2,400 ticks, and the island fills it with hundreds of small
 * events: fights, rumours, trades, a tribe or two. Watched live that reads as
 * "nothing is happening", which is the opposite of true - so when the clock
 * turns over, the day that ended gets a headline and three facts.
 *
 * It lives in front of the world for ten seconds and then leaves on its own.
 * Nothing about it is modal: it never takes the pointer, so you can keep
 * driving the simulation while it is up.
 */

import { useEffect } from 'react';

import { useSimStore } from '@/state/simStore';

/** How long a card stays up. Long enough to read four lines, twice. */
export const DAY_CARD_MS = 10_000;

export function DayCard(): React.ReactElement | null {
  const report = useSimStore((state) => state.dayReport);
  const dismiss = useSimStore((state) => state.dismissDay);

  // Keyed on the day, so a card that arrives while one is up gets the full
  // ten seconds rather than inheriting the end of its predecessor's timer -
  // which is what happens at MAX speed, where a day lands every fifteen
  // seconds.
  const day = report?.day ?? null;
  useEffect(() => {
    if (day === null) return;
    const timer = setTimeout(dismiss, DAY_CARD_MS);
    return () => clearTimeout(timer);
  }, [day, dismiss]);

  if (!report) return null;

  return (
    <div className="pointer-events-none absolute inset-x-0 top-24 z-30 flex justify-center px-4">
      <button
        type="button"
        onClick={dismiss}
        title="Dismiss"
        className="pointer-events-auto max-w-xl cursor-default rounded-2xl bg-slate-950/85 px-6 py-4 text-left shadow-2xl ring-1 ring-amber-300/25 backdrop-blur"
      >
        <div className="flex items-baseline gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-[0.2em] text-amber-300/80">
            Day {report.day + 1}
          </span>
          <span className="text-[11px] uppercase tracking-wide text-slate-500">
            {report.season}
          </span>
        </div>
        <p className="pt-1 text-lg font-semibold leading-snug text-slate-100">{report.headline}</p>
        <ul className="pt-1.5 space-y-0.5">
          {report.lines.map((line) => (
            <li key={line} className="text-[12px] leading-relaxed text-slate-300">
              {line}
            </li>
          ))}
        </ul>
      </button>
    </div>
  );
}
