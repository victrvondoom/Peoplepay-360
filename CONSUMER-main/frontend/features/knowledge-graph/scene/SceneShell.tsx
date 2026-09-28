"use client";

import { useEffect, useRef } from "react";
import { Canvas, useThree } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { EffectComposer, Bloom } from "@react-three/postprocessing";
import * as THREE from "three";
import gsap from "gsap";

/** Camera fly-to: eases the camera and OrbitControls target toward
 * `focusPos` with a GSAP tween whenever it changes (spec 4.5: "never an
 * instant cut"). Shared by every mode so node-select / replay-step /
 * mode-switch camera moves all feel the same. */
export function CameraDirector({
  focusPos,
  controlsRef,
  offset = [2.3, 1.5, 4.8],
  duration = 1.1,
}: {
  focusPos: THREE.Vector3;
  controlsRef: React.RefObject<{ target: THREE.Vector3; update: () => void } | null>;
  offset?: [number, number, number];
  duration?: number;
}) {
  const { camera } = useThree();
  const prevKey = useRef<string>("");

  useEffect(() => {
    const key = `${focusPos.x.toFixed(2)},${focusPos.y.toFixed(2)},${focusPos.z.toFixed(2)}`;
    if (key === prevKey.current) return;
    prevKey.current = key;

    const targetCamPos = focusPos.clone().add(new THREE.Vector3(...offset));
    gsap.to(camera.position, { x: targetCamPos.x, y: targetCamPos.y, z: targetCamPos.z, duration, ease: "power3.inOut" });
    const controls = controlsRef.current;
    if (controls) {
      gsap.to(controls.target, {
        x: focusPos.x,
        y: focusPos.y,
        z: focusPos.z,
        duration,
        ease: "power3.inOut",
        onUpdate: () => controls.update(),
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusPos.x, focusPos.y, focusPos.z]);

  return null;
}

export interface OrbitControlsHandle {
  target: THREE.Vector3;
  update: () => void;
}

export function SceneOrbitControls({
  controlsRef, autoRotate, enabled = true, minDistance = 2.2, maxDistance = 30, autoRotateSpeed = 0.32, onStart,
}: {
  controlsRef: React.RefObject<OrbitControlsHandle | null>;
  autoRotate: boolean;
  enabled?: boolean;
  minDistance?: number;
  maxDistance?: number;
  autoRotateSpeed?: number;
  onStart?: () => void;
}) {
  return (
    <OrbitControls
      ref={controlsRef as never}
      enableDamping
      dampingFactor={0.08}
      autoRotate={autoRotate}
      autoRotateSpeed={autoRotateSpeed}
      minDistance={minDistance}
      maxDistance={maxDistance}
      enabled={enabled}
      onStart={onStart}
    />
  );
}

/** Base Canvas + bloom, identical across all three modes (spec: "share only
 * the design system"). Each mode supplies its own children (nodes, edges,
 * camera rig, controls) -- this only owns the WebGL container, lighting
 * environment, and post-processing. */
export function SceneShell({
  children,
  cameraPosition = [3, 2.4, 9],
  fov = 46,
}: {
  children: React.ReactNode;
  cameraPosition?: [number, number, number];
  fov?: number;
}) {
  return (
    <Canvas
      dpr={[1, 1.5]}
      gl={{ antialias: true, alpha: false, powerPreference: "high-performance" }}
      camera={{ position: cameraPosition, fov }}
    >
      {children}
      <EffectComposer multisampling={0}>
        <Bloom luminanceThreshold={0.18} luminanceSmoothing={0.82} intensity={0.85} mipmapBlur radius={0.55} />
      </EffectComposer>
    </Canvas>
  );
}
