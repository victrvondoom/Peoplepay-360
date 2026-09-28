"use client";

import { AppealsCenter } from "@/components/appeals/AppealsCenter";

export default function AppealsPage() {
  return (
    <div className="relative z-10 mx-auto flex min-h-screen max-w-[1600px] flex-col px-4 py-5 sm:px-6 lg:px-8">
      <header className="mb-4">
        <p className="text-xs uppercase tracking-[0.22em] text-cyan-200">PROXY Command Center</p>
        <h1 className="mt-2 bg-gradient-to-r from-white via-cyan-100 to-purple-200 bg-clip-text text-3xl font-semibold text-transparent sm:text-4xl">
          Appeals
        </h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-proxy-muted">
          Every appeal letter, complaint email, escalation note, and consumer complaint PROXY has generated for
          you -- real documents from the multi-agent negotiation engine, not templates.
        </p>
      </header>
      <AppealsCenter />
    </div>
  );
}
