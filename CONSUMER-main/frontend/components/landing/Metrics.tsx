"use client";

import { motion } from "framer-motion";
import { useSystemHealth } from "./useSystemHealth";
import { DOMAINS } from "@/lib/aperture/tokens";
import CountUp from "./CountUp";

export default function Metrics() {
  const { health, latencyMs, loading } = useSystemHealth();

  const cards = [
    {
      label: "regulated domains",
      value: DOMAINS.length,
      display: <CountUp value={DOMAINS.length} />,
    },
    {
      label: "knowledge chunks indexed",
      value: health?.vector_store.total_points ?? null,
      display: <CountUp value={health?.vector_store.total_points ?? null} />,
    },
    {
      label: "case events tracked",
      value: health?.graph_store.events ?? null,
      display: <CountUp value={health?.graph_store.events ?? null} />,
    },
    {
      label: "this health check",
      value: latencyMs,
      display: latencyMs != null ? `${latencyMs}ms` : "--",
    },
  ];

  return (
    <section id="metrics" style={{ position: "relative", zIndex: 1, padding: "6rem 1.5rem" }}>
      <div style={{ maxWidth: "900px", margin: "0 auto" }}>
        <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.78rem", letterSpacing: "0.14em", color: "var(--cyan)", marginBottom: "0.75rem", textAlign: "center" }}>
          LIVE, NOT ROUNDED
        </p>
        <h2 style={{ fontFamily: "var(--font-display)", fontSize: "clamp(1.6rem, 3vw, 2.2rem)", fontWeight: 400, marginBottom: "0.75rem", textAlign: "center" }}>
          Numbers from this running instance.
        </h2>
        <p style={{ textAlign: "center", opacity: 0.6, marginBottom: "2.5rem", fontSize: "0.92rem" }}>
          {loading ? "fetching..." : health ? "fetched from /health just now -- refresh to see them change." : "backend unreachable right now."}
        </p>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "1.5rem" }}>
          {cards.map((card, i) => (
            <motion.div
              key={card.label}
              initial={{ opacity: 0, y: 10 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-10%" }}
              transition={{ duration: 0.4, delay: i * 0.05, ease: [0.16, 1, 0.3, 1] }}
              className="aperture-glass"
              style={{ borderRadius: "8px", padding: "1.5rem", textAlign: "center" }}
            >
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "1.8rem", color: "var(--cyan)", marginBottom: "0.4rem" }}>
                {card.display}
              </div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "0.72rem", opacity: 0.6, letterSpacing: "0.04em" }}>
                {card.label}
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
