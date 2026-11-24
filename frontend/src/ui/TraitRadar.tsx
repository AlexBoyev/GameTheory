/**
 * The personality at a glance (SPEC section 9.4).
 *
 * Eight bars told you each trait and nothing about the person. The same
 * numbers as a shape are comparable: you learn to recognise the lopsided
 * silhouette of a schemer, and two agents can be told apart in a second.
 * The exact values are still there, next to each label, because "how
 * cunning exactly" is a question the bars could answer and a polygon
 * cannot.
 */

import { radarPoint, radarPolygon, radarRing } from '@/ui/radar';

export interface TraitRadarProps {
  traits: Readonly<Record<string, number>>;
  /** Which traits to draw, in order, clockwise from the top. */
  order: readonly string[];
}

const WIDTH = 220;
const HEIGHT = 150;
const RADIUS = 52;
const LABEL_RADIUS = RADIUS + 14;
const RINGS = [0.25, 0.5, 0.75, 1];
/* The box is wider than it is tall because the east and west labels sit
   beside the chart rather than above or below it; a square viewBox clipped
   them to their last two characters. */

export function TraitRadar({ traits, order }: TraitRadarProps): React.ReactElement {
  const values = order.map((trait) => traits[trait] ?? 0);

  return (
    <svg
      viewBox={`${-WIDTH / 2} ${-HEIGHT / 2} ${WIDTH} ${HEIGHT}`}
      className="mx-auto block w-full max-w-[260px]"
      role="img"
      aria-label={order.map((trait) => `${trait} ${traits[trait]?.toFixed(2)}`).join(', ')}
    >
      {RINGS.map((fraction) => (
        <polygon
          key={fraction}
          points={radarRing(order.length, fraction, RADIUS)}
          className="fill-none stroke-slate-600/40"
          strokeWidth={0.5}
        />
      ))}

      {order.map((trait, index) => {
        const spoke = radarPoint(index, order.length, 1, RADIUS);
        return (
          <line
            key={trait}
            x1={0}
            y1={0}
            x2={spoke.x}
            y2={spoke.y}
            className="stroke-slate-600/40"
            strokeWidth={0.5}
          />
        );
      })}

      <polygon
        points={radarPolygon(values, RADIUS)}
        className="fill-violet-400/30 stroke-violet-300"
        strokeWidth={1.2}
        strokeLinejoin="round"
      />

      {order.map((trait, index) => {
        const at = radarPoint(index, order.length, 1, LABEL_RADIUS);
        const anchor = at.x > 1 ? 'start' : at.x < -1 ? 'end' : 'middle';
        return (
          <text
            key={trait}
            x={at.x}
            y={at.y}
            textAnchor={anchor}
            dominantBaseline="middle"
            className="fill-slate-400 text-[6px]"
          >
            {trait.slice(0, 4)} {(traits[trait] ?? 0).toFixed(2).slice(1)}
          </text>
        );
      })}
    </svg>
  );
}
