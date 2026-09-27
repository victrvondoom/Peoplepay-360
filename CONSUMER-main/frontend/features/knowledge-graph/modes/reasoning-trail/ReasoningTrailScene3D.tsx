"use client";

import { useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { Building2, FileText, Gavel, Layers, Scale, ScrollText } from "lucide-react";
import type { GraphEdgeData, GraphNodeData, NodeKind } from "../../schemas";
import { ENTITY_COLOR } from "../../scene/legend";
import { spiralLayout, hashPhase } from "../../scene/layout";
import { GlowOrb, GlowEdge, VoidEnvironment } from "../../scene/primitives";
import { SceneShell, SceneOrbitControls, CameraDirector, type OrbitControlsHandle } from "../../scene/SceneShell";

const ICONS: Record<NodeKind, React.ReactNode> = {
  case: <ScrollText className="size-3" style={{ color: ENTITY_COLOR.case }} />,
  domain: <Layers className="size-3" style={{ color: ENTITY_COLOR.domain }} />,
  institution: <Building2 className="size-3" style={{ color: ENTITY_COLOR.institution }} />,
  document: <FileText className="size-3" style={{ color: ENTITY_COLOR.document }} />,
  appeal: <Scale className="size-3" style={{ color: ENTITY_COLOR.appeal }} />,
  regulation: <Gavel className="size-3" style={{ color: ENTITY_COLOR.regulation }} />,
  you: <ScrollText className="size-3" style={{ color: ENTITY_COLOR.you }} />,
};

export interface ReplayState {
  active: boolean;
  currentNodeId: string | null;
  visitedNodeIds: Set<string>;
}

export interface ReasoningTrailScene3DProps {
  nodes: GraphNodeData[];
  edges: GraphEdgeData[];
  selectedNodeId: string | null;
  onSelectNode: (id: string) => void;
  replay: ReplayState | null;
}

function Scene({ nodes, edges, selectedNodeId, onSelectNode, replay }: ReasoningTrailScene3DProps) {
  const controlsRef = useRef<OrbitControlsHandle | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [userInteracted, setUserInteracted] = useState(false);

  const positions = useMemo(() => spiralLayout(nodes.map((n) => n.id), "case"), [nodes]);
  const nodeById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  const focusId = replay?.active ? replay.currentNodeId : selectedNodeId ?? "case";
  const focusPos = useMemo(() => {
    const p = focusId ? positions.get(focusId) : null;
    return p ? new THREE.Vector3(...p) : new THREE.Vector3(0, 0, 0);
  }, [focusId, positions]);

  const particleEdgeKeys = useMemo(() => new Set(edges.slice(0, 50).map((e) => `${e.source}::${e.target}`)), [edges]);
  const autoRotate = !replay?.active && !userInteracted && !selectedNodeId;

  return (
    <>
      <VoidEnvironment />
      <pointLight position={[6, 6, 6]} intensity={0.5} color="#ffffff" />
      <CameraDirector focusPos={focusPos} controlsRef={controlsRef} />
      <SceneOrbitControls controlsRef={controlsRef} autoRotate={autoRotate} enabled={!replay?.active} onStart={() => setUserInteracted(true)} />

      {edges.map((edge, i) => {
        const from = positions.get(edge.source);
        const to = positions.get(edge.target);
        if (!from || !to) return null;
        const targetNode = nodeById.get(edge.target);
        const touchesFocus = replay?.active
          ? replay.currentNodeId === edge.source || replay.currentNodeId === edge.target
          : hoveredId === edge.source || hoveredId === edge.target || selectedNodeId === edge.source || selectedNodeId === edge.target;
        const dimmed = replay?.active
          ? !(replay.visitedNodeIds.has(edge.source) && replay.visitedNodeIds.has(edge.target))
          : Boolean(hoveredId || selectedNodeId) && !touchesFocus;
        return (
          <GlowEdge
            key={`${edge.source}-${edge.target}-${i}`}
            from={from}
            to={to}
            color={targetNode ? ENTITY_COLOR[targetNode.kind] : "#00e5ff"}
            active={touchesFocus}
            dimmed={dimmed}
            particles={particleEdgeKeys.has(`${edge.source}::${edge.target}`)}
            phase={hashPhase(edge.source + edge.target)}
          />
        );
      })}

      {nodes.map((node) => {
        const pos = positions.get(node.id);
        if (!pos) return null;
        const current = Boolean(replay?.active && replay.currentNodeId === node.id);
        const selected = node.id === selectedNodeId && !replay?.active;
        const dimmed = Boolean(replay?.active) && !current && !(replay?.visitedNodeIds.has(node.id) ?? false);
        const baseRadius = node.id === "case" ? 0.85 : node.kind === "domain" || node.kind === "institution" ? 0.6 : 0.45;
        return (
          <GlowOrb
            key={node.id}
            id={node.id}
            position={pos}
            radius={baseRadius}
            color={ENTITY_COLOR[node.kind]}
            label={node.label}
            icon={ICONS[node.kind]}
            emphasized={selected || current}
            dimmed={dimmed}
            onSelect={replay?.active ? undefined : onSelectNode}
            onHover={setHoveredId}
          />
        );
      })}
    </>
  );
}

export default function ReasoningTrailScene3D(props: ReasoningTrailScene3DProps) {
  function stepNode(direction: 1 | -1) {
    if (props.nodes.length === 0) return;
    const idx = props.nodes.findIndex((n) => n.id === props.selectedNodeId);
    const nextIdx = idx === -1 ? 0 : (idx + direction + props.nodes.length) % props.nodes.length;
    props.onSelectNode(props.nodes[nextIdx].id);
  }

  return (
    <div
      className="relative h-full min-h-[500px] w-full overflow-hidden outline-none"
      tabIndex={0}
      role="application"
      aria-label="3D reasoning trail graph. Use arrow keys to step between nodes."
      onKeyDown={(e) => {
        if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); stepNode(1); }
        if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); stepNode(-1); }
      }}
    >
      <SceneShell>
        <Scene {...props} />
      </SceneShell>
    </div>
  );
}
