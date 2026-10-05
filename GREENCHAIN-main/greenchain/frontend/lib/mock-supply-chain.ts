export type SupplyChainEntityKind =
  | "supplier"
  | "component"
  | "manufacturer"
  | "logistics"
  | "market"

export type SupplyChainStatus = "stable" | "watch" | "critical"

export interface SupplyChainLocation {
  id: string
  name: string
  region: string
  country: string
  coordinates: {
    x: number
    y: number
  }
  throughput: string
  risk: SupplyChainStatus
}

export interface SupplyChainEntity {
  id: string
  name: string
  kind: SupplyChainEntityKind
  locationId: string
  status: SupplyChainStatus
  tier: string
  summary: string
  throughput: string
  confidence: number
  graph: {
    x: number
    y: number
  }
  tags: string[]
}

export interface SupplyChainLink {
  id: string
  sourceId: string
  targetId: string
  label: string
  status: SupplyChainStatus
  leadTimeDays: number
  volume: string
}

export interface SupplyChainMetric {
  id: string
  label: string
  value: string
  delta: string
}

export interface SupplyChainSnapshot {
  title: string
  updatedAt: string
  entities: SupplyChainEntity[]
  links: SupplyChainLink[]
  locations: SupplyChainLocation[]
  metrics: SupplyChainMetric[]
  alerts: string[]
}

export const supplyChainSnapshot: SupplyChainSnapshot = {
  title: "Project Obsidian / Battery Cell Network",
  updatedAt: "04:12 UTC",
  metrics: [
    {
      id: "uptime",
      label: "Network integrity",
      value: "97.4%",
      delta: "+1.2%",
    },
    {
      id: "latency",
      label: "Average lead time",
      value: "14.8d",
      delta: "-0.9d",
    },
    { id: "exceptions", label: "Open exceptions", value: "03", delta: "-2" },
    { id: "visibility", label: "Confidence", value: "92%", delta: "+4%" },
  ],
  alerts: [
    "Cathode precursor lane rerouted through Kaohsiung due to port weather.",
    "Component node CN-SHENZHEN-12 requires verification on cobalt feed traceability.",
    "Lithium supply from Atacama remains stable with no detected delay propagation.",
  ],
  locations: [
    {
      id: "cl",
      name: "Atacama Basin",
      region: "LATAM",
      country: "Chile",
      coordinates: { x: 16, y: 63 },
      throughput: "41 kt / month",
      risk: "stable",
    },
    {
      id: "cn",
      name: "Shenzhen Corridor",
      region: "APAC",
      country: "China",
      coordinates: { x: 74, y: 34 },
      throughput: "128 kt / month",
      risk: "watch",
    },
    {
      id: "kr",
      name: "Ulsan Cluster",
      region: "APAC",
      country: "South Korea",
      coordinates: { x: 80, y: 32 },
      throughput: "86 kt / month",
      risk: "stable",
    },
    {
      id: "de",
      name: "Leipzig Assembly",
      region: "EMEA",
      country: "Germany",
      coordinates: { x: 49, y: 28 },
      throughput: "58 kt / month",
      risk: "critical",
    },
    {
      id: "us",
      name: "New Jersey Port",
      region: "North America",
      country: "United States",
      coordinates: { x: 28, y: 31 },
      throughput: "73 kt / month",
      risk: "stable",
    },
  ],
  entities: [
    {
      id: "supplier-lithium",
      name: "Lithium Brine 7A",
      kind: "supplier",
      locationId: "cl",
      status: "stable",
      tier: "Tier 3",
      summary:
        "Primary lithium extraction feed for the cathode precursor chain.",
      throughput: "11.2 kt",
      confidence: 96,
      graph: { x: 14, y: 61 },
      tags: ["Raw material", "Verified", "Low volatility"],
    },
    {
      id: "component-cathode",
      name: "Precursor Line CN-12",
      kind: "component",
      locationId: "cn",
      status: "watch",
      tier: "Tier 2",
      summary:
        "Cathode precursor mixing and refinement with moderate delay risk.",
      throughput: "8.7 kt",
      confidence: 88,
      graph: { x: 38, y: 48 },
      tags: ["Cobalt", "Constraint", "Customs review"],
    },
    {
      id: "manufacturer-cell",
      name: "Cell Stack ULS-4",
      kind: "manufacturer",
      locationId: "kr",
      status: "stable",
      tier: "Tier 1",
      summary:
        "Battery cell assembly line with strong traceability and spare capacity.",
      throughput: "13.9 kt",
      confidence: 94,
      graph: { x: 58, y: 39 },
      tags: ["Assembly", "High confidence", "Redundant tooling"],
    },
    {
      id: "logistics-port",
      name: "Atlantic Transfer 9",
      kind: "logistics",
      locationId: "us",
      status: "stable",
      tier: "Transit",
      summary:
        "Transatlantic consolidation hub for battery modules and pack materials.",
      throughput: "17.4 kt",
      confidence: 91,
      graph: { x: 76, y: 52 },
      tags: ["Port", "On time", "Sea / rail"],
    },
    {
      id: "manufacturer-pack",
      name: "Pack Forge Leipzig",
      kind: "manufacturer",
      locationId: "de",
      status: "critical",
      tier: "Tier 1",
      summary:
        "Final pack integration constrained by one coating machine and labor limits.",
      throughput: "6.1 kt",
      confidence: 84,
      graph: { x: 88, y: 31 },
      tags: ["Constraint", "Line 2 outage", "Escalated"],
    },
  ],
  links: [
    {
      id: "l1",
      sourceId: "supplier-lithium",
      targetId: "component-cathode",
      label: "Lithium carbonate",
      status: "stable",
      leadTimeDays: 7,
      volume: "2.4 kt",
    },
    {
      id: "l2",
      sourceId: "component-cathode",
      targetId: "manufacturer-cell",
      label: "Cathode precursor",
      status: "watch",
      leadTimeDays: 11,
      volume: "1.7 kt",
    },
    {
      id: "l3",
      sourceId: "manufacturer-cell",
      targetId: "logistics-port",
      label: "Cell modules",
      status: "stable",
      leadTimeDays: 9,
      volume: "2.9 kt",
    },
    {
      id: "l4",
      sourceId: "logistics-port",
      targetId: "manufacturer-pack",
      label: "Pack modules",
      status: "watch",
      leadTimeDays: 5,
      volume: "2.1 kt",
    },
    {
      id: "l5",
      sourceId: "manufacturer-cell",
      targetId: "manufacturer-pack",
      label: "Direct air bridge",
      status: "critical",
      leadTimeDays: 3,
      volume: "0.8 kt",
    },
  ],
}
