import { create } from "zustand";

export type KGMode = "reasoning-trail" | "institution-intelligence" | "knowledge-footprint";

interface KnowledgeGraphState {
  mode: KGMode;
  setMode: (mode: KGMode) => void;

  // Reasoning Trail
  selectedCaseId: string | null;
  setSelectedCaseId: (id: string | null) => void;
  selectedNodeId: string | null;
  setSelectedNodeId: (id: string | null) => void;

  replayActive: boolean;
  replayIndex: number;
  replayPlaying: boolean;
  replaySpeed: number;
  startReplay: () => void;
  exitReplay: () => void;
  setReplayIndex: (index: number) => void;
  setReplayPlaying: (playing: boolean) => void;
  setReplaySpeed: (speed: number) => void;

  // Institution Intelligence
  selectedInstitutionNodeId: string | null;
  setSelectedInstitutionNodeId: (id: string | null) => void;
  // Deep-link from Institution Radar (/dashboard/institution-radar) into a
  // pre-filled, auto-run query -- consumed once by InstitutionMode then
  // cleared, so navigating back to this page later doesn't re-trigger it.
  pendingInstitutionQuery: { domain: string; institution: string } | null;
  setPendingInstitutionQuery: (query: { domain: string; institution: string } | null) => void;

  // Knowledge Footprint
  selectedDomain: string | null;
  setSelectedDomain: (domain: string | null) => void;
  revealCount: number;
  setRevealCount: (count: number) => void;
  scrubPlaying: boolean;
  setScrubPlaying: (playing: boolean) => void;

  // Cross-mode
  askAIOpen: boolean;
  setAskAIOpen: (open: boolean) => void;
  scriptedCaption: string | null;
  setScriptedCaption: (caption: string | null) => void;
}

/** Page-local UI state only (spec section 1: "Zustand — page-local UI
 * state"). Server data lives in TanStack Query (queries.ts); this store
 * never holds fetched data, only which mode/node/replay-step/timeline
 * position the user is currently looking at. */
export const useKnowledgeGraphStore = create<KnowledgeGraphState>((set) => ({
  mode: "reasoning-trail",
  setMode: (mode) => set({ mode, selectedNodeId: null, selectedInstitutionNodeId: null }),

  selectedCaseId: null,
  setSelectedCaseId: (id) =>
    set({ selectedCaseId: id, selectedNodeId: null, replayActive: false, replayPlaying: false, replayIndex: 0 }),
  selectedNodeId: null,
  setSelectedNodeId: (id) => set({ selectedNodeId: id }),

  replayActive: false,
  replayIndex: 0,
  replayPlaying: false,
  replaySpeed: 1,
  startReplay: () => set({ replayActive: true, replayIndex: 0, replayPlaying: true }),
  exitReplay: () => set({ replayActive: false, replayPlaying: false }),
  setReplayIndex: (index) => set({ replayIndex: index }),
  setReplayPlaying: (playing) => set({ replayPlaying: playing }),
  setReplaySpeed: (speed) => set({ replaySpeed: speed }),

  selectedInstitutionNodeId: null,
  setSelectedInstitutionNodeId: (id) => set({ selectedInstitutionNodeId: id }),
  pendingInstitutionQuery: null,
  setPendingInstitutionQuery: (query) => set({ pendingInstitutionQuery: query }),

  selectedDomain: null,
  setSelectedDomain: (domain) => set({ selectedDomain: domain }),
  revealCount: 0,
  setRevealCount: (count) => set({ revealCount: count }),
  scrubPlaying: false,
  setScrubPlaying: (playing) => set({ scrubPlaying: playing }),

  askAIOpen: false,
  setAskAIOpen: (open) => set({ askAIOpen: open }),
  scriptedCaption: null,
  setScriptedCaption: (caption) => set({ scriptedCaption: caption }),
}));
