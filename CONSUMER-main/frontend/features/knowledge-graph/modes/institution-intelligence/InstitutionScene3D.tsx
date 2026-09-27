"use client";

import { useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { ENTITY_COLOR } from "../../scene/legend";
import { KIND_ICON } from "../../components/NodeDetailPanel";
import { clusterLayout, hashPhase, type Vec3 } from "../../scene/layout";
import { GlowOrb, GlowEdge, VoidEnvironment } from "../../scene/primitives";
import { SceneShell, SceneOrbitControls, CameraDirector, type OrbitControlsHandle } from "../../scene/SceneShell";
import type { ConstellationEdge, ConstellationNode } from "./buildConstellation";

function iconFor(node: ConstellationNode) {
  const Icon = KIND_ICON[node.kind];
  return <Icon className="size-3" style={{ color: ENTITY_COLOR[node.kind] }} />;
}

export interface InstitutionScene3DProps {
  nodes: ConstellationNode[];
  edges: ConstellationEdge[];
  sharedEdges: ConstellationEdge[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

function computeLayout(nodes: ConstellationNode[]): Map<string, Vec3> {
  const byCluster = new Map<number, string[]>();
  const centerByCluster = new Map<number, string>();
  for (const n of nodes) {
    if (!byCluster.has(n.clusterIndex)) byCluster.set(n.clusterIndex, []);
    byCluster.get(n.clusterIndex)!.push(n.id);
    if (n.kind === "institution") centerByCluster.set(n.clusterIndex, n.id);
  }
  const clusterIndices = Array.from(byCluster.keys()).sort((a, b) => a - b);
  const positions = new Map<string, Vec3>();
  clusterIndices.forEach((idx, i) => {
    const count = clusterIndices.length;
    const centerX = count <= 1 ? 0 : (i - (count - 1) / 2) * 7.2;
    const ids = byCluster.get(idx)!;
    const centerId = centerByCluster.get(idx) ?? ids[0];
    clusterLayout(ids, centerId, [centerX, 0, 0]).forEach((pos, id) => positions.set(id, pos));
  });
  return positions;
}

function Scene({ nodes, edges, sharedEdges, selectedId, onSelect }: InstitutionScene3DProps) {
  const controlsRef = useRef<OrbitControlsHandle | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [userInteracted, setUserInteracted] = useState(false);
  const positions = useMemo(() => computeLayout(nodes), [nodes]);
  const nodeById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  const focusPos = useMemo(() => {
    const p = selectedId ? positions.get(selectedId) : null;
    return p ? new THREE.Vector3(...p) : new THREE.Vector3(0, 0, 0);
  }, [selectedId, positions]);

  const particleEdgeKeys = useMemo(() => new Set(edges.slice(0, 50).map((e) => `${e.source}::${e.target}`)), [edges]);

  return (
    <>
      <VoidEnvironment near={11} far={30} />
      <pointLight position={[8, 6, 8]} intensity={0.5} color="#ffffff" />
      <CameraDirector focusPos={focusPos} controlsRef={controlsRef} offset={[2.4, 1.8, 5.4]} />
      <SceneOrbitControls controlsRef={controlsRef} autoRotate={!userInteracted && !selectedId} autoRotateSpeed={0.26} minDistance={2.5} maxDistance={34} onStart={() => setUserInteracted(true)} />

      {edges.map((edge, i) => {
        const from = positions.get(edge.source);
        const to = positions.get(edge.target);
        if (!from || !to) return null;
        const targetNode = nodeById.get(edge.target);
        const active = hoveredId === edge.source || hoveredId === edge.target || selectedId === edge.source || selectedId === edge.target;
        return (
          <GlowEdge key={`${edge.source}-${edge.target}-${i}`} from={from} to={to} color={targetNode ? ENTITY_COLOR[targetNode.kind] : "#ffc857"} active={active} dimmed={Boolean(hoveredId || selectedId) && !active} particles={particleEdgeKeys.has(`${edge.source}::${edge.target}`)} phase={hashPhase(edge.source + edge.target)} />
        );
      })}

      {sharedEdges.map((edge, i) => {
        const from = positions.get(edge.source);
        const to = positions.get(edge.target);
        if (!from || !to) return null;
        return <GlowEdge key={`shared-${i}`} from={from} to={to} color="#ffe9b0" active strength={0.9} particles phase={hashPhase(`shared${edge.source}${edge.target}`)} />;
      })}

      {nodes.map((node) => {
        const pos = positions.get(node.id);
        if (!pos) return null;
        return (
          <GlowOrb
            key={node.id}
            id={node.id}
            position={pos}
            radius={node.kind === "institution" ? 0.7 : node.kind === "regulation" ? 0.4 + node.weight * 0.25 : 0.4}
            color={ENTITY_COLOR[node.kind]}
            label={node.label}
            icon={iconFor(node)}
            emphasized={node.id === selectedId}
            dimmed={false}
            onSelect={onSelect}
            onHover={setHoveredId}
          />
        );
      })}
    </>
  );
}

export default function InstitutionScene3D(props: InstitutionScene3DProps) {
  function stepNode(direction: 1 | -1) {
    if (props.nodes.length === 0) return;
    const idx = props.nodes.findIndex((n) => n.id === props.selectedId);
    const nextIdx = idx === -1 ? 0 : (idx + direction + props.nodes.length) % props.nodes.length;
    props.onSelect(props.nodes[nextIdx].id);
  }

  return (
    <div
      className="relative h-full min-h-[500px] w-full overflow-hidden outline-none"
      tabIndex={0}
      role="application"
      aria-label="3D institution comparison graph. Use arrow keys to step between nodes."
      onKeyDown={(e) => {
        if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); stepNode(1); }
        if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); stepNode(-1); }
      }}
    >
      <SceneShell cameraPosition={[0, 2.6, 11]}>
        <Scene {...props} />
      </SceneShell>
    </div>
  );
}
