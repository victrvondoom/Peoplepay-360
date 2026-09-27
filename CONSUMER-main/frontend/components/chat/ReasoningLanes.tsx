"use client";

import { Sparkles } from "lucide-react";
import { domainTheme } from "./domain-theme";
import { ESTIMATED_STAGES, traceToStages } from "./pipeline";

interface LaneData {
  domain: string;
  /** Real trace once the response has arrived; undefined while still processing. */
  trace?: string[];
}

type Point = [number, number];

function cubicPoint(p0: Point, p1: Point, p2: Point, p3: Point, t: number): Point {
  const mt = 1 - t;
  const a = mt * mt * mt;
  const b = 3 * mt * mt * t;
  const c = 3 * mt * t * t;
  const d = t * t * t;
  return [a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]];
}

const TOP_PAD = 26;
const CORE_X = 68;
const CORE_R = 20;

/**
 * Every classified domain is a curved conduit that converges on a single
 * pulsing synthesis core -- a direct read of the real architecture (Domain
 * Router -> N domains reasoning in parallel via asyncio.gather -> merged
 * response), not decorative chrome. Small beads travel each conduit while
 * that domain is still reasoning; once its real agent_trace lands, the
 * conduit settles and every stage node reflects something that actually ran.
 */
export function ReasoningLanes({ lanes, processing, filledCount }: { lanes: LaneData[]; processing: boolean; filledCount: number }) {
  if (lanes.length === 0) return null;

  const n = lanes.length;
  const laneGap = n <= 3 ? 58 : n <= 5 ? 48 : 38;
  const width = 560;
  const height = TOP_PAD * 2 + Math.max(n - 1, 0) * laneGap + 40;
  const coreY = height / 2;
  const endX = width - 118;

  const laneGeom = lanes.map((lane, i) => {
    const endY = n === 1 ? coreY : TOP_PAD + 20 + i * laneGap;
    const p0: Point = [endX, endY];
    const p3: Point = [CORE_X + CORE_R + 10, coreY];
    const p1: Point = [p0[0] - (p0[0] - p3[0]) * 0.42, p0[1]];
    const p2: Point = [p3[0] + (p0[0] - p3[0]) * 0.22, p3[1] + (p0[1] - p3[1]) * 0.12];
    const d = `M${p0[0]},${p0[1]} C${p1[0]},${p1[1]} ${p2[0]},${p2[1]} ${p3[0]},${p3[1]}`;
    const theme = domainTheme(lane.domain);
    const stageLabels = lane.trace ? traceToStages(lane.trace).map((s) => s.label) : ESTIMATED_STAGES;
    const activeCount = lane.trace ? stageLabels.length : Math.min(filledCount, stageLabels.length);
    const done = Boolean(lane.trace);
    const currentLabel = !done && processing ? stageLabels[Math.min(activeCount, stageLabels.length - 1)] : done ? "Complete" : "Queued";
    return { lane, theme, p0, p1, p2, p3, d, stageLabels, activeCount, done, currentLabel };
  });

  const anyProcessing = processing && laneGeom.some((l) => !l.done);

  return (
    <div className="reasoning-orbit overflow-hidden rounded-xl border border-white/10 bg-black/30 p-3">
      <svg width="100%" viewBox={`0 0 ${width} ${height}`} className="block" role="img" aria-label="Multi-domain reasoning pipeline">
        <defs>
          <radialGradient id="coreGlow">
            <stop offset="0%" stopColor="rgba(0,229,255,.6)" />
            <stop offset="60%" stopColor="rgba(0,229,255,.18)" />
            <stop offset="100%" stopColor="rgba(0,229,255,0)" />
          </radialGradient>
          <pattern id="orbitDots" width="14" height="14" patternUnits="userSpaceOnUse">
            <circle cx="1" cy="1" r="1" fill="rgba(255,255,255,.05)" />
          </pattern>
        </defs>

        <rect x={0} y={0} width={width} height={height} fill="url(#orbitDots)" />

        {/* Conduits */}
        {laneGeom.map(({ lane, theme, d, done }) => (
          <path
            key={`link-${lane.domain}`}
            d={d}
            fill="none"
            stroke={theme.color}
            strokeWidth={done ? 2 : 1.4}
            strokeOpacity={done ? 0.5 : 0.22}
            strokeDasharray={done ? undefined : "2 5"}
            strokeLinecap="round"
          />
        ))}

        {/* Traveling beads -- one per still-reasoning lane */}
        {laneGeom.map(({ lane, theme, d, done }) =>
          !done && processing ? (
            <circle key={`bead-${lane.domain}`} r={3} fill={theme.color}>
              <animateMotion dur="1.7s" repeatCount="indefinite" path={d} />
              <animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.15;0.85;1" dur="1.7s" repeatCount="indefinite" />
            </circle>
          ) : null
        )}

        {/* Synthesis core */}
        <circle cx={CORE_X} cy={coreY} r={CORE_R + 14} fill="url(#coreGlow)" />
        {anyProcessing && (
          <circle cx={CORE_X} cy={coreY} r={CORE_R + 7} fill="none" stroke="rgba(0,229,255,.35)" strokeWidth={1} strokeDasharray="3 5">
            <animateTransform attributeName="transform" type="rotate" from={`0 ${CORE_X} ${coreY}`} to={`360 ${CORE_X} ${coreY}`} dur="6s" repeatCount="indefinite" />
          </circle>
        )}
        <circle
          cx={CORE_X}
          cy={coreY}
          r={CORE_R}
          fill="#050608"
          stroke={anyProcessing ? "#00e5ff" : "#37f29a"}
          strokeWidth={2}
        >
          {anyProcessing && <animate attributeName="stroke-opacity" values="1;0.4;1" dur="1.6s" repeatCount="indefinite" />}
        </circle>
        <Sparkles x={CORE_X - 8} y={coreY - 8} width={16} height={16} color={anyProcessing ? "#00e5ff" : "#37f29a"} />

        {/* Lanes: chip + stage beads laid along each conduit's own curve */}
        {laneGeom.map(({ lane, theme, p0, p1, p2, p3, stageLabels, activeCount, done, currentLabel }) => {
          const progress = stageLabels.length ? activeCount / stageLabels.length : 0;
          const ringR = 13;
          const circumference = 2 * Math.PI * ringR;
          return (
            <g key={lane.domain}>
              {stageLabels.map((label, stageIndex) => {
                const t = stageLabels.length > 1 ? 0.1 + (stageIndex / (stageLabels.length - 1)) * 0.72 : 0.4;
                const [x, y] = cubicPoint(p0, p1, p2, p3, t);
                const filled = stageIndex < activeCount;
                const isCurrent = processing && !done && stageIndex === activeCount - 1;
                const size = isCurrent ? 6 : 4.5;
                return (
                  <g key={`${lane.domain}-${stageIndex}`} transform={`translate(${x},${y}) rotate(45)`}>
                    <rect
                      x={-size / 2}
                      y={-size / 2}
                      width={size}
                      height={size}
                      rx={1}
                      fill={filled ? theme.color : "rgba(255,255,255,.14)"}
                      opacity={filled ? 1 : 0.55}
                    >
                      <title>{label}</title>
                      {isCurrent && <animate attributeName="opacity" values="1;0.4;1" dur="1s" repeatCount="indefinite" />}
                    </rect>
                    {isCurrent && (
                      <rect x={-size} y={-size} width={size * 2} height={size * 2} rx={2} fill="none" stroke={theme.color} strokeOpacity={0.4}>
                        <animate attributeName="width" values={`${size * 1.4};${size * 3.2}`} dur="1.3s" repeatCount="indefinite" />
                        <animate attributeName="height" values={`${size * 1.4};${size * 3.2}`} dur="1.3s" repeatCount="indefinite" />
                        <animate attributeName="x" values={`${-size * 0.7};${-size * 1.6}`} dur="1.3s" repeatCount="indefinite" />
                        <animate attributeName="y" values={`${-size * 0.7};${-size * 1.6}`} dur="1.3s" repeatCount="indefinite" />
                        <animate attributeName="opacity" values="0.5;0" dur="1.3s" repeatCount="indefinite" />
                      </rect>
                    )}
                  </g>
                );
              })}

              {/* Domain chip with progress ring, anchored at the conduit's outer end */}
              <g transform={`translate(${p0[0] + 14},${p0[1]})`}>
                <circle r={ringR} fill="none" stroke="rgba(255,255,255,.1)" strokeWidth={2.5} />
                <circle
                  r={ringR}
                  fill="none"
                  stroke={theme.color}
                  strokeWidth={2.5}
                  strokeLinecap="round"
                  strokeDasharray={circumference}
                  strokeDashoffset={circumference * (1 - progress)}
                  transform="rotate(-90)"
                />
                <circle r={ringR - 5} fill={done ? `${theme.color}25` : "rgba(255,255,255,.04)"} />
              </g>
              <text x={p0[0] + 34} y={p0[1] - 3} fontSize="11" fontWeight={600} fill={theme.color}>
                {theme.label}
              </text>
              <text x={p0[0] + 34} y={p0[1] + 11} fontSize="9" fill="rgba(237,234,226,.5)">
                {done ? "complete" : `${currentLabel}`.slice(0, 30)}
              </text>
            </g>
          );
        })}
      </svg>
      <style jsx>{`
        .reasoning-orbit {
          position: relative;
          background-image: radial-gradient(circle at 8% 50%, rgba(0, 229, 255, 0.07), transparent 55%);
        }
      `}</style>
    </div>
  );
}
