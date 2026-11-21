/** A ring under the selected agent, so you never lose them in the crowd. */

import { useFrame } from '@react-three/fiber';
import { useRef } from 'react';
import type * as THREE from 'three';

import { frameAlpha, interpolatePose, readPose } from '@/lib/interpolation';
import type { IslandSampler } from '@/lib/terrain';
import { useSelectionStore } from '@/state/selectionStore';
import { simState } from '@/state/simStore';

export interface SelectionRingProps {
  sampler: IslandSampler;
}

const RADIUS = 1.1;

export function SelectionRing({ sampler }: SelectionRingProps): React.ReactElement {
  const ringRef = useRef<THREE.Mesh>(null);

  useFrame(({ clock }) => {
    const ring = ringRef.current;
    if (!ring) return;

    const selected = useSelectionStore.getState().selectedAgentId;
    const { currentFrame, previousFrame } = simState();
    if (selected === null || !currentFrame || currentFrame.stride <= 0) {
      ring.visible = false;
      return;
    }

    // Find the agent's slot in the current frame; ids are not slot indices
    // once anyone has died, so this has to be a search.
    const total = Math.floor(currentFrame.agents.length / currentFrame.stride);
    let slot = -1;
    for (let index = 0; index < total; index += 1) {
      if (readPose(currentFrame, index)?.id === selected) {
        slot = index;
        break;
      }
    }
    if (slot < 0) {
      ring.visible = false;
      return;
    }

    const alpha = frameAlpha(previousFrame, currentFrame, performance.now());
    const pose = interpolatePose(previousFrame, currentFrame, slot, alpha);
    if (!pose) {
      ring.visible = false;
      return;
    }

    ring.visible = true;
    ring.position.set(pose.x, sampler.heightAt(pose.x, pose.z) + 0.08, pose.z);
    const pulse = 1 + Math.sin(clock.elapsedTime * 3) * 0.06;
    ring.scale.setScalar(pulse);
  });

  return (
    <mesh ref={ringRef} rotation={[-Math.PI / 2, 0, 0]} visible={false}>
      <ringGeometry args={[RADIUS, RADIUS + 0.22, 28]} />
      <meshBasicMaterial color="#ffffff" transparent opacity={0.85} depthWrite={false} />
    </mesh>
  );
}
