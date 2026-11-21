/**
 * The island mesh: a displaced plane with smooth normals and vertex colours.
 *
 * Phase 1 builds it from the browser-side sampler. Phase 3 replaces the
 * sampler with the backend heightmap from `GET /api/world/terrain` - the mesh
 * construction below does not change.
 */

import { useEffect, useMemo } from 'react';
import * as THREE from 'three';

import { biomeColor, terrainColorAt } from '@/lib/colors';
import type { IslandSampler } from '@/lib/terrain';

export interface TerrainProps {
  sampler: IslandSampler;
  /** Grid segments per axis; 128 keeps the silhouette soft without stutter. */
  segments?: number;
}

export function Terrain({ sampler, segments = 128 }: TerrainProps): React.ReactElement {
  const geometry = useMemo(() => {
    const { size, maxHeight, waterLevel } = sampler.params;
    const geo = new THREE.PlaneGeometry(size, size, segments, segments);
    geo.rotateX(-Math.PI / 2);

    const position = geo.attributes.position as THREE.BufferAttribute;
    const colours = new Float32Array(position.count * 3);
    const colour = new THREE.Color();

    for (let index = 0; index < position.count; index += 1) {
      const x = position.getX(index);
      const z = position.getZ(index);
      const normalised = sampler.normalisedAt(x, z);
      position.setY(index, normalised * maxHeight);

      // Prefer the backend's biome classification; fall back to height bands
      // when the sampler is the browser-side noise island.
      const biome = sampler.biomeAt?.(x, z);
      colour.set(biome ? biomeColor(biome) : terrainColorAt(normalised, waterLevel));
      colours[index * 3] = colour.r;
      colours[index * 3 + 1] = colour.g;
      colours[index * 3 + 2] = colour.b;
    }

    geo.setAttribute('color', new THREE.BufferAttribute(colours, 3));
    position.needsUpdate = true;
    // Smooth normals are what makes this read as a soft toy, not a terrain mesh.
    geo.computeVertexNormals();
    return geo;
  }, [sampler, segments]);

  useEffect(() => () => geometry.dispose(), [geometry]);

  return (
    <mesh geometry={geometry} receiveShadow castShadow>
      <meshStandardMaterial vertexColors roughness={0.95} metalness={0} />
    </mesh>
  );
}
