/**
 * Berry bushes, trees, animals and stone - one `InstancedMesh` per kind.
 *
 * Phase 2 draws them as simple rounded shapes so the simulation is legible:
 * you can watch an agent walk to a bush and the bush visibly empty. Phase 3
 * replaces these with the proper toy-diorama vegetation.
 */

import { useFrame } from '@react-three/fiber';
import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';

import type { IslandSampler } from '@/lib/terrain';
import { simState, useSimStore, type ResourceNode } from '@/state/simStore';

export interface ResourcesProps {
  sampler: IslandSampler;
}

interface KindStyle {
  colour: string;
  radius: number;
  /** How much the shape shrinks as the node is harvested (0 = not at all). */
  shrink: number;
  /** Lift above the ground, as a multiple of radius. */
  lift: number;
  roughness: number;
}

const STYLES: Record<string, KindStyle> = {
  berry_bush: { colour: '#7fae6b', radius: 0.95, shrink: 0.45, lift: 0.9, roughness: 0.8 },
  tree: { colour: '#5f9465', radius: 1.9, shrink: 0.15, lift: 1.5, roughness: 0.85 },
  rabbit: { colour: '#f1e7dc', radius: 0.38, shrink: 0, lift: 1.0, roughness: 0.6 },
  deer: { colour: '#b98c62', radius: 0.85, shrink: 0, lift: 1.1, roughness: 0.6 },
  stone: { colour: '#b3b0a8', radius: 0.8, shrink: 0, lift: 0.7, roughness: 1.0 },
  corpse: { colour: '#9c6a6a', radius: 0.5, shrink: 0.6, lift: 0.5, roughness: 0.7 },
};

/** Water is drawn by the water plane, not as nodes. */
const HIDDEN = new Set(['water']);

interface KindProps {
  nodes: ResourceNode[];
  style: KindStyle;
  sampler: IslandSampler;
}

function KindInstances({ nodes, style, sampler }: KindProps): React.ReactElement {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);

  const write = (mesh: THREE.InstancedMesh, index: number, node: ResourceNode, scale: number) => {
    dummy.position.set(
      node.x,
      sampler.heightAt(node.x, node.z) + style.radius * style.lift * scale,
      node.z,
    );
    dummy.scale.setScalar(scale);
    dummy.rotation.set(0, (node.id % 8) * 0.4, 0);
    dummy.updateMatrix();
    mesh.setMatrixAt(index, dummy.matrix);
  };

  // Positions never move, so the matrices are written once per world - not,
  // as an omitted dependency array would have it, on every React render.
  useEffect(() => {
    const mesh = meshRef.current;
    if (!mesh) return;
    nodes.forEach((node, index) => write(mesh, index, node, 1));
    mesh.count = nodes.length;
    mesh.instanceMatrix.needsUpdate = true;
    // `write` closes over `sampler` and `style`, which are the other inputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, sampler, style]);

  // Amounts change constantly; shrink harvested nodes with no React re-render.
  useFrame(() => {
    const mesh = meshRef.current;
    if (!mesh || style.shrink <= 0) return;
    const amounts = simState().resourceAmounts;

    nodes.forEach((node, index) => {
      // The wire carries fullness in 0..1, already quantised to 2% steps.
      const fullness = amounts.get(node.id);
      if (fullness === undefined) return;
      write(mesh, index, node, 1 - style.shrink * (1 - Math.max(0, Math.min(1, fullness))));
    });
    mesh.instanceMatrix.needsUpdate = true;
  });

  return (
    <instancedMesh
      ref={meshRef}
      args={[undefined, undefined, Math.max(1, nodes.length)]}
      castShadow
      receiveShadow
      frustumCulled={false}
    >
      <sphereGeometry args={[style.radius, 10, 8]} />
      <meshStandardMaterial color={style.colour} roughness={style.roughness} metalness={0} />
    </instancedMesh>
  );
}

export function Resources({ sampler }: ResourcesProps): React.ReactElement {
  // Only the node *set* is reactive; amounts are read imperatively per frame.
  const version = useSimStore((state) => state.resourceVersion);
  const nodes = useSimStore((state) => state.resourceNodes);

  const grouped = useMemo(() => {
    const byKind = new Map<string, ResourceNode[]>();
    for (const node of nodes) {
      if (HIDDEN.has(node.kind) || !STYLES[node.kind]) continue;
      const bucket = byKind.get(node.kind);
      if (bucket) bucket.push(node);
      else byKind.set(node.kind, [node]);
    }
    return [...byKind.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [nodes]);

  return (
    <>
      {grouped.map(([kind, kindNodes]) => (
        <KindInstances
          key={`${kind}-${version}`}
          nodes={kindNodes}
          style={STYLES[kind]!}
          sampler={sampler}
        />
      ))}
    </>
  );
}
