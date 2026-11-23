/**
 * What am I looking at? - the legend, the controls and the links.
 *
 * Opened with `?`, and from the TopBar. This is deliberately the one place
 * that explains the simulation in words, because the island does not explain
 * itself.
 */

import { BIOME_COLORS } from '@/lib/colors';
import { KEYBINDINGS } from '@/lib/keybindings';
import { STATE_EMOJI } from '@/lib/stateIcons';
import { Panel } from '@/ui/primitives';

export interface HelpOverlayProps {
  onClose: () => void;
  backendOrigin: string;
}

const RESOURCE_LEGEND: { colour: string; label: string; note: string }[] = [
  {
    colour: '#7fae6b',
    label: 'Berry bush',
    note: 'Food. Shrinks as it is picked; regrows, but not in winter.',
  },
  { colour: '#5f9465', label: 'Tree', note: 'Wood, for shelters once building lands.' },
  {
    colour: '#f1e7dc',
    label: 'Rabbit',
    note: 'Small food, hunted alone - a dice roll on courage.',
  },
  { colour: '#b98c62', label: 'Deer', note: 'Big food, needs two hunters: a Stag Hunt.' },
  { colour: '#b3b0a8', label: 'Stone', note: 'Scenery - nothing is built from it yet.' },
  { colour: '#9c6a6a', label: 'Corpse', note: 'A body leaves food behind, briefly.' },
];

