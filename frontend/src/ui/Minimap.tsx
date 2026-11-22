/**
 * The whole island at a glance, with a camera marker (SPEC 9.4).
 *
 * Drawn on a 2D canvas on a timer rather than as React elements: it shows a
 * few hundred moving dots, and reconciling a few hundred DOM nodes eight
 * times a second would cost more than the 3D scene does. It reads the stores
 * non-reactively for the same reason.
 *
 * Clicking it flies the camera there, which is the fastest way to get from
 * "something is happening over there" to looking at it.
 */

import { useCallback, useEffect, useRef } from 'react';

import { tribeColor } from '@/lib/colors';
import { cameraState } from '@/state/cameraStore';
import { useSelectionStore } from '@/state/selectionStore';
import { simState, useSimStore } from '@/state/simStore';
import { useSocietyStore } from '@/state/societyStore';
import { useUiStore } from '@/state/uiStore';

const SIZE = 150;
const REDRAW_MS = 120;
const AGENT_DOT = 1.6;
const SELECTED_DOT = 3.2;

export function Minimap(): React.ReactElement | null {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const terrain = useSimStore((state) => state.terrain);
  const close = useUiStore((state) => state.set);
  const requestFly = useSelectionStore((state) => state.requestFly);
  const extent = terrain?.size ?? 256;

  /** World units -> canvas pixels. */
  const project = useCallback(
    (x: number, z: number): [number, number] => [
      ((x + extent / 2) / extent) * SIZE,
      ((z + extent / 2) / extent) * SIZE,
    ],
    [extent],
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext('2d');
    if (!context) return;

    const draw = (): void => {
      const { currentFrame } = simState();
      const { shelters } = useSocietyStore.getState();
      const selected = useSelectionStore.getState().selectedAgentId;

      context.clearRect(0, 0, SIZE, SIZE);

      // The island, as a disc: the real coastline is in the 3D view, and a
      // silhouette here would cost a terrain fetch for no extra meaning.
      context.fillStyle = 'rgba(56, 86, 112, 0.55)';
      context.beginPath();
      context.arc(SIZE / 2, SIZE / 2, SIZE * 0.47, 0, Math.PI * 2);
      context.fill();
      context.strokeStyle = 'rgba(148, 183, 210, 0.35)';
      context.stroke();

      context.fillStyle = 'rgba(214, 190, 150, 0.8)';
      for (const shelter of shelters) {
        const [px, py] = project(shelter.x, shelter.z);
        context.fillRect(px - 1.5, py - 1.5, 3, 3);
      }

      if (currentFrame && currentFrame.stride > 0) {
        const { agents, stride } = currentFrame;
        const total = Math.floor(agents.length / stride);
        for (let index = 0; index < total; index += 1) {
          const offset = index * stride;
          const id = agents[offset] ?? 0;
          const [px, py] = project(agents[offset + 1] ?? 0, agents[offset + 2] ?? 0);
          const isSelected = id === selected;
          context.fillStyle = isSelected ? '#ffffff' : tribeColor(agents[offset + 5] ?? -1);
          context.beginPath();
          context.arc(px, py, isSelected ? SELECTED_DOT : AGENT_DOT, 0, Math.PI * 2);
          context.fill();
        }
      }

      // Where the camera is looking, and roughly how much it can see.
      const view = cameraState();
      const [cx, cy] = project(view.x, view.z);
      const reach = Math.max(6, (view.distance / extent) * SIZE);
      context.save();
      context.translate(cx, cy);
      context.rotate(-view.heading);
      context.fillStyle = 'rgba(248, 250, 252, 0.22)';
      context.beginPath();
      context.moveTo(0, 0);
      context.lineTo(-reach * 0.6, -reach);
      context.lineTo(reach * 0.6, -reach);
      context.closePath();
      context.fill();
      context.restore();

      context.strokeStyle = '#f8fafc';
      context.lineWidth = 1.5;
      context.beginPath();
      context.arc(cx, cy, 2.5, 0, Math.PI * 2);
      context.stroke();
    };

    draw();
    const timer = setInterval(draw, REDRAW_MS);
    return () => clearInterval(timer);
  }, [extent, project]);

  const onClick = (event: React.MouseEvent<HTMLCanvasElement>): void => {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * extent - extent / 2;
    const z = ((event.clientY - rect.top) / rect.height) * extent - extent / 2;
    requestFly(x, z);
  };

  return (
    <div className="pointer-events-auto overflow-hidden rounded-2xl bg-slate-900/85 shadow-lg ring-1 ring-white/10 backdrop-blur">
      <div className="flex items-center gap-2 border-b border-white/10 px-2 py-1">
        <span className="text-[9px] uppercase tracking-wider text-slate-500">Island</span>
        <button
          type="button"
          onClick={() => close('minimapOpen', false)}
          aria-label="Close minimap"
          className="ml-auto rounded px-1 text-slate-500 transition hover:bg-white/10 hover:text-slate-200"
        >
          ×
        </button>
      </div>
      <canvas
        ref={canvasRef}
        width={SIZE}
        height={SIZE}
        onClick={onClick}
        title="Click to fly the camera there"
        className="block cursor-crosshair"
      />
    </div>
  );
}
