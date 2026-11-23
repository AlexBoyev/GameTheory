/**
 * Tribe territory rings and camp markers (SPEC section 9.4).
 *
 * A tribe's territory is derived from where its members actually are, so
 * these rings breathe: they swell as a tribe spreads out to forage and
 * tighten when it gathers at camp.
 *
 * The ring also carries the tribe's diplomacy: red while it is at war, and a
 * second thin ring inside it while it holds a pact with anyone. Both can be
 * true at once - a tribe can fight one neighbour and shelter another.
 */

import { useMemo } from 'react';
import * as THREE from 'three';

import type { IslandSampler } from '@/lib/terrain';
import { PACT_COLOUR, WAR_COLOUR, tribeRings } from '@/scene/territoryRings';
import { useSocietyStore } from '@/state/societyStore';

export interface TerritoriesProps {
  sampler: IslandSampler;
}

const LIFT = 0.25;
const RING_WIDTH = 1.2;

export function Territories({ sampler }: TerritoriesProps): React.ReactElement | null {
  const tribes = useSocietyStore((state) => state.tribes);

  const rings = useMemo(
    () =>
      tribeRings(tribes).map((ring) => {
        const tribe = tribes.find((candidate) => candidate.id === ring.id);
        const x = tribe?.camp_x ?? 0;
        const z = tribe?.camp_z ?? 0;
        return {
          ...ring,
          position: new THREE.Vector3(x, sampler.heightAt(x, z) + LIFT, z),
        };
      }),
    [tribes, sampler],
  );

  if (rings.length === 0) return null;

  return (
    <>
      {rings.map((ring) => (
        <group key={ring.id} position={ring.position}>
          <mesh rotation={[-Math.PI / 2, 0, 0]}>
            <ringGeometry args={[ring.radius, ring.radius + RING_WIDTH, 48]} />
            <meshBasicMaterial
              color={ring.atWar ? WAR_COLOUR : ring.colour}
              transparent
              opacity={ring.atWar ? 0.75 : 0.5}
              depthWrite={false}
              side={THREE.DoubleSide}
            />
          </mesh>
          {/* A tribe with a pact wears a second, thinner ring inside the first. */}
          {ring.pactRadii && (
            <mesh rotation={[-Math.PI / 2, 0, 0]}>
              <ringGeometry args={[ring.pactRadii[0], ring.pactRadii[1], 48]} />
              <meshBasicMaterial
                color={PACT_COLOUR}
                transparent
                opacity={0.7}
                depthWrite={false}
                side={THREE.DoubleSide}
              />
            </mesh>
          )}
          {/* A post marking the camp itself. */}
          <mesh position={[0, 1.2, 0]} castShadow>
            <cylinderGeometry args={[0.18, 0.18, 2.4, 6]} />
            <meshStandardMaterial color={ring.colour} roughness={0.8} />
          </mesh>
        </group>
      ))}
    </>
  );
}
