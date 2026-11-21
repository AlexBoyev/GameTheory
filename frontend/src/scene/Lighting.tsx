/**
 * Sun, sky and the day/night cycle, driven by the simulation clock.
 *
 * The sun is updated imperatively from the store inside `useFrame`: time of
 * day changes 10 times a second, and re-rendering React for each would be
 * wasteful when all that moves is a light.
 */

import { useFrame } from '@react-three/fiber';
import { useRef } from 'react';
import * as THREE from 'three';

import { sunColorAt } from '@/lib/colors';
import { TAU, clamp01, remap } from '@/lib/math';
import { simState } from '@/state/simStore';

export interface LightingProps {
  /** World extent, used to size the shadow camera. */
  size: number;
  shadows?: boolean;
}

const NIGHT_INTENSITY = 0.25;
const DAY_INTENSITY = 1.5;

/**
 * How often the shadow map is re-rendered, in milliseconds.
 *
 * three.js re-renders shadows every frame by default, which means drawing the
 * whole island into a 2048x2048 depth buffer sixty times a second. The sun
 * crosses the sky over four sim-minutes, so four shadow updates a second is
 * already smoother than anyone can see - and it takes the island's shadow
 * pass from 60 renders a second to 4.
 */
const SHADOW_INTERVAL_MS = 250;

export function Lighting({ size, shadows = true }: LightingProps): React.ReactElement {
  const sunRef = useRef<THREE.DirectionalLight>(null);
  const hemiRef = useRef<THREE.HemisphereLight>(null);
  const colour = useRef(new THREE.Color('#fff6e2'));
  const lastShadow = useRef(0);
  const shadowsConfigured = useRef(false);

  // The renderer comes from `useFrame`'s state rather than `useThree`, so
  // that driving it imperatively is not a mutation of a hook's return value.
  useFrame((state) => {
    const sun = sunRef.current;
    if (!sun) return;
    const { timeOfDay } = simState();

    if (!shadowsConfigured.current) {
      state.gl.shadowMap.autoUpdate = false;
      state.gl.shadowMap.needsUpdate = true;
      shadowsConfigured.current = true;
    }

    if (shadows) {
      const now = performance.now();
      if (now - lastShadow.current >= SHADOW_INTERVAL_MS) {
        state.gl.shadowMap.needsUpdate = true;
        lastShadow.current = now;
      }
    }

    // 0.0 = midnight, 0.5 = noon: the sun arcs from east to west.
    const angle = (timeOfDay - 0.25) * TAU;
    const elevation = Math.sin(angle);
    const radius = size * 0.9;
    sun.position.set(Math.cos(angle) * radius, Math.max(0.08, elevation) * radius, radius * 0.35);

    const daylight = clamp01(remap(elevation, -0.15, 0.45, 0, 1));
    sun.intensity = NIGHT_INTENSITY + daylight * (DAY_INTENSITY - NIGHT_INTENSITY);
    sun.color.set(colour.current.set(sunColorAt(timeOfDay)));

    if (hemiRef.current) {
      hemiRef.current.intensity = 0.35 + daylight * 0.5;
    }
  });

  return (
    <>
      <hemisphereLight ref={hemiRef} args={['#cfe9f5', '#b5ad92', 0.7]} />
      <directionalLight
        ref={sunRef}
        castShadow={shadows}
        intensity={1.4}
        position={[size * 0.5, size * 0.6, size * 0.35]}
        shadow-mapSize-width={2048}
        shadow-mapSize-height={2048}
        shadow-camera-left={-size * 0.7}
        shadow-camera-right={size * 0.7}
        shadow-camera-top={size * 0.7}
        shadow-camera-bottom={-size * 0.7}
        shadow-camera-near={1}
        shadow-camera-far={size * 3}
        shadow-bias={-0.0005}
      />
      <ambientLight intensity={0.25} />
    </>
  );
}
