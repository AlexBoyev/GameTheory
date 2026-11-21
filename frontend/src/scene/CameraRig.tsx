/**
 * Orbit, zoom, pan, keyboard panning, follow-selected and fly-to.
 *
 * Clamped so the observer cannot get under the island or lose the camera in
 * the sea. Following works by moving the orbit *target* to the agent, so the
 * usual orbit and zoom controls keep working while you follow someone.
 */

import { OrbitControls } from '@react-three/drei';
import { useFrame, useThree } from '@react-three/fiber';
import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib';

import { frameAlpha, interpolatePose, readPose } from '@/lib/interpolation';
import type { IslandSampler } from '@/lib/terrain';
import { useSelectionStore } from '@/state/selectionStore';
import { simState } from '@/state/simStore';

export interface CameraRigProps {
  /** World extent; zoom limits are derived from it. */
  size: number;
  sampler: IslandSampler;
}

const PAN_SPEED = 42;
const ROTATE_SPEED = 1.4;
const FLY_EASE = 0.12;
const FOLLOW_EASE = 0.18;

export function CameraRig({ size, sampler }: CameraRigProps): React.ReactElement {
  const controlsRef = useRef<OrbitControlsImpl>(null);
  const keys = useRef(new Set<string>());
  const flyTo = useRef<THREE.Vector3 | null>(null);
  const camera = useThree((three) => three.camera);

  useEffect(() => {
    const down = (event: KeyboardEvent): void => {
      // Never steal keys from a text field.
      if (event.target instanceof HTMLInputElement) return;
      keys.current.add(event.key.toLowerCase());
    };
    const up = (event: KeyboardEvent): void => {
      keys.current.delete(event.key.toLowerCase());
    };
    const blur = (): void => keys.current.clear();

    window.addEventListener('keydown', down);
    window.addEventListener('keyup', up);
    window.addEventListener('blur', blur);
    return () => {
      window.removeEventListener('keydown', down);
      window.removeEventListener('keyup', up);
      window.removeEventListener('blur', blur);
    };
  }, []);

  useFrame((_, delta) => {
    const controls = controlsRef.current;
    if (!controls) return;

    const pressed = keys.current;
    const limit = size / 2;

    // --- fly-to requests (double-click, or clicking an event)
    const requested = useSelectionStore.getState().flyTarget;
    if (requested) {
      flyTo.current = new THREE.Vector3(
        requested.x,
        sampler.heightAt(requested.x, requested.z),
        requested.z,
      );
      useSelectionStore.getState().consumeFly();
    }

    // --- follow the selected agent by dragging the orbit target along
    const { selectedAgentId, following } = useSelectionStore.getState();
    if (following && selectedAgentId !== null) {
      const { currentFrame, previousFrame } = simState();
      if (currentFrame && currentFrame.stride > 0) {
        const total = Math.floor(currentFrame.agents.length / currentFrame.stride);
        for (let index = 0; index < total; index += 1) {
          if (readPose(currentFrame, index)?.id !== selectedAgentId) continue;
          const pose = interpolatePose(
            previousFrame,
            currentFrame,
            index,
            frameAlpha(previousFrame, currentFrame, performance.now()),
          );
          if (pose) {
            flyTo.current = null;
            const target = new THREE.Vector3(pose.x, sampler.heightAt(pose.x, pose.z), pose.z);
            const offset = camera.position.clone().sub(controls.target);
            controls.target.lerp(target, FOLLOW_EASE);
            camera.position.copy(controls.target).add(offset);
          }
          break;
        }
      }
    } else if (flyTo.current) {
      const offset = camera.position.clone().sub(controls.target);
      controls.target.lerp(flyTo.current, FLY_EASE);
      camera.position.copy(controls.target).add(offset);
      if (controls.target.distanceTo(flyTo.current) < 0.5) flyTo.current = null;
    }

    // --- keyboard panning, relative to where the camera is looking
    let forward = 0;
    let strafe = 0;
    if (pressed.has('w') || pressed.has('arrowup')) forward += 1;
    if (pressed.has('s') || pressed.has('arrowdown')) forward -= 1;
    if (pressed.has('a') || pressed.has('arrowleft')) strafe -= 1;
    if (pressed.has('d') || pressed.has('arrowright')) strafe += 1;

    if (forward !== 0 || strafe !== 0) {
      useSelectionStore.getState().setFollowing(false);
      flyTo.current = null;
      const heading = new THREE.Vector3();
      camera.getWorldDirection(heading);
      heading.y = 0;
      heading.normalize();
      const right = new THREE.Vector3(-heading.z, 0, heading.x);
      const move = heading
        .multiplyScalar(forward)
        .add(right.multiplyScalar(strafe))
        .normalize()
        .multiplyScalar(PAN_SPEED * delta);

      controls.target.add(move);
      controls.target.x = THREE.MathUtils.clamp(controls.target.x, -limit, limit);
      controls.target.z = THREE.MathUtils.clamp(controls.target.z, -limit, limit);
      camera.position.add(move);
    }

    // --- Q/E orbit
    const spin = (pressed.has('q') ? 1 : 0) - (pressed.has('e') ? 1 : 0);
    if (spin !== 0) {
      const offset = camera.position.clone().sub(controls.target);
      offset.applyAxisAngle(new THREE.Vector3(0, 1, 0), spin * ROTATE_SPEED * delta);
      camera.position.copy(controls.target).add(offset);
    }

    controls.update();
  });

  return (
    <OrbitControls
      ref={controlsRef}
      makeDefault
      enableDamping
      dampingFactor={0.08}
      minDistance={size * 0.03}
      maxDistance={size * 1.6}
      // Stop just short of the horizon so the camera stays above the water.
      maxPolarAngle={Math.PI * 0.49}
      minPolarAngle={0.08}
      panSpeed={0.9}
      zoomSpeed={0.9}
    />
  );
}
