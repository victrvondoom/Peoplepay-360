"use client";

/** Loading state (spec 9): a few soft glowing orbs pulsing in a loose
 * formation instead of a generic spinner on a black screen -- the page
 * should feel alive even before data arrives. Pure CSS, no WebGL, so it's
 * cheap to show immediately. */
export function LoadingOrbs({ label = "Loading the graph..." }: { label?: string }) {
  const orbs = [
    { color: "#00e5ff", x: 46, y: 40, delay: 0 },
    { color: "#9b5cff", x: 58, y: 55, delay: 0.3 },
    { color: "#ffc857", x: 40, y: 60, delay: 0.6 },
    { color: "#37f29a", x: 55, y: 42, delay: 0.9 },
  ];
  return (
    <div className="relative flex h-full min-h-[500px] w-full flex-col items-center justify-center gap-4 overflow-hidden">
      <div className="relative h-40 w-40">
        {orbs.map((orb, i) => (
          <span
            key={i}
            className="loading-orb absolute rounded-full"
            style={{
              left: `${orb.x}%`,
              top: `${orb.y}%`,
              width: 14,
              height: 14,
              background: orb.color,
              boxShadow: `0 0 22px ${orb.color}aa`,
              animationDelay: `${orb.delay}s`,
            }}
          />
        ))}
      </div>
      <p className="font-mono text-xs uppercase tracking-[.2em] text-proxy-tertiary">{label}</p>
      <style jsx>{`
        .loading-orb {
          animation: kgOrbPulse 2.4s ease-in-out infinite;
        }
        @keyframes kgOrbPulse {
          0%, 100% { transform: scale(0.8); opacity: 0.4; }
          50% { transform: scale(1.3); opacity: 1; }
        }
        @media (prefers-reduced-motion: reduce) {
          .loading-orb { animation: none; opacity: 0.85; }
        }
      `}</style>
    </div>
  );
}
