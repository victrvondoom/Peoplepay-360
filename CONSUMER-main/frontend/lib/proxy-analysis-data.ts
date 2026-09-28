import type { AgentStage, StageStatus } from "./design-tokens";

export type DomainKey = "health_insurance" | "banking" | "telecom" | "airlines" | "healthcare_provider" | "housing" | "ecommerce" | "government";

export type DomainConfig = {
  key: DomainKey;
  label: string;
  shortLabel: string;
  tagline: string;
  entityLabel: string;
  counterpartyLabel: string;
  primaryMetric: string;
  matchMetric: string;
  documentTitle: string;
  actionName: string;
  uploadSlots: string[];
  graphNodes: string[];
  workflowSteps: string[];
  specialistAgents: string[];
  sampleCounterparty: string;
  sampleMatter: string;
  sampleClaimant: string;
  sampleIssue: string;
  documentPreview: string[];
  sourcesLabel: string;
};

export const domainRegistry: DomainConfig[] = [
  {
    key: "health_insurance",
    label: "Health Insurance",
    shortLabel: "Health",
    tagline: "Claim denial, reimbursement, policy clauses, medical necessity, IRDAI rules.",
    entityLabel: "Claim",
    counterpartyLabel: "Insurer",
    primaryMetric: "Appeal Success",
    matchMetric: "Policy Match",
    documentTitle: "Policy and medical evidence",
    actionName: "Generate Appeal",
    uploadSlots: ["Insurance Policy", "Claim Rejection Letter", "Medical Report", "Hospital Bills"],
    graphNodes: ["Claim", "Policy", "Coverage", "Hospital", "Treatment", "IRDAI Regulation"],
    workflowSteps: ["Upload Documents", "Research", "Evidence", "AI Strategy", "Appeal Draft", "Export PDF"],
    specialistAgents: ["Policy Agent", "Claims Agent", "Medical Agent", "Regulations Agent"],
    sampleCounterparty: "Star Health and Allied Insurance",
    sampleMatter: "Cataract surgery rejection",
    sampleClaimant: "Rakesh Selvaraj",
    sampleIssue: "Waiting-period and pre-authorization denial needs clause-specific review.",
    documentPreview: ["Policy wording includes surgical treatment coverage subject to eligibility.", "Cataract waiting period clause requires policy-age verification.", "Medical report confirms physician-directed treatment."],
    sourcesLabel: "IRDAI + insurer policies",
  },
  {
    key: "banking",
    label: "Banking & Cards",
    shortLabel: "Banking",
    tagline: "Chargebacks, unauthorized transactions, loan disputes, fees, RBI guidance.",
    entityLabel: "Dispute",
    counterpartyLabel: "Bank",
    primaryMetric: "Recovery Probability",
    matchMetric: "Rule Match",
    documentTitle: "Statements and dispute evidence",
    actionName: "Generate Bank Complaint",
    uploadSlots: ["Bank Statement", "Transaction Proof", "Complaint Response", "KYC / Account Terms"],
    graphNodes: ["Dispute", "Account", "Transaction", "Merchant", "Bank Policy", "RBI Guideline"],
    workflowSteps: ["Upload Evidence", "Transaction Research", "Liability Analysis", "RBI Strategy", "Complaint Draft", "Export"],
    specialistAgents: ["Transaction Agent", "RBI Agent", "Fraud Agent", "Complaint Agent"],
    sampleCounterparty: "HDFC Bank",
    sampleMatter: "Unauthorized card transaction",
    sampleClaimant: "Aarav Mehta",
    sampleIssue: "Customer reported transaction within timeline but refund was denied without clear liability analysis.",
    documentPreview: ["Statement shows disputed transaction timestamp.", "Complaint response denies liability without addressing reporting window.", "RBI guidance requires customer liability assessment."],
    sourcesLabel: "RBI + bank terms",
  },
  {
    key: "telecom",
    label: "Telecom & Broadband",
    shortLabel: "Telecom",
    tagline: "Billing, service outages, plan mis-selling, porting, TRAI rules.",
    entityLabel: "Service Issue",
    counterpartyLabel: "Provider",
    primaryMetric: "Resolution Probability",
    matchMetric: "Plan Match",
    documentTitle: "Bills and service records",
    actionName: "Generate TRAI Complaint",
    uploadSlots: ["Monthly Bill", "Plan Terms", "Support Tickets", "Outage / Speed Proof"],
    graphNodes: ["Issue", "Subscriber", "Plan", "Bill", "Service Ticket", "TRAI Rule"],
    workflowSteps: ["Upload Records", "Plan Research", "Evidence", "Regulatory Strategy", "Complaint Draft", "Export"],
    specialistAgents: ["Billing Agent", "Plan Agent", "Service Quality Agent", "TRAI Agent"],
    sampleCounterparty: "Airtel Broadband",
    sampleMatter: "Wrong broadband billing",
    sampleClaimant: "Nisha Rao",
    sampleIssue: "Provider billed for upgraded plan despite no consent record and unresolved outage tickets.",
    documentPreview: ["Bill shows unexpected plan upgrade.", "Support ticket confirms outage period.", "TRAI escalation requires service and billing evidence."],
    sourcesLabel: "TRAI + provider terms",
  },
  {
    key: "airlines",
    label: "Airlines & Travel Refunds",
    shortLabel: "Airlines",
    tagline: "Cancellations, delays, denied boarding, baggage, DGCA passenger rights.",
    entityLabel: "Travel Claim",
    counterpartyLabel: "Airline",
    primaryMetric: "Refund Probability",
    matchMetric: "Fare Rule Match",
    documentTitle: "Ticket and travel evidence",
    actionName: "Generate Airline Claim",
    uploadSlots: ["Ticket / PNR", "Cancellation Notice", "Baggage Proof", "Airline Response"],
    graphNodes: ["Claim", "PNR", "Fare Rule", "Flight Event", "Airline Policy", "DGCA Rule"],
    workflowSteps: ["Upload Travel Docs", "Fare Research", "Evidence", "DGCA Strategy", "Claim Draft", "Export"],
    specialistAgents: ["Fare Agent", "Flight Event Agent", "Baggage Agent", "DGCA Agent"],
    sampleCounterparty: "IndiGo",
    sampleMatter: "Cancelled flight refund",
    sampleClaimant: "Kabir Shah",
    sampleIssue: "Refund was converted to credit shell despite passenger requesting original payment reversal.",
    documentPreview: ["PNR confirms passenger and flight segment.", "Cancellation notice identifies airline-initiated disruption.", "DGCA passenger rights support refund route."],
    sourcesLabel: "DGCA + airline rules",
  },
  {
    key: "healthcare_provider",
    label: "Healthcare Provider Billing",
    shortLabel: "Provider Billing",
    tagline: "Hospital bills, discharge records, duplicate charges, consent and records disputes.",
    entityLabel: "Billing Review",
    counterpartyLabel: "Provider",
    primaryMetric: "Reduction Probability",
    matchMetric: "Charge Match",
    documentTitle: "Hospital billing evidence",
    actionName: "Generate Billing Dispute",
    uploadSlots: ["Itemized Bill", "Discharge Summary", "Consent Forms", "Payment Receipts"],
    graphNodes: ["Billing Review", "Patient", "Procedure", "Charge", "Consent", "Hospital Policy"],
    workflowSteps: ["Upload Bills", "Charge Research", "Evidence", "Reduction Strategy", "Dispute Draft", "Export"],
    specialistAgents: ["Billing Agent", "Medical Records Agent", "Consent Agent", "Negotiation Agent"],
    sampleCounterparty: "Apollo Hospital",
    sampleMatter: "Duplicate procedure charges",
    sampleClaimant: "Meera Iyer",
    sampleIssue: "Bill includes duplicate consumables and unsupported package add-ons.",
    documentPreview: ["Itemized bill contains repeated charge codes.", "Discharge summary lists one procedure episode.", "Receipt trail confirms partial payment already made."],
    sourcesLabel: "Hospital policy + medical records",
  },
  {
    key: "housing",
    label: "Housing & Rentals",
    shortLabel: "Housing",
    tagline: "Security deposits, rent agreements, repairs, maintenance, possession disputes.",
    entityLabel: "Housing Dispute",
    counterpartyLabel: "Landlord / Builder",
    primaryMetric: "Recovery Probability",
    matchMetric: "Agreement Match",
    documentTitle: "Agreement and property evidence",
    actionName: "Generate Legal Notice",
    uploadSlots: ["Rental / Sale Agreement", "Payment Proof", "Inspection Photos", "Notice / Messages"],
    graphNodes: ["Dispute", "Agreement", "Deposit", "Property", "Repair Duty", "Notice"],
    workflowSteps: ["Upload Records", "Agreement Research", "Evidence", "Remedy Strategy", "Notice Draft", "Export"],
    specialistAgents: ["Agreement Agent", "Payment Agent", "Evidence Agent", "Notice Agent"],
    sampleCounterparty: "Greenview Residency",
    sampleMatter: "Security deposit deduction",
    sampleClaimant: "Priya Menon",
    sampleIssue: "Deposit was withheld for normal wear without inspection proof or itemized deduction.",
    documentPreview: ["Agreement describes deposit return conditions.", "Move-out photos show no major damage.", "Messages request itemized deduction but no response received."],
    sourcesLabel: "Agreement + housing law references",
  },
  {
    key: "ecommerce",
    label: "E-commerce & Warranty",
    shortLabel: "E-commerce",
    tagline: "Refunds, defective products, marketplace sellers, warranty denials, delivery disputes.",
    entityLabel: "Consumer Claim",
    counterpartyLabel: "Marketplace / Seller",
    primaryMetric: "Refund Probability",
    matchMetric: "Policy Match",
    documentTitle: "Order and product evidence",
    actionName: "Generate Consumer Complaint",
    uploadSlots: ["Order Invoice", "Return Policy", "Product Photos", "Support Chat"],
    graphNodes: ["Claim", "Order", "Product", "Seller", "Warranty", "Consumer Rule"],
    workflowSteps: ["Upload Order", "Policy Research", "Evidence", "Consumer Strategy", "Complaint Draft", "Export"],
    specialistAgents: ["Order Agent", "Warranty Agent", "Seller Policy Agent", "Consumer Agent"],
    sampleCounterparty: "Amazon Marketplace Seller",
    sampleMatter: "Defective appliance refund",
    sampleClaimant: "Dev Patel",
    sampleIssue: "Seller refused replacement despite defect proof submitted inside return window.",
    documentPreview: ["Invoice confirms delivery date and seller.", "Photo evidence shows defect on arrival.", "Support chat confirms return request inside window."],
    sourcesLabel: "Consumer rules + marketplace terms",
  },
  {
    key: "government",
    label: "Government & Public Grievance",
    shortLabel: "Government",
    tagline: "RTI, certificates, public schemes, administrative delays, public grievance appeals.",
    entityLabel: "Grievance",
    counterpartyLabel: "Department",
    primaryMetric: "Escalation Strength",
    matchMetric: "Rule Match",
    documentTitle: "Application and department evidence",
    actionName: "Generate Grievance Appeal",
    uploadSlots: ["Application / RTI", "Acknowledgement", "Department Response", "Supporting Proof"],
    graphNodes: ["Grievance", "Applicant", "Application", "Department", "Timeline", "Rule"],
    workflowSteps: ["Upload Records", "Rule Research", "Evidence", "Escalation Strategy", "Appeal Draft", "Export"],
    specialistAgents: ["Public Rule Agent", "Timeline Agent", "Evidence Agent", "Escalation Agent"],
    sampleCounterparty: "Municipal Department",
    sampleMatter: "Delayed certificate application",
    sampleClaimant: "Farhan Ali",
    sampleIssue: "Application crossed the service timeline without reasoned response or escalation guidance.",
    documentPreview: ["Acknowledgement confirms application filing date.", "Department response lacks reasoned order.", "Timeline evidence supports escalation."],
    sourcesLabel: "Public grievance + RTI references",
  },
];

