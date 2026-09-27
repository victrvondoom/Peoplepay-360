"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Bot, Loader2, Send, X } from "lucide-react";
import { useKnowledgeGraphStore } from "../store";
import { askAboutCase } from "../api";

interface Exchange {
  question: string;
  answer: string;
}

/** "Ask the AI Assistant" cross-mode integration (spec 8). Slide-over chat
 * that queries the currently focused case; the answer becomes a caption and
 * the AI's cited node is focused in the scene, reusing the exact visual
 * language as Reasoning Replay. Scoped to whatever case is active in
 * Reasoning Trail mode -- if none is selected yet, it asks the user to pick
 * one first rather than answering with no graph context. */
export function AskAIPanel({ onClose }: { onClose: () => void }) {
  const selectedCaseId = useKnowledgeGraphStore((s) => s.selectedCaseId);
  const setMode = useKnowledgeGraphStore((s) => s.setMode);
  const setSelectedNodeId = useKnowledgeGraphStore((s) => s.setSelectedNodeId);
  const [message, setMessage] = useState("");
  const [history, setHistory] = useState<Exchange[]>([]);

  const mutation = useMutation({
    mutationFn: (q: string) => askAboutCase(selectedCaseId as string, q),
    onSuccess: (data, question) => {
      setHistory((h) => [...h, { question, answer: data.answer }]);
      setMessage("");
      // Cross-mode integration: bring the case graph into view with the
      // case node focused, so the chat answer and the graph feel like one
      // system rather than two disconnected panels (spec 8).
      setMode("reasoning-trail");
      setSelectedNodeId("case");
    },
  });

  function submit() {
    if (!message.trim() || !selectedCaseId || mutation.isPending) return;
    mutation.mutate(message.trim());
  }

  return (
    <div className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-white/10 bg-[#050608]/97 backdrop-blur-2xl">
      <div className="flex items-center justify-between border-b border-white/10 p-4">
        <div className="flex items-center gap-2">
          <Bot className="size-4 text-cyan-200" />
          <p className="text-sm font-semibold text-proxy-text">Ask the AI Assistant</p>
        </div>
        <button onClick={onClose} className="grid size-7 place-items-center rounded-lg text-proxy-tertiary hover:bg-white/10 hover:text-proxy-text">
          <X className="size-4" />
        </button>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {!selectedCaseId ? (
          <p className="text-xs text-proxy-tertiary">Select a case in Reasoning Trail mode first, then ask a natural-language question about it here.</p>
        ) : history.length === 0 ? (
          <p className="text-xs text-proxy-tertiary">Ask a question about the current case -- e.g. &quot;Why did this claim get denied?&quot;</p>
        ) : (
          history.map((ex, i) => (
            <div key={i} className="space-y-2">
              <p className="rounded-lg bg-white/[.04] px-3 py-2 text-xs text-proxy-text">{ex.question}</p>
              <p className="rounded-lg border border-cyan-300/15 bg-cyan-300/5 px-3 py-2 text-xs leading-5 text-proxy-muted">{ex.answer}</p>
            </div>
          ))
        )}
        {mutation.isError && <p className="text-xs text-red-300">{(mutation.error as Error).message}</p>}
      </div>

      <div className="flex items-center gap-2 border-t border-white/10 p-3">
        <input
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          disabled={!selectedCaseId}
          placeholder={selectedCaseId ? "Ask about this case..." : "Select a case first..."}
          className="flex-1 rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-xs text-proxy-text outline-none placeholder:text-proxy-tertiary focus:border-cyan-300/40 disabled:opacity-40"
        />
        <button onClick={submit} disabled={!selectedCaseId || !message.trim() || mutation.isPending} className="grid size-9 shrink-0 place-items-center rounded-lg bg-cyan-300/15 text-cyan-100 hover:bg-cyan-300/25 disabled:opacity-30">
          {mutation.isPending ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
        </button>
      </div>
    </div>
  );
}
