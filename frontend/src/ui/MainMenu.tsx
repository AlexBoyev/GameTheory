/**
 * The first screen, and the one Escape comes back to (SPEC 9.4).
 *
 * The app used to drop you straight into a running island with no idea what
 * you were looking at or what the keys did - the help overlay existed, but
 * only if you thought to press `?`. This is where someone arriving for the
 * first time finds out what the thing is, and where someone mid-run goes to
 * stop and think.
 *
 * It pauses while it is open. A simulation running behind a menu you are
 * reading is a simulation you are not watching, and at 50x it would be a
 * different world by the time you pressed Start.
 */

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

const KEYS: readonly { key: string; what: string }[] = [
  { key: 'Space', what: 'play / pause' },
  { key: '1 – 7', what: 'speed, 1x to MAX' },
  { key: '.', what: 'one tick' },
  { key: 'Click', what: 'inspect an agent' },
  { key: 'F', what: 'follow it' },
  { key: 'C / L', what: 'charts / event log' },
  { key: 'G / T / H', what: 'territories / trust / heatmap' },
  { key: 'R', what: 'new world' },
  { key: 'Esc', what: 'back to this menu' },
  { key: '?', what: 'full help' },
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
            Controls
          </h2>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-3">
            {KEYS.map((binding) => (
              <div key={binding.key} className="flex items-baseline justify-between gap-2">
                <dt>
                  <kbd className="rounded bg-white/10 px-1.5 py-0.5 font-mono text-[10px] text-slate-200">
                    {binding.key}
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
