/** A name and what they are doing, following the cursor. */

import { useEffect, useState } from 'react';

import { readPose } from '@/lib/interpolation';
import { STATE_EMOJI } from '@/lib/stateIcons';
import { useSelectionStore } from '@/state/selectionStore';
import { simState } from '@/state/simStore';

/**
 * The hovered agent's state is read from the latest frame rather than fetched:
 * a tooltip must not fire HTTP requests as the cursor sweeps across a crowd.
 */
function stateNameOf(agentId: number): string | null {
  const { currentFrame, legend } = simState();
  if (!currentFrame || currentFrame.stride <= 0) return null;

  const total = Math.floor(currentFrame.agents.length / currentFrame.stride);
  for (let index = 0; index < total; index += 1) {
    const pose = readPose(currentFrame, index);
    if (pose?.id === agentId) return legend?.states[pose.state] ?? null;
  }
  return null;
}

export function HoverTooltip(): React.ReactElement | null {
  const hoveredAgentId = useSelectionStore((state) => state.hoveredAgentId);
  const [cursor, setCursor] = useState({ x: 0, y: 0 });

  useEffect(() => {
    const move = (event: PointerEvent): void => setCursor({ x: event.clientX, y: event.clientY });
    window.addEventListener('pointermove', move);
    return () => window.removeEventListener('pointermove', move);
  }, []);

  if (hoveredAgentId === null) return null;

  const stateName = stateNameOf(hoveredAgentId);

  return (
    <div
      className="pointer-events-none fixed z-20 -translate-y-full rounded-lg bg-slate-900/90 px-2 py-1 text-[11px] text-slate-200 shadow-lg ring-1 ring-white/10"
      style={{ left: cursor.x + 12, top: cursor.y - 8 }}
    >
      <span className="font-mono text-slate-400">#{hoveredAgentId}</span>
      {stateName && (
        <>
          {' '}
          <span>{STATE_EMOJI[stateName] ?? ''}</span> <span>{stateName}</span>
        </>
      )}
      <span className="ml-1.5 text-slate-500">click to inspect</span>
    </div>
  );
}
