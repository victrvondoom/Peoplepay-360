"use client";

import type { LucideIcon } from "lucide-react";

/** Empty state (spec 9): clear copy + a concrete next action, never a bare
 * void with no guidance. */
export function EmptyState({
  icon: Icon, title, description, action,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex h-full min-h-[500px] flex-col items-center justify-center gap-3 px-6 text-center">
      <div className="grid size-12 place-items-center rounded-2xl border border-white/10 bg-white/[.03]">
        <Icon className="size-5 text-cyan-200" />
      </div>
      <p className="text-sm font-semibold text-proxy-text">{title}</p>
      <p className="max-w-sm text-xs leading-5 text-proxy-tertiary">{description}</p>
      {action}
    </div>
  );
}
