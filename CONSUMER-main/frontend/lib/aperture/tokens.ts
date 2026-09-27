// Design tokens for the Aperture landing page ((marketing) route group only).
// Scoped deliberately separate from the dashboard's --proxy-* tokens in
// app/globals.css -- this page has its own chaos/order narrative palette.

export const apertureColors = {
  void: "#07070B",
  ink: "#14132A",
  ember: "#FF6A3D",
  cyan: "#5FF0D7",
  violet: "#9B7BFF",
  bone: "#EDEAE2",
} as const;

export const DOMAINS = [
  { key: "banking", label: "Banking" },
  { key: "health_insurance", label: "Health Insurance" },
  { key: "airlines", label: "Airlines" },
  { key: "telecom", label: "Telecom" },
  { key: "ecommerce", label: "E-Commerce" },
  { key: "government", label: "Government" },
  { key: "housing", label: "Housing" },
  { key: "healthcare", label: "Healthcare" },
] as const;

export const LIFECYCLE_STEPS = [
  { n: "01", title: "Authenticate", body: "Every call carries a verified caller identity before it touches a domain agent." },
  { n: "02", title: "Route", body: "Domain classification picks the specialist -- or specialists -- your query actually needs." },
  { n: "03", title: "Retrieve", body: "Vector + graph lookups pull the regulations and precedent relevant to the case." },
  { n: "04", title: "Enforce policy", body: "Evidence is checked against the case before it's allowed to shape the answer." },
  { n: "05", title: "Draft", body: "Specialist agents produce the response, strategy, and next steps." },
  { n: "06", title: "Review & log", body: "A review pass audits the draft; the full trace is written to the case timeline." },
] as const;
