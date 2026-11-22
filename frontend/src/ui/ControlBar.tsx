/** Play, pause, step, speed and reset - the observer's hands. */

import { useState } from 'react';

import { SPEED_PRESETS, speedLabel, useSimControls } from '@/app/useSimControls';
import { saveScreenshot } from '@/lib/screenshot';
import { ResetDialog } from '@/ui/ResetDialog';
import { Button } from '@/ui/primitives';
import { usePerfStore } from '@/state/perfStore';
import { useSettingsStore, type Quality } from '@/state/settingsStore';
import { useSimStore } from '@/state/simStore';
import { useUiStore } from '@/state/uiStore';

const QUALITIES: Quality[] = ['low', 'med', 'high'];

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
  const tick = useSimStore((state) => state.tick);
  const resetOpen = useUiStore((state) => state.resetOpen);
  const setResetOpen = (open: boolean): void => useUiStore.getState().set('resetOpen', open);
  const [shotFailed, setShotFailed] = useState(false);

  const running = status === 'running';

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
          <Button onClick={() => void controls.step(50)} title="Step 50 ticks">
            +50
          </Button>

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
            className="px-1 font-mono text-[10px] text-slate-400"
            title="Simulation ticks per second (trailing 1s average, measured by the engine)"
          >
            {ticksPerSecond.toFixed(0)} tps
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

          <Button
            onClick={() => {
              if (!saveScreenshot(tick)) setShotFailed(true);
            }}
            title="Save a PNG of the island"
          >
            📷
          </Button>
          {shotFailed && (
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
