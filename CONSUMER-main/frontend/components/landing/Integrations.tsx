"use client";

import { motion } from "framer-motion";
import { DOMAINS } from "@/lib/aperture/tokens";
import { useSystemHealth } from "./useSystemHealth";

export default function Integrations() {
  const { health } = useSystemHealth();

  return (
    <section style={{ position: "relative", zIndex: 1, padding: "6rem 1.5rem" }}>
      <div style={{ maxWidth: "800px", margin: "0 auto", textAlign: "center" }}>
        <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.78rem", letterSpacing: "0.14em", color: "var(--violet)", marginBottom: "0.75rem" }}>
          WORKS WITH WHAT YOU ALREADY RUN
        </p>
        <h2 style={{ fontFamily: "var(--font-display)", fontSize: "clamp(1.6rem, 3vw, 2.2rem)", fontWeight: 400, marginBottom: "2rem" }}>
          One gate, eight regulated domains.
        </h2>

        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem", justifyContent: "center", marginBottom: "2rem" }}>
          {DOMAINS.map((d, i) => (
            <motion.span
              key={d.key}
              initial={{ opacity: 0, scale: 0.9 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true, margin: "-10%" }}
              transition={{ duration: 0.35, delay: i * 0.04 }}
              className="aperture-glass"
              style={{ borderRadius: "999px", padding: "0.5rem 1rem", fontFamily: "var(--font-mono)", fontSize: "0.78rem" }}
            >
              {d.label}
            </motion.span>
          ))}
        </div>

        {health && (
          <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.78rem", opacity: 0.55 }}>
            reasoning model in this instance: {health.llm.provider}
            {health.llm.reasoning_model ? ` / ${health.llm.reasoning_model}` : ""}
          </p>
        )}
      </div>
    </section>
  );
}
