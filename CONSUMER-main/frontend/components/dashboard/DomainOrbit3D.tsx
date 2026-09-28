"use client";

import { useMemo, useRef, useState } from "react";
import { Canvas, useFrame, type ThreeEvent } from "@react-three/fiber";
import { Html, Line } from "@react-three/drei";
import * as THREE from "three";
import { domainTheme } from "@/components/chat/domain-theme";
import type { DomainOrbitStat } from "./DomainOrbit";

const RING_R = 1.7;

function CorePulse({ confidence }: { confidence: number }) {
  const meshRef = useRef<THREE.Mesh>(null);
  const ringRef = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    if (meshRef.current) {
      const s = 1 + Math.sin(clock.getElapsedTime() * 1.6) * 0.05;
      meshRef.current.scale.setScalar(s);
    }
    if (ringRef.current) ringRef.current.rotation.z += 0.006;
  });
  const thetaLength = Math.max(confidence, 0.02) * Math.PI * 2;
  return (
    <group>
      <mesh ref={meshRef}>
        <icosahedronGeometry args={[0.46, 2]} />
        <meshStandardMaterial color="#07080b" emissive="#00e5ff" emissiveIntensity={0.15} roughness={0.25} metalness={0.6} transparent opacity={0.9} />
      </mesh>
      <mesh ref={ringRef} rotation={[Math.PI / 2, 0, -Math.PI / 2]}>
        <ringGeometry args={[0.52, 0.58, 48, 1, 0, thetaLength]} />
        <meshBasicMaterial color="#00e5ff" transparent opacity={0.9} side={THREE.DoubleSide} />
      </mesh>
      <pointLight color="#00e5ff" intensity={2.5} distance={2.4} />
      <Html center occlude={false} style={{ pointerEvents: "none" }}>
        <div className="flex flex-col items-center">
          <span className="text-lg font-semibold text-proxy-text">{Math.round(confidence * 100)}%</span>
          <span className="text-[8px] tracking-[0.15em] text-proxy-tertiary">AVG CONFIDENCE</span>
        </div>
      </Html>
    </group>
  );
}

interface NodeDatum {
  stat: DomainOrbitStat;
  angle0: number;
  radius: number;
}

function OrbitNode({
  datum, index, total, active, onHover, onLeave, onPick,
}: {
  datum: NodeDatum;
  index: number;
  total: number;
  active: boolean;
  onHover: () => void;
  onLeave: () => void;
  onPick: () => void;
}) {
  const groupRef = useRef<THREE.Group>(null);
  const meshRef = useRef<THREE.Mesh>(null);
  const theme = domainTheme(datum.stat.domain);
  const hasActivity = datum.stat.count > 0;

  useFrame(({ clock }) => {
    if (!groupRef.current) return;
    const t = clock.getElapsedTime() * 0.12 + datum.angle0;
    const x = Math.cos(t) * datum.radius;
    const z = Math.sin(t) * datum.radius;
    const y = Math.sin(t * 2 + index) * 0.12;
    groupRef.current.position.set(x, y, z);
    if (meshRef.current) {
      const s = active ? 1.35 : 1;
      meshRef.current.scale.lerp(new THREE.Vector3(s, s, s), 0.2);
    }
  });

  return (
    <group ref={groupRef}>
      <mesh
        ref={meshRef}
        onPointerOver={(e: ThreeEvent<PointerEvent>) => { e.stopPropagation(); onHover(); }}
        onPointerOut={(e: ThreeEvent<PointerEvent>) => { e.stopPropagation(); onLeave(); }}
        onClick={(e: ThreeEvent<MouseEvent>) => { e.stopPropagation(); onPick(); }}
      >
        <icosahedronGeometry args={[datum.radius > 0 ? 0.14 + (datum.stat.count / total) * 0.1 : 0.1, 1]} />
        <meshStandardMaterial
          color={theme.color}
          emissive={theme.color}
          emissiveIntensity={active ? 1.2 : hasActivity ? 0.7 : 0.25}
          roughness={0.35}
          metalness={0.4}
          transparent
          opacity={hasActivity ? 1 : 0.4}
        />
      </mesh>
      {hasActivity && <pointLight color={theme.color} intensity={active ? 2.4 : 1} distance={1.1} />}
    </group>
  );
}

// Built imperatively via THREE.Line + primitive (rather than the JSX <line>
// intrinsic) since React's ambient SVG typings and R3F's both claim the
// lowercase `line` tag, which TS resolves to the wrong one in this file.
function SpokeLine({ node, index, color, active }: { node: NodeDatum; index: number; color: string; active: boolean }) {
  const lineObj = useMemo(() => {
    const geometry = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0, 0, 0), new THREE.Vector3(node.radius, 0, 0)]);
    const material = new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.14 });
    return new THREE.Line(geometry, material);
  }, [color, node.radius]);

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime() * 0.12 + node.angle0;
    const x = Math.cos(t) * node.radius;
    const z = Math.sin(t) * node.radius;
    const y = Math.sin(t * 2 + index) * 0.12;
    const pos = lineObj.geometry.attributes.position as THREE.BufferAttribute;
    pos.setXYZ(1, x, y, z);
    pos.needsUpdate = true;
    (lineObj.material as THREE.LineBasicMaterial).opacity = active ? 0.6 : 0.14;
  });

  return <primitive object={lineObj} />;
}

