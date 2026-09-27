"use client";

import { useMemo, useRef, useState } from "react";
import { useFrame, type ThreeEvent } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import * as THREE from "three";
import { SceneShell, SceneOrbitControls, type OrbitControlsHandle } from "../../scene/SceneShell";
import { VoidEnvironment } from "../../scene/primitives";
import { orreryAssignment } from "../../scene/layout";
import { ENTITY_COLOR } from "../../scene/legend";

export interface OrreryCase {
  caseId: string;
  title: string;
  createdAt: string | null;
  avgConfidence: number | null;
}
export interface OrreryDomain {
  domain: string;
  label: string;
  color: string;
  caseCount: number;
  cases: OrreryCase[];
  mostRecentAt: string | null;
}

export interface FootprintScene3DProps {
  domains: OrreryDomain[];
  revealedCaseIds: Set<string>;
  selectedDomain: string | null;
  onSelectDomain: (domain: string) => void;
  onSelectCase: (caseId: string) => void;
}

/** YOU -- a warm, softly pulsing sun at the center (spec 7.2). */
function SunCore() {
  const meshRef = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    const s = 1 + Math.sin(clock.getElapsedTime() * 0.7) * 0.045;
    meshRef.current?.scale.setScalar(s);
  });
  return (
    <group>
      <mesh ref={meshRef}>
        <icosahedronGeometry args={[0.62, 3]} />
        <meshStandardMaterial color="#1a0e02" emissive={ENTITY_COLOR.you} emissiveIntensity={1.4} roughness={0.3} metalness={0.15} />
      </mesh>
      <pointLight color={ENTITY_COLOR.you} intensity={6} distance={20} />
      <Html center occlude={false} style={{ pointerEvents: "none" }}>
        <span className="font-mono text-xs font-semibold tracking-[0.24em] text-amber-100">YOU</span>
      </Html>
    </group>
  );
}

function Moon({ caseItem, index, total, planetRadius, onPick }: { caseItem: OrreryCase; index: number; total: number; planetRadius: number; onPick: (id: string) => void }) {
  const ref = useRef<THREE.Group>(null);
  const angle0 = useMemo(() => (index / Math.max(total, 1)) * Math.PI * 2, [index, total]);
  const orbitR = planetRadius + 0.32 + (index % 3) * 0.13;
  const speed = 0.5 + (index % 3) * 0.15;

  useFrame(({ clock }) => {
    if (!ref.current) return;
    const t = clock.getElapsedTime() * speed + angle0;
    ref.current.position.set(Math.cos(t) * orbitR, Math.sin(t * 1.6) * 0.08, Math.sin(t) * orbitR);
  });

  return (
    <group ref={ref}>
      <mesh
        onClick={(e: ThreeEvent<MouseEvent>) => { e.stopPropagation(); onPick(caseItem.caseId); }}
        onPointerOver={(e: ThreeEvent<PointerEvent>) => { e.stopPropagation(); document.body.style.cursor = "pointer"; }}
        onPointerOut={() => { document.body.style.cursor = "auto"; }}
      >
        <sphereGeometry args={[0.06, 10, 10]} />
        <meshStandardMaterial color="#dbeafe" emissive="#8fd8ff" emissiveIntensity={0.55} roughness={0.5} />
      </mesh>
    </group>
  );
}

