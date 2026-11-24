/**
 * Radar-chart geometry (SPEC section 9.4: the Inspector's traits radar).
 *
 * Separate from the component because the maths is the part worth testing
 * and it needs no renderer: that the first axis points straight up, that the
 * axes are evenly spaced, and that a value of zero sits at the centre rather
 * than on the rim.
 */

export interface Point {
  x: number;
  y: number;
}

/**
 * Where the `index`th of `count` axes reaches, at `value` of `radius`.
 *
 * Angles start at twelve o'clock and run clockwise, which is what makes the
 * shape readable: the first trait is where the eye lands, and the order on
 * screen matches the order in the list that defines it.
 */
export function radarPoint(index: number, count: number, value: number, radius: number): Point {
  const clamped = Math.min(1, Math.max(0, value));
  const angle = -Math.PI / 2 + (index / count) * Math.PI * 2;
  return {
    x: Math.cos(angle) * radius * clamped,
    y: Math.sin(angle) * radius * clamped,
  };
}

/** The closed polygon through every value, as an SVG `points` attribute. */
export function radarPolygon(values: readonly number[], radius: number): string {
  return values
    .map((value, index) => {
      const point = radarPoint(index, values.length, value, radius);
      return `${point.x.toFixed(2)},${point.y.toFixed(2)}`;
    })
    .join(' ');
}

/** One of the background rings, at `fraction` of full radius. */
export function radarRing(count: number, fraction: number, radius: number): string {
  return radarPolygon(new Array<number>(count).fill(fraction), radius);
}
