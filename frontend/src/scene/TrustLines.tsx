/**
 * The social graph, drawn over the island (SPEC section 9.4).
 *
 * Green between people who trust each other, red between people who do not,
 * brighter the stronger the feeling. This is the overlay that makes the
 * invisible half of the simulation visible: you can watch a tribe appear as
 * a knot of green before any tribe officially exists.
 */

import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';

import type { IslandSampler } from '@/lib/terrain';
import { useSocietyStore } from '@/state/societyStore';

export interface TrustLinesProps {
  sampler: IslandSampler;
}

const LIFT = 1.4;
const ALLY_COLOUR = new THREE.Color('#6ee7a8');
const TRUST_COLOUR = new THREE.Color('#4ade80');
const DISTRUST_COLOUR = new THREE.Color('#f87171');

export function TrustLines({ sampler }: TrustLinesProps): React.ReactElement | null {
  const edges = useSocietyStore((state) => state.trustEdges);
  const geometryRef = useRef<THREE.BufferGeometry>(null);

  // Two vertices per edge, each with a position and a colour. Rebuilt
  // whenever the poll brings a new graph - a couple of times a second, not
  // sixty, which is why a plain `LineSegments` is fine here.
  const { positions, colours } = useMemo(() => {
    const points = new Float32Array(edges.length * 6);
    const tints = new Float32Array(edges.length * 6);
    const colour = new THREE.Color();

    edges.forEach((edge, index) => {
      const offset = index * 6;
      points[offset] = edge.ax;
      points[offset + 1] = sampler.heightAt(edge.ax, edge.az) + LIFT;
      points[offset + 2] = edge.az;
      points[offset + 3] = edge.bx;
      points[offset + 4] = sampler.heightAt(edge.bx, edge.bz) + LIFT;
      points[offset + 5] = edge.bz;

      const strength = Math.min(1, Math.abs(edge.trust));
      const base = edge.ally ? ALLY_COLOUR : edge.trust >= 0 ? TRUST_COLOUR : DISTRUST_COLOUR;
      colour.copy(base).multiplyScalar(0.35 + 0.65 * strength);
      for (const vertex of [0, 3]) {
        tints[offset + vertex] = colour.r;
        tints[offset + vertex + 1] = colour.g;
        tints[offset + vertex + 2] = colour.b;
      }
    });

    return { positions: points, colours: tints };
  }, [edges, sampler]);

  useEffect(() => {
    const geometry = geometryRef.current;
    if (!geometry) return;
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colours, 3));
    geometry.computeBoundingSphere();
  }, [positions, colours]);

  if (edges.length === 0) return null;

  return (
    <lineSegments frustumCulled={false}>
      <bufferGeometry ref={geometryRef} />
      <lineBasicMaterial vertexColors transparent opacity={0.65} depthWrite={false} />
    </lineSegments>
  );
}
