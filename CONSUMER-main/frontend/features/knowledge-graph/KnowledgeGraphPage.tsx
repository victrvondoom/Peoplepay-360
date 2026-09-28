"use client";

import { useEffect } from "react";
import { Bot } from "lucide-react";
import { KnowledgeGraphQueryProvider } from "./QueryProvider";
import { useKnowledgeGraphStore } from "./store";
import { ModeSwitcher } from "./components/ModeSwitcher";
import { AskAIPanel } from "./components/AskAIPanel";
import { ReasoningTrailMode } from "./modes/reasoning-trail/ReasoningTrailMode";
import { InstitutionMode } from "./modes/institution-intelligence/InstitutionMode";
import { FootprintMode } from "./modes/knowledge-footprint/FootprintMode";

function PageShell() {
  const mode = useKnowledgeGraphStore((s) => s.mode);
  const setMode = useKnowledgeGraphStore((s) => s.setMode);
  const setSelectedCaseId = useKnowledgeGraphStore((s) => s.setSelectedCaseId);
  const setPendingInstitutionQuery = useKnowledgeGraphStore((s) => s.setPendingInstitutionQuery);
  const askAIOpen = useKnowledgeGraphStore((s) => s.askAIOpen);
  const setAskAIOpen = useKnowledgeGraphStore((s) => s.setAskAIOpen);

  // Deep-link from Notifications / other pages (?case=<id>) straight into
  // that case's Reasoning Trail, or from the Institution Radar
  // (?institution=<domain>|<name>) straight into a pre-filled, auto-run
  // Institution Intelligence query.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const caseId = params.get("case");
    const domain = params.get("domain");
    const institution = params.get("institution");
    if (caseId) {
      setSelectedCaseId(caseId);
      setMode("reasoning-trail");
      window.history.replaceState({}, "", window.location.pathname);
    } else if (domain && institution) {
      setPendingInstitutionQuery({ domain, institution });
      setMode("institution-intelligence");
      window.history.replaceState({}, "", window.location.pathname);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function openCase(caseId: string) {
    setSelectedCaseId(caseId);
    setMode("reasoning-trail");
  }

  return (
    <div className="flex min-h-[760px] flex-1 flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="font-mono text-xs uppercase tracking-[.22em] text-cyan-200">PROXY AI Reasoning</p>
          <h1 className="mt-2 text-3xl font-semibold sm:text-4xl">Knowledge Graph</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-proxy-muted">Watch how the AI actually reasons over the live graph -- one case at a time, across institutions, and across everything you&apos;ve ever filed.</p>
        </div>
        <button
          onClick={() => setAskAIOpen(true)}
          className="ask-orb inline-flex items-center gap-1.5 self-start rounded-lg px-3 py-2 text-xs font-medium text-black sm:self-auto"
        >
          <Bot className="size-3.5" /> Ask the AI Assistant
        </button>
        <style jsx>{`.ask-orb { background: radial-gradient(circle at 30% 30%, #5cf5ff, #00b8d9 55%, #6a3df0); }`}</style>
      </div>

      <ModeSwitcher />

      {mode === "reasoning-trail" && <ReasoningTrailMode />}
      {mode === "institution-intelligence" && <InstitutionMode />}
      {mode === "knowledge-footprint" && <FootprintMode onOpenCase={openCase} />}

      {askAIOpen && <AskAIPanel onClose={() => setAskAIOpen(false)} />}
    </div>
  );
}

/** Entry point for /dashboard/knowledge-graph. Everything under
 * features/knowledge-graph/ is self-contained: its own types, Zod schemas,
 * fetchers, TanStack Query client, Zustand store, and 3D scene logic. */
export function KnowledgeGraphPage() {
  return (
    <KnowledgeGraphQueryProvider>
      <PageShell />
    </KnowledgeGraphQueryProvider>
  );
}
