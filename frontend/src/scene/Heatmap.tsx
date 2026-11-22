/**
 * Where the island is actually used (overlay `h`).
 *
 * Accumulated in the browser from the frames already arriving rather than
 * asked for from the backend: the data is a side effect of rendering, so the
 * simulation pays nothing for it, and it starts from the moment you switch
 * the overlay on - which is usually what you want ("where have they been
 * since the drought?").
 *
 * Drawn as a single canvas texture on one plane, so the cost is one draw call
 * and one texture upload a second however many cells it has.
 */

import { useFrame } from '@react-three/fiber';
import { useEffect, useRef } from 'react';
import * as THREE from 'three';

import { simState, useSimStore } from '@/state/simStore';

const CELLS = 64;
const UPLOAD_INTERVAL_MS = 500;
const SAMPLE_INTERVAL_MS = 100;
/** Each sample fades by this much per upload, so the map follows recent life. */
const DECAY = 0.985;
const HEIGHT_ABOVE_WATER = 0.35;

/** Blue (cold) through amber to red (busy), as a flat lookup. */
function heatColour(value: number, out: [number, number, number, number]): void {
  const heat = Math.min(1, value);
  if (heat <= 0.001) {
    out[3] = 0;
    return;
  }
  // Two linear ramps: cold -> amber -> hot. Cheap, and reads correctly.
  if (heat < 0.5) {
    const ratio = heat / 0.5;
    out[0] = Math.round(56 + ratio * 190);
    out[1] = Math.round(120 + ratio * 60);
    out[2] = Math.round(190 - ratio * 150);
  } else {
    const ratio = (heat - 0.5) / 0.5;
    out[0] = Math.round(246 - ratio * 20);
    out[1] = Math.round(180 - ratio * 130);
    out[2] = Math.round(40 - ratio * 20);
  }
  out[3] = Math.round(40 + heat * 160);
}

export function Heatmap(): React.ReactElement | null {
  const terrain = useSimStore((state) => state.terrain);
  const epoch = useSimStore((state) => state.worldEpoch);
  const extent = terrain?.size ?? 256;

  // Everything mutable lives in refs and is attached to the material
  // imperatively, the same way `StateIcons` drives its instanced meshes: the
  // React compiler forbids both mutating a memo/state value after render and
  // reading a ref during one, so the texture is never named in the JSX.
  const counts = useRef(new Float32Array(CELLS * CELLS));
  const lastSample = useRef(0);
  const lastUpload = useRef(0);
  const surface = useRef<{ canvas: HTMLCanvasElement; texture: THREE.CanvasTexture } | null>(null);
  const material = useRef<THREE.MeshBasicMaterial>(null);

  useEffect(() => {
    const canvas = document.createElement('canvas');
    canvas.width = CELLS;
    canvas.height = CELLS;
    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.magFilter = THREE.LinearFilter;
    surface.current = { canvas, texture };
    if (material.current) {
      material.current.map = texture;
      material.current.needsUpdate = true;
    }
    return () => {
      texture.dispose();
      surface.current = null;
    };
  }, []);

  // A new world is a new map; the old one would be a lie about this island.
  useEffect(() => {
    counts.current.fill(0);
  }, [epoch]);

  useFrame(() => {
    const now = performance.now();
    if (now - lastSample.current >= SAMPLE_INTERVAL_MS) {
      lastSample.current = now;
      const { currentFrame } = simState();
      if (currentFrame && currentFrame.stride > 0) {
        const { agents, stride } = currentFrame;
        const total = Math.floor(agents.length / stride);
        for (let index = 0; index < total; index += 1) {
          const offset = index * stride;
          const column = Math.floor((((agents[offset + 1] ?? 0) + extent / 2) / extent) * CELLS);
          const row = Math.floor((((agents[offset + 2] ?? 0) + extent / 2) / extent) * CELLS);
          if (column < 0 || column >= CELLS || row < 0 || row >= CELLS) continue;
          const cell = row * CELLS + column;
          const grid = counts.current;
          grid[cell] = (grid[cell] ?? 0) + 1;
        }
      }
    }

    if (now - lastUpload.current < UPLOAD_INTERVAL_MS) return;
    lastUpload.current = now;

    const drawn = surface.current;
    if (!drawn) return;
    const context = drawn.canvas.getContext('2d');
    if (!context) return;

    const grid = counts.current;
    let peak = 0;
    for (let index = 0; index < grid.length; index += 1) {
      const value = (grid[index] ?? 0) * DECAY;
      grid[index] = value;
      if (value > peak) peak = value;
    }
    if (peak <= 0) {
      context.clearRect(0, 0, CELLS, CELLS);
      drawn.texture.needsUpdate = true;
      return;
    }

    const image = context.createImageData(CELLS, CELLS);
    const pixel: [number, number, number, number] = [0, 0, 0, 0];
    for (let index = 0; index < grid.length; index += 1) {
      // Normalised against the busiest cell, so the scale is always readable
      // whether the island holds 20 agents or 500.
      heatColour((grid[index] ?? 0) / peak, pixel);
      const base = index * 4;
      image.data[base] = pixel[0];
      image.data[base + 1] = pixel[1];
      image.data[base + 2] = pixel[2];
      image.data[base + 3] = pixel[3];
    }
    context.putImageData(image, 0, 0);
    drawn.texture.needsUpdate = true;
  });

  if (!terrain) return null;

  return (
    <mesh
      rotation={[-Math.PI / 2, 0, 0]}
      position={[0, (terrain.water_level ?? 0) + HEIGHT_ABOVE_WATER, 0]}
      renderOrder={2}
    >
      <planeGeometry args={[extent, extent]} />
      <meshBasicMaterial ref={material} transparent depthWrite={false} toneMapped={false} />
    </mesh>
  );
}
