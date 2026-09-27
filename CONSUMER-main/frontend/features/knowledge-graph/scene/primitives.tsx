"use client";

import { useMemo, useRef } from "react";
import { useFrame, type ThreeEvent } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import * as THREE from "three";
import type { Vec3 } from "./layout";

/* -------------------------------------------------------------------------
 * Fresnel rim-light shader -- an orb reads as a glass object occupying 3D
 * space (spec 4.2) rather than a flat emissive sphere.
 * ---------------------------------------------------------------------- */

const RIM_VERTEX = `
  varying vec3 vNormal;
  varying vec3 vViewDir;
  void main() {
    vNormal = normalize(normalMatrix * normal);
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    vViewDir = normalize(-mvPosition.xyz);
    gl_Position = projectionMatrix * mvPosition;
  }
`;

const RIM_FRAGMENT = `
  uniform vec3 uColor;
  uniform float uIntensity;
  varying vec3 vNormal;
  varying vec3 vViewDir;
  void main() {
    float rim = pow(1.0 - max(dot(normalize(vNormal), normalize(vViewDir)), 0.0), 2.3);
    gl_FragColor = vec4(uColor, rim * uIntensity);
  }
`;

function useRimMaterial(color: string, intensity: number) {
  return useMemo(
    () =>
      new THREE.ShaderMaterial({
        uniforms: { uColor: { value: new THREE.Color(color) }, uIntensity: { value: intensity } },
        vertexShader: RIM_VERTEX,
        fragmentShader: RIM_FRAGMENT,
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [color]
  );
}

export interface GlowOrbProps {
  id: string;
  position: Vec3;
  radius: number;
  color: string;
  label?: string;
  icon?: React.ReactNode;
  emphasized?: boolean;
  dimmed?: boolean;
  showLabel?: boolean;
  onSelect?: (id: string) => void;
  onHover?: (id: string | null) => void;
}

/** A single graph entity: icosahedral glass core + additive rim shell.
 * Idle nodes breathe (scale 1.0 -> ~1.02 -> 1.0, ~4s cycle, spec 4.2);
 * emphasized nodes (selected / active replay step) pulse harder and grow a
 * halo ring. */
export function GlowOrb({ id, position, radius, color, label, icon, emphasized, dimmed, showLabel = true, onSelect, onHover }: GlowOrbProps) {
  const coreRef = useRef<THREE.Mesh>(null);
  const shellRef = useRef<THREE.Mesh>(null);
  const ringRef = useRef<THREE.Mesh>(null);
  const seed = useMemo(() => Math.random() * Math.PI * 2, []);
  const rimMaterial = useRimMaterial(color, emphasized ? 2.1 : 1.0);

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    const breathing = 1 + Math.sin(t * 0.5 + seed) * (emphasized ? 0.035 : 0.018);
    const focus = emphasized ? 1.18 : 1;
    const scale = breathing * focus;
    coreRef.current?.scale.lerp(new THREE.Vector3(scale, scale, scale), 0.12);
    shellRef.current?.scale.lerp(new THREE.Vector3(scale * 1.3, scale * 1.3, scale * 1.3), 0.12);
    if (ringRef.current) {
      ringRef.current.rotation.z += emphasized ? 0.02 : 0.004;
    }
  });

  return (
    <group position={position}>
      <mesh
        ref={coreRef}
        onClick={(e: ThreeEvent<MouseEvent>) => {
          e.stopPropagation();
          onSelect?.(id);
        }}
        onPointerOver={(e: ThreeEvent<PointerEvent>) => {
          e.stopPropagation();
          onHover?.(id);
          document.body.style.cursor = "pointer";
        }}
        onPointerOut={(e: ThreeEvent<PointerEvent>) => {
          e.stopPropagation();
          onHover?.(null);
          document.body.style.cursor = "auto";
        }}
      >
        <icosahedronGeometry args={[radius, 2]} />
        <meshStandardMaterial
          color="#050608"
          emissive={color}
          emissiveIntensity={dimmed ? 0.16 : emphasized ? 1.3 : 0.5}
          roughness={0.3}
          metalness={0.5}
          transparent
          opacity={dimmed ? 0.35 : 1}
        />
      </mesh>
      <mesh ref={shellRef}>
        <icosahedronGeometry args={[radius, 2]} />
        <primitive object={rimMaterial} attach="material" />
      </mesh>
      {emphasized && (
        <mesh ref={ringRef} rotation={[Math.PI / 2.4, 0, 0]}>
          <ringGeometry args={[radius * 1.55, radius * 1.68, 48]} />
          <meshBasicMaterial color={color} transparent opacity={0.5} side={THREE.DoubleSide} />
        </mesh>
      )}
      {!dimmed && <pointLight color={color} intensity={emphasized ? 3 : 1} distance={radius * 9} />}
      {showLabel && label && (
        <Html center distanceFactor={12} occlude={false} style={{ pointerEvents: "none", opacity: dimmed ? 0.35 : 1 }}>
          <div className="flex flex-col items-center gap-1" style={{ transform: `translateY(${radius * 34 + 14}px)` }}>
            {icon}
            <span
              className="whitespace-nowrap rounded px-1.5 py-0.5 font-mono text-[10px] font-medium"
              style={{ color: emphasized ? "#fff" : "#dbeafe", background: emphasized ? `${color}33` : "transparent" }}
            >
              {label}
            </span>
          </div>
        </Html>
      )}
    </group>
  );
}

