"use client";

import type { GlobalSearchResult } from "@/lib/api-client";

const FACTORS: Array<{ key: keyof GlobalSearchResult["evidence_scores"]; label: string; color: string }> = [
  { key: "similarity_score", label: "Relevance", color: "#00e5ff" },
  { key: "authority_score", label: "Authority", color: "#9b5cff" },
  { key: "legal_weight", label: "Legal Weight", color: "#ffc857" },
  { key: "freshness_score", label: "Freshness", color: "#37f29a" },
];

/** Shows *why* a result ranked where it did -- the Evidence Scoring Engine
 * blends similarity/authority/legal-weight/freshness (see
 * backend/app/services/evidence_scoring.py), but a single percentage badge
 * hides that reasoning. This makes it visible. */
export function EvidenceScoreBreakdown({ scores }: { scores: GlobalSearchResult["evidence_scores"] }) {
  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
      {FACTORS.map((factor) => {
        const value = scores[factor.key];
        return (
          <div key={factor.key}>
            <div className="mb-1 flex items-center justify-between text-[10px]">
              <span className="text-proxy-tertiary">{factor.label}</span>
              <span className="text-proxy-text">{Math.round(value * 100)}%</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-white/5">
              <div className="h-full rounded-full transition-all" style={{ width: `${value * 100}%`, backgroundColor: factor.color }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
