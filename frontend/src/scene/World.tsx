/**
 * Everything inside the canvas.
 *
 * The island sampler is the scene's single source of truth for "how high is
 * the ground here". From Phase 2 it comes from the backend heightmap, which
 * is what keeps agents standing on the same island the simulation thinks they
 * are walking on; the browser-side noise island remains as a fallback for
 * when the terrain endpoint is unavailable.
 */

import { useEffect, useMemo, useState } from 'react';

import { createGridSampler, fetchTerrain, type TerrainGrid } from '@/api/terrain';
import { createIslandSampler } from '@/lib/terrain';
import { Agents } from '@/scene/Agents';
import { CameraRig } from '@/scene/CameraRig';
import { Lighting } from '@/scene/Lighting';
import { PerfProbe } from '@/scene/PerfProbe';
import { Resources } from '@/scene/Resources';
import { SelectionRing } from '@/scene/SelectionRing';
import { Shelters } from '@/scene/Shelters';
import { Heatmap } from '@/scene/Heatmap';
import { NameTags } from '@/scene/NameTags';
import { Screenshotter } from '@/scene/Screenshotter';
import { SpeechBubbles } from '@/scene/SpeechBubbles';
import { StateIcons } from '@/scene/StateIcons';
import { Terrain } from '@/scene/Terrain';
import { Territories } from '@/scene/Territories';
import { TrustLines } from '@/scene/TrustLines';
import { Water } from '@/scene/Water';
import { useSettingsStore } from '@/state/settingsStore';
import { useSimStore } from '@/state/simStore';
import { useUiStore } from '@/state/uiStore';

const FALLBACK_TERRAIN = { size: 256, resolution: 128, water_level: 0.32, max_height: 18 };
const MAX_MESH_SEGMENTS = 160;

export function World(): React.ReactElement {
  const terrain = useSimStore((state) => state.terrain);
  const seed = useSimStore((state) => state.seed);
  const worldEpoch = useSimStore((state) => state.worldEpoch);
  const maxAgents = useSimStore((state) => state.config?.max_agents ?? 1024);
  const quality = useSettingsStore((state) => state.quality);
  const profile = useSettingsStore((state) => state.profile());
  const showHeatmap = useUiStore((state) => state.showHeatmap);
  const showNames = useUiStore((state) => state.showNames);
  const showTrustLines = useUiStore((state) => state.showTrustLines);
  const showTerritories = useUiStore((state) => state.showTerritories);

  const [loaded, setLoaded] = useState<{ epoch: number; grid: TerrainGrid } | null>(null);
  const available = terrain?.available ?? false;

  // Refetch per world, not per connection: `worldEpoch` advances on every
  // `hello`, which is exactly when a reset has given us a new island.
  useEffect(() => {
    if (!available) return;
    let cancelled = false;
    void fetchTerrain()
      .then((grid) => {
        if (!cancelled) setLoaded({ epoch: worldEpoch, grid });
      })
      .catch(() => {
        // Leave the fallback island in place; the banner already says we are
        // not fully connected, and a missing heightmap is not fatal.
      });
    return () => {
      cancelled = true;
    };
  }, [available, worldEpoch]);

  // Tagging the fetch with its epoch means a reset falls back to the noise
  // island for the one frame before the new heightmap lands, instead of
  // drawing agents on the world they just left.
  const grid = loaded?.epoch === worldEpoch ? loaded.grid : null;

  const meta = terrain ?? FALLBACK_TERRAIN;

  const sampler = useMemo(
    () =>
      grid
        ? createGridSampler(grid)
        : createIslandSampler({
            size: meta.size,
            maxHeight: meta.max_height,
            waterLevel: meta.water_level,
            seed,
          }),
    [grid, meta.size, meta.max_height, meta.water_level, seed],
  );

  const segments = grid
    ? Math.min(MAX_MESH_SEGMENTS, grid.resolution - 1)
    : quality === 'low'
      ? 72
      : 128;

  return (
    <>
      <color attach="background" args={['#cfe9f5']} />
      <fog attach="fog" args={['#dceff7', meta.size * 0.9, meta.size * 2.6]} />

      <PerfProbe />
      <Lighting size={meta.size} shadows={profile.shadows} />
      <Terrain sampler={sampler} segments={segments} />
      <Water sampler={sampler} />
      <Resources sampler={sampler} />
      <Shelters sampler={sampler} />
      <Agents sampler={sampler} capacity={Math.max(256, maxAgents)} shadows={profile.shadows} />
      <StateIcons sampler={sampler} capacity={Math.max(256, maxAgents)} />
      <SpeechBubbles sampler={sampler} />
      <Screenshotter />
      <SelectionRing sampler={sampler} />

      {showHeatmap && <Heatmap />}
      {showNames && <NameTags sampler={sampler} />}
      {showTrustLines && <TrustLines sampler={sampler} />}
      {showTerritories && <Territories sampler={sampler} />}

      <CameraRig size={meta.size} sampler={sampler} />
    </>
  );
}
