/** Play, pause, step, speed and reset - the observer's hands. */

import { SPEED_PRESETS, speedLabel, useSimControls } from '@/app/useSimControls';
import { ResetDialog } from '@/ui/ResetDialog';
import { Button } from '@/ui/primitives';
import { usePerfStore } from '@/state/perfStore';
import { useScreenshotStore } from '@/state/screenshotStore';
import { useSettingsStore, type Quality } from '@/state/settingsStore';
import { useSimStore } from '@/state/simStore';
import { useUiStore } from '@/state/uiStore';

const QUALITIES: Quality[] = ['low', 'med', 'high'];

/** Ticks a second at 1x: the engine runs 1/dt of them, and dt is 0.1. */
const TICKS_PER_SECOND_AT_1X = 10;

/** A day is 240 sim-seconds at dt 0.1. */
const TICKS_PER_DAY = 2400;

/** Jumps worth offering: a glance, a scene, and a decent chunk of a day. */
const STEPS = [50, 100, 500] as const;

/**
 * Skips worth offering, in days.
 *
 * The interesting part of a run is days 8 to 20, where agents start dying of
 * old age and strategies are inherited rather than merely played. Getting
 * there in real time is minutes of watching, and the day is the unit the
 * world actually changes in - so half a day and a day are the jumps, and the
 * engine runs them in chunks with a progress bar rather than freezing.
 */
const SKIPS: ReadonlyArray<readonly [string, number]> = [
  ['½ day', TICKS_PER_DAY / 2],
  ['1 day', TICKS_PER_DAY],
];

export function ControlBar(): React.ReactElement {
  const controls = useSimControls();
  const status = useSimStore((state) => state.status);
  const speed = useSimStore((state) => state.speed);
  const ticksPerSecond = useSimStore((state) => state.ticksPerSecond);
  const quality = useSettingsStore((state) => state.quality);
  const setQuality = useSettingsStore((state) => state.setQuality);
  const fps = usePerfStore((state) => state.fps);
  const drawCalls = usePerfStore((state) => state.drawCalls);
  const triangles = usePerfStore((state) => state.triangles);
  const framesPerSecond = usePerfStore((state) => state.framesPerSecond);
  const resetOpen = useUiStore((state) => state.resetOpen);
  const setResetOpen = (open: boolean): void => useUiStore.getState().set('resetOpen', open);
  const requestShot = useScreenshotStore((state) => state.request);
  const shotFailed = useScreenshotStore((state) => state.lastSucceeded);

  const skipRemaining = useSimStore((state) => state.skipRemaining);
  const running = status === 'running';
  const skipping = skipRemaining > 0;

  // What the engine is actually delivering against what was asked for. A
  // big population simply cannot be ticked at 25x - measured, 300 agents
  // tops out near 10x - and the honest thing is to say so rather than let
  // the speed buttons imply a promise the machine cannot keep.
  const targetTicksPerSecond = speed > 0 ? speed * TICKS_PER_SECOND_AT_1X : 0;
  const actualMultiple = ticksPerSecond / TICKS_PER_SECOND_AT_1X;
  const behind =
    running && targetTicksPerSecond > 0 && ticksPerSecond < targetTicksPerSecond * 0.75;

  return (
    <>
      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 flex justify-center p-3">
        <div className="pointer-events-auto flex flex-wrap items-center gap-1.5 rounded-2xl bg-slate-900/85 px-3 py-2 shadow-xl ring-1 ring-white/10 backdrop-blur">
          <Button onClick={() => void controls.toggle()} title="Play / pause (Space)">
            {running ? '⏸ Pause' : '▶ Play'}
          </Button>
          <Button onClick={() => void controls.step(1)} title="Step one tick (.)">
            ⏭ Step
          </Button>
          {/* A day is 2,400 ticks, so +500 is about a fifth of one - enough to
              see a tribe form or a war start without sitting through it. */}
          {STEPS.map((count) => (
            <Button
              key={count}
              onClick={() => void controls.step(count)}
              title={`Step ${count} ticks (${(count / TICKS_PER_DAY).toFixed(2)} of a day)`}
            >
              +{count}
            </Button>
          ))}
          {SKIPS.map(([label, count]) => (
            <Button
              key={label}
              onClick={() => void controls.step(count)}
              title={`Fast-forward ${count.toLocaleString()} ticks. Runs as fast as the machine can, showing progress; Pause cancels it.`}
            >
              {'»'} {label}
            </Button>
          ))}

          {skipping && (
            <span
              className="px-1 font-mono text-[10px] text-sky-300"
              title="Ticks still to run. Pause stops it where it is."
            >
              {'»'} {skipRemaining.toLocaleString()} left
            </span>
          )}

          <span className="mx-1 h-6 w-px bg-white/10" />

          {SPEED_PRESETS.map((preset) => (
            <Button
              key={preset}
              active={running && speed === preset}
              onClick={() => void controls.setSpeed(preset)}
              title={`Speed ${speedLabel(preset)}`}
            >
              {speedLabel(preset)}
            </Button>
          ))}

          <span className="mx-1 h-6 w-px bg-white/10" />

          <span
            className={`px-1 font-mono text-[10px] ${behind ? 'text-amber-400' : 'text-slate-400'}`}
            title={
              behind
                ? `Asked for ${speed}x, managing about ${actualMultiple.toFixed(0)}x. ` +
                  'The island is larger than this machine can tick that fast; it runs ' +
                  'as fast as it can rather than falling behind. Fewer agents go faster.'
                : 'Simulation ticks per second (trailing 1s average, measured by the engine)'
            }
          >
            {ticksPerSecond.toFixed(0)} tps{behind ? ` · ${actualMultiple.toFixed(0)}x` : ''}
          </span>
          <span
            className={`px-1 font-mono text-[10px] ${fps > 0 && fps < 30 ? 'text-amber-400' : 'text-slate-400'}`}
            title={`Render: ${fps} fps, ${drawCalls} draw calls, ${(triangles / 1000).toFixed(0)}k triangles. Socket: ${framesPerSecond} frames/s.`}
          >
            {fps} fps · {drawCalls} dc
          </span>

          <span className="mx-1 h-6 w-px bg-white/10" />

          {QUALITIES.map((option) => (
            <Button
              key={option}
              active={quality === option}
              onClick={() => setQuality(option)}
              title={`Render quality: ${option}`}
            >
              {option}
            </Button>
          ))}

          <Button onClick={requestShot} title="Save a PNG of the island">
            📷
          </Button>
          {shotFailed === false && (
            <span
              className="px-1 text-[10px] text-amber-300"
              title="The browser would not export the canvas"
            >
              no image
            </span>
          )}

          <Button onClick={() => setResetOpen(true)} tone="danger" title="New world (R)">
            ⟲ Reset
          </Button>
        </div>
      </div>

      {resetOpen && <ResetDialog onClose={() => setResetOpen(false)} />}
    </>
  );
}
