"use client";

import { Suspense } from "react";
import { Canvas } from "@react-three/fiber";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { ParticleField } from "./ParticleField";
import { FloatingShapes } from "./FloatingShapes";

export function SceneBackground() {
  return (
    <div className="fixed inset-0 -z-10 pointer-events-none">
      {/* Purely decorative -- isolated so a WebGL/three.js crash here can
          never take down the page it's rendered on (each page mounts its
          own instance, so an uncaught error previously broke navigation
          entirely rather than just losing the background effect). */}
      <ErrorBoundary>
        <Canvas
          camera={{ position: [0, 0, 12], fov: 50, near: 0.1, far: 100 }}
          gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
          dpr={[1, 1.5]}
        >
          <ambientLight intensity={0.2} />
          <pointLight position={[10, 10, 10]} intensity={0.5} />
          <Suspense fallback={null}>
            <ParticleField />
            <FloatingShapes />
          </Suspense>
        </Canvas>
      </ErrorBoundary>
    </div>
  );
}
