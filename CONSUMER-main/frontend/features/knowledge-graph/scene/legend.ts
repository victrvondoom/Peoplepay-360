import type { NodeKind } from "../schemas";

/** Fixed entity color legend (spec 4.3) -- used consistently across all
 * three modes and both the 3D and 2D-fallback renderers. Do not vary these
 * per-mode; the whole point is that "cyan" means "case" everywhere on this
 * page. */
export const ENTITY_COLOR: Record<NodeKind, string> = {
  case: "#00e5ff",
  domain: "#9b5cff",
  institution: "#ffc857",
  document: "#37f29a",
  appeal: "#ff4dd2",
  regulation: "#5c9bff",
  you: "#ffb454",
};

export const ENTITY_LABEL: Record<NodeKind, string> = {
  case: "Case",
  domain: "Domain",
  institution: "Institution",
  document: "Document",
  appeal: "Appeal",
  regulation: "Regulation",
  you: "You",
};

export const LEGEND_ITEMS: Array<{ kind: NodeKind; label: string; color: string }> = (
  ["case", "domain", "institution", "document", "appeal", "regulation"] as NodeKind[]
).map((kind) => ({ kind, label: ENTITY_LABEL[kind], color: ENTITY_COLOR[kind] }));
