"use client";

import { motion } from "framer-motion";

const COMPLIANCE_MARKS = [
  { label: "SOC 2 Type II", status: "planned" },
  { label: "GDPR", status: "in progress" },
  { label: "ISO 27001", status: "planned" },
];

export default function TrustSection() {
  return (
    <section style={{ position: "relative", zIndex: 1, padding: "6rem 1.5rem" }}>
      <div style={{ maxWidth: "720px", margin: "0 auto", textAlign: "center" }}>
        <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.78rem", letterSpacing: "0.14em", color: "var(--cyan)", marginBottom: "0.75rem" }}>
          GOVERNED BY DEFAULT
        </p>
        <h2 style={{ fontFamily: "var(--font-display)", fontSize: "clamp(1.6rem, 3vw, 2.2rem)", fontWeight: 400, marginBottom: "2rem" }}>
          Every request, accounted for.
        </h2>

        <div style={{ display: "flex", gap: "1rem", justifyContent: "center", flexWrap: "wrap", marginBottom: "2.5rem" }}>
          {COMPLIANCE_MARKS.map((mark) => (
            <div
              key={mark.label}
              className="aperture-glass"
              style={{ borderRadius: "6px", padding: "0.6rem 1rem", textAlign: "left" }}
            >
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "0.78rem", color: "var(--bone)" }}>{mark.label}</div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "0.68rem", color: "var(--violet)", opacity: 0.8 }}>{mark.status}</div>
            </div>
          ))}
        </div>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-10%" }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          className="aperture-glass"
          style={{ borderRadius: "8px", padding: "1.25rem", textAlign: "left", fontFamily: "var(--font-mono)", fontSize: "0.8rem" }}
        >
          <div style={{ opacity: 0.5, marginBottom: "0.5rem" }}># actual case-timeline event schema</div>
          <pre style={{ margin: 0, whiteSpace: "pre-wrap", opacity: 0.8, lineHeight: 1.6 }}>
{JSON.stringify(
  {
    actor: "system",
    event_type: "document_uploaded",
    title: "Document uploaded: bank_statement.pdf",
    body: "Indexed: true",
  },
  null,
  2
)}
          </pre>
        </motion.div>
      </div>
    </section>
  );
}
