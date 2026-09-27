"use client";

import { Clock, Pause, Play, RotateCcw } from "lucide-react";

interface TimelineEventLite {
  title: string;
  createdAt: string;
}

/** Timeline scrubber (spec 7.2) -- "the single highest-value, lowest-effort
 * novel element on the whole page." Dragging reveals cases in the order
 * they actually happened, so the orrery visibly grows. */
export function TimelineScrubber({
  events, revealCount, playing, onScrub, onPlayPause, onReset,
}: {
  events: TimelineEventLite[];
  revealCount: number;
  playing: boolean;
  onScrub: (count: number) => void;
  onPlayPause: () => void;
  onReset: () => void;
}) {
  if (events.length === 0) return null;
  const current = events[Math.max(0, Math.min(revealCount, events.length) - 1)];
  const atEnd = revealCount >= events.length;

  return (
    <div className="flex flex-col gap-2 rounded-2xl border border-amber-300/20 bg-black/55 p-3 backdrop-blur-2xl">
      <div className="flex items-center gap-2">
        <Clock className="size-3.5 text-amber-200" />
        <p className="min-w-0 flex-1 truncate text-[11px] text-proxy-muted">
          {revealCount === 0 ? "Drag to replay your case history" : `${current.title} · ${new Date(current.createdAt).toLocaleDateString()}`}
        </p>
        <span className="shrink-0 font-mono text-[10px] text-proxy-tertiary">{revealCount} / {events.length} cases</span>
      </div>
      <input
        type="range" min={0} max={events.length} step={1} value={revealCount}
        onChange={(e) => onScrub(Number(e.target.value))}
        className="orrery-scrub w-full"
        aria-label="Case history timeline"
      />
      <div className="flex items-center gap-1.5">
        <button onClick={onPlayPause} className="grid size-8 place-items-center rounded-lg border border-amber-300/30 bg-amber-300/10 text-amber-100 hover:bg-amber-300/20" aria-label={playing ? "Pause timeline" : "Play timeline growth"}>
          {playing ? <Pause className="size-4" /> : <Play className="size-4" />}
        </button>
        <button onClick={onReset} disabled={atEnd} className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[.03] px-2.5 py-1.5 text-[11px] text-proxy-muted hover:border-amber-300/30 hover:text-amber-100 disabled:opacity-30">
          <RotateCcw className="size-3" /> Jump to today
        </button>
      </div>
      <style jsx>{`
        .orrery-scrub { -webkit-appearance: none; appearance: none; height: 4px; border-radius: 999px; background: linear-gradient(90deg, #ffc857 ${events.length ? (revealCount / events.length) * 100 : 0}%, rgba(255,255,255,.08) 0); outline: none; }
        .orrery-scrub::-webkit-slider-thumb { -webkit-appearance: none; appearance: none; width: 13px; height: 13px; border-radius: 50%; background: #ffc857; box-shadow: 0 0 10px rgba(255,200,87,.7); cursor: pointer; }
        .orrery-scrub::-moz-range-thumb { width: 13px; height: 13px; border: none; border-radius: 50%; background: #ffc857; box-shadow: 0 0 10px rgba(255,200,87,.7); cursor: pointer; }
      `}</style>
    </div>
  );
}
