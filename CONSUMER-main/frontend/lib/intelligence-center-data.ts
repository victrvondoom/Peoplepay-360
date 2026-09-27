import type { ComponentType, CSSProperties } from "react";
import { Activity, BrainCircuit, Building2, CheckCircle2, CircleDot, ClipboardList, FileHeart, FileText, Gauge, HeartPulse, Landmark, Shield, Sparkles, Stethoscope, Target, TimerReset, Waypoints, Zap } from "lucide-react";

export type NodeKind = "Claim" | "Policy" | "Coverage" | "Exclusion" | "Waiting Period" | "Hospital" | "Doctor" | "Disease" | "Diagnosis" | "Treatment" | "Medical Report" | "Bill" | "Evidence" | "Insurance Company" | "Appeal" | "Consumer Right" | "IRDAI Regulation" | "Government Rule" | "FAQ" | "AI Finding" | "Strategy" | "Recommendation" | "Final Decision";
export type LayerKey = "Documents" | "Entities" | "Relationships" | "AI Reasoning" | "Recommendations" | "Appeal";

export type IntelNode = { id: string; label: string; kind: NodeKind; x: number; y: number; confidence: number; layer: LayerKey; agent: string; source: string; summary: string; why: string; page: string; action: string };
export type IntelEdge = { from: string; to: string; confidence: number; label: string; layer: LayerKey };

export const layerKeys: LayerKey[] = ["Documents", "Entities", "Relationships", "AI Reasoning", "Recommendations", "Appeal"];

export const kindStyles: Record<NodeKind, { color: string; glow: string; icon: ComponentType<{ className?: string; style?: CSSProperties }> }> = {
  Claim: { color: "#00e5ff", glow: "rgba(0,229,255,.34)", icon: FileText },
  Policy: { color: "#61a5ff", glow: "rgba(97,165,255,.30)", icon: Shield },
  Coverage: { color: "#37f29a", glow: "rgba(55,242,154,.30)", icon: CheckCircle2 },
  Exclusion: { color: "#ff4d6d", glow: "rgba(255,77,109,.28)", icon: CircleDot },
  "Waiting Period": { color: "#ffc857", glow: "rgba(255,200,87,.28)", icon: TimerReset },
  Hospital: { color: "#9b5cff", glow: "rgba(155,92,255,.30)", icon: Building2 },
  Doctor: { color: "#7de3ff", glow: "rgba(125,227,255,.25)", icon: Stethoscope },
  Disease: { color: "#ff7eb6", glow: "rgba(255,126,182,.22)", icon: HeartPulse },
  Diagnosis: { color: "#ff9f1c", glow: "rgba(255,159,28,.22)", icon: Activity },
  Treatment: { color: "#37f29a", glow: "rgba(55,242,154,.25)", icon: FileHeart },
  "Medical Report": { color: "#b7f7ff", glow: "rgba(183,247,255,.20)", icon: FileText },
  Bill: { color: "#ffd166", glow: "rgba(255,209,102,.22)", icon: ClipboardList },
  Evidence: { color: "#00e5ff", glow: "rgba(0,229,255,.24)", icon: Target },
  "Insurance Company": { color: "#9b5cff", glow: "rgba(155,92,255,.28)", icon: Landmark },
  Appeal: { color: "#37f29a", glow: "rgba(55,242,154,.28)", icon: Waypoints },
  "Consumer Right": { color: "#61a5ff", glow: "rgba(97,165,255,.26)", icon: Shield },
  "IRDAI Regulation": { color: "#c8a5ff", glow: "rgba(200,165,255,.25)", icon: Landmark },
  "Government Rule": { color: "#c8a5ff", glow: "rgba(200,165,255,.25)", icon: Landmark },
  FAQ: { color: "#a8b3c7", glow: "rgba(168,179,199,.18)", icon: CircleDot },
  "AI Finding": { color: "#00e5ff", glow: "rgba(0,229,255,.34)", icon: BrainCircuit },
  Strategy: { color: "#ffc857", glow: "rgba(255,200,87,.28)", icon: Zap },
  Recommendation: { color: "#37f29a", glow: "rgba(55,242,154,.30)", icon: Sparkles },
  "Final Decision": { color: "#f7fbff", glow: "rgba(247,251,255,.20)", icon: Gauge },
};

