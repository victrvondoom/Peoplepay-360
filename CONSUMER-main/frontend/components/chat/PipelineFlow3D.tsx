"use client";

import { useMemo, useRef, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Line } from "@react-three/drei";
import { Check, Loader2 } from "lucide-react";
import * as THREE from "three";

export interface FlowStage {
  key: string;
  label: string;
  done: boolean;
  active: boolean;
}

// Text labels are NOT rendered inside the Canvas (see below for why) --
// only the sphere/curve/particle visual lives in 3D. That visual sits in a
// narrow, fixed-width column, so its geometry is kept tight and centered
// rather than swinging wide, since anything drifting past the canvas edge
// just gets clipped by the panel's rounded border.
function stagePositions(count: number): [number, number, number][] {
  return Array.from({ length: count }, (_, i) => {
    const t = count <= 1 ? 0 : i / (count - 1);
    return [Math.sin(i * 1.3) * 0.18, 1.05 - t * 2.1, Math.cos(i * 1.3) * 0.4] as [number, number, number];
  });
}

// Ambient "thinking" particles drift the full length of the path at all
// times -- faint and slow while idle, brighter and faster while an agent is
// actually processing -- so the scene never looks static, only quieter.
function AmbientFlow({ curve, color, processing }: { curve: THREE.CatmullRomCurve3; color: string; processing: boolean }) {
  const count = 8;
  const refs = useRef<(THREE.Mesh | null)[]>([]);
  useFrame(({ clock }) => {
    const speed = processing ? 0.22 : 0.07;
    for (let i = 0; i < count; i++) {
      const mesh = refs.current[i];
      if (!mesh) continue;
      const phase = (clock.getElapsedTime() * speed + i / count) % 1;
      mesh.position.copy(curve.getPointAt(phase));
      const mat = mesh.material as THREE.MeshBasicMaterial;
      mat.opacity = (processing ? 0.75 : 0.28) * Math.sin(phase * Math.PI);
    }
  });
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <mesh key={i} ref={(m) => { refs.current[i] = m; }}>
          <sphereGeometry args={[0.032, 6, 6]} />
          <meshBasicMaterial color={color} transparent opacity={0} />
        </mesh>
      ))}
    </>
  );
}

function Node({ position, color, done, active }: { position: [number, number, number]; color: string; done: boolean; active: boolean }) {
  const meshRef = useRef<THREE.Mesh>(null);
  const ringRef = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    if (meshRef.current) {
      const pulse = active ? 1 + Math.sin(clock.getElapsedTime() * 3.4) * 0.16 : done ? 1 : 0.68;
      meshRef.current.scale.lerp(new THREE.Vector3(pulse, pulse, pulse), 0.18);
    }
    if (ringRef.current) {
      ringRef.current.rotation.z += active ? 0.045 : 0.006;
      const s = active ? 1.7 : 1.3;
      ringRef.current.scale.lerp(new THREE.Vector3(s, s, 1), 0.15);
    }
  });
  const dim = !done && !active;
  return (
    <group position={position}>
      <mesh ref={meshRef}>
        <icosahedronGeometry args={[0.13, 1]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={dim ? 0.15 : active ? 1.1 : 0.7}
          roughness={0.35}
          metalness={0.4}
          transparent
          opacity={dim ? 0.35 : 1}
        />
      </mesh>
      {(active || done) && (
        <mesh ref={ringRef}>
          <ringGeometry args={[0.18, 0.2, 32]} />
          <meshBasicMaterial color={color} transparent opacity={active ? 0.55 : 0.28} side={THREE.DoubleSide} />
        </mesh>
      )}
      {!dim && <pointLight color={color} intensity={active ? 3 : 1.3} distance={0.9} />}
    </group>
  );
}

