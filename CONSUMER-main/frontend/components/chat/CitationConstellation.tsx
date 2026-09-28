"use client";

import { useState } from "react";
import { ExternalLink, ShieldCheck } from "lucide-react";
import type { Citation } from "@/lib/api-client";
import { domainTheme } from "./domain-theme";

const SIZE = 220;
const CENTER = SIZE / 2;

/**
 * Citations arranged radially around a center point: higher confidence sits
 * closer to center and renders larger, so source quality is legible from
 * layout alone, not just a number buried in a list row.
 */
export function CitationConstellation({ citations }: { citations: Citation[] }) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  if (citations.length === 0) return null;

  const ranked = [...citations].sort((a, b) => b.confidence - a.confidence).slice(0, 8);
  const active = activeIndex !== null ? ranked[activeIndex] : null;

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
      <svg width={SIZE} height={SIZE} className="shrink-0" role="img" aria-label="Citation confidence map">
        <circle cx={CENTER} cy={CENTER} r={4} fill="#00e5ff" opacity={0.8} />
        <circle cx={CENTER} cy={CENTER} r={SIZE / 2 - 4} fill="none" stroke="rgba(255,255,255,.06)" />
        <circle cx={CENTER} cy={CENTER} r={SIZE / 3} fill="none" stroke="rgba(255,255,255,.05)" />
        {ranked.map((citation, index) => {
          const angle = (index / ranked.length) * Math.PI * 2 - Math.PI / 2;
          // Higher confidence -> smaller radius (closer to center)
          const radius = 30 + (1 - citation.confidence) * (SIZE / 2 - 46);
          const x = CENTER + radius * Math.cos(angle);
          const y = CENTER + radius * Math.sin(angle);
          const theme = domainTheme(citation.domain);
          const nodeR = 4 + citation.confidence * 8;
          const isActive = activeIndex === index;
          return (
            <g key={`${citation.title}-${index}`}>
              <line x1={CENTER} y1={CENTER} x2={x} y2={y} stroke={theme.color} strokeOpacity={isActive ? 0.5 : 0.15} strokeWidth={1} />
              <circle
                cx={x}
                cy={y}
                r={nodeR}
                fill={theme.color}
                fillOpacity={isActive ? 1 : 0.75}
                stroke={isActive ? "#fff" : "none"}
                strokeWidth={1.5}
                style={{ cursor: "pointer", transition: "all .15s ease" }}
                onMouseEnter={() => setActiveIndex(index)}
                onMouseLeave={() => setActiveIndex(null)}
                onClick={() => citation.url && window.open(citation.url, "_blank", "noopener,noreferrer")}
              />
            </g>
          );
        })}
      </svg>

      <div className="min-w-0 flex-1">
        {active ? (
          <div className="rounded-xl border border-white/10 bg-black/30 p-3 text-xs">
            <div className="mb-1 flex items-center gap-1.5">
              <ShieldCheck className="size-3.5 shrink-0" style={{ color: domainTheme(active.domain).color }} />
              <span className="font-medium text-proxy-text line-clamp-1">{active.title}</span>
            </div>
            <p className="text-proxy-tertiary">
              {active.authority} &middot; {domainTheme(active.domain).label} &middot; {Math.round(active.confidence * 100)}% confidence
            </p>
            {active.url && (
              <a
                href={active.url}
                target="_blank"
                rel="noreferrer"
                className="mt-1.5 inline-flex items-center gap-1 text-cyan-200 hover:text-cyan-100"
              >
                View source <ExternalLink className="size-3" />
              </a>
            )}
          </div>
        ) : (
          <p className="text-xs text-proxy-tertiary">
            {ranked.length} source{ranked.length === 1 ? "" : "s"} &middot; closer to center = higher confidence. Hover a node.
          </p>
        )}
      </div>
    </div>
  );
}
