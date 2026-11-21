/**
 * Tribe territory rings and camp markers (SPEC section 9.4).
 *
 * A tribe's territory is derived from where its members actually are, so
 * these rings breathe: they swell as a tribe spreads out to forage and
 * tighten when it gathers at camp.
 */

import { useMemo } from 'react';
import * as THREE from 'three';

import type { IslandSampler } from '@/lib/terrain';
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
      tribes
        .filter((tribe) => tribe.territory_radius > 1)
        .map((tribe) => ({
          id: tribe.id,
          colour: tribe.colour,
          radius: tribe.territory_radius,
          atWar: (tribe.at_war_with ?? []).length > 0,
          position: new THREE.Vector3(
            tribe.camp_x,
            sampler.heightAt(tribe.camp_x, tribe.camp_z) + LIFT,
            tribe.camp_z,
          ),
        })),
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
              color={ring.atWar ? '#f87171' : ring.colour}
              transparent
              opacity={ring.atWar ? 0.75 : 0.5}
              depthWrite={false}
              side={THREE.DoubleSide}
            />
          </mesh>
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
