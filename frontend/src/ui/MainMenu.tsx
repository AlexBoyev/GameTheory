/**
 * The first screen, and the one Escape comes back to (SPEC 9.4).
 *
 * The app used to drop you straight into a running island with no idea what
 * you were looking at or what the keys did - the help overlay existed, but
 * only if you thought to press `?`. This is where someone arriving for the
 * first time finds out what the thing is, and where someone mid-run goes to
 * stop and think.
 *
 * Layering: this sits at z-40, above the HUD. Help and the new-world dialog
 * are opened *from* here, so they sit at z-50 - at z-30 they rendered behind
 * this panel and the buttons looked dead.
 *
 * It pauses while it is open. A simulation running behind a menu you are
 * reading is a simulation you are not watching, and at 50x it would be a
 * different world by the time you pressed Start.
 */

import { keyFor } from '@/lib/keybindings';
import { Button } from '@/ui/primitives';

export interface MainMenuProps {
  /** False before the first Start, which decides the wording throughout. */
  started: boolean;
  onStart: () => void;
  onNewWorld: () => void;
  onHelp: () => void;
}

const WATCH_FOR: readonly { title: string; body: string }[] = [
  {
    title: 'They are not scripted',
    body: 'Every agent scores its options each tick - eat, drink, forage, hunt, talk, trade, lie, steal, fight - and picks from the best few. Click one to see the scores it used and why.',
  },
  {
    title: 'Trust is earned and spent',
    body: 'They remember who shared and who defected, gossip about each other, and sometimes lie about it. Reputation is hearsay; trust is first-hand.',
  },
  {
    title: 'Societies form on their own',
    body: 'Tribes get founded and joined, leaders get challenged and deposed, tribes sign pacts and declare war. None of it is staged - it emerges or it does not.',
  },
  {
    title: 'Strategies are inherited',
    body: 'Children are born with a parent strategy, sometimes mutated. Generations turn over, so what survives is whatever actually pays on this island.',
  },
];

/**
 * A short summary, named by action rather than by key.
 *
 * The keys themselves come from `KEYBINDINGS`, which is the same table the
 * handlers and the help overlay read - this screen spelling them out again
 * would be a third copy free to disagree with the other two, which is
 * exactly what that module exists to prevent.
 */
const SUMMARY: readonly { keys: string; what: string }[] = [
  { keys: keyFor('togglePlay'), what: 'play / pause' },
  { keys: `${keyFor('speed1')} – ${keyFor('speedMax')}`, what: 'speed, 1x to MAX' },
  { keys: keyFor('step'), what: 'one tick' },
  { keys: 'Click', what: 'inspect an agent' },
  { keys: keyFor('followSelected'), what: 'follow it' },
  {
    keys: `${keyFor('toggleCharts')} / ${keyFor('toggleLog')}`,
    what: 'charts / event log',
  },
  {
    keys: [keyFor('toggleTerritories'), keyFor('toggleTrustLines'), keyFor('toggleHeatmap')].join(
      ' / ',
    ),
    what: 'territories / trust / heatmap',
  },
  { keys: keyFor('reset'), what: 'new world' },
  { keys: keyFor('escapeBack'), what: 'back to this menu' },
  { keys: keyFor('toggleHelp'), what: 'full help' },
];

export function MainMenu({ started, onStart, onNewWorld, onHelp }: MainMenuProps): React.ReactElement {
  return (
    <div className="pointer-events-auto absolute inset-0 z-40 overflow-y-auto bg-slate-950/80 p-6 backdrop-blur-md">
      <div className="mx-auto flex min-h-full max-w-3xl flex-col justify-center gap-6 py-6">
        <header>
          <h1 className="text-3xl font-semibold tracking-tight text-slate-100">Game Theory</h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-300">
            An island of agents with needs, personalities and an inherited game-theory strategy.
            They forage and starve, trade and steal, befriend and betray, form tribes, depose
            leaders and go to war — and none of it is scripted. You are here to watch what a
            society does when nobody is telling it what to do.
          </p>
        </header>

        <div className="grid gap-3 sm:grid-cols-2">
          {WATCH_FOR.map((item) => (
            <section key={item.title} className="rounded-xl bg-white/5 p-3 ring-1 ring-white/10">
              <h2 className="text-[11px] font-semibold uppercase tracking-wide text-emerald-300">
                {item.title}
              </h2>
              <p className="mt-1 text-[12px] leading-relaxed text-slate-300">{item.body}</p>
            </section>
          ))}
        </div>

        <section className="rounded-xl bg-white/5 p-3 ring-1 ring-white/10">
          <h2 className="pb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            What happens, and when
          </h2>
          <p className="text-[12px] leading-relaxed text-slate-300">
            A day is 2,400 ticks. Measured on the default island: they are trading and fighting
            within the first minute, the first hut goes up around tick 200, the first tribe is
            founded by tick 600, and somebody is challenged for its leadership shortly after.
            Wars and raids start around day 1.5. Old age takes the first of them near day 8 — that
            is when strategies start being inherited rather than just played.
          </p>
          <p className="mt-1.5 text-[11px] leading-relaxed text-slate-500">
            Most of it is small and constant: hundreds of encounters a day, each one a game being
            played. Open the charts (C) to see the shape of it, or the log (L) to read it.
          </p>
        </section>

        <section className="rounded-xl bg-white/5 p-3 ring-1 ring-white/10">
          <h2 className="pb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            Controls
          </h2>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-3">
            {SUMMARY.map((binding) => (
              <div key={binding.what} className="flex items-baseline justify-between gap-2">
                <dt>
                  <kbd className="rounded bg-white/10 px-1.5 py-0.5 font-mono text-[10px] text-slate-200">
                    {binding.keys}
                  </kbd>
                </dt>
                <dd className="flex-1 text-right text-[11px] text-slate-400">{binding.what}</dd>
              </div>
            ))}
          </dl>
        </section>

        <footer className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={onStart}
            className="rounded-xl bg-emerald-500 px-5 py-2.5 text-sm font-semibold text-slate-900 shadow-lg transition hover:bg-emerald-400"
          >
            {started ? 'Resume' : 'Start'}
          </button>
          <Button onClick={onNewWorld}>New world…</Button>
          <Button onClick={onHelp}>Help</Button>
          <p className="ml-auto text-[11px] text-slate-500">
            {started ? 'Paused while this is open.' : 'Runs locally. No account, no cloud.'}
          </p>
        </footer>
      </div>
    </div>
  );
}
