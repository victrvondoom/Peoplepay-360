/** Per-domain color identity, used consistently across the reasoning lanes,
 * domain chips, and citation constellation so a multi-domain answer is
 * visually legible at a glance -- which domain is which color stays
 * constant everywhere it appears. */
export interface DomainTheme {
  label: string;
  color: string;
  glow: string;
}

export const DOMAIN_THEME: Record<string, DomainTheme> = {
  health_insurance: { label: "Health Insurance", color: "#00e5ff", glow: "rgba(0,229,255,.45)" },
  banking: { label: "Banking", color: "#ffc857", glow: "rgba(255,200,87,.45)" },
  airlines: { label: "Airlines", color: "#9b5cff", glow: "rgba(155,92,255,.45)" },
  telecom: { label: "Telecom", color: "#37f29a", glow: "rgba(55,242,154,.45)" },
  ecommerce: { label: "E-commerce", color: "#ff6fb0", glow: "rgba(255,111,176,.45)" },
  government: { label: "Government", color: "#5c9bff", glow: "rgba(92,155,255,.45)" },
  housing: { label: "Housing", color: "#ff9a5c", glow: "rgba(255,154,92,.45)" },
  healthcare: { label: "Healthcare", color: "#ff4d6d", glow: "rgba(255,77,109,.45)" },
};

const FALLBACK: DomainTheme = { label: "General", color: "#a8b3c7", glow: "rgba(168,179,199,.4)" };

export function domainTheme(domain: string): DomainTheme {
  return DOMAIN_THEME[domain] ?? { ...FALLBACK, label: domain };
}
