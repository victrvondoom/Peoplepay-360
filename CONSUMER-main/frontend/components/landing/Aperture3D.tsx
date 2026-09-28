"use client";

import { useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Edges, MeshTransmissionMaterial } from "@react-three/drei";
import * as THREE from "three";
import type { MotionValue } from "framer-motion";
import { apertureColors } from "@/lib/aperture/tokens";

const PARTICLE_FRAGMENT = `
  uniform vec3 uColor;
  varying float vAlpha;
  void main() {
    vec2 uv = gl_PointCoord - 0.5;
    float d = length(uv);
    if (d > 0.5) discard;
    float alpha = smoothstep(0.5, 0.0, d) * vAlpha;
    gl_FragColor = vec4(uColor, alpha);
  }
`;

const CHAOS_VERTEX = `
  attribute float aSeed;
  uniform float uTime;
  varying float vAlpha;
  void main() {
    vec3 pos = position;
    float t = uTime * (1.2 + aSeed);
    pos.x += mod(t * 1.1 + aSeed * 6.0, 4.2) - 2.1;
    pos.y += sin(t * 4.0 + aSeed * 20.0) * 0.3 * (0.3 + aSeed);
    pos.z += cos(t * 3.0 + aSeed * 12.0) * 0.25;
    vAlpha = 0.35 + 0.5 * abs(sin(t * 5.0 + aSeed * 30.0));
    vec4 mvPosition = modelViewMatrix * vec4(pos, 1.0);
    gl_PointSize = (2.2 + aSeed * 3.2) * (260.0 / -mvPosition.z);
    gl_Position = projectionMatrix * mvPosition;
  }
`;

const ORDER_VERTEX = `
  attribute float aSeed;
  uniform float uTime;
  varying float vAlpha;
  void main() {
    vec3 pos = position;
    float t = uTime * 0.55;
    pos.x += mod(t + aSeed * 5.0, 5.2);
    vAlpha = 0.55 + 0.35 * aSeed;
    vec4 mvPosition = modelViewMatrix * vec4(pos, 1.0);
    gl_PointSize = 2.6 * (260.0 / -mvPosition.z);
    gl_Position = projectionMatrix * mvPosition;
  }
`;

function useParticleGeometry(count: number, build: (i: number, arr: Float32Array) => void) {
  return useMemo(() => {
    const positions = new Float32Array(count * 3);
    const seeds = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      build(i, positions);
      seeds[i] = Math.random();
    }
    return { positions, seeds };
  }, [count, build]);
}

function ChaosField({ count = 220 }: { count?: number }) {
  const build = useMemo(() => (i: number, arr: Float32Array) => {
    arr[i * 3] = -Math.random() * 4.2 - 1.8;
    arr[i * 3 + 1] = (Math.random() - 0.5) * 2.6;
    arr[i * 3 + 2] = (Math.random() - 0.5) * 2.2;
  }, []);
  const { positions, seeds } = useParticleGeometry(count, build);
  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        uniforms: { uTime: { value: 0 }, uColor: { value: new THREE.Color(apertureColors.ember) } },
        vertexShader: CHAOS_VERTEX,
        fragmentShader: PARTICLE_FRAGMENT,
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    []
  );
  useFrame((_, delta) => {
    material.uniforms.uTime.value += delta;
  });
  return (
    <points material={material}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        <bufferAttribute attach="attributes-aSeed" args={[seeds, 1]} />
      </bufferGeometry>
    </points>
  );
}

function OrderField({ count = 160 }: { count?: number }) {
  const lanes = 4;
  const build = useMemo(() => (i: number, arr: Float32Array) => {
    const lane = i % lanes;
    arr[i * 3] = Math.random() * 5.2 + 1.8;
    arr[i * 3 + 1] = (lane - (lanes - 1) / 2) * 0.5;
    arr[i * 3 + 2] = (lane - (lanes - 1) / 2) * 0.35;
  }, []);
  const { positions, seeds } = useParticleGeometry(count, build);
  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        uniforms: { uTime: { value: 0 }, uColor: { value: new THREE.Color(apertureColors.cyan) } },
        vertexShader: ORDER_VERTEX,
        fragmentShader: PARTICLE_FRAGMENT,
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    []
  );
  useFrame((_, delta) => {
    material.uniforms.uTime.value += delta;
  });
  return (
    <points material={material}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        <bufferAttribute attach="attributes-aSeed" args={[seeds, 1]} />
      </bufferGeometry>
    </points>
  );
}

const DESTINATIONS = [
  { label: "claude", pos: [6.4, 0.5, 0] as [number, number, number] },
  { label: "gpt-4.1", pos: [6.6, -0.4, 0.3] as [number, number, number] },
  { label: "internal-tool", pos: [6.2, 0.1, -0.5] as [number, number, number] },
  { label: "audit-log", pos: [6.8, -0.1, 0.6] as [number, number, number] },
];

