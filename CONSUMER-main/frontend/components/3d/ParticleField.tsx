"use client";

import { useRef, useMemo, useEffect } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";

export function ParticleField({ count = 800, speed = 0.15 }: { count?: number; speed?: number }) {
  const ref = useRef<THREE.Points>(null);
  const { pointer } = useThree();

  const positions = useMemo(() => {
    const pos = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const i3 = i * 3;
      const r = 6 + Math.random() * 14;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      pos[i3] = r * Math.sin(phi) * Math.cos(theta);
      pos[i3 + 1] = r * Math.sin(phi) * Math.sin(theta);
      pos[i3 + 2] = r * Math.cos(phi);
    }
    return pos;
  }, [count]);

  useEffect(() => {
    if (ref.current) {
      const geom = ref.current.geometry;
      geom.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    }
  }, [positions]);

  useFrame((state) => {
    if (!ref.current) return;
    // The `position` attribute is set in the useEffect above, which can
    // commit after useFrame's render loop has already started ticking (most
    // often the very first frame) -- geometry.attributes.position is briefly
    // undefined in that window, not just when ref.current is null.
    const attribute = ref.current.geometry.attributes.position;
    if (!attribute) return;
    const pos = attribute.array as Float32Array;
    const time = state.clock.elapsedTime;

    for (let i = 0; i < count; i++) {
      const i3 = i * 3;
      pos[i3] += Math.sin(time * 0.2 + i * 0.01) * 0.001;
      pos[i3 + 1] += Math.cos(time * 0.15 + i * 0.01) * 0.001;
      pos[i3 + 2] += Math.sin(time * 0.1 + i * 0.02) * 0.001;
    }

    ref.current.rotation.x += (pointer.y * 0.3 - ref.current.rotation.x) * 0.02;
    ref.current.rotation.y += (pointer.x * 0.3 - ref.current.rotation.y) * 0.02;
    attribute.needsUpdate = true;
  });

  return (
    <points ref={ref}>
      <bufferGeometry />
      <pointsMaterial
        size={0.04}
        color="#00e5ff"
        transparent
        opacity={0.6}
        blending={THREE.AdditiveBlending}
        depthWrite={false}
        sizeAttenuation
      />
    </points>
  );
}
