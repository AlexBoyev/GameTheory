/**
 * What a tribe's territory ring says about its diplomacy (SPEC section 9.4).
 *
 * Its own module, not part of `Territories.tsx`, for two reasons: the mapping
 * is the part worth testing and it needs no renderer to test, and a component
 * file that also exports helpers loses fast refresh.
 */

const PACT_RING_GAP = 1.0;
const PACT_RING_WIDTH = 0.5;
const MIN_RADIUS = 1;

export const WAR_COLOUR = '#f87171';
export const PACT_COLOUR = '#7dd3b8';

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
 * War and a pact are independent - a tribe can fight one neighbour while
 * sheltering another - so both flags can be true at once, and really are:
 * Elmkin was allied with Ashkin while at war with Elmfolk at tick 5,700 of
 * the default seed.
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
