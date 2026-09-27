"use client";

import Link from "next/link";
import { motion } from "framer-motion";

export default function FinalCTA() {
  return (
    <section style={{ position: "relative", zIndex: 1, padding: "8rem 1.5rem", textAlign: "center" }}>
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-15%" }}
        transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
        style={{ maxWidth: "640px", margin: "0 auto" }}
      >
        <h2
          style={{
            fontFamily: "var(--font-display)",
            fontSize: "clamp(2rem, 4.5vw, 3.2rem)",
            fontWeight: 400,
            lineHeight: 1.15,
            marginBottom: "2rem",
          }}
        >
          Put your agents behind one gate.
        </h2>
        <div style={{ display: "flex", gap: "1rem", justifyContent: "center", flexWrap: "wrap" }}>
          <Link
            href="/signup"
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.85rem",
              padding: "0.85rem 1.5rem",
              borderRadius: "6px",
              background: "var(--cyan)",
              color: "var(--void)",
              fontWeight: 600,
              boxShadow: "0 0 28px rgba(95,240,215,0.28)",
            }}
          >
            Get your endpoint
          </Link>
          <Link
            href="/signup"
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.85rem",
              padding: "0.85rem 1.5rem",
              borderRadius: "6px",
              border: "1px solid rgba(237,234,226,0.2)",
              color: "var(--bone)",
            }}
          >
            Talk to engineering
          </Link>
        </div>
      </motion.div>
    </section>
  );
}
