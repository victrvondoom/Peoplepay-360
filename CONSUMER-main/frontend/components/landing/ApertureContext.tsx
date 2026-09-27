"use client";

import { createContext, useContext, useMemo, useRef } from "react";
import { useMotionValue, type MotionValue } from "framer-motion";

interface ApertureContextValue {
  scrollYProgress: MotionValue<number>;
  pulse: MotionValue<number>;
  triggerPulse: () => void;
}

const ApertureCtx = createContext<ApertureContextValue | null>(null);

// Shared state between the DOM sections and the fixed R3F canvas: scroll
// progress drives the camera choreography (see Aperture3D CameraRig), and
// `pulse` is how a hovered HowItWorks facet callout tells the crystal to
// visibly ripple -- the one place the 3D object and DOM content connect.
// `scrollYProgress` is owned by the page (framer-motion's useScroll against
// the page container) and passed in, so there's a single source of truth.
export function ApertureProvider({
  children,
  scrollYProgress,
}: {
  children: React.ReactNode;
  scrollYProgress: MotionValue<number>;
}) {
  const pulse = useMotionValue(0);
  const pulseTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  const value = useMemo<ApertureContextValue>(() => ({
    scrollYProgress,
    pulse,
    triggerPulse: () => {
      pulse.set(1);
      if (pulseTimeout.current) clearTimeout(pulseTimeout.current);
      pulseTimeout.current = setTimeout(() => pulse.set(0), 900);
    },
  }), [scrollYProgress, pulse]);

  return <ApertureCtx.Provider value={value}>{children}</ApertureCtx.Provider>;
}

export function useAperture(): ApertureContextValue {
  const ctx = useContext(ApertureCtx);
  if (!ctx) throw new Error("useAperture must be used within an ApertureProvider");
  return ctx;
}
