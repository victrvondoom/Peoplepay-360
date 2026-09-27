"use client";

import { Building2, FileText, Gavel, Layers, Scale, ScrollText, Users } from "lucide-react";
import type { NodeKind } from "../schemas";
import { ENTITY_COLOR, ENTITY_LABEL } from "../scene/legend";

export const KIND_ICON: Record<NodeKind, typeof ScrollText> = {
  case: ScrollText,
  domain: Layers,
  institution: Building2,
  document: FileText,
  appeal: Scale,
  regulation: Gavel,
  you: Users,
};

export interface InspectableNode {
  id: string;
  kind: NodeKind;
  label: string;
  detail?: Record<string, unknown>;
}

/** Generic right-panel inspector -- works for both Reasoning Trail (real
 * case/appeal/document/regulation detail from the backend) and Institution
 * Intelligence (client-assembled detail from the same-shaped node) so the
 * two modes share this one presentation without sharing layout/metaphor. */
export function NodeDetailPanel({ node }: { node: InspectableNode }) {
  const Icon = KIND_ICON[node.kind];
  const color = ENTITY_COLOR[node.kind];
  const entries = Object.entries(node.detail ?? {}).filter(([, v]) => v !== null && v !== undefined && v !== "");

  return (
    <>
      <div className="mb-4 flex items-center gap-2">
        <div className="grid size-9 place-items-center rounded-lg border" style={{ borderColor: color, boxShadow: `0 0 18px ${color}55` }}>
          <Icon className="size-4" style={{ color }} />
        </div>
        <div className="min-w-0">
          <p className="font-mono text-[10px] uppercase tracking-[.16em] text-proxy-tertiary">{ENTITY_LABEL[node.kind]}</p>
          <p className="truncate text-sm font-semibold text-proxy-text">{node.label}</p>
        </div>
      </div>
      <div className="space-y-3">
        {entries.length === 0 && <p className="text-xs text-proxy-tertiary">No further detail recorded for this entity.</p>}
        {entries.map(([key, value]) => (
          <div key={key} className="rounded-xl border border-white/10 bg-black/20 p-3">
            <p className="mb-1 font-mono text-[10px] uppercase tracking-[.16em] text-proxy-tertiary">{key.replace(/_/g, " ")}</p>
            <p className="text-sm leading-6 text-proxy-muted">{typeof value === "boolean" ? (value ? "Yes" : "No") : String(value)}</p>
          </div>
        ))}
      </div>
    </>
  );
}
