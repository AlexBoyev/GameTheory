/**
 * Frame interpolation.
 *
 * The backend broadcasts at most 20 Hz while the renderer runs at 60; every
 * agent position you see between two frames is interpolated here.
 */

import { TAU, clamp01, lerp } from '@/lib/math';

/** Shortest signed delta between two angles, in `(-PI, PI]`. */
export function angleDelta(from: number, to: number): number {
  let delta = (to - from) % TAU;
  if (delta > Math.PI) delta -= TAU;
  if (delta <= -Math.PI) delta += TAU;
  return delta;
}

/** Interpolate an angle the short way round. */
export function lerpAngle(from: number, to: number, alpha: number): number {
  return from + angleDelta(from, to) * clamp01(alpha);
}

export interface AgentFrame {
  /** Flat `[id, x, z, heading, state, tribe, flags]` repeated per agent. */
  readonly agents: Float32Array;
  readonly stride: number;
  readonly tick: number;
  /** Wall-clock ms when this frame arrived, for alpha calculation. */
  readonly receivedAt: number;
}

export interface AgentPose {
  id: number;
  x: number;
  z: number;
  heading: number;
  state: number;
  tribe: number;
  flags: number;
}

/**
 * Interpolation factor for "now" between two frames.
 *
 * Clamped to `[0, 1]`: if the next frame is late we hold the last pose rather
 * than extrapolating agents into the sea.
 */
export function frameAlpha(
  previous: AgentFrame | null,
  current: AgentFrame | null,
  now: number,
): number {
  if (!previous || !current) return 1;
  const span = current.receivedAt - previous.receivedAt;
  if (span <= 0) return 1;
  return clamp01((now - current.receivedAt) / span + 1);
}

/** Read agent `index` out of a frame, or `null` when out of range. */
export function readPose(frame: AgentFrame, index: number): AgentPose | null {
  const offset = index * frame.stride;
  if (offset + frame.stride > frame.agents.length) return null;
  return {
    id: frame.agents[offset] ?? 0,
    x: frame.agents[offset + 1] ?? 0,
    z: frame.agents[offset + 2] ?? 0,
    heading: frame.agents[offset + 3] ?? 0,
    state: frame.agents[offset + 4] ?? 0,
    tribe: frame.agents[offset + 5] ?? -1,
    flags: frame.agents[offset + 6] ?? 0,
  };
}

/**
 * Pose of agent `index` at interpolation factor `alpha`.
 *
 * Falls back to the current frame when the agent is new (it was not in the
 * previous frame, so there is nothing to interpolate from).
 */
export function interpolatePose(
  previous: AgentFrame | null,
  current: AgentFrame,
  index: number,
  alpha: number,
): AgentPose | null {
  const now = readPose(current, index);
  if (!now) return null;
  if (!previous) return now;
  const before = readPose(previous, index);
  if (!before || before.id !== now.id) return now;
  return {
    ...now,
    x: lerp(before.x, now.x, alpha),
    z: lerp(before.z, now.z, alpha),
    heading: lerpAngle(before.heading, now.heading, alpha),
  };
}
