"use client";

import { Landmark, Orbit, Waypoints } from "lucide-react";
import { useKnowledgeGraphStore, type KGMode } from "../store";

const MODES: Array<{ id: KGMode; label: string; icon: typeof Waypoints }> = [
  { id: "reasoning-trail", label: "Reasoning Trail", icon: Waypoints },
  { id: "institution-intelligence", label: "Institution Intelligence", icon: Landmark },
  { id: "knowledge-footprint", label: "My Knowledge Footprint", icon: Orbit },
];

/** Three-way pill switcher (spec 2) -- three genuinely different visual
 * experiences, not tabs on one graph. Active mode gets the signature accent
 * glow. */
export function ModeSwitcher() {
  const mode = useKnowledgeGraphStore((s) => s.mode);
  const setMode = useKnowledgeGraphStore((s) => s.setMode);

  return (
    <div className="flex flex-wrap items-center gap-1.5 overflow-x-auto rounded-2xl border border-white/10 bg-glass p-1.5 backdrop-blur-2xl sm:gap-2">
      {MODES.map((m) => {
        const active = mode === m.id;
        return (
          <button
            key={m.id}
            onClick={() => setMode(m.id)}
            className={`inline-flex shrink-0 items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-medium transition-colors ${
              active ? "bg-cyan-300/15 text-cyan-100 shadow-[0_0_18px_rgba(0,229,255,.25)]" : "text-proxy-muted hover:bg-white/5"
            }`}
          >
            <m.icon className="size-3.5" /> {m.label}
          </button>
        );
      })}
    </div>
  );
}
