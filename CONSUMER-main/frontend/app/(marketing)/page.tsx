"use client";

import { useRef } from "react";
import dynamic from "next/dynamic";
import { useScroll } from "framer-motion";
import { ApertureProvider, useAperture } from "@/components/landing/ApertureContext";
import { useDeviceTier } from "@/components/landing/useDeviceTier";
import ApertureFallback from "@/components/landing/ApertureFallback";
import Nav from "@/components/landing/Nav";
import Hero from "@/components/landing/Hero";
import ProblemSection from "@/components/landing/ProblemSection";
import HowItWorks from "@/components/landing/HowItWorks";
import LiveDemo from "@/components/landing/LiveDemo";
import TrustSection from "@/components/landing/TrustSection";
import Metrics from "@/components/landing/Metrics";
import Integrations from "@/components/landing/Integrations";
import FinalCTA from "@/components/landing/FinalCTA";
import Footer from "@/components/landing/Footer";

const Aperture3D = dynamic(() => import("@/components/landing/Aperture3D"), {
  ssr: false,
  loading: () => <ApertureFallback />,
});

function ApertureBackdrop() {
  const tier = useDeviceTier();
  const { scrollYProgress, pulse } = useAperture();

  if (tier === "low") return <ApertureFallback />;
  if (tier === "checking") return <ApertureFallback />;
  return <Aperture3D scrollYProgress={scrollYProgress} pulse={pulse} />;
}

export default function LandingPage() {
  const containerRef = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: containerRef, offset: ["start start", "end end"] });

  return (
    <ApertureProvider scrollYProgress={scrollYProgress}>
      <div ref={containerRef} style={{ position: "relative" }}>
        <ApertureBackdrop />
        <div className="aperture-spine" aria-hidden />
        <div style={{ position: "relative", zIndex: 1 }}>
          <Nav />
          <Hero />
          <ProblemSection />
          <HowItWorks />
          <LiveDemo />
          <TrustSection />
          <Metrics />
          <Integrations />
          <FinalCTA />
          <Footer />
        </div>
      </div>
    </ApertureProvider>
  );
}
