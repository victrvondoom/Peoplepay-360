import { NewAnalysisFlow } from "@/components/new-analysis/NewAnalysisFlow";

export default function Page() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
      <header className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[.22em] text-cyan-200">PROXY Command Center</p>
          <h1 className="mt-2 text-3xl font-semibold sm:text-4xl">New Multi-domain AI Analysis</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-proxy-muted">
            A single connected flow: pick a focus domain, add evidence or describe the problem, watch the real multi-agent pipeline run, then act on the results.
          </p>
        </div>
      </header>
      <NewAnalysisFlow />
    </div>
  );
}
