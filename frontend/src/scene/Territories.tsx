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
import { useSocietyStore } from '@/state/societyStore';

export interface TerritoriesProps {
  sampler: IslandSampler;
}

const LIFT = 0.25;
const RING_WIDTH = 1.2;

export const WAR_COLOUR = '#f87171';
export const PACT_COLOUR = '#7dd3b8';
const PACT_RING_GAP = 1.0;
const PACT_RING_WIDTH = 0.5;
const MIN_RADIUS = 1;

/** One tribe's rings, ready to draw. */
export interface TribeRing {
  id: number;
  colour: string;
  radius: number;
  atWar: boolean;
  allied: boolean;
  /** Inner and outer radius of the pact ring, or null when there is no pact. */
  pactRadii: [number, number] | null;
}

/**
 * Derive the rings from the tribe list.
 *
 * Pulled out of the component so the diplomacy mapping can be tested without
 * a renderer: which tribes get a ring at all, which turn red, and which wear
 * the second pact ring. War and a pact are independent - a tribe can fight
 * one neighbour while sheltering another - so both flags can be true.
 */
export function tribeRings(tribes: readonly TribeLike[]): TribeRing[] {
  return tribes
    .filter((tribe) => tribe.territory_radius > MIN_RADIUS)
    .map((tribe) => {
      const radius = tribe.territory_radius;
      const allied = (tribe.allied_with ?? []).length > 0;
      return {
        id: tribe.id,
        colour: tribe.colour,
        radius,
        atWar: (tribe.at_war_with ?? []).length > 0,
        allied,
        pactRadii: allied
          ? ([
              Math.max(0.1, radius - PACT_RING_GAP - PACT_RING_WIDTH),
              Math.max(0.2, radius - PACT_RING_GAP),
            ] as [number, number])
          : null,
      };
    });
}

/** The parts of a tribe these rings are drawn from. */
export interface TribeLike {
  id: number;
  colour: string;
  camp_x: number;
  camp_z: number;
  territory_radius: number;
  at_war_with?: number[];
  allied_with?: number[];
}

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
