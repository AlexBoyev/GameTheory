/**
 * The application shell: one canvas, one socket, and the HUD around it.
 *
 * The socket is owned here (not in a store) so React's lifecycle closes it;
 * envelopes are pushed straight into the sim store.
 */

import { Canvas } from '@react-three/fiber';
import { useEffect } from 'react';

import { createWorldSocket } from '@/api/ws';
import { useKeyboard } from '@/app/useKeyboard';
import { useSimPolling } from '@/app/useSimPolling';
import { useSocietyPolling } from '@/app/useSocietyPolling';
import { useUrlState } from '@/app/useUrlState';
import { World } from '@/scene/World';
import { Hud } from '@/ui/Hud';
import { useSettingsStore } from '@/state/settingsStore';
import { useSimStore } from '@/state/simStore';

export function App(): React.ReactElement {
  const profile = useSettingsStore((state) => state.profile());

  useEffect(() => {
    const { ingest, setConnection } = useSimStore.getState();
    const socket = createWorldSocket({ onEnvelope: ingest, onStatus: setConnection });
    return () => socket.close();
  }, []);

  useSimPolling();
  useSocietyPolling();
  useKeyboard();
  useUrlState();

  return (
    <div className="relative h-full w-full">
      <Canvas
        shadows={profile.shadows}
        dpr={profile.dpr}
        camera={{ position: [140, 110, 140], fov: 42, near: 0.5, far: 2000 }}
        // `preserveDrawingBuffer` is what makes the screenshot button
        // possible: without it the buffer is cleared before `toDataURL` can
        // read it and you get a blank PNG.
        gl={{ antialias: true, preserveDrawingBuffer: true }}
      >
        <World />
      </Canvas>

      <Hud />
    </div>
  );
}
