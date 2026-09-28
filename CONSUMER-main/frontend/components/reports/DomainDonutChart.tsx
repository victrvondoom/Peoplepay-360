"use client";

import { useState } from "react";
import { domainTheme } from "@/components/chat/domain-theme";

const SIZE = 200;
const CENTER = SIZE / 2;
const RADIUS = 78;
const STROKE = 26;

function polarToCartesian(radius: number, angleDeg: number): [number, number] {
  const rad = ((angleDeg - 90) * Math.PI) / 180;
  return [CENTER + radius * Math.cos(rad), CENTER + radius * Math.sin(rad)];
}

function arcPath(startAngle: number, endAngle: number): string {
  const [x1, y1] = polarToCartesian(RADIUS, endAngle);
  const [x2, y2] = polarToCartesian(RADIUS, startAngle);
  const largeArc = endAngle - startAngle > 180 ? 1 : 0;
  return `M${x1},${y1} A${RADIUS},${RADIUS} 0 ${largeArc} 0 ${x2},${y2}`;
}

export function DomainDonutChart({ data }: { data: Array<{ domain: string; count: number }> }) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const total = data.reduce((sum, d) => sum + d.count, 0);

  if (total === 0) {
    return (
      <div className="flex h-[200px] items-center justify-center text-xs text-proxy-tertiary">
        No domain activity yet
      </div>
    );
  }

  let cumulative = 0;
  const segments = data.map((entry, index) => {
    const fraction = entry.count / total;
    const startAngle = cumulative * 360;
    cumulative += fraction;
    const endAngle = cumulative * 360;
    return { ...entry, startAngle, endAngle, index };
  });

  const active = activeIndex !== null ? segments[activeIndex] : null;

  return (
    <div className="flex items-center gap-5">
      <svg width={SIZE} height={SIZE} className="shrink-0" role="img" aria-label="Domain distribution">
        {segments.map((segment) => {
          const theme = domainTheme(segment.domain);
          const isActive = activeIndex === segment.index;
          // Tiny gap between segments for visual separation
          const gap = segments.length > 1 ? 1.5 : 0;
          return (
            <path
              key={segment.domain}
              d={arcPath(segment.startAngle + gap, segment.endAngle - gap)}
              fill="none"
              stroke={theme.color}
              strokeWidth={isActive ? STROKE + 4 : STROKE}
              strokeLinecap="round"
              opacity={activeIndex === null || isActive ? 1 : 0.35}
              style={{ transition: "all .15s ease", cursor: "pointer" }}
              onMouseEnter={() => setActiveIndex(segment.index)}
              onMouseLeave={() => setActiveIndex(null)}
            />
          );
        })}
        <text x={CENTER} y={CENTER - 4} textAnchor="middle" fontSize="22" fontWeight={700} fill="#f7fbff">
          {active ? active.count : total}
        </text>
        <text x={CENTER} y={CENTER + 16} textAnchor="middle" fontSize="10" fill="#687386">
          {active ? domainTheme(active.domain).label : "Total"}
        </text>
      </svg>

      <div className="flex-1 space-y-1.5">
        {segments.map((segment) => {
          const theme = domainTheme(segment.domain);
          return (
            <div
              key={segment.domain}
              onMouseEnter={() => setActiveIndex(segment.index)}
              onMouseLeave={() => setActiveIndex(null)}
              className="flex items-center gap-2 rounded-lg px-1.5 py-1 text-xs transition-colors hover:bg-white/[0.03]"
            >
              <span className="size-2.5 shrink-0 rounded-full" style={{ backgroundColor: theme.color }} />
              <span className="flex-1 truncate text-proxy-muted">{theme.label}</span>
              <span className="font-medium text-proxy-text">{segment.count}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
