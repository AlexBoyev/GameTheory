/** Small numeric helpers shared by the scene and the stores. */

export const TAU = Math.PI * 2;

export function clamp(value: number, min: number, max: number): number {
  return value < min ? min : value > max ? max : value;
}

export function clamp01(value: number): number {
  return clamp(value, 0, 1);
}

export function lerp(from: number, to: number, alpha: number): number {
  return from + (to - from) * alpha;
}

/** Hermite smoothstep on `[0, 1]`. Used for both noise and camera easing. */
export function smoothstep(value: number): number {
  const t = clamp01(value);
  return t * t * (3 - 2 * t);
}

/** Map `value` from one range to another, clamped to the output range. */
export function remap(
  value: number,
  inMin: number,
  inMax: number,
  outMin: number,
  outMax: number,
): number {
  if (inMax === inMin) return outMin;
  return lerp(outMin, outMax, clamp01((value - inMin) / (inMax - inMin)));
}

export function degToRad(degrees: number): number {
  return (degrees * Math.PI) / 180;
}
