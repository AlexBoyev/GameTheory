/**
 * Saving a PNG without making every frame pay for it.
 *
 * The obvious way is `preserveDrawingBuffer: true` on the WebGL context, so
 * the buffer is still readable after a frame. It also makes the driver keep a
 * copy of every frame forever, which headless Chrome reports as "GPU stall
 * due to ReadPixels" and which costs real frame time on a scene this size.
 *
 * So instead: no flag, and when a shot is requested this re-renders the scene
 * and reads the canvas in the same turn of the loop, before the browser has a
 * chance to clear it. The cost lands on the one frame you asked for.
 */

import { useFrame } from '@react-three/fiber';

import { screenshotName } from '@/lib/screenshot';
import { useScreenshotStore } from '@/state/screenshotStore';
import { simState } from '@/state/simStore';

export function Screenshotter(): null {
  useFrame((state) => {
    const { requested, resolve } = useScreenshotStore.getState();
    if (!requested) return;

    // Render first: without this the buffer may already have been presented
    // and cleared, and `toDataURL` returns a blank image.
    state.gl.render(state.scene, state.camera);

    let url: string;
    try {
      url = state.gl.domElement.toDataURL('image/png');
    } catch {
      // Some browsers refuse to export a canvas; say so rather than
      // appearing to do nothing.
      resolve(false);
      return;
    }

    if (url.startsWith('data:image/png') && url.length > 100) {
      const link = document.createElement('a');
      link.href = url;
      link.download = screenshotName(simState().tick);
      link.click();
      resolve(true);
    } else {
      resolve(false);
    }
  });

  return null;
}
