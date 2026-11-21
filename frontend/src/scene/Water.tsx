/**
 * The sea: a translucent plane with a slow swell.
 *
 * Phase 3 replaces the bob with a proper animated water shader; the geometry
 * and extent stay the same.
 */

import { useFrame } from '@react-three/fiber';
import { useRef } from 'react';
import type * as THREE from 'three';

import { BIOME_COLORS } from '@/lib/colors';
import type { IslandSampler } from '@/lib/terrain';

export interface WaterProps {
  sampler: IslandSampler;
}

const SWELL_AMPLITUDE = 0.06;
const SWELL_SPEED = 0.6;

export function Water({ sampler }: WaterProps): React.ReactElement {
  const meshRef = useRef<THREE.Mesh>(null);
  const { size, maxHeight, waterLevel } = sampler.params;
  const level = waterLevel * maxHeight;

  useFrame(({ clock }) => {
    if (!meshRef.current) return;
    meshRef.current.position.y =
      level + Math.sin(clock.elapsedTime * SWELL_SPEED) * SWELL_AMPLITUDE;
  });

  return (
    <mesh ref={meshRef} position={[0, level, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
      {/* Wider than the island so the horizon is water, not void. */}
      <planeGeometry args={[size * 3, size * 3, 1, 1]} />
      <meshStandardMaterial
        color={BIOME_COLORS.water}
        transparent
        opacity={0.82}
        roughness={0.25}
        metalness={0.1}
      />
    </mesh>
  );
}
