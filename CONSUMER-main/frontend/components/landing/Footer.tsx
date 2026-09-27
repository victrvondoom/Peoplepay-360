import Link from "next/link";
import { DOMAINS } from "@/lib/aperture/tokens";

export default function Footer() {
  return (
    <footer
      style={{
        position: "relative",
        zIndex: 1,
        borderTop: "1px solid rgba(237,234,226,0.08)",
        padding: "3rem 1.5rem 2rem",
        fontFamily: "var(--font-mono)",
        fontSize: "0.75rem",
        color: "var(--bone)",
        opacity: 0.7,
      }}
    >
      <div style={{ maxWidth: "1100px", margin: "0 auto", display: "flex", flexWrap: "wrap", gap: "2.5rem", justifyContent: "space-between" }}>
        <div>
          <div style={{ marginBottom: "0.6rem", letterSpacing: "0.08em" }}>PROXY</div>
          <div style={{ opacity: 0.6, maxWidth: "260px", lineHeight: 1.6 }}>
            Every agent call passes through one gate, across {DOMAINS.length} regulated domains.
          </div>
        </div>
        <div style={{ display: "flex", gap: "3rem", flexWrap: "wrap" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <span style={{ opacity: 0.5, marginBottom: "0.25rem" }}>PRODUCT</span>
            <a href="#how-it-works" className="aperture-nav-link">How it works</a>
            <a href="#live-demo" className="aperture-nav-link">Live demo</a>
            <a href="#metrics" className="aperture-nav-link">Metrics</a>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <span style={{ opacity: 0.5, marginBottom: "0.25rem" }}>ACCOUNT</span>
            <Link href="/login" className="aperture-nav-link">Log in</Link>
            <Link href="/signup" className="aperture-nav-link">Sign up</Link>
          </div>
        </div>
      </div>
      <div style={{ maxWidth: "1100px", margin: "2rem auto 0", opacity: 0.4 }}>
        &copy; {new Date().getFullYear()} PROXY.
      </div>
    </footer>
  );
}
