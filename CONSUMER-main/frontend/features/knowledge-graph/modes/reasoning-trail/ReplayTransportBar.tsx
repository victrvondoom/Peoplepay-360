"use client";

import { Pause, Play, SkipBack, SkipForward, Sparkles, X } from "lucide-react";

export interface ReplayStepView {
  index: number;
  agent: string;
  color: string;
  caption: string;
}

const SPEEDS = [0.5, 1, 2];

/** Reasoning Replay's transport bar (spec 5.3) -- the flagship interaction
 * on the whole page. Scrubs through the REAL agent_trace sequence exposed
 * by GET /graph/case/{id}/reasoning-trail. */
export function ReplayTransportBar({
  steps, index, playing, speed, onPlayPause, onStepBack, onStepForward, onScrub, onSpeedChange, onExit,
}: {
  steps: ReplayStepView[];
  index: number;
  playing: boolean;
  speed: number;
  onPlayPause: () => void;
  onStepBack: () => void;
  onStepForward: () => void;
  onScrub: (index: number) => void;
  onSpeedChange: (speed: number) => void;
  onExit: () => void;
}) {
  if (steps.length === 0) return null;
  const current = steps[index];

  return (
    <div className="flex flex-col gap-2 rounded-2xl border border-cyan-300/20 bg-black/55 p-3 backdrop-blur-2xl">
      <div className="flex items-center gap-2">
        <span className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 font-mono text-[10px] font-medium" style={{ backgroundColor: `${current.color}22`, color: current.color }}>
          <Sparkles className="size-3" /> {current.agent}
        </span>
        <p className="min-w-0 flex-1 truncate text-[11px] text-proxy-muted">{current.caption}</p>
        <span className="shrink-0 font-mono text-[10px] text-proxy-tertiary">Step {index + 1} / {steps.length}</span>
        <button onClick={onExit} title="Exit reasoning replay" className="grid size-6 shrink-0 place-items-center rounded-md text-proxy-tertiary hover:bg-white/10 hover:text-proxy-text">
          <X className="size-3.5" />
        </button>
      </div>

      <input
        type="range"
        min={0}
        max={Math.max(steps.length - 1, 0)}
        step={1}
        value={index}
        onChange={(e) => onScrub(Number(e.target.value))}
        className="replay-scrub w-full"
        aria-label="Reasoning replay progress"
      />

      <div className="flex items-center gap-1.5">
        <button onClick={onStepBack} disabled={index === 0} className="grid size-7 place-items-center rounded-lg border border-white/10 bg-white/[.03] text-proxy-muted hover:border-cyan-300/30 hover:text-cyan-100 disabled:opacity-30" aria-label="Previous step">
          <SkipBack className="size-3.5" />
        </button>
        <button onClick={onPlayPause} className="grid size-8 place-items-center rounded-lg border border-cyan-300/30 bg-cyan-300/10 text-cyan-100 hover:bg-cyan-300/20" aria-label={playing ? "Pause replay" : "Play replay"}>
          {playing ? <Pause className="size-4" /> : <Play className="size-4" />}
        </button>
        <button onClick={onStepForward} disabled={index === steps.length - 1} className="grid size-7 place-items-center rounded-lg border border-white/10 bg-white/[.03] text-proxy-muted hover:border-cyan-300/30 hover:text-cyan-100 disabled:opacity-30" aria-label="Next step">
          <SkipForward className="size-3.5" />
        </button>
        <div className="ml-auto flex items-center gap-1 rounded-lg border border-white/10 bg-white/[.02] p-0.5">
          {SPEEDS.map((s) => (
            <button key={s} onClick={() => onSpeedChange(s)} className={`rounded-md px-1.5 py-1 font-mono text-[10px] font-medium transition-colors ${speed === s ? "bg-cyan-300/20 text-cyan-100" : "text-proxy-tertiary hover:text-proxy-muted"}`}>
              {s}x
            </button>
          ))}
        </div>
      </div>

      <style jsx>{`
        .replay-scrub { -webkit-appearance: none; appearance: none; height: 4px; border-radius: 999px; background: linear-gradient(90deg, #00e5ff ${(index / Math.max(steps.length - 1, 1)) * 100}%, rgba(255,255,255,.08) 0); outline: none; }
        .replay-scrub::-webkit-slider-thumb { -webkit-appearance: none; appearance: none; width: 13px; height: 13px; border-radius: 50%; background: #00e5ff; box-shadow: 0 0 10px rgba(0,229,255,.7); cursor: pointer; }
        .replay-scrub::-moz-range-thumb { width: 13px; height: 13px; border: none; border-radius: 50%; background: #00e5ff; box-shadow: 0 0 10px rgba(0,229,255,.7); cursor: pointer; }
      `}</style>
    </div>
  );
}
