/**
 * Everything about one agent: needs, personality, what it is doing and why.
 *
 * The decision trace is the point of this panel. Utility AI is otherwise a
 * black box - seeing "Drink 1.12 beat Gather 0.41" is the difference between
 * watching beans wobble and understanding a decision.
 */

import { useAgentDetail } from '@/app/useAgentDetail';
import { tribeColor } from '@/lib/colors';
import { STATE_EMOJI } from '@/lib/stateIcons';
import { Empty, Meter, Panel, Row } from '@/ui/primitives';
import { TraitRadar } from '@/ui/TraitRadar';
import { useSelectionStore } from '@/state/selectionStore';

const TRAIT_ORDER = [
  'aggression',
  'honesty',
  'loyalty',
  'greed',
  'sociability',
  'cunning',
  'courage',
  'charisma',
] as const;

export function Inspector(): React.ReactElement | null {
  const selectedAgentId = useSelectionStore((state) => state.selectedAgentId);
  const following = useSelectionStore((state) => state.following);
  const toggleFollow = useSelectionStore((state) => state.toggleFollow);
  const clear = useSelectionStore((state) => state.clear);
  const requestFly = useSelectionStore((state) => state.requestFly);
  const { detail, error } = useAgentDetail(selectedAgentId);

  if (selectedAgentId === null) return null;

  // The generated DTO marks fields with server-side defaults as optional.
  const trace = detail?.decision_trace ?? [];
  const memories = detail?.memories ?? [];
  const carriedFood = detail?.inventory?.food ?? 0;
  // Present only for deliberative agents; absent means "does not think",
  // which is different from "has not thought yet".
  const mind = detail?.llm ?? null;

  return (
    <Panel
      title={detail ? detail.summary.name : `Agent ${selectedAgentId}`}
      badge={detail ? `#${detail.summary.id}` : undefined}
      onClose={clear}
      className="max-h-[calc(100vh-11rem)] w-72"
    >
      {error && !detail && <Empty>Could not load this agent: {error}</Empty>}
      {!detail && !error && <Empty>Loading...</Empty>}

      {detail && (
        <div className="space-y-3 p-3">
          <div className="flex items-center gap-2">
            <span
              className="h-3 w-3 shrink-0 rounded-full ring-1 ring-white/20"
              style={{ backgroundColor: tribeColor(detail.summary.tribe_id ?? -1) }}
            />
            <span className="text-[11px] text-slate-300">
              {detail.life_stage}, age {detail.age.toFixed(0)}
            </span>
            <span className="ml-auto text-[11px] text-slate-400">
              {detail.summary.alive ? `${detail.summary.health.toFixed(0)} hp` : 'dead'}
            </span>
          </div>

          <div className="rounded-lg bg-slate-800/60 p-2">
            <p className="text-[10px] uppercase tracking-wide text-slate-400">Doing</p>
            <p className="text-sm text-slate-100">
              {STATE_EMOJI[detail.summary.state] ?? '•'} {detail.current_skill ?? 'nothing'}
            </p>
            {detail.thought && (
              <p className="mt-1 text-[11px] italic text-slate-400">
                &ldquo;{detail.thought}&rdquo;
              </p>
            )}
          </div>

          <Section title="Needs">
            <div className="space-y-1">
              <Meter label="hunger" value={detail.needs.hunger} />
              <Meter label="thirst" value={detail.needs.thirst} />
              <Meter label="energy" value={detail.needs.energy} />
              <Meter label="safety" value={detail.needs.safety} />
              <Meter label="social" value={detail.needs.social} />
            </div>
          </Section>

          {trace.length > 0 && (
            <Section title="Why this, not that">
              <ul className="space-y-1">
                {trace.map((option) => (
                  <li
                    key={option.skill}
                    className={`rounded px-1.5 py-0.5 text-[11px] ${
                      option.chosen ? 'bg-emerald-500/15 text-emerald-200' : 'text-slate-400'
                    }`}
                  >
                    <div className="flex items-baseline justify-between gap-2">
                      <span>
                        {option.chosen ? '→ ' : ''}
                        {option.skill}
                      </span>
                      <span className="font-mono tabular-nums">{option.score.toFixed(2)}</span>
                    </div>
                    {/* The named inputs the score is made of, which add up to
                        it. Absent for skills that score themselves directly. */}
                    {(option.because ?? []).map((reason) => (
                      <div
                        key={reason.name}
                        className="flex items-baseline justify-between gap-2 pl-3 text-[10px] text-slate-500"
                      >
                        <span className="truncate">{reason.name}</span>
                        <span className="font-mono tabular-nums">
                          +{reason.score.toFixed(2)}
                        </span>
                      </div>
                    ))}
                  </li>
                ))}
              </ul>
            </Section>
          )}

          <Section title="Personality">
            <TraitRadar traits={detail.traits} order={TRAIT_ORDER} />
          </Section>

          <Section title="Facts">
            <Row label="strategy" value={detail.summary.strategy} />
            <Row label="brain" value={detail.summary.brain_type} />
            <Row
              label="tribe"
              value={detail.summary.tribe_id === null ? 'none' : `#${detail.summary.tribe_id}`}
            />
            <Row label="food carried" value={carriedFood.toFixed(1)} />
            <Row
              label="position"
              value={`${detail.summary.x.toFixed(0)}, ${detail.summary.z.toFixed(0)}`}
            />
          </Section>

          {mind && (
            <Section title="Deliberating">
              {mind.goal ? (
                <p className="text-[11px] text-slate-200">{mind.goal}</p>
              ) : (
                <p className="text-[11px] text-slate-500">no plan yet</p>
              )}
              {mind.thought && (
                <p className="mt-1 text-[11px] italic text-slate-400">
                  &ldquo;{mind.thought}&rdquo;
                </p>
              )}
              {(mind.plan ?? []).length > 0 && (
                <ol className="mt-1 space-y-0.5">
                  {(mind.plan ?? []).map((step, index) => (
                    <li key={`${step}-${index}`} className="text-[11px] text-slate-300">
                      <span className="font-mono text-slate-500">{index + 1}.</span> {step}
                    </li>
                  ))}
                </ol>
              )}
              {(mind.beliefs ?? []).length > 0 && (
                <>
                  <p className="mt-2 text-[10px] uppercase tracking-wide text-slate-500">
                    Has come to believe
                  </p>
                  <ul className="space-y-0.5">
                    {(mind.beliefs ?? []).map((belief, index) => (
                      <li key={`${belief}-${index}`} className="text-[11px] text-amber-200/80">
                        {belief}
                      </li>
                    ))}
                  </ul>
                </>
              )}
              {mind.last_prompt && (
                <details className="mt-2">
                  <summary className="cursor-pointer text-[10px] uppercase tracking-wide text-slate-500">
                    Last prompt and reply
                  </summary>
                  <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded bg-black/30 p-2 text-[10px] text-slate-400">
                    {mind.last_prompt}
                  </pre>
                  <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap break-words rounded bg-black/30 p-2 text-[10px] text-slate-400">
                    {mind.last_response || '(no reply)'}
                  </pre>
                </details>
              )}
            </Section>
          )}

          {memories.length > 0 && (
            <Section title="Remembers">
              <ul className="space-y-0.5">
                {memories.map((memory, index) => (
                  <li key={`${memory.tick}-${index}`} className="text-[11px] text-slate-400">
                    <span className="font-mono text-slate-500">{memory.tick}</span> {memory.summary}
                  </li>
                ))}
              </ul>
            </Section>
          )}

          <div className="flex gap-2 pt-1">
            <button
              type="button"
              onClick={toggleFollow}
              className={`flex-1 rounded-lg px-2 py-1.5 text-[11px] font-medium transition ${
                following
                  ? 'bg-emerald-500/90 text-slate-900'
                  : 'bg-white/10 text-slate-200 hover:bg-white/20'
              }`}
            >
              {following ? 'Following (F)' : 'Follow (F)'}
            </button>
            <button
              type="button"
              onClick={() => requestFly(detail.summary.x, detail.summary.z)}
              className="flex-1 rounded-lg bg-white/10 px-2 py-1.5 text-[11px] font-medium text-slate-200 transition hover:bg-white/20"
            >
              Fly to
            </button>
          </div>
        </div>
      )}
    </Panel>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}): React.ReactElement {
  return (
    <div>
      <p className="mb-1 text-[10px] uppercase tracking-wide text-slate-500">{title}</p>
      {children}
    </div>
  );
}
