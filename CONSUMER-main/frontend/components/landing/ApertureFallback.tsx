import { apertureColors } from "@/lib/aperture/tokens";

// Low-tier / reduced-motion / pre-hydration substitute for the R3F scene --
// same chaos -> order color language and composition, rendered as a static
// SVG so it costs nothing to paint and never stutters.
export default function ApertureFallback() {
  return (
    <div
      aria-hidden
      style={{ position: "fixed", inset: 0, zIndex: 0, pointerEvents: "none" }}
    >
      <svg width="100%" height="100%" preserveAspectRatio="xMidYMid slice" viewBox="0 0 1200 800">
        <defs>
          <radialGradient id="ap-void" cx="50%" cy="45%" r="70%">
            <stop offset="0%" stopColor={apertureColors.ink} />
            <stop offset="100%" stopColor={apertureColors.void} />
          </radialGradient>
          <linearGradient id="ap-facet" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor={apertureColors.ember} stopOpacity="0.25" />
            <stop offset="50%" stopColor={apertureColors.violet} stopOpacity="0.35" />
            <stop offset="100%" stopColor={apertureColors.cyan} stopOpacity="0.3" />
          </linearGradient>
        </defs>
        <rect width="1200" height="800" fill="url(#ap-void)" />
        <polygon
          points="600,260 720,330 700,470 560,500 480,410 520,300"
          fill="url(#ap-facet)"
          stroke={apertureColors.violet}
          strokeOpacity="0.5"
          strokeWidth="1"
        />
        {Array.from({ length: 14 }).map((_, i) => (
          <circle
            key={`chaos-${i}`}
            cx={140 + (i % 7) * 34 + Math.sin(i) * 12}
            cy={340 + Math.floor(i / 7) * 60 + Math.cos(i) * 10}
            r={2.2}
            fill={apertureColors.ember}
            opacity={0.6}
          />
        ))}
        {Array.from({ length: 16 }).map((_, i) => (
          <circle
            key={`order-${i}`}
            cx={820 + (i % 8) * 30}
            cy={380 + Math.floor(i / 8) * 26}
            r={2}
            fill={apertureColors.cyan}
            opacity={0.65}
          />
        ))}
      </svg>
    </div>
  );
}
