"use client";

import { motion } from "framer-motion";

export default function ProblemSection() {
  return (
    <section
      style={{
        position: "relative",
        zIndex: 1,
        minHeight: "70vh",
        display: "flex",
        alignItems: "center",
        padding: "6rem 1.5rem",
      }}
    >
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-15%" }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        style={{ maxWidth: "480px", marginLeft: "clamp(1.5rem, 8vw, 8rem)" }}
      >
        <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.78rem", letterSpacing: "0.14em", color: "var(--ember)", marginBottom: "1rem" }}>
          WITHOUT A PROXY
        </p>
        <h2 style={{ fontFamily: "var(--font-display)", fontSize: "clamp(1.8rem, 3.4vw, 2.6rem)", fontWeight: 400, lineHeight: 1.15, marginBottom: "1.25rem" }}>
          Your agents already talk to everything. You just can&apos;t see it.
        </h2>
        <p style={{ fontSize: "1rem", lineHeight: 1.75, opacity: 0.8 }}>
          Domain agents call models, pull documents, and escalate cases without a single
          shared checkpoint. Evidence gets attached to the wrong case, retries go
          unbounded, and there&apos;s no record of which document actually shaped which
          answer -- until a user asks why the report doesn&apos;t match what they uploaded.
        </p>
      </motion.div>
    </section>
  );
}
