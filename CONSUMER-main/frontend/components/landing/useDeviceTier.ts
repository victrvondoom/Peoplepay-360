"use client";

import { useEffect, useState } from "react";

export type DeviceTier = "high" | "low" | "checking";

// Decides whether the visitor gets the real WebGL Aperture scene or the
// static/CSS fallback -- a good fallback beats a stuttering 3D scene.
export function useDeviceTier(): DeviceTier {
  const [tier, setTier] = useState<DeviceTier>("checking");

  useEffect(() => {
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reducedMotion) {
      setTier("low");
      return;
    }

    let hasWebGL = false;
    try {
      const canvas = document.createElement("canvas");
      hasWebGL = !!(canvas.getContext("webgl2") || canvas.getContext("webgl"));
    } catch {
      hasWebGL = false;
    }

    const cores = navigator.hardwareConcurrency ?? 4;
    const isSmallViewport = window.innerWidth < 640;

    setTier(hasWebGL && cores >= 4 && !isSmallViewport ? "high" : "low");
  }, []);

  return tier;
}
