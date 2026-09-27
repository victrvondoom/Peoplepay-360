"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Loader2, RotateCw } from "lucide-react";
import { getSystemHealth, API_BASE, type SystemHealth } from "@/lib/api-client";

const HEALTH_URL = `${API_BASE.replace(/\/api\/v1\/?$/, "")}/health`;

export default function LiveDemo() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runs, setRuns] = useState(0);

  const run = () => {
    setLoading(true);
    setError(null);
    getSystemHealth()
      .then(({ health, latencyMs }) => {
        setHealth(health);
        setLatencyMs(latencyMs);
        setRuns((r) => r + 1);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <section id="live-demo" style={{ position: "relative", zIndex: 1, padding: "6rem 1.5rem" }}>
      <div style={{ maxWidth: "760px", margin: "0 auto" }}>
        <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.78rem", letterSpacing: "0.14em", color: "var(--cyan)", marginBottom: "0.75rem", textAlign: "center" }}>
          TRY IT
        </p>
        <h2 style={{ fontFamily: "var(--font-display)", fontSize: "clamp(1.6rem, 3vw, 2.2rem)", fontWeight: 400, textAlign: "center", marginBottom: "2rem" }}>
          A real call to the running proxy, right now.
        </h2>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-10%" }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          className="aperture-glass"
          style={{ borderRadius: "8px", padding: "1.5rem", fontFamily: "var(--font-mono)", fontSize: "0.85rem" }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
            <span style={{ opacity: 0.5 }}>~ curl {HEALTH_URL}</span>
            <button
              onClick={run}
              disabled={loading}
              style={{ display: "flex", alignItems: "center", gap: "0.4rem", background: "none", border: "1px solid rgba(237,234,226,0.15)", borderRadius: "4px", padding: "0.3rem 0.6rem", color: "var(--bone)", opacity: 0.8, fontFamily: "var(--font-mono)", fontSize: "0.72rem" }}
            >
              {loading ? <Loader2 size={12} className="aperture-spin" /> : <RotateCw size={12} />}
              run again
            </button>
          </div>

          {loading && (
            <div style={{ opacity: 0.6 }}>connecting...</div>
          )}

          {error && !loading && (
            <div style={{ color: "var(--ember)" }}>
              request failed: {error}
              <div style={{ opacity: 0.5, marginTop: "0.5rem", fontSize: "0.78rem" }}>
                the backend isn&apos;t reachable from here -- start it and hit &quot;run again&quot;.
              </div>
            </div>
          )}

          {health && !loading && !error && (
            <>
              <div style={{ color: "var(--cyan)", marginBottom: "0.6rem" }}>
                &#8618; {latencyMs}ms &middot; status: {health.status} &middot; provider: {health.llm.provider}
                {health.llm.reasoning_model ? ` (${health.llm.reasoning_model})` : ""} &middot; run #{runs}
              </div>
              <pre style={{ margin: 0, whiteSpace: "pre-wrap", opacity: 0.75, lineHeight: 1.6 }}>
{JSON.stringify(
  {
    vector_store: health.vector_store,
    graph_store: health.graph_store,
    llm: health.llm,
  },
  null,
  2
)}
              </pre>
            </>
          )}
        </motion.div>
      </div>
    </section>
  );
}
