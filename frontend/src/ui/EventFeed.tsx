/**
 * The log: what just happened, newest first.
 *
 * Seeded from `GET /api/events` on mount so a fresh tab is not blank, then
 * fed by the socket. Clicking a row flies the camera to where it happened,
 * which is how you catch up with something you only saw in text.
 *
 * Two deliberate limits keep this panel from eating the frame budget at high
 * speed: rows are sampled four times a second rather than on every message
 * (`useThrottledEvents`), and only `VISIBLE_ROWS` of them are rendered.
 */

import { memo, useEffect, useMemo, useState } from 'react';

import { api } from '@/api/rest';
import type { DayData, EventItem } from '@/api/types';
import { useThrottledEvents } from '@/app/useThrottledEvents';
import { EVENT_EMOJI } from '@/lib/stateIcons';
import { Empty, Panel } from '@/ui/primitives';
import { useSelectionStore } from '@/state/selectionStore';
import { useSimStore } from '@/state/simStore';

/** More than this and you are not reading, you are watching a waterfall. */
const VISIBLE_ROWS = 60;

/** Day headlines shown before the strip starts scrolling - about a week. */
const DAYS_BEFORE_SCROLL = 5;

function Chronicle(): React.ReactElement | null {
  const history = useSimStore((state) => state.dayHistory);
  const showDay = useSimStore((state) => state.showDay);
  if (history.length === 0) return null;

  return (
    <div className="shrink-0 border-b border-white/10 bg-white/[0.03] px-2 py-1.5">
      {/* Scrolls rather than truncating: the whole point of keeping these is
          that a day you looked away for is still reachable. */}
      <ul
        className="space-y-0.5 overflow-y-auto"
        style={{ maxHeight: `${DAYS_BEFORE_SCROLL * 20}px` }}
      >
        {history.map((entry: DayData) => (
          <li key={entry.day}>
            <button
              type="button"
              onClick={() => showDay(entry)}
              title="Show this day's card again"
              className="flex w-full items-baseline gap-2 rounded px-1 py-0.5 text-left transition hover:bg-white/10"
            >
              <span className="shrink-0 font-mono text-[10px] tabular-nums text-amber-300/80">
                d{entry.day + 1}
              </span>
              <span className="min-w-0 flex-1 truncate text-[11px] text-slate-300">
                {entry.headline}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

interface RowProps {
  event: EventItem;
  onPick: (event: EventItem) => void;
}

const Row = memo(function Row({ event, onPick }: RowProps): React.ReactElement {
  return (
    <li>
      <button
        type="button"
        onClick={() => onPick(event)}
        className="flex w-full items-baseline gap-2 px-3 py-1.5 text-left transition hover:bg-white/5"
      >
        <span className="shrink-0 text-xs">{EVENT_EMOJI[event.type] ?? '•'}</span>
        <span className="min-w-0 flex-1 text-[11px] leading-snug text-slate-300">
          {event.summary}
        </span>
        <span className="shrink-0 font-mono text-[10px] tabular-nums text-slate-500">
          {event.tick}
        </span>
      </button>
    </li>
  );
});

export function EventFeed(): React.ReactElement {
  const seedEvents = useSimStore((state) => state.seedEvents);
  const requestFly = useSelectionStore((state) => state.requestFly);
  const select = useSelectionStore((state) => state.select);
  const [filter, setFilter] = useState<string>('all');

  const recent = useThrottledEvents(VISIBLE_ROWS * 4);

  useEffect(() => {
    void api
      .events(200)
      .then((payload) => seedEvents(payload.items as EventItem[]))
      .catch(() => {
        // Nothing to backfill; the socket will fill the feed as things happen.
      });
  }, [seedEvents]);

  const types = useMemo(() => {
    const seen = new Set(recent.map((event) => event.type));
    return ['all', ...[...seen].sort()];
  }, [recent]);

  const shown = useMemo(() => {
    const matching = filter === 'all' ? recent : recent.filter((event) => event.type === filter);
    return matching.slice(0, VISIBLE_ROWS);
  }, [recent, filter]);

  const onPick = useMemo(
    () => (event: EventItem) => {
      if (event.x !== null && event.z !== null) requestFly(event.x, event.z);
      if (event.actors.length > 0) select(event.actors[0] ?? null);
    },
    [requestFly, select],
  );

  return (
    <Panel title="Event log" badge={`${recent.length}`} className="max-h-96 w-80">
      <Chronicle />
      {types.length > 2 && (
        <div className="flex shrink-0 flex-wrap gap-1 border-b border-white/10 px-2 py-1.5">
          {types.map((type) => (
            <button
              key={type}
              type="button"
              onClick={() => setFilter(type)}
              className={`rounded px-1.5 py-0.5 text-[10px] transition ${
                filter === type
                  ? 'bg-white/20 text-slate-100'
                  : 'text-slate-500 hover:bg-white/10 hover:text-slate-300'
              }`}
            >
              {type === 'all' ? 'all' : `${EVENT_EMOJI[type] ?? '•'} ${type}`}
            </button>
          ))}
        </div>
      )}

      {shown.length === 0 ? (
        <Empty>Nothing yet. Births, deaths and hunts show up here.</Empty>
      ) : (
        <ul className="divide-y divide-white/5">
          {shown.map((event, index) => (
            <Row key={`${event.tick}-${event.type}-${index}`} event={event} onPick={onPick} />
          ))}
        </ul>
      )}
    </Panel>
  );
}