export const intelNodes: IntelNode[] = [
  { id: "claim", label: "Claim Rejection", kind: "Claim", x: 420, y: 260, confidence: 91, layer: "Entities", agent: "Research Agent", source: "Claim letter", page: "p.1", summary: "Insurer denied cataract procedure citing waiting period and pre-authorization gap.", why: "This is the central dispute object. Every policy, evidence, and regulation relationship is evaluated against it.", action: "Open rejection letter" },
  { id: "policy", label: "Family Health Optima", kind: "Policy", x: 230, y: 160, confidence: 88, layer: "Documents", agent: "Research Agent", source: "Policy PDF", page: "p.16", summary: "Policy wording contains cataract waiting-period and surgical coverage clauses.", why: "The policy defines the rules the insurer used to reject the claim.", action: "Open policy clause" },
  { id: "coverage", label: "Surgical Coverage", kind: "Coverage", x: 585, y: 145, confidence: 84, layer: "Relationships", agent: "Knowledge Graph Agent", source: "Policy PDF", page: "p.18", summary: "Coverage may apply if eligibility and medical necessity are established.", why: "This node keeps the denial from being treated as automatically valid.", action: "Compare coverage" },
  { id: "waiting", label: "Waiting Period", kind: "Waiting Period", x: 175, y: 315, confidence: 79, layer: "Relationships", agent: "Research Agent", source: "Policy PDF", page: "p.16", summary: "Clause requires exact policy inception and continuity verification.", why: "The denial relies on this clause, so the AI isolates it as a contested reason.", action: "Verify policy age" },
  { id: "hospital", label: "Network Hospital", kind: "Hospital", x: 625, y: 315, confidence: 76, layer: "Entities", agent: "Evidence Agent", source: "Hospital bill", page: "p.1", summary: "Bill indicates network hospital processing and cashless route.", why: "Hospital context helps reconstruct pre-authorization and claim workflow.", action: "Open hospital bill" },
  { id: "diagnosis", label: "Cataract Diagnosis", kind: "Diagnosis", x: 390, y: 95, confidence: 93, layer: "Entities", agent: "Evidence Agent", source: "Medical report", page: "p.2", summary: "Medical record identifies age-related cataract in right eye.", why: "Diagnosis evidence anchors medical necessity and treatment relevance.", action: "Open medical report" },
  { id: "treatment", label: "IOL Procedure", kind: "Treatment", x: 760, y: 235, confidence: 87, layer: "Entities", agent: "Evidence Agent", source: "Discharge summary", page: "p.3", summary: "Treatment was phacoemulsification with IOL implantation.", why: "Treatment entity links medical evidence to policy coverage language.", action: "Trace treatment" },
  { id: "irdai", label: "IRDAI Claim Review", kind: "IRDAI Regulation", x: 455, y: 430, confidence: 82, layer: "Relationships", agent: "Knowledge Graph Agent", source: "IRDAI guidance", page: "rule index", summary: "Claim decision should include clear reasons and document requirements.", why: "Regulation constrains how the insurer should explain and reassess denial.", action: "Open regulation" },
  { id: "finding", label: "Weak Denial Logic", kind: "AI Finding", x: 655, y: 465, confidence: 86, layer: "AI Reasoning", agent: "Strategy Agent", source: "Reasoning trace", page: "trace 04", summary: "Denial applies waiting period before verifying policy continuity and medical necessity evidence.", why: "This is the AI's key reasoning bridge between evidence and strategy.", action: "Inspect reasoning" },
  { id: "strategy", label: "Appeal Strategy", kind: "Strategy", x: 870, y: 365, confidence: 78, layer: "Recommendations", agent: "Strategy Agent", source: "Strategy memo", page: "v1", summary: "Appeal should focus on policy continuity, clinical necessity, and pre-auth timeline.", why: "Strategy chooses the narrowest high-confidence argument instead of overclaiming.", action: "Open strategy" },
  { id: "appeal", label: "Appeal Draft", kind: "Appeal", x: 920, y: 135, confidence: 81, layer: "Appeal", agent: "Negotiation Agent", source: "Generated draft", page: "draft", summary: "Draft asks for clause-specific reassessment and missing-document clarification.", why: "The appeal path converts reasoning into user action.", action: "Open draft" },
  { id: "review", label: "Review Complete", kind: "Final Decision", x: 1040, y: 260, confidence: 74, layer: "AI Reasoning", agent: "Review Agent", source: "Review checklist", page: "final", summary: "Review agent flags missing doctor note and policy schedule as residual risk.", why: "Review protects against hallucination and weak arguments.", action: "Open review" },
];

export const intelEdges: IntelEdge[] = [
  { from: "policy", to: "claim", confidence: 88, label: "governs", layer: "Relationships" },
  { from: "policy", to: "coverage", confidence: 84, label: "defines", layer: "Relationships" },
  { from: "policy", to: "waiting", confidence: 79, label: "contains", layer: "Relationships" },
  { from: "diagnosis", to: "claim", confidence: 93, label: "supports", layer: "Entities" },
  { from: "hospital", to: "treatment", confidence: 76, label: "performed", layer: "Entities" },
  { from: "treatment", to: "coverage", confidence: 87, label: "may trigger", layer: "Relationships" },
  { from: "irdai", to: "claim", confidence: 82, label: "review standard", layer: "Relationships" },
  { from: "claim", to: "finding", confidence: 86, label: "reasoned by", layer: "AI Reasoning" },
  { from: "finding", to: "strategy", confidence: 78, label: "drives", layer: "Recommendations" },
  { from: "strategy", to: "appeal", confidence: 81, label: "drafts", layer: "Appeal" },
  { from: "appeal", to: "review", confidence: 74, label: "validated by", layer: "AI Reasoning" },
];

export const intelTimeline = ["Research Started", "Policy Matched", "Evidence Found", "Regulation Added", "Strategy Built", "Appeal Draft", "Review Complete"];