export function HelpOverlay({ onClose, backendOrigin }: HelpOverlayProps): React.ReactElement {
  const groups = ['simulation', 'camera', 'overlays'] as const;

  return (
    <div className="pointer-events-auto absolute inset-0 z-30 overflow-y-auto bg-slate-950/70 p-4 backdrop-blur-sm">
      <div className="mx-auto max-w-4xl">
        <Panel title="Game Theory - what you are watching" onClose={onClose}>
          <div className="grid gap-4 p-4 md:grid-cols-2">
            <section className="md:col-span-2">
              <p className="text-[12px] leading-relaxed text-slate-300">
                An island of agents, each with needs, a personality and an inherited game-theory
                strategy. Nobody is scripted: every bean is choosing, every tick, between eating,
                drinking, sleeping, foraging, hunting and running away - by scoring each option and
                picking from the top few. Click one to see the scores it used.
              </p>
              <p className="mt-2 text-[12px] leading-relaxed text-slate-400">
                Survival is only the floor. They also trust, gossip, lie, detect lies, trade,
                bribe, betray, found tribes, depose leaders, go to war, sue for peace and sign
                pacts - and a few of them think it through with a local LLM, out loud.
              </p>
            </section>

            <Group title="The emoji above their heads">
              <ul className="grid grid-cols-2 gap-x-3 gap-y-1">
                {Object.entries(STATE_EMOJI).map(([state, emoji]) => (
                  <li key={state} className="text-[11px] text-slate-300">
                    <span className="mr-1.5">{emoji}</span>
                    {state}
                  </li>
                ))}
                <li className="text-[11px] text-slate-500">
                  <span className="mr-1.5">·</span>no icon = wandering or walking
                </li>
              </ul>
            </Group>

            <Group title="Things on the ground">
              <ul className="space-y-1">
                {RESOURCE_LEGEND.map((entry) => (
                  <li key={entry.label} className="flex gap-2 text-[11px]">
                    <span
                      className="mt-0.5 h-3 w-3 shrink-0 rounded-full ring-1 ring-white/20"
                      style={{ backgroundColor: entry.colour }}
                    />
                    <span className="text-slate-300">
                      <span className="text-slate-100">{entry.label}</span> - {entry.note}
                    </span>
                  </li>
                ))}
              </ul>
            </Group>

            <Group title="The island">
              <ul className="space-y-1">
                {Object.entries(BIOME_COLORS).map(([biome, colour]) => (
                  <li key={biome} className="flex items-center gap-2 text-[11px] text-slate-300">
                    <span
                      className="h-3 w-3 rounded ring-1 ring-white/20"
                      style={{ backgroundColor: colour }}
                    />
                    {biome}
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-[11px] text-slate-500">
                Agents cannot walk on water, and they drink at spots on the shore. Berries grow in
                meadow and forest; deer keep to the trees and hills.
              </p>
            </Group>

            <Group title="Tribe rings (press G)">
              <p className="text-[11px] leading-relaxed text-slate-300">
                A ring around a camp is a tribe's territory, drawn from where its members actually
                are, so it breathes as they forage. The ring turns{' '}
                <span className="text-red-300">red</span> while that tribe is at war, and grows a
                second thin <span className="text-emerald-300">green</span> ring inside it while it
                holds a pact with another tribe. The post in the middle is the camp itself, where
                the common food store lives.
              </p>
            </Group>

            <Group title="A bean's colour">
              <p className="text-[11px] leading-relaxed text-slate-300">
                Beige means no tribe; once one forms, its members take its colour. A pale gold glow
                marks an agent with an LLM mind. Size follows age, and the selected agent wears a
                white ring.
              </p>
            </Group>

            {groups.map((group) => (
              <Group key={group} title={`Keys - ${group}`}>
                <ul className="space-y-0.5">
                  {KEYBINDINGS.filter((binding) => binding.group === group).map((binding) => (
                    <li
                      key={binding.action}
                      className="flex items-baseline justify-between gap-3 text-[11px]"
                    >
                      <span className="text-slate-400">{binding.label}</span>
                      <kbd className="rounded bg-white/10 px-1.5 py-0.5 font-mono text-[10px] text-slate-200">
                        {binding.key === ' ' ? 'Space' : binding.key}
                      </kbd>
                    </li>
                  ))}
                </ul>
                {group === 'camera' && (
                  <p className="mt-1.5 text-[10px] text-slate-500">
                    Also: drag to orbit, wheel to zoom, WASD or arrows to pan, Q/E to rotate,
                    double-click to fly somewhere.
                  </p>
                )}
                {group === 'overlays' && (
                  <p className="mt-1.5 text-[10px] text-slate-500">
                    Trust lines, territories and the heatmap need Phase 4 data - the keys are wired,
                    the overlays are not drawn yet.
                  </p>
                )}
              </Group>
            ))}

            <Group title="Drive it from anywhere">
              <p className="mb-1.5 text-[11px] text-slate-400">
                Everything these buttons do is an HTTP call, and this UI follows the engine within a
                second - so you can steer it from a terminal and watch the result here.
              </p>
              <pre className="overflow-x-auto rounded-lg bg-slate-950/70 p-2 text-[10px] leading-relaxed text-slate-300">
                {`POST ${backendOrigin}/api/sim/start
POST ${backendOrigin}/api/sim/pause
POST ${backendOrigin}/api/sim/speed   {"multiplier": 10}
POST ${backendOrigin}/api/sim/step    {"n": 50}
POST ${backendOrigin}/api/sim/reset   {"seed": 7}
GET  ${backendOrigin}/api/agents
GET  ${backendOrigin}/api/agents/0
GET  ${backendOrigin}/api/events?limit=50`}
              </pre>
              <p className="mt-1.5 text-[11px] text-slate-400">
                Full interactive docs:{' '}
                <a
                  className="text-sky-300 underline hover:text-sky-200"
                  href={`${backendOrigin}/docs`}
                  target="_blank"
                  rel="noreferrer"
                >
                  {backendOrigin}/docs
                </a>
              </p>
            </Group>

            <Group title="This page's URL">
              <p className="text-[11px] leading-relaxed text-slate-400">
                The URL tracks what you are looking at, so a link restores it:
              </p>
              <pre className="mt-1.5 overflow-x-auto rounded-lg bg-slate-950/70 p-2 text-[10px] text-slate-300">
                {`?agent=12&speed=10&panels=log,inspector&help=1`}
              </pre>
              <p className="mt-1.5 text-[11px] text-slate-500">
                <code>speed</code> is applied on load, so a link can start the world running at a
                chosen rate.
              </p>
            </Group>
          </div>
        </Panel>
      </div>
    </div>
  );
}

function Group({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}): React.ReactElement {
  return (
    <section className="rounded-xl bg-slate-800/40 p-3">
      <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-300">
        {title}
      </h3>
      {children}
    </section>
  );
}