function Spokes({ nodes, activeDomain }: { nodes: NodeDatum[]; activeDomain: string | null }) {
  return (
    <group>
      {nodes.map((n, i) => (
        <SpokeLine key={n.stat.domain} node={n} index={i} color={domainTheme(n.stat.domain).color} active={activeDomain === n.stat.domain} />
      ))}
    </group>
  );
}

function Scene({
  stats, overallConfidence, activeDomain, onHover, onLeave, onPick,
}: {
  stats: DomainOrbitStat[];
  overallConfidence: number | null;
  activeDomain: string | null;
  onHover: (d: string) => void;
  onLeave: () => void;
  onPick: (d: string) => void;
}) {
  const groupRef = useRef<THREE.Group>(null);
  const target = useRef({ x: 0, y: 0 });
  const total = Math.max(1, ...stats.map((s) => s.count));

  const nodes: NodeDatum[] = useMemo(
    () => stats.map((stat, i) => ({ stat, angle0: (i / stats.length) * Math.PI * 2, radius: RING_R })),
    [stats]
  );

  useFrame(({ pointer }) => {
    if (!groupRef.current) return;
    target.current.x = pointer.x * 0.25;
    target.current.y = pointer.y * 0.12;
    groupRef.current.rotation.y += (target.current.x - groupRef.current.rotation.y) * 0.03;
    groupRef.current.rotation.x += (0.32 - target.current.y * 0.3 - groupRef.current.rotation.x) * 0.03;
  });

  return (
    <group ref={groupRef} rotation={[0.32, 0, 0]}>
      <ambientLight intensity={0.55} />
      <Line
        points={Array.from({ length: 65 }, (_, i) => {
          const a = (i / 64) * Math.PI * 2;
          return [Math.cos(a) * RING_R, 0, Math.sin(a) * RING_R] as [number, number, number];
        })}
        color="#ffffff"
        transparent
        opacity={0.08}
      />
      <Spokes nodes={nodes} activeDomain={activeDomain} />
      <CorePulse confidence={overallConfidence ?? 0} />
      {nodes.map((n, i) => (
        <OrbitNode
          key={n.stat.domain}
          datum={n}
          index={i}
          total={total}
          active={activeDomain === n.stat.domain}
          onHover={() => onHover(n.stat.domain)}
          onLeave={onLeave}
          onPick={() => onPick(n.stat.domain)}
        />
      ))}
    </group>
  );
}

export default function DomainOrbit3D({
  stats, overallConfidence, totalRuns, onSelect,
}: {
  stats: DomainOrbitStat[];
  overallConfidence: number | null;
  totalRuns: number;
  onSelect: (domain: string) => void;
}) {
  const [active, setActive] = useState<string | null>(null);
  const activeStat = stats.find((s) => s.domain === active) ?? null;
  const activeTheme = activeStat ? domainTheme(activeStat.domain) : null;

  return (
    <div className="relative flex flex-1 flex-col items-center justify-center py-4">
      <div className="orbit-ring pointer-events-none absolute" style={{ width: 364, height: 364 }} />
      <div className="orbit-ring-slow pointer-events-none absolute" style={{ width: 400, height: 400 }} />

      <div className="relative h-[320px] w-[320px]">
        <Canvas
          dpr={[1, 1.5]}
          gl={{ antialias: true, alpha: true, powerPreference: "low-power" }}
          camera={{ position: [0, 1.6, 4.6], fov: 42 }}
        >
          <Scene
            stats={stats}
            overallConfidence={overallConfidence}
            activeDomain={active}
            onHover={setActive}
            onLeave={() => setActive(null)}
            onPick={onSelect}
          />
        </Canvas>
      </div>

      <div className="mt-1 flex min-h-10 flex-col items-center text-center">
        {activeStat && activeTheme ? (
          <>
            <p className="text-sm font-medium" style={{ color: activeTheme.color }}>{activeTheme.label}</p>
            <p className="text-[11px] text-proxy-tertiary">
              {activeStat.count} analys{activeStat.count === 1 ? "is" : "es"}
              {activeStat.avgConfidence !== null ? ` · ${Math.round(activeStat.avgConfidence * 100)}% confidence` : ""}
              {" · click to explore"}
            </p>
          </>
        ) : (
          <p className="text-[11px] text-proxy-tertiary">{totalRuns} total agent runs &middot; hover a node to inspect</p>
        )}
      </div>

      <style jsx>{`
        .orbit-ring {
          border-radius: 9999px;
          border: 1px dashed rgba(0, 229, 255, 0.12);
          animation: spin 70s linear infinite;
        }
        .orbit-ring-slow {
          border-radius: 9999px;
          border: 1px dashed rgba(155, 92, 255, 0.08);
          animation: spin 110s linear infinite reverse;
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
