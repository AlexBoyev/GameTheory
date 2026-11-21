/**
 * What the deliberative agents say, over their heads (SPEC 9.2).
 *
 * This is the only place the LLM layer is visible in the world itself, so it
 * has to read at a glance and never get in the way: a few bubbles at a time,
 * each expiring on its own timer, drawn on canvas textures rather than DOM
 * overlays so they sort and scale with the scene.
 *
 * Not instanced, unlike `StateIcons`: every bubble has different text, so
 * each needs its own texture anyway, and there are at most a handful.
 */

import { useFrame, useThree } from '@react-three/fiber';
import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';

import { frameAlpha, findPoseById } from '@/lib/interpolation';
import type { IslandSampler } from '@/lib/terrain';
import { simState, useSimStore, type SpeechLine } from '@/state/simStore';
import { useUiStore } from '@/state/uiStore';

const BUBBLE_HEIGHT = 4.2;
const PIXELS_PER_UNIT = 26;
const MAX_CHARS_PER_LINE = 26;
const FADE_MS = 600;

/** Wrap `text` to lines of at most `MAX_CHARS_PER_LINE`, on word boundaries. */
function wrap(text: string): string[] {
  const lines: string[] = [];
  let line = '';
  for (const word of text.split(/\s+/)) {
    const candidate = line ? `${line} ${word}` : word;
    if (candidate.length > MAX_CHARS_PER_LINE && line) {
      lines.push(line);
      line = word;
    } else {
      line = candidate;
    }
  }
  if (line) lines.push(line);
  return lines.slice(0, 3);
}

function roundedRect(
  context: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number,
): void {
  context.beginPath();
  context.moveTo(x + radius, y);
  context.arcTo(x + width, y, x + width, y + height, radius);
  context.arcTo(x + width, y + height, x, y + height, radius);
  context.arcTo(x, y + height, x, y, radius);
  context.arcTo(x, y, x + width, y, radius);
  context.closePath();
}

interface Bubble {
  texture: THREE.CanvasTexture;
  width: number;
  height: number;
}

/** Draw one bubble onto its own canvas, sized to the text. */
function drawBubble(text: string): Bubble {
  const lines = wrap(text);
  const fontSize = 22;
  const padding = 14;
  const lineHeight = fontSize * 1.3;

  const measure = document.createElement('canvas').getContext('2d');
  if (measure) measure.font = `500 ${fontSize}px system-ui, sans-serif`;
  const textWidth = Math.max(
    60,
    ...lines.map((line) => (measure ? measure.measureText(line).width : line.length * 10)),
  );

  const canvas = document.createElement('canvas');
  // Device pixels, so the text is crisp when the camera is close.
  canvas.width = Math.ceil(textWidth + padding * 2);
  canvas.height = Math.ceil(lines.length * lineHeight + padding * 2);

  const context = canvas.getContext('2d');
  if (context) {
    context.font = `500 ${fontSize}px system-ui, sans-serif`;
    context.textBaseline = 'middle';
    context.fillStyle = 'rgba(248, 250, 252, 0.94)';
    roundedRect(context, 1, 1, canvas.width - 2, canvas.height - 2, 14);
    context.fill();
    context.strokeStyle = 'rgba(100, 116, 139, 0.55)';
    context.lineWidth = 2;
    context.stroke();

    context.fillStyle = '#1e293b';
    lines.forEach((line, index) => {
      context.fillText(line, padding, padding + lineHeight * (index + 0.5));
    });
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return {
    texture,
    width: canvas.width / PIXELS_PER_UNIT,
    height: canvas.height / PIXELS_PER_UNIT,
  };
}

export interface SpeechBubblesProps {
  sampler: IslandSampler;
}

export function SpeechBubbles({ sampler }: SpeechBubblesProps): React.ReactElement | null {
  const lines = useSimStore((state) => state.speech);
  const enabled = useUiStore((state) => state.showSpeechBubbles);
  const camera = useThree((three) => three.camera);
  const groups = useRef(new Map<number, THREE.Object3D>());

  const bubbles = useMemo(() => {
    const drawn = new Map<number, Bubble>();
    for (const line of lines) drawn.set(line.agentId, drawBubble(line.text));
    return drawn;
  }, [lines]);

  // Canvas textures hold a GPU allocation each; dropping the React element is
  // not enough to release them.
  useEffect(
    () => () => bubbles.forEach((bubble) => bubble.texture.dispose()),
    [bubbles],
  );

  useFrame(() => {
    if (!enabled) return;
    const { currentFrame, previousFrame } = simState();
    const now = performance.now();
    const alpha = frameAlpha(previousFrame, currentFrame, now);

    for (const line of lines) {
      const group = groups.current.get(line.agentId);
      if (!group) continue;
      const pose = findPoseById(previousFrame, currentFrame, line.agentId, alpha);
      const remaining = line.until - now;
      if (!pose || remaining <= 0) {
        group.visible = false;
        continue;
      }
      group.visible = true;
      group.position.set(pose.x, sampler.heightAt(pose.x, pose.z) + BUBBLE_HEIGHT, pose.z);
      group.quaternion.copy(camera.quaternion);
      const fade = Math.min(1, remaining / FADE_MS);
      group.scale.setScalar(0.85 + 0.15 * fade);
      const mesh = group.children[0];
      if (mesh instanceof THREE.Mesh && mesh.material instanceof THREE.MeshBasicMaterial) {
        mesh.material.opacity = fade;
      }
    }
  });

  if (!enabled || lines.length === 0) return null;

  return (
    <>
      {lines.map((line: SpeechLine) => {
        const bubble = bubbles.get(line.agentId);
        if (!bubble) return null;
        return (
          <group
            key={`${line.agentId}-${line.until}`}
            ref={(group) => {
              if (group) groups.current.set(line.agentId, group);
              else groups.current.delete(line.agentId);
            }}
            visible={false}
          >
            <mesh frustumCulled={false}>
              <planeGeometry args={[bubble.width, bubble.height]} />
              <meshBasicMaterial
                map={bubble.texture}
                transparent
                opacity={1}
                depthWrite={false}
                toneMapped={false}
              />
            </mesh>
          </group>
        );
      })}
    </>
  );
}