function DomainPlanet({
  domain, index, total, orbitRadius, planetScale, revealedCaseIds, active, onHover, onLeave, onPick, onPickCase,
}: {
  domain: OrreryDomain;
  index: number;
  total: number;
  orbitRadius: number;
  planetScale: number;
  revealedCaseIds: Set<string>;
  active: boolean;
  onHover: () => void;
  onLeave: () => void;
  onPick: () => void;
  onPickCase: (id: string) => void;
}) {
  const groupRef = useRef<THREE.Group>(null);
  const meshRef = useRef<THREE.Mesh>(null);
  const angle0 = (index / Math.max(total, 1)) * Math.PI * 2;

  const revealedCases = domain.cases.filter((c) => !c.createdAt || revealedCaseIds.has(c.caseId));
  const growth = domain.cases.length > 0 ? Math.max(0.22, revealedCases.length / domain.cases.length) : 1;
  const visible = revealedCases.length > 0;

  useFrame(({ clock }) => {
    if (!groupRef.current) return;
    const t = clock.getElapsedTime() * 0.055 + angle0;
    groupRef.current.position.set(Math.cos(t) * orbitRadius, Math.sin(t * 1.3 + index) * 0.18, Math.sin(t) * orbitRadius);
    if (meshRef.current) {
      const s = planetScale * growth * (active ? 1.28 : 1);
      meshRef.current.scale.lerp(new THREE.Vector3(s, s, s), 0.14);
    }
  });

  if (!visible) return null;

  return (
    <group ref={groupRef}>
      <mesh
        ref={meshRef}
        onClick={(e: ThreeEvent<MouseEvent>) => { e.stopPropagation(); onPick(); }}
        onPointerOver={(e: ThreeEvent<PointerEvent>) => { e.stopPropagation(); onHover(); document.body.style.cursor = "pointer"; }}
        onPointerOut={(e: ThreeEvent<PointerEvent>) => { e.stopPropagation(); onLeave(); document.body.style.cursor = "auto"; }}
      >
        <icosahedronGeometry args={[1, 2]} />
        <meshStandardMaterial color="#07080b" emissive={domain.color} emissiveIntensity={active ? 1.3 : 0.6} roughness={0.3} metalness={0.5} />
      </mesh>
      <pointLight color={domain.color} intensity={active ? 2.6 : 1.1} distance={planetScale * 8} />
      {revealedCases.map((c, i) => (
        <Moon key={c.caseId} caseItem={c} index={i} total={revealedCases.length} planetRadius={planetScale} onPick={onPickCase} />
      ))}
      <Html center distanceFactor={13} occlude={false} style={{ pointerEvents: "none" }}>
        <span className="whitespace-nowrap rounded px-1.5 py-0.5 font-mono text-[10px] font-medium" style={{ transform: `translateY(${planetScale * 42 + 16}px)`, color: active ? "#fff" : "#dbeafe", background: active ? `${domain.color}33` : "transparent" }}>
          {domain.label} &middot; {revealedCases.length}/{domain.cases.length}
        </span>
      </Html>
    </group>
  );
}

function Scene({ domains, revealedCaseIds, selectedDomain, onSelectDomain, onSelectCase }: FootprintScene3DProps) {
  const controlsRef = useRef<OrbitControlsHandle | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const [userInteracted, setUserInteracted] = useState(false);
  const assigned = useMemo(() => orreryAssignment(domains), [domains]);

  return (
    <>
      <VoidEnvironment near={11} far={34} />
      <ambientLight intensity={0.3} />
      <SunCore />
      <SceneOrbitControls
        controlsRef={controlsRef}
        autoRotate={!userInteracted}
        autoRotateSpeed={0.22}
        minDistance={3}
        maxDistance={32}
        onStart={() => setUserInteracted(true)}
      />
      {assigned.map((d, i) => (
        <DomainPlanet
          key={d.domain}
          domain={d}
          index={i}
          total={assigned.length}
          orbitRadius={d.orbitRadius}
          planetScale={d.planetScale}
          revealedCaseIds={revealedCaseIds}
          active={hovered === d.domain || selectedDomain === d.domain}
          onHover={() => setHovered(d.domain)}
          onLeave={() => setHovered(null)}
          onPick={() => onSelectDomain(d.domain)}
          onPickCase={onSelectCase}
        />
      ))}
    </>
  );
}

export default function FootprintScene3D(props: FootprintScene3DProps) {
  return (
    <div className="relative h-full min-h-[500px] w-full overflow-hidden">
      <SceneShell cameraPosition={[0, 3.2, 12]}>
        <Scene {...props} />
      </SceneShell>
    </div>
  );
}