function DestinationNodes() {
  return (
    <>
      {DESTINATIONS.map((d) => (
        <group key={d.label} position={d.pos}>
          <mesh>
            <sphereGeometry args={[0.05, 12, 12]} />
            <meshBasicMaterial color={apertureColors.cyan} />
          </mesh>
          <pointLight color={apertureColors.cyan} intensity={2} distance={1.2} />
        </group>
      ))}
    </>
  );
}

function ApertureCrystal({ pulse }: { pulse: MotionValue<number> }) {
  const meshRef = useRef<THREE.Mesh>(null);
  useFrame((_, delta) => {
    if (!meshRef.current) return;
    meshRef.current.rotation.y += delta * 0.09;
    const p = pulse.get();
    const targetScale = 1 + p * 0.06;
    meshRef.current.scale.lerp(new THREE.Vector3(targetScale, targetScale, targetScale), 0.15);
  });
  return (
    <mesh ref={meshRef}>
      <icosahedronGeometry args={[1.7, 1]} />
      <MeshTransmissionMaterial
        thickness={0.6}
        roughness={0.08}
        transmission={0.92}
        ior={1.5}
        chromaticAberration={0.05}
        anisotropy={0.25}
        distortion={0.15}
        distortionScale={0.3}
        temporalDistortion={0.08}
        color={apertureColors.bone}
        flatShading
      />
      <Edges color={apertureColors.violet} threshold={1} />
    </mesh>
  );
}

interface CameraStage {
  at: number;
  pos: [number, number, number];
  look: [number, number, number];
}

const STAGES: CameraStage[] = [
  { at: 0, pos: [1.4, 0.5, 5.4], look: [0.3, 0, 0] },
  { at: 0.22, pos: [3.2, 0.3, 6.8], look: [-1.8, 0, 0] },
  { at: 0.48, pos: [0, 0.6, 6.2], look: [0, 0, 0] },
  { at: 0.74, pos: [-2.8, 0.2, 6.6], look: [1.8, 0, 0] },
  { at: 1, pos: [0.2, 0.7, 8.2], look: [0, 0, 0] },
];

function lerpVec3(a: [number, number, number], b: [number, number, number], t: number): [number, number, number] {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
}

function CameraRig({ scrollYProgress }: { scrollYProgress: MotionValue<number> }) {
  const target = useRef(new THREE.Vector3());
  useFrame((state) => {
    const p = Math.min(Math.max(scrollYProgress.get(), 0), 1);
    let seg = STAGES[0];
    let next = STAGES[STAGES.length - 1];
    for (let i = 0; i < STAGES.length - 1; i++) {
      if (p >= STAGES[i].at && p <= STAGES[i + 1].at) {
        seg = STAGES[i];
        next = STAGES[i + 1];
        break;
      }
    }
    const span = next.at - seg.at || 1;
    const localT = Math.min(Math.max((p - seg.at) / span, 0), 1);
    const pos = lerpVec3(seg.pos, next.pos, localT);
    const look = lerpVec3(seg.look, next.look, localT);
    // extra slow orbit through the "how it works" middle stretch
    const orbit = p > 0.3 && p < 0.65 ? Math.sin((p - 0.3) / 0.35 * Math.PI) * 1.4 : 0;
    state.camera.position.lerp(new THREE.Vector3(pos[0] + orbit, pos[1], pos[2]), 0.08);
    target.current.lerp(new THREE.Vector3(...look), 0.08);
    state.camera.lookAt(target.current);
  });
  return null;
}

function Scene({ scrollYProgress, pulse }: { scrollYProgress: MotionValue<number>; pulse: MotionValue<number> }) {
  return (
    <>
      <ambientLight intensity={0.6} />
      <pointLight position={[-4, 1, 3]} color={apertureColors.ember} intensity={12} />
      <pointLight position={[4, 1, 3]} color={apertureColors.cyan} intensity={10} />
      <pointLight position={[0, 3, 4]} color={apertureColors.violet} intensity={6} />
      <ApertureCrystal pulse={pulse} />
      <ChaosField />
      <OrderField />
      <DestinationNodes />
      <CameraRig scrollYProgress={scrollYProgress} />
    </>
  );
}

export default function Aperture3D({
  scrollYProgress,
  pulse,
}: {
  scrollYProgress: MotionValue<number>;
  pulse: MotionValue<number>;
}) {
  return (
    <Canvas
      dpr={[1, 1.5]}
      gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
      camera={{ position: [1.4, 0.5, 5.4], fov: 42 }}
      style={{ position: "fixed", inset: 0, zIndex: 0, pointerEvents: "none" }}
    >
      <color attach="background" args={[apertureColors.void]} />
      <fog attach="fog" args={[apertureColors.void, 8, 16]} />
      <Scene scrollYProgress={scrollYProgress} pulse={pulse} />
    </Canvas>
  );
}
