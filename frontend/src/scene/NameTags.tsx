/**
 * Who is who: a name over each nearby head (overlay `n`).
 *
 * Only the agents closest to the camera get a label, because 500 of them at
 * once is unreadable and expensive - and the ones far away are a few pixels
 * tall anyway. Each label is a canvas texture cached by name, so a label is
 * drawn once per agent for the life of the world rather than per frame.
 */

import { useFrame, useThree } from '@react-three/fiber';
import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';

import { frameAlpha, interpolatePose } from '@/lib/interpolation';
import type { IslandSampler } from '@/lib/terrain';
import { simState } from '@/state/simStore';
import { useSocietyStore } from '@/state/societyStore';

const LABEL_HEIGHT = 3.4;
const PIXELS_PER_UNIT = 30;
const FONT_PX = 22;
/** How many labels to show at once, nearest the camera first. */
const MAX_LABELS = 24;

function labelTexture(name: string): { texture: THREE.CanvasTexture; width: number } {
  const canvas = document.createElement('canvas');
  const measure = document.createElement('canvas').getContext('2d');
  if (measure) measure.font = `600 ${FONT_PX}px system-ui, sans-serif`;
  const width = Math.ceil((measure ? measure.measureText(name).width : name.length * 11) + 16);
  canvas.width = width;
  canvas.height = FONT_PX + 12;

  const context = canvas.getContext('2d');
  if (context) {
    context.fillStyle = 'rgba(15, 23, 42, 0.72)';
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.font = `600 ${FONT_PX}px system-ui, sans-serif`;
    context.textBaseline = 'middle';
    context.fillStyle = '#e2e8f0';
    context.fillText(name, 8, canvas.height / 2);
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return { texture, width: canvas.width / PIXELS_PER_UNIT };
}

export interface NameTagsProps {
  sampler: IslandSampler;
}

export function NameTags({ sampler }: NameTagsProps): React.ReactElement | null {
  const names = useSocietyStore((state) => state.names);
  const camera = useThree((three) => three.camera);
  const group = useRef<THREE.Group>(null);
  const textures = useRef(new Map<string, { texture: THREE.CanvasTexture; width: number }>());

  const slots = useMemo(
    () => Array.from({ length: MAX_LABELS }, (_, index) => index),
    [],
  );

  // One texture per distinct name, released when the world changes.
  useEffect(() => {
    const cache = textures.current;
    return () => {
      cache.forEach((entry) => entry.texture.dispose());
      cache.clear();
    };
  }, [names]);

  useFrame(() => {
    const parent = group.current;
    if (!parent) return;
    const { currentFrame, previousFrame } = simState();
    if (!currentFrame || currentFrame.stride <= 0 || names.size === 0) {
      for (const child of parent.children) child.visible = false;
      return;
    }

    const alpha = frameAlpha(previousFrame, currentFrame, performance.now());
    const total = Math.floor(currentFrame.agents.length / currentFrame.stride);

    // Nearest to the camera wins the limited number of labels.
    const candidates: { name: string; x: number; z: number; distance: number }[] = [];
    for (let index = 0; index < total; index += 1) {
      const pose = interpolatePose(previousFrame, currentFrame, index, alpha);
      if (!pose) continue;
      const name = names.get(pose.id);
      if (name === undefined) continue;
      const dx = pose.x - camera.position.x;
      const dz = pose.z - camera.position.z;
      candidates.push({ name, x: pose.x, z: pose.z, distance: dx * dx + dz * dz });
    }
    candidates.sort((first, second) => first.distance - second.distance);

    parent.children.forEach((child, slot) => {
      const entry = candidates[slot];
      if (!entry) {
        child.visible = false;
        return;
      }
      let texture = textures.current.get(entry.name);
      if (!texture) {
        texture = labelTexture(entry.name);
        textures.current.set(entry.name, texture);
      }
      const mesh = child as THREE.Mesh;
      const material = mesh.material as THREE.MeshBasicMaterial;
      if (material.map !== texture.texture) {
        material.map = texture.texture;
        material.needsUpdate = true;
      }
      mesh.scale.set(texture.width, 1, 1);
      child.visible = true;
      child.position.set(entry.x, sampler.heightAt(entry.x, entry.z) + LABEL_HEIGHT, entry.z);
      child.quaternion.copy(camera.quaternion);
    });
  });

  if (names.size === 0) return null;

  return (
    <group ref={group}>
      {slots.map((slot) => (
        <mesh key={slot} visible={false} frustumCulled={false}>
          <planeGeometry args={[1, 1.1]} />
          <meshBasicMaterial transparent depthWrite={false} toneMapped={false} />
        </mesh>
      ))}
    </group>
  );
}
