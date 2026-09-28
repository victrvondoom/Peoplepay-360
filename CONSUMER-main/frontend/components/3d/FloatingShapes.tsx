"use client";

import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

function Shape({ position, color, shape }: { position: [number, number, number]; color: string; shape: "torus" | "octahedron" | "icosahedron" | "torusKnot" }) {
  const ref = useRef<THREE.Mesh>(null);
  const basePos = useRef(new THREE.Vector3(...position));

  useFrame((state) => {
    if (!ref.current) return;
    const t = state.clock.elapsedTime;
    const offset = basePos.current.y;
    ref.current.position.y = basePos.current.y + Math.sin(t * 0.4 + offset) * 0.6;
    ref.current.position.x = basePos.current.x + Math.cos(t * 0.3 + offset * 0.5) * 0.4;
    ref.current.rotation.x += 0.005;
    ref.current.rotation.y += 0.01;
    ref.current.rotation.z += 0.003;
  });

  const geometries = {
    torus: <torusGeometry args={[0.4, 0.15, 16, 32]} />,
    octahedron: <octahedronGeometry args={[0.45]} />,
    icosahedron: <icosahedronGeometry args={[0.4]} />,
    torusKnot: <torusKnotGeometry args={[0.35, 0.12, 64, 8]} />,
  };

  return (
    <mesh ref={ref} position={position}>
      {geometries[shape]}
      <meshStandardMaterial color={color} wireframe roughness={0.2} metalness={0.8} transparent opacity={0.35} />
    </mesh>
  );
}

const shapes: Array<{ position: [number, number, number]; color: string; shape: "torus" | "octahedron" | "icosahedron" | "torusKnot" }> = [
  { position: [-3.5, 1.5, -4], color: "#00e5ff", shape: "torus" },
  { position: [4, -1, -5], color: "#9b5cff", shape: "octahedron" },
  { position: [-2, -2.5, -3], color: "#37f29a", shape: "icosahedron" },
  { position: [3, 2, -6], color: "#ffc857", shape: "torusKnot" },
  { position: [0, 0.5, -8], color: "#ff4d6d", shape: "torus" },
  { position: [-4.5, -0.5, -7], color: "#00e5ff", shape: "icosahedron" },
];

export function FloatingShapes() {
  return (
    <>
      {shapes.map((s, i) => (
        <Shape key={i} position={s.position} color={s.color} shape={s.shape} />
      ))}
    </>
  );
}
