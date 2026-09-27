"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { useSystemHealth } from "./useSystemHealth";
import CountUp from "./CountUp";

export default function Hero() {
  const { health, loading } = useSystemHealth();

  return (
    <section
      style={{
        position: "relative",
        zIndex: 1,
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        padding: "0 1.5rem",
      }}
    >
      <div style={{ maxWidth: "720px", margin: "0 auto", textAlign: "center" }}>
        <motion.p
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 0.7, y: 0 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          style={{ fontFamily: "var(--font-mono)", fontSize: "0.78rem", letterSpacing: "0.14em", color: "var(--cyan)", marginBottom: "1.25rem" }}
        >
          AGENTIC AI PROXY
        </motion.p>
        <motion.h1
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.08, ease: [0.16, 1, 0.3, 1] }}
          style={{
            fontFamily: "var(--font-display)",
            fontSize: "clamp(2.6rem, 6vw, 4.4rem)",
            lineHeight: 1.08,
            fontWeight: 400,
            color: "var(--bone)",
            marginBottom: "1.25rem",
          }}
        >
          Every agent call passes through one gate.
        </motion.h1>
        <motion.p
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 0.85, y: 0 }}
          transition={{ duration: 0.5, delay: 0.16, ease: [0.16, 1, 0.3, 1] }}
          style={{ fontSize: "1.05rem", lineHeight: 1.65, color: "var(--bone)", marginBottom: "2.25rem" }}
        >
          Route, authenticate, and enforce evidence before it reaches a specialist, a model, or your case record.
          Built for consumer-protection cases across 8 regulated domains.
        </motion.p>
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.24, ease: [0.16, 1, 0.3, 1] }}
          style={{ display: "flex", gap: "1rem", justifyContent: "center", flexWrap: "wrap" }}
        >
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
          <a
            href="#how-it-works"
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.85rem",
              padding: "0.85rem 1.5rem",
              borderRadius: "6px",
              border: "1px solid rgba(237,234,226,0.2)",
              color: "var(--bone)",
            }}
          >
            See how it works
          </a>
        </motion.div>
      </div>

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.6, delay: 0.5 }}
        style={{
          position: "absolute",
          bottom: "2rem",
          left: 0,
          right: 0,
          textAlign: "center",
          fontFamily: "var(--font-mono)",
          fontSize: "0.78rem",
          color: "var(--bone)",
          opacity: 0.55,
        }}
      >
        {loading ? (
          "connecting to proxy..."
        ) : health ? (
          <>
            <CountUp value={health.vector_store.total_points ?? null} /> knowledge chunks indexed ·{" "}
            {health.vector_store.collections ?? 0} domain collections · {health.graph_store.events ?? 0} case events tracked
          </>
        ) : (
          "backend unreachable -- start the API to see live status"
        )}
      </motion.div>
    </section>
  );
}
