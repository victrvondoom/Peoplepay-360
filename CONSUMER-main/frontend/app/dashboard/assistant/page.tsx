"use client";

import { AssistantChat } from "@/components/chat/AssistantChat";

export default function AssistantPage() {
  return (
    <div className="relative z-10 mx-auto flex h-[100dvh] max-w-[1600px] flex-col px-4 py-5 sm:px-6 lg:px-8">
      <header className="mb-4 shrink-0">
        <p className="text-xs uppercase tracking-[0.22em] text-cyan-200">PROXY Command Center</p>
        <h1 className="mt-2 bg-gradient-to-r from-white via-cyan-100 to-purple-200 bg-clip-text text-3xl font-semibold text-transparent sm:text-4xl">
          AI Assistant
        </h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-proxy-muted">
          A multi-agent assistant that classifies your question across all 8 domains, retrieves and scores real
          evidence, and shows exactly which agents ran -- not a black box.
        </p>
      </header>
      <AssistantChat />
    </div>
  );
}