/* -------------------------------------------------------------------------
 * Edges: glowing 3D tubes with directional particle flow (spec 4.4).
 * ---------------------------------------------------------------------- */

export interface GlowEdgeProps {
  from: Vec3;
  to: Vec3;
  color: string;
  active?: boolean;
  dimmed?: boolean;
  strength?: number;
  particles?: boolean;
  phase?: number;
}

export function GlowEdge({ from, to, color, active, dimmed, strength = 0.5, particles = true, phase = 0 }: GlowEdgeProps) {
  const particleRefs = useRef<(THREE.Mesh | null)[]>([]);

  const curve = useMemo(() => {
    const a = new THREE.Vector3(...from);
    const b = new THREE.Vector3(...to);
    const mid = a.clone().add(b).multiplyScalar(0.5);
    const dir = b.clone().sub(a);
    const len = dir.length() || 1;
    const perp = new THREE.Vector3(-dir.y, dir.x, dir.z * 0.4).normalize().multiplyScalar(Math.min(0.45, len * 0.12));
    mid.add(perp);
    return new THREE.QuadraticBezierCurve3(a, mid, b);
  }, [from, to]);

  const tubeGeometry = useMemo(() => new THREE.TubeGeometry(curve, 22, Math.max(0.012, strength * 0.03), 6, false), [curve, strength]);

  useFrame(({ clock }) => {
    if (!particles) return;
    const t0 = clock.getElapsedTime();
    particleRefs.current.forEach((mesh, i) => {
      if (!mesh) return;
      const speed = active ? 0.35 : 0.16;
      const t = (t0 * speed + phase + i / 3) % 1;
      mesh.position.copy(curve.getPointAt(t));
      const mat = mesh.material as THREE.MeshBasicMaterial;
      mat.opacity = (active ? 0.95 : 0.55) * Math.sin(t * Math.PI);
    });
  });

  return (
    <group>
      <mesh geometry={tubeGeometry}>
        <meshBasicMaterial color={color} transparent opacity={dimmed ? 0.06 : active ? 0.55 : 0.22} />
      </mesh>
      {particles &&
        !dimmed &&
        [0, 1, 2].map((i) => (
          <mesh key={i} ref={(m) => { particleRefs.current[i] = m; }}>
            <sphereGeometry args={[Math.max(0.02, strength * 0.045), 6, 6]} />
            <meshBasicMaterial color={color} transparent opacity={0} depthWrite={false} />
          </mesh>
        ))}
    </group>
  );
}

/* -------------------------------------------------------------------------
 * Void environment: near-black background + volumetric fog (spec 4.1),
 * shared across every mode's scene.
 * ---------------------------------------------------------------------- */

export function VoidEnvironment({ near = 10, far = 28 }: { near?: number; far?: number }) {
  return (
    <>
      <color attach="background" args={["#020203"]} />
      <fog attach="fog" args={["#020203", near, far]} />
      <ambientLight intensity={0.35} />
    </>
  );
}
