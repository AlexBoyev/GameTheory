/**
 * Radar geometry: the part of the traits radar that can be wrong silently.
 *
 * A polygon that renders is not a polygon that is right - an off-by-one in
 * the angle step, or a value measured from the rim instead of the centre,
 * both still draw a plausible-looking shape.
 */

import { describe, expect, it } from 'vitest';

import { radarPoint, radarPolygon, radarRing } from '@/ui/radar';

const EIGHT = 8;
const R = 100;

describe('radarPoint', () => {
  it('puts the first axis straight up', () => {
    const point = radarPoint(0, EIGHT, 1, R);

    expect(point.x).toBeCloseTo(0);
    expect(point.y).toBeCloseTo(-R, 5);
  });

  it('runs clockwise, so the second axis of four points right', () => {
    const point = radarPoint(1, 4, 1, R);

    expect(point.x).toBeCloseTo(R, 5);
    expect(point.y).toBeCloseTo(0);
  });

  it('measures value from the centre, not the rim', () => {
    expect(radarPoint(0, EIGHT, 0, R)).toEqual({ x: 0, y: -0 });
    expect(radarPoint(0, EIGHT, 0.5, R).y).toBeCloseTo(-R / 2, 5);
  });

  it('clamps a value outside [0, 1] rather than drawing outside the chart', () => {
    expect(radarPoint(0, EIGHT, 2, R).y).toBeCloseTo(-R, 5);
    expect(radarPoint(0, EIGHT, -1, R).y).toBeCloseTo(0, 5);
  });

  it('spaces the axes evenly', () => {
    const distances = Array.from({ length: EIGHT }, (_, index) => {
      const a = radarPoint(index, EIGHT, 1, R);
      const b = radarPoint((index + 1) % EIGHT, EIGHT, 1, R);
      return Math.hypot(a.x - b.x, a.y - b.y);
    });

    for (const distance of distances) expect(distance).toBeCloseTo(distances[0] ?? 0, 5);
  });
});

describe('radarPolygon', () => {
  it('emits one point per value', () => {
    const points = radarPolygon([0.1, 0.2, 0.3, 0.4], R).split(' ');

    expect(points).toHaveLength(4);
    expect(points[0]).toMatch(/^-?\d+\.\d{2},-?\d+\.\d{2}$/);
  });

  it('collapses to the centre when everything is zero', () => {
    // Asserted as numbers rather than as a string: the formatter emits
    // signed zeros, and "-0.00" is the same point as "0.00".
    const coordinates = radarPolygon([0, 0, 0], R)
      .split(' ')
      .flatMap((pair) => pair.split(',').map(Number));

    expect(coordinates).toHaveLength(6);
    for (const value of coordinates) expect(value).toBeCloseTo(0, 5);
  });
});

describe('radarRing', () => {
  it('is the same shape at every vertex', () => {
    const vertices = radarRing(EIGHT, 0.5, R).split(' ');

    expect(vertices).toHaveLength(EIGHT);
    const radii = vertices.map((pair) => {
      const [x, y] = pair.split(',').map(Number);
      return Math.hypot(x ?? 0, y ?? 0);
    });
    for (const radius of radii) expect(radius).toBeCloseTo(R / 2, 1);
  });
});
