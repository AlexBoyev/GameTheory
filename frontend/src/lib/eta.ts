/**
 * How long the world will take to get somewhere, at the rate it is going.
 *
 * "How long to day 10?" is the question a person actually has, and the tps
 * readout does not answer it: a day is 2,400 ticks, which is arithmetic
 * nobody should have to do while watching. The engine publishes a measured
 * trailing rate, so the honest answer is available for free.
 *
 * It is deliberately a projection of the *current* rate rather than a
 * promise. Measured over ten days, the rate falls as the population grows -
 * 137 tps on day 1 and 87 by day 6 on the default island - so a projection
 * made early reads optimistic, and this says "at this rate" rather than
 * pretending otherwise.
 */

/** A day is 240 sim-seconds at dt 0.1. */
export const TICKS_PER_DAY = 2400;

/** Below this the rate is noise (a paused world, or one that just started). */
const MIN_USEFUL_TPS = 1;

/** Format seconds the way a person would say them. */
export function humanDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '-';
  if (seconds < 90) return `${Math.round(seconds)} s`;
  const minutes = seconds / 60;
  if (minutes < 90) return `${minutes < 10 ? minutes.toFixed(1) : Math.round(minutes)} min`;
  return `${(minutes / 60).toFixed(1)} h`;
}

/**
 * Seconds to reach `targetDay` from `tick` at `ticksPerSecond`, or null when
 * the rate is too low to project from or the day is already behind us.
 */
export function secondsToDay(
  tick: number,
  targetDay: number,
  ticksPerSecond: number,
): number | null {
  if (ticksPerSecond < MIN_USEFUL_TPS) return null;
  const remaining = targetDay * TICKS_PER_DAY - tick;
  if (remaining <= 0) return null;
  return remaining / ticksPerSecond;
}

/** The tooltip line under the tps readout: a day, and the next round day. */
export function paceSummary(tick: number, ticksPerSecond: number): string | null {
  if (ticksPerSecond < MIN_USEFUL_TPS) return null;
  const perDay = humanDuration(TICKS_PER_DAY / ticksPerSecond);
  const day = Math.floor(tick / TICKS_PER_DAY);
  // The next landmark worth quoting: 10, 20, 50, then every 50.
  const landmarks = [10, 20, 50, 100];
  const next = landmarks.find((candidate) => candidate > day);
  if (next === undefined) return `At this rate: a day every ${perDay}.`;
  const seconds = secondsToDay(tick, next, ticksPerSecond);
  if (seconds === null) return `At this rate: a day every ${perDay}.`;
  return `At this rate: a day every ${perDay}, day ${next} in ${humanDuration(seconds)}.`;
}
