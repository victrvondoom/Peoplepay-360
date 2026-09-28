"use client";

import { useMemo, useRef, useState } from "react";
import type { NodeKind } from "../schemas";
import { ENTITY_COLOR, LEGEND_ITEMS } from "./legend";
import { useForceSimulation2D, type ForceEdge2D, type ForceNode2D } from "./useForceSimulation2D";

export interface Fallback2DNode {
  id: string;
  kind: NodeKind;
  label: string;
  size: number;
}
export interface Fallback2DEdge {
  source: string;
  target: string;
}

const SPACE = 640;

/** Full 2D fallback (spec 11): same color legend and interaction model as
 * the 3D scenes (click to select, drag to reposition, scroll to zoom), used
 * whenever device tier / reduced-motion / viewport rules out WebGL. A
 * smooth 2D graph beats a stuttering 3D one. */
export function Fallback2DGraph({
  nodes, edges, anchorId, selectedId, onSelect, emptyMessage,
}: {
  nodes: Fallback2DNode[];
  edges: Fallback2DEdge[];
  anchorId?: string;
  selectedId: string | null;
  onSelect: (id: string) => void;
  emptyMessage?: string;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const groupRef = useRef<SVGGElement>(null);
  const [view, setView] = useState({ x: 0, y: 0, k: 1 });
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const dragState = useRef<{ id: string; moved: boolean } | null>(null);

  const forceNodes: ForceNode2D[] = useMemo(() => nodes.map((n) => ({ id: n.id, r: n.size })), [nodes]);
  const forceEdges: ForceEdge2D[] = useMemo(() => edges.map((e) => ({ source: e.source, target: e.target })), [edges]);
  const { position, pin, release } = useForceSimulation2D(forceNodes, forceEdges, SPACE, SPACE, anchorId);

  function clientToSimPoint(clientX: number, clientY: number) {
    const group = groupRef.current;
    const svg = svgRef.current;
    if (!group || !svg) return { x: 0, y: 0 };
    const pt = svg.createSVGPoint();
    pt.x = clientX;
    pt.y = clientY;
    const ctm = group.getScreenCTM();
    if (!ctm) return { x: 0, y: 0 };
    const local = pt.matrixTransform(ctm.inverse());
    return { x: local.x, y: local.y };
  }

  function onWheel(e: React.WheelEvent) {
    e.preventDefault();
    const nextK = Math.min(2.6, Math.max(0.45, view.k * (1 - e.deltaY * 0.0012)));
    setView((v) => ({ ...v, k: nextK }));
  }

  function onNodeMouseDown(e: React.MouseEvent, id: string) {
    e.stopPropagation();
    dragState.current = { id, moved: false };
    const start = { x: e.clientX, y: e.clientY };
    const move = (event: MouseEvent) => {
      const state = dragState.current;
      if (!state) return;
      if (!state.moved && Math.hypot(event.clientX - start.x, event.clientY - start.y) > 5) state.moved = true;
      const sim = clientToSimPoint(event.clientX, event.clientY);
      pin(id, sim.x, sim.y);
    };
    const up = () => {
      const state = dragState.current;
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
      if (state) {
        release(state.id);
        if (!state.moved) onSelect(state.id);
      }
      dragState.current = null;
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  }

  if (nodes.length === 0) {
    return (
      <div className="flex h-full min-h-[500px] flex-col items-center justify-center gap-2 text-center">
        <p className="text-sm text-proxy-tertiary">{emptyMessage ?? "Nothing to show yet."}</p>
      </div>
    );
  }

  return (
    <div className="relative h-full min-h-[500px] w-full overflow-hidden">
      <div className="absolute bottom-4 left-4 z-10 flex flex-wrap gap-2 rounded-xl border border-white/10 bg-black/45 px-3 py-2 backdrop-blur-xl">
        {LEGEND_ITEMS.map((item) => (
          <span key={item.kind} className="flex items-center gap-1.5 font-mono text-[10px] text-proxy-muted">
            <span className="size-2 rounded-full" style={{ backgroundColor: item.color }} />
            {item.label}
          </span>
        ))}
      </div>
      <svg ref={svgRef} viewBox={`0 0 ${SPACE} ${SPACE}`} className="h-full w-full cursor-grab active:cursor-grabbing" role="img" aria-label="Knowledge graph (2D fallback)" onWheel={onWheel}>
        <g ref={groupRef} transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
          {edges.map((edge, i) => {
            const from = position(edge.source);
            const to = position(edge.target);
            const targetKind = nodes.find((n) => n.id === edge.target)?.kind;
            const active = hoveredId === edge.source || hoveredId === edge.target || selectedId === edge.source || selectedId === edge.target;
            return (
              <line
                key={`${edge.source}-${edge.target}-${i}`}
                x1={from.x} y1={from.y} x2={to.x} y2={to.y}
                stroke={targetKind ? ENTITY_COLOR[targetKind] : "#00e5ff"}
                strokeWidth={active ? 2 : 1.2}
                strokeOpacity={active ? 0.7 : 0.22}
              />
            );
          })}
          {nodes.map((node) => {
            const pos = position(node.id);
            const isSelected = node.id === selectedId;
            const isHovered = node.id === hoveredId;
            const color = ENTITY_COLOR[node.kind];
            return (
              <g key={node.id} transform={`translate(${pos.x} ${pos.y})`} style={{ cursor: "grab" }} onMouseDown={(e) => onNodeMouseDown(e, node.id)} onMouseEnter={() => setHoveredId(node.id)} onMouseLeave={() => setHoveredId(null)}>
                <circle
                  r={node.size}
                  fill="rgba(5,5,8,.92)"
                  stroke={color}
                  strokeWidth={isSelected ? 3 : 1.5}
                  style={{ filter: `drop-shadow(0 0 ${isSelected ? 16 : isHovered ? 10 : 6}px ${color}77)` }}
                />
                <text y={node.size + 15} textAnchor="middle" fill="#dbeafe" fontSize={11} fontFamily="var(--font-mono, monospace)" style={{ pointerEvents: "none" }}>
                  {node.label}
                </text>
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}
