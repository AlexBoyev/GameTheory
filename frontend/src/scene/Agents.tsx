/**
 * Agents as one `InstancedMesh` of bean bodies, plus picking.
 *
 * One draw call for the whole population is what makes hundreds of agents
 * affordable (SPEC 9.5). Positions come from the interpolated WS frames and
 * the mesh is written to imperatively - this component never re-renders on a
 * frame message.
 *
 * Clicking is done by raycasting the instanced mesh: three gives us an
 * `instanceId`, and because instances are written in frame order we can map
 * that straight back to an agent id.
 */

import type { ThreeEvent } from '@react-three/fiber';
import { useFrame } from '@react-three/fiber';
import { useCallback, useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';

import { tribeColor } from '@/lib/colors';
import { frameAlpha, interpolatePose } from '@/lib/interpolation';
import type { IslandSampler } from '@/lib/terrain';
import { useSelectionStore } from '@/state/selectionStore';
import { simState } from '@/state/simStore';

export interface AgentsProps {
  sampler: IslandSampler;
  /** Instance capacity; must be >= the world's `max_agents`. */
  capacity?: number;
  shadows?: boolean;
}

const BODY_RADIUS = 0.5;
const BODY_LENGTH = 0.7;
const BOB_SPEED = 0.008;
const BOB_AMOUNT = 0.07;
const SELECTED_SCALE = 1.35;
const FLAG_LLM = 1;

export function Agents({
  sampler,
  capacity = 1024,
  shadows = true,
}: AgentsProps): React.ReactElement {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const colour = useMemo(() => new THREE.Color(), []);
  const hidden = useMemo(() => new THREE.Matrix4().makeScale(0, 0, 0), []);

  /** Instance slot -> agent id, rebuilt every frame. */
  const slotToAgent = useRef<number[]>([]);

  const select = useSelectionStore((state) => state.select);
  const hover = useSelectionStore((state) => state.hover);
  const requestFly = useSelectionStore((state) => state.requestFly);

  useEffect(() => {
    const mesh = meshRef.current;
    if (!mesh) return;
    for (let index = 0; index < capacity; index += 1) {
      mesh.setMatrixAt(index, hidden);
      mesh.setColorAt(index, colour.set(tribeColor(-1)));
    }
    mesh.count = 0;
    mesh.instanceMatrix.needsUpdate = true;
  }, [capacity, colour, hidden]);

  useFrame(() => {
    const mesh = meshRef.current;
    if (!mesh) return;

    const { currentFrame, previousFrame } = simState();
    if (!currentFrame || currentFrame.stride <= 0) {
      mesh.count = 0;
      return;
    }

    const { selectedAgentId, hoveredAgentId } = useSelectionStore.getState();
    const now = performance.now();
    const alpha = frameAlpha(previousFrame, currentFrame, now);
    const total = Math.min(capacity, Math.floor(currentFrame.agents.length / currentFrame.stride));
    const slots = slotToAgent.current;
    slots.length = total;

    for (let index = 0; index < total; index += 1) {
      const pose = interpolatePose(previousFrame, currentFrame, index, alpha);
      if (!pose) continue;
      slots[index] = pose.id;

      const ground = sampler.heightAt(pose.x, pose.z);
      // Walk bob: a hint of squash-and-stretch.
      const bob = Math.sin(now * BOB_SPEED + index) * BOB_AMOUNT;
      const emphasis =
        pose.id === selectedAgentId
          ? SELECTED_SCALE
          : pose.id === hoveredAgentId
            ? (1 + SELECTED_SCALE) / 2
            : 1;

      dummy.position.set(pose.x, ground + (BODY_RADIUS + BODY_LENGTH / 2) * emphasis, pose.z);
      dummy.rotation.set(0, -pose.heading, 0);
      dummy.scale.set((1 - bob * 0.5) * emphasis, (1 + bob) * emphasis, (1 - bob * 0.5) * emphasis);
      dummy.updateMatrix();
      mesh.setMatrixAt(index, dummy.matrix);

      // LLM minds glow faintly; everyone else wears their tribe colour.
      const base = tribeColor(pose.tribe);
      mesh.setColorAt(index, colour.set(pose.flags & FLAG_LLM ? '#f6e7a8' : base));
    }

    mesh.count = total;
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  });

  const agentAt = useCallback((instanceId: number | undefined): number | null => {
    if (instanceId === undefined) return null;
    return slotToAgent.current[instanceId] ?? null;
  }, []);

  const onClick = useCallback(
    (event: ThreeEvent<MouseEvent>) => {
      const id = agentAt(event.instanceId);
      if (id === null) return;
      event.stopPropagation();
      select(id);
    },
    [agentAt, select],
  );

  const onDoubleClick = useCallback(
    (event: ThreeEvent<MouseEvent>) => {
      const id = agentAt(event.instanceId);
      if (id === null) return;
      event.stopPropagation();
      select(id);
      requestFly(event.point.x, event.point.z);
    },
    [agentAt, select, requestFly],
  );

  const onPointerMove = useCallback(
    (event: ThreeEvent<PointerEvent>) => {
      const id = agentAt(event.instanceId);
      if (id !== null) {
        event.stopPropagation();
        hover(id);
      }
    },
    [agentAt, hover],
  );

  const onPointerOut = useCallback(() => hover(null), [hover]);

  return (
    <instancedMesh
      ref={meshRef}
      args={[undefined, undefined, capacity]}
      castShadow={shadows}
      receiveShadow={shadows}
      frustumCulled={false}
      onClick={onClick}
      onDoubleClick={onDoubleClick}
      onPointerMove={onPointerMove}
      onPointerOut={onPointerOut}
    >
      <capsuleGeometry args={[BODY_RADIUS, BODY_LENGTH, 4, 12]} />
      <meshStandardMaterial roughness={0.65} metalness={0} />
    </instancedMesh>
  );
}
