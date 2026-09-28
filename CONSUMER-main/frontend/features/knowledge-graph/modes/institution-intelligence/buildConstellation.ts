import type { InstitutionGraphResponse } from "../../schemas";
import type { InspectableNode } from "../../components/NodeDetailPanel";

/** Reshapes the backend's institution-graph response (institutions +
 * patterns + similar_cases + server-computed shared entities) into generic
 * graph nodes/edges the Comparative Constellation scene renders, using the
 * SAME fixed entity-kind legend as every other mode: institution = amber,
 * pattern is treated as a "regulation" (a discovered rule/insight) = blue,
 * similar case = cyan, matching the case color used everywhere else on the
 * page. */
export interface ConstellationNode extends InspectableNode {
  clusterIndex: number;
  weight: number;
}
export interface ConstellationEdge {
  source: string;
  target: string;
}

export function buildConstellation(data: InstitutionGraphResponse | undefined): {
  nodes: ConstellationNode[];
  edges: ConstellationEdge[];
  sharedEdges: ConstellationEdge[];
} {
  if (!data) return { nodes: [], edges: [], sharedEdges: [] };

  const nodes: ConstellationNode[] = [];
  const edges: ConstellationEdge[] = [];

  data.institutions.forEach((entry) => {
    const institutionId = `institution-${entry.index}`;
    nodes.push({
      id: institutionId,
      kind: "institution",
      label: entry.institution_name,
      clusterIndex: entry.index,
      weight: 1,
      detail: { domain: entry.domain, institution: entry.institution_name, patterns: entry.patterns.length, similar_cases: entry.similar_cases.length },
    });

    entry.patterns.forEach((p, i) => {
      const id = `pattern-${entry.index}-${i}`;
      nodes.push({
        id,
        kind: "regulation",
        label: p.pattern.length > 40 ? `${p.pattern.slice(0, 40)}...` : p.pattern,
        clusterIndex: entry.index,
        weight: p.confidence,
        detail: { pattern: p.pattern, confidence: `${Math.round(p.confidence * 100)}%` },
      });
      edges.push({ source: institutionId, target: id });
    });

    entry.similar_cases.forEach((c) => {
      const id = `case-${entry.index}-${c.case_id}`;
      nodes.push({
        id,
        kind: "case",
        label: c.title.length > 32 ? `${c.title.slice(0, 32)}...` : c.title,
        clusterIndex: entry.index,
        weight: 1,
        detail: { title: c.title, summary: c.summary },
      });
      edges.push({ source: institutionId, target: id });
    });
  });

  const sharedEdges: ConstellationEdge[] = data.shared.map((s) => {
    if (s.type === "pattern") return { source: `pattern-0-${s.a_i}`, target: `pattern-1-${s.b_i}` };
    return { source: `case-0-${s.case_id}`, target: `case-1-${s.case_id}` };
  });

  return { nodes, edges, sharedEdges };
}