function Scene({ stages, color, processing }: { stages: FlowStage[]; color: string; processing: boolean }) {
  const groupRef = useRef<THREE.Group>(null);
  const target = useRef({ x: 0, y: 0 });
  const positions = useMemo(() => stagePositions(stages.length), [stages.length]);
  const curve = useMemo(() => new THREE.CatmullRomCurve3(positions.map((p) => new THREE.Vector3(...p)), false, "catmullrom", 0.4), [positions]);
  const fullPoints = useMemo(() => curve.getPoints(80), [curve]);

  const lastDoneIndex = stages.reduce((acc, s, i) => (s.done ? i : acc), -1);
  const activeIndex = stages.findIndex((s) => s.active);
  const progressT = lastDoneIndex >= 0 ? (lastDoneIndex + (activeIndex >= 0 ? 0.5 : 0)) / Math.max(stages.length - 1, 1) : 0;
  const progressPoints = useMemo(() => (progressT > 0 ? curve.getPoints(Math.max(Math.round(80 * progressT), 2)) : []), [curve, progressT]);

  useFrame(({ clock, pointer }) => {
    if (!groupRef.current) return;
    const rotSpeed = processing ? 0.22 : 0.1;
    target.current.x = pointer.x * 0.3;
    target.current.y = pointer.y * 0.18;
    groupRef.current.rotation.y += (target.current.x + Math.sin(clock.getElapsedTime() * rotSpeed) * 0.22 - groupRef.current.rotation.y) * 0.04;
    groupRef.current.rotation.x += (-target.current.y * 0.35 - groupRef.current.rotation.x) * 0.04;
  });

  return (
    <group ref={groupRef}>
      <ambientLight intensity={0.5} />
      <Line points={fullPoints} color="#ffffff" transparent opacity={0.1} lineWidth={1.5} />
      {progressPoints.length > 1 && <Line points={progressPoints} color={color} transparent opacity={0.8} lineWidth={2.2} />}
      <AmbientFlow curve={curve} color={color} processing={processing} />
      {stages.map((s, i) => (
        <Node key={s.key} position={positions[i]} color={color} done={s.done} active={s.active} />
      ))}
    </group>
  );
}

export default function PipelineFlow3D({ stages, color, processing }: { stages: FlowStage[]; color: string; processing: boolean }) {
  const [ready, setReady] = useState(false);
  return (
    <div className="flex h-[280px] w-full gap-2.5" onPointerEnter={() => setReady(true)}>
      {/* The 3D visual: just glowing nodes + a connecting curve + drifting
          particles, no text -- kept in its own fixed-width column so it
          never has to negotiate space with label text. */}
      <div className="relative h-full w-[86px] shrink-0 overflow-hidden rounded-lg">
        <Canvas
          dpr={[1, 1.5]}
          gl={{ antialias: true, alpha: true, powerPreference: "low-power" }}
          camera={{ position: [0, 0, 3.6], fov: 32 }}
          style={{ position: "absolute", inset: 0 }}
          onCreated={() => setReady(true)}
        >
          <Scene stages={stages} color={color} processing={processing} />
        </Canvas>
        {!ready && <div className="absolute inset-0 animate-pulse rounded-lg bg-white/[.02]" aria-hidden />}
      </div>

      {/* Labels: ordinary flexbox, vertically distributed to match the
          nodes' top-to-bottom order -- this is what guarantees the text can
          never get clipped or overflow the panel, unlike text projected
          from 3D world space into a narrow frame. */}
      <div className="flex min-w-0 flex-1 flex-col justify-between py-1.5">
        {stages.map((s) => (
          <div key={s.key} className="flex min-w-0 items-center gap-1.5">
            <span
              className="grid size-4 shrink-0 place-items-center rounded-full"
              style={{ backgroundColor: s.done ? color : s.active ? `${color}30` : "rgba(255,255,255,.06)" }}
            >
              {s.done ? (
                <Check className="size-2.5 text-black" />
              ) : s.active ? (
                <Loader2 className="size-2.5 animate-spin" style={{ color }} />
              ) : null}
            </span>
            <span
              className="truncate text-[11px] font-medium"
              style={{ color: s.done || s.active ? color : "var(--proxy-tertiary)" }}
            >
              {s.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
