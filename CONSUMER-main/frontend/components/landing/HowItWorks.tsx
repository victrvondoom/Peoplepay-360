"use client";

import { motion } from "framer-motion";
import { LIFECYCLE_STEPS } from "@/lib/aperture/tokens";
import { useAperture } from "./ApertureContext";

export default function HowItWorks() {
  const { triggerPulse } = useAperture();

  return (
    <section
      id="how-it-works"
      style={{
        position: "relative",
        zIndex: 1,
        padding: "6rem 1.5rem",
      }}
    >
      <div style={{ maxWidth: "480px", marginLeft: "auto", marginRight: "clamp(1.5rem, 8vw, 8rem)" }}>
        <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.78rem", letterSpacing: "0.14em", color: "var(--violet)", marginBottom: "1.5rem" }}>
          01&ndash;06 &middot; REQUEST LIFECYCLE
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: "1.75rem" }}>
          {LIFECYCLE_STEPS.map((step, i) => (
            <motion.div
              key={step.n}
              initial={{ opacity: 0, y: 10 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-10%" }}
              transition={{ duration: 0.45, delay: i * 0.06, ease: [0.16, 1, 0.3, 1] }}
              onMouseEnter={triggerPulse}
              style={{ display: "flex", gap: "1rem", cursor: "default" }}
            >
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.85rem", color: "var(--cyan)", opacity: 0.7, paddingTop: "0.15rem" }}>
                {step.n}
              </span>
              <div>
                <h3 style={{ fontSize: "1.05rem", fontWeight: 600, marginBottom: "0.35rem", color: "var(--bone)" }}>
                  {step.title}
                </h3>
                <p style={{ fontSize: "0.92rem", lineHeight: 1.6, opacity: 0.72 }}>{step.body}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
