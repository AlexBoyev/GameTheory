/**
 * The huts agents build - dome shelters, in one instanced draw call.
 *
 * Shelters are the first thing in this world that outlives the moment that
 * made it, so they are worth drawing properly: a hemisphere on the ground,
 * tinted by the owner's tribe.
 */

import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';

import { tribeColor } from '@/lib/colors';
import type { IslandSampler } from '@/lib/terrain';
import { useSocietyStore } from '@/state/societyStore';

export interface SheltersProps {
  sampler: IslandSampler;
  capacity?: number;
}

const RADIUS = 1.6;

export function Shelters({ sampler, capacity = 512 }: SheltersProps): React.ReactElement | null {
  const shelters = useSocietyStore((state) => state.shelters);
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const colour = useMemo(() => new THREE.Color(), []);

  useEffect(() => {
    const mesh = meshRef.current;
    if (!mesh) return;

    const drawn = Math.min(capacity, shelters.length);
    for (let index = 0; index < drawn; index += 1) {
      const shelter = shelters[index];
      if (!shelter) continue;
      dummy.position.set(shelter.x, sampler.heightAt(shelter.x, shelter.z), shelter.z);
      // Better-built huts are a little larger.
      const scale = 0.8 + 0.4 * (shelter.quality ?? 1);
      dummy.scale.set(scale, scale * 0.8, scale);
      dummy.rotation.set(0, (shelter.id % 8) * 0.4, 0);
      dummy.updateMatrix();
      mesh.setMatrixAt(index, dummy.matrix);
      mesh.setColorAt(index, colour.set(tribeColor(shelter.tribe_id ?? -1)));
    }

    mesh.count = drawn;
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }, [shelters, sampler, capacity, dummy, colour]);

  if (shelters.length === 0) return null;

  return (
    <instancedMesh
      ref={meshRef}
      args={[undefined, undefined, capacity]}
      castShadow
      receiveShadow
      frustumCulled={false}
    >
      {/* A hemisphere: half a sphere, flat side down. */}
      <sphereGeometry args={[RADIUS, 12, 8, 0, Math.PI * 2, 0, Math.PI / 2]} />
      <meshStandardMaterial roughness={0.9} metalness={0} flatShading />
    </instancedMesh>
  );
}