export type Analysis = {
  id: string;
  domain: DomainKey;
  claimant: string;
  counterparty: string;
  matter: string;
  status: "Analyzing" | "Action Ready" | "Needs Evidence" | "Submitted";
  updated: string;
  successProbability: number;
  confidence: number;
  policyMatch: number;
  missingDocuments: string[];
  activeStage: AgentStage;
  stages: Record<AgentStage, StageStatus>;
  documents: Array<{ name: string; type: string; pages: number; state: string }>;
  explanation: Array<{ question: string; answer: string; citations: string[] }>;
  highlights: Array<{ doc: string; label: string; type: "exclusion" | "waiting" | "coverage" | "diagnosis"; page: number; text: string }>;
  graph: Array<{ from: string; to: string; type: string }>;
  appealDraft: string;
  timeline: Array<{ time: string; event: string; detail: string }>;
};

const baseStages: Record<AgentStage, StageStatus> = { research: "done", evidence: "done", graph: "done", strategy: "done", negotiation: "done", review: "running" };

function buildAnalysis(config: DomainConfig, index: number): Analysis {
  const id = `AN-${String(index + 1).padStart(2, "0")}-${config.key.replace(/_/g, "-").toUpperCase()}`;
  return {
    id,
    domain: config.key,
    claimant: config.sampleClaimant,
    counterparty: config.sampleCounterparty,
    matter: config.sampleMatter,
    status: index < 3 ? "Action Ready" : index < 6 ? "Analyzing" : "Needs Evidence",
    updated: `${index + 2} min ago`,
    successProbability: 82 - index * 3,
    confidence: 88 - index * 2,
    policyMatch: 84 - index * 2,
    missingDocuments: [config.uploadSlots[1], "Signed escalation authorization", "Original timestamp proof"].slice(0, (index % 3) + 1),
    activeStage: "review",
    stages: index % 2 === 0 ? baseStages : { research: "done", evidence: "done", graph: "running", strategy: "waiting", negotiation: "waiting", review: "waiting" },
    documents: config.uploadSlots.map((slot, slotIndex) => ({ name: slot, type: `${config.shortLabel} PDF`, pages: 2 + slotIndex * 4, state: slotIndex < 2 ? "Indexed" : "Parsed" })),
    explanation: [
      { question: `Why does this ${config.entityLabel.toLowerCase()} need action?`, answer: config.sampleIssue, citations: [`${config.uploadSlots[1]} p.1`, config.sourcesLabel] },
      { question: "Which rules or terms apply?", answer: `The strongest path combines ${config.sourcesLabel} with the uploaded evidence and timeline.`, citations: [config.sourcesLabel, `${config.uploadSlots[0]} p.2`] },
      { question: "Recommended next steps", answer: `Collect ${config.uploadSlots.slice(0, 2).join(" and ")}, then use the ${config.actionName.toLowerCase()} workflow with citations.`, citations: ["Strategy Agent", "Evidence Agent"] },
    ],
    highlights: config.documentPreview.map((text, page) => ({ doc: config.uploadSlots[page % config.uploadSlots.length], label: page === 0 ? "Primary fact" : page === 1 ? "Contested term" : "Supporting evidence", type: page === 1 ? "waiting" : "coverage", page: page + 1, text })),
    graph: config.graphNodes.slice(0, -1).map((node, graphIndex) => ({ from: node, to: config.graphNodes[graphIndex + 1], type: graphIndex === 0 ? "connects to" : "supports" })),
    appealDraft: `Subject: ${config.actionName} for ${id}\n\nDear ${config.counterpartyLabel} Review Team,\n\nPlease review this ${config.entityLabel.toLowerCase()} concerning ${config.sampleMatter}. The available records indicate that the response does not fully address the applicable terms, evidence, and timeline.\n\nWe request a reasoned reassessment with reference to the cited documents and applicable rules.\n\nRegards,\nPROXY AI Analysis Desk`,
    timeline: [
      { time: "09:12", event: "Documents uploaded", detail: `${config.uploadSlots.join(", ")} entered analysis.` },
      { time: "09:18", event: "Research Agent completed", detail: `Qdrant searched ${config.sourcesLabel}.` },
      { time: "09:24", event: "Knowledge Graph built", detail: `Neo4j path connected ${config.graphNodes[0]} to ${config.graphNodes.at(-1)}.` },
      { time: "09:31", event: `${config.actionName} ready`, detail: "Negotiation Agent produced cited draft copy." },
    ],
  };
}

export const analyses: Analysis[] = domainRegistry.map(buildAnalysis);
export const demoAnalysis = analyses[0];
export const getDomainConfig = (domain: DomainKey) => domainRegistry.find((item) => item.key === domain) ?? domainRegistry[0];
export const getAnalysisById = (id: string) => analyses.find((item) => item.id.toLowerCase() === id.toLowerCase()) ?? demoAnalysis;

export const findDomainAnalysis = (domain: DomainKey) => analyses.find((item) => item.domain === domain) ?? demoAnalysis;

