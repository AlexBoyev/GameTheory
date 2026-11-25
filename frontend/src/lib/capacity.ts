/**
 * What speed a given population can actually hold.
 *
 * The two dials in the new-world dialog are really one decision. Asking for
 * 400 agents and then pressing 25x is asking for four times what the machine
 * can do - which used to look like a bug (the backend froze) and is really a
 * budget. The engine now degrades instead of seizing up, and the dialog says
 * the price up front.
 *
 * Measured with `python driver.py --bench`, pure engine, 400 ticks: 100
 * agents run at 350 ticks a second, 150 at 233, 300 at 98, 500 at 54. A tick
 * is 0.1 sim-seconds, so 1x is ten ticks a second and the multiple is
 * tps/10. Re-measure before editing these numbers; they are from this
 * machine and will drift with the simulation's own cost.
 */

/** Agents against the fastest multiple they sustain, from the bench. */
const MEASURED: readonly (readonly [agents: number, speed: number])[] = [
  [100, 35],
  [150, 23],
  [300, 10],
  [500, 5],
];

export function speedCeiling(population: number): number {
  const first = MEASURED[0]!;
  if (population <= first[0]) return first[1];

  for (let index = 1; index < MEASURED.length; index++) {
    const [agents, speed] = MEASURED[index]!;
    const [fewer, faster] = MEASURED[index - 1]!;
    if (population <= agents) {
      const across = (population - fewer) / (agents - fewer);
      return faster + across * (speed - faster);
    }
  }

  // Past the measured range the cost keeps climbing, so hold the last
  // point's agent-seconds rather than extrapolating the line into nonsense.
  const [agents, speed] = MEASURED[MEASURED.length - 1]!;
  return (speed * agents) / population;
}

/** The population slider's hint, which changes as you drag it. */
export function populationHint(population: number): string {
  const ceiling = speedCeiling(population);
  const rounded = ceiling >= 10 ? Math.round(ceiling / 5) * 5 : Math.round(ceiling);
  return `The island comfortably feeds a few hundred. This many runs at about ${rounded}x at best.`;
}
