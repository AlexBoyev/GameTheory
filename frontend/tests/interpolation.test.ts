import { describe, expect, it } from 'vitest';

import {
  angleDelta,
  frameAlpha,
  interpolatePose,
  lerpAngle,
  readPose,
  type AgentFrame,
} from '@/lib/interpolation';

const STRIDE = 7;

function frame(tick: number, receivedAt: number, agents: number[]): AgentFrame {
  return { agents: Float32Array.from(agents), stride: STRIDE, tick, receivedAt };
}

describe('angles', () => {
  it('takes the short way round the circle', () => {
    expect(angleDelta(0.1, Math.PI * 2 - 0.1)).toBeCloseTo(-0.2, 5);
    expect(angleDelta(Math.PI * 2 - 0.1, 0.1)).toBeCloseTo(0.2, 5);
  });

  it('never interpolates the long way', () => {
    const halfway = lerpAngle(0.1, Math.PI * 2 - 0.1, 0.5);
    expect(Math.cos(halfway)).toBeCloseTo(1, 3);
  });
});

describe('frameAlpha', () => {
  it('is 1 without a previous frame', () => {
    expect(frameAlpha(null, frame(1, 0, []), 100)).toBe(1);
  });

  it('is 0 at the previous frame and 1 at the current one', () => {
    const previous = frame(1, 0, []);
    const current = frame(2, 100, []);
    expect(frameAlpha(previous, current, 0)).toBeCloseTo(0, 5);
    expect(frameAlpha(previous, current, 100)).toBeCloseTo(1, 5);
  });

  it('clamps instead of extrapolating when a frame is late', () => {
    expect(frameAlpha(frame(1, 0, []), frame(2, 100, []), 900)).toBe(1);
  });
});

describe('poses', () => {
  const previous = frame(1, 0, [7, 0, 0, 0, 1, 2, 0]);
  const current = frame(2, 100, [7, 10, 20, 1, 1, 2, 0]);

  it('reads a pose out of the flat array', () => {
    const pose = readPose(current, 0);
    expect(pose).toEqual({ id: 7, x: 10, z: 20, heading: 1, state: 1, tribe: 2, flags: 0 });
  });

  it('returns null past the end of the array', () => {
    expect(readPose(current, 1)).toBeNull();
  });

  it('interpolates position halfway between two frames', () => {
    const pose = interpolatePose(previous, current, 0, 0.5);
    expect(pose?.x).toBeCloseTo(5, 5);
    expect(pose?.z).toBeCloseTo(10, 5);
  });

  it('does not interpolate across a recycled slot', () => {
    const recycled = frame(2, 100, [99, 10, 20, 1, 1, 2, 0]);
    const pose = interpolatePose(previous, recycled, 0, 0.5);
    expect(pose?.x).toBe(10);
  });
});
