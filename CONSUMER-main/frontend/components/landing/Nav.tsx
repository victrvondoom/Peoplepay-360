"use client";

import Link from "next/link";

export default function Nav() {
  return (
    <header
      className="aperture-glass"
      style={{
        position: "sticky",
        top: 0,
        zIndex: 20,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0.9rem 1.5rem",
      }}
    >
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.85rem", letterSpacing: "0.08em", color: "var(--bone)" }}>
        PROXY
      </span>
      <nav style={{ display: "flex", alignItems: "center", gap: "1.75rem" }}>
        <a href="#how-it-works" className="aperture-nav-link">How it works</a>
        <a href="#live-demo" className="aperture-nav-link">Live demo</a>
        <a href="#metrics" className="aperture-nav-link">Metrics</a>
        <Link
          href="/login"
          style={{ fontFamily: "var(--font-mono)", fontSize: "0.78rem", color: "var(--bone)", opacity: 0.75 }}
        >
          Log in
        </Link>
        <Link
          href="/signup"
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "0.78rem",
            padding: "0.5rem 0.95rem",
            border: `1px solid var(--cyan)`,
            borderRadius: "6px",
            color: "var(--cyan)",
            boxShadow: "0 0 18px rgba(95,240,215,0.18)",
          }}
        >
          Get your endpoint
        </Link>
      </nav>
    </header>
  );
}
