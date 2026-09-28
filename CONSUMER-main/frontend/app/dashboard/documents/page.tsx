"use client";

import { DocumentVault } from "@/components/documents/DocumentVault";

export default function DocumentsPage() {
  return (
    <div className="relative z-10 mx-auto flex min-h-screen max-w-[1600px] flex-col px-4 py-5 sm:px-6 lg:px-8">
      <header className="mb-4">
        <p className="text-xs uppercase tracking-[0.22em] text-cyan-200">PROXY Document Vault</p>
        <h1 className="mt-2 bg-gradient-to-r from-white via-cyan-100 to-purple-200 bg-clip-text text-3xl font-semibold text-transparent sm:text-4xl">
          Documents
        </h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-proxy-muted">
          Real upload, real text extraction, real classification, and real vector indexing -- every document you
          add here becomes searchable evidence the AI can cite.
        </p>
      </header>
      <DocumentVault />
    </div>
  );
}
