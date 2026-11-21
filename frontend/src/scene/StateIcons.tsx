/**
 * The emoji floating over each agent's head (SPEC 9.2).
 *
 * This is what turns "120 beans milling about" into something you can read at
 * a glance: a crowd round the lake is obviously drinking, and the one being
 * chased is obviously terrified.
 *
 * One `InstancedMesh` per state rather than a texture atlas with a custom
 * shader: a dozen draw calls is nothing, and this way the emoji are just
 * textures.
 */

import { useFrame, useThree } from '@react-three/fiber';
import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';

import { frameAlpha, interpolatePose } from '@/lib/interpolation';
import { STATE_EMOJI } from '@/lib/stateIcons';
import type { IslandSampler } from '@/lib/terrain';
import { simState, useSimStore } from '@/state/simStore';

const ICON_SIZE = 1.5;
const ICON_HEIGHT = 2.5;
const TEXTURE_PIXELS = 72;

function emojiTexture(emoji: string): THREE.CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = TEXTURE_PIXELS;
  canvas.height = TEXTURE_PIXELS;
  const context = canvas.getContext('2d');
  if (context) {
    context.font = `${TEXTURE_PIXELS * 0.78}px "Segoe UI Emoji", "Apple Color Emoji", sans-serif`;
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    context.fillText(emoji, TEXTURE_PIXELS / 2, TEXTURE_PIXELS * 0.55);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

export interface StateIconsProps {
  sampler: IslandSampler;
  capacity?: number;
}

export function StateIcons({
  sampler,
  capacity = 512,
}: StateIconsProps): React.ReactElement | null {
  const legend = useSimStore((state) => state.legend);
  const camera = useThree((three) => three.camera);

  const dummy = useMemo(() => new THREE.Object3D(), []);
  const meshes = useRef(new Map<number, THREE.InstancedMesh>());

  /** Wire code -> emoji, for the states that have one. */
  const iconStates = useMemo(() => {
    const states = legend?.states ?? [];
    return states
      .map((name, code) => ({ code, name, emoji: STATE_EMOJI[name] }))
      .filter((entry): entry is { code: number; name: string; emoji: string } =>
        Boolean(entry.emoji),
      );
  }, [legend]);

  const textures = useMemo(
    () => new Map(iconStates.map((entry) => [entry.code, emojiTexture(entry.emoji)])),
    [iconStates],
  );

  useEffect(() => () => textures.forEach((texture) => texture.dispose()), [textures]);

  useFrame(() => {
    const { currentFrame, previousFrame } = simState();
    const counts = new Map<number, number>();

    if (currentFrame && currentFrame.stride > 0) {
      const alpha = frameAlpha(previousFrame, currentFrame, performance.now());
      const total = Math.floor(currentFrame.agents.length / currentFrame.stride);

      for (let index = 0; index < total; index += 1) {
        const pose = interpolatePose(previousFrame, currentFrame, index, alpha);
        if (!pose) continue;
        const mesh = meshes.current.get(pose.state);
        if (!mesh) continue;

        const slot = counts.get(pose.state) ?? 0;
        if (slot >= capacity) continue;

        dummy.position.set(pose.x, sampler.heightAt(pose.x, pose.z) + ICON_HEIGHT, pose.z);
        // Billboard: borrow the camera's rotation so icons always face us.
        dummy.quaternion.copy(camera.quaternion);
        dummy.scale.setScalar(1);
        dummy.updateMatrix();
        mesh.setMatrixAt(slot, dummy.matrix);
        counts.set(pose.state, slot + 1);
      }
    }

    meshes.current.forEach((mesh, code) => {
      mesh.count = counts.get(code) ?? 0;
      mesh.instanceMatrix.needsUpdate = true;
    });
  });

  if (iconStates.length === 0) return null;

  return (
    <>
      {iconStates.map((entry) => (
        <instancedMesh
          key={entry.code}
          ref={(mesh) => {
            if (mesh) meshes.current.set(entry.code, mesh);
            else meshes.current.delete(entry.code);
          }}
          args={[undefined, undefined, capacity]}
          frustumCulled={false}
        >
          <planeGeometry args={[ICON_SIZE, ICON_SIZE]} />
          <meshBasicMaterial
            map={textures.get(entry.code) ?? null}
            transparent
            depthWrite={false}
            toneMapped={false}
          />
        </instancedMesh>
      ))}
    </>
  );
}
