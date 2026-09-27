"use client";

import { AlertTriangle, RotateCw } from "lucide-react";

/** Error state (spec 9): short, specific message + retry, styled like the
 * rest of the app's error states -- never a blank/broken canvas. */
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex h-full min-h-[500px] flex-col items-center justify-center gap-3 px-6 text-center">
      <div className="grid size-12 place-items-center rounded-2xl border border-red-400/20 bg-red-400/10">
        <AlertTriangle className="size-5 text-red-300" />
      </div>
      <p className="text-sm font-semibold text-proxy-text">Couldn&apos;t load the graph</p>
      <p className="max-w-sm text-xs leading-5 text-proxy-tertiary">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[.04] px-3 py-1.5 text-xs text-proxy-muted hover:border-cyan-300/30 hover:text-cyan-100"
        >
          <RotateCw className="size-3.5" /> Retry
        </button>
      )}
    </div>
  );
}
