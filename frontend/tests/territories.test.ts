/**
 * Tribe rings: the diplomacy a viewer can see at a glance.
 *
 * The rings are the only place tribe diplomacy shows up in the scene, and
 * the mapping is easy to get subtly wrong - a tribe can be at war with one
 * neighbour and allied with another at the same time, which really happens
 * (Elmkin, tick 5,700 of seed 1337, allied with Ashkin while fighting
 * Elmfolk). Testing the derivation rather than the pixels is what makes
 * that checkable at all.
 */

import { describe, expect, it } from 'vitest';

import { tribeRings, type TribeLike } from '@/scene/territoryRings';

function tribe(overrides: Partial<TribeLike> = {}): TribeLike {
  return {
    id: 1,
    colour: '#e8d2a6',
    camp_x: 0,
    camp_z: 0,
    territory_radius: 20,
    ...overrides,
  };
}

describe('tribeRings', () => {
  it('skips tribes too small to draw', () => {
    expect(tribeRings([tribe({ territory_radius: 0.5 })])).toHaveLength(0);
    expect(tribeRings([tribe({ territory_radius: 1 })])).toHaveLength(0);
    expect(tribeRings([tribe({ territory_radius: 1.1 })])).toHaveLength(1);
  });

  it('gives a peaceful tribe one ring in its own colour', () => {
    const [ring] = tribeRings([tribe()]);

    expect(ring?.atWar).toBe(false);
    expect(ring?.allied).toBe(false);
    expect(ring?.pactRadii).toBeNull();
    expect(ring?.colour).toBe('#e8d2a6');
  });

  it('flags a tribe at war', () => {
    const [ring] = tribeRings([tribe({ at_war_with: [2] })]);

    expect(ring?.atWar).toBe(true);
    expect(ring?.pactRadii).toBeNull();
  });

  it('gives a tribe with a pact a second ring inside the first', () => {
    const [ring] = tribeRings([tribe({ territory_radius: 20, allied_with: [2] })]);

    expect(ring?.allied).toBe(true);
    expect(ring?.pactRadii).not.toBeNull();
    const [inner, outer] = ring?.pactRadii ?? [0, 0];
    expect(outer).toBeLessThan(20);
    expect(inner).toBeLessThan(outer);
  });

  it('draws both when a tribe fights one neighbour and shelters another', () => {
    const [ring] = tribeRings([tribe({ at_war_with: [4], allied_with: [8] })]);

    expect(ring?.atWar).toBe(true);
    expect(ring?.pactRadii).not.toBeNull();
  });

  it('keeps the pact ring positive on a tiny territory', () => {
    const [ring] = tribeRings([tribe({ territory_radius: 1.2, allied_with: [2] })]);
    const [inner, outer] = ring?.pactRadii ?? [0, 0];

    expect(inner).toBeGreaterThan(0);
    expect(outer).toBeGreaterThan(inner);
  });

  it('treats an absent diplomacy list as no diplomacy', () => {
    // The API omits both fields when a tribe has neither, so the component
    // must cope with the keys simply not being there.
    const bare = {
      id: 7,
      colour: '#bfbfe8',
      camp_x: 10,
      camp_z: -4,
      territory_radius: 12,
    };
    const [ring] = tribeRings([bare]);

    expect(ring?.atWar).toBe(false);
    expect(ring?.pactRadii).toBeNull();
  });
});
