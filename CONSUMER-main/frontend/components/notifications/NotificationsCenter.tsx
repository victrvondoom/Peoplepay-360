"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Bell, Search, Loader2, PenLine, Upload, FileCheck2, ArrowUpCircle, Activity,
  CheckCheck, Radio, Download, ChevronDown, Bot,
} from "lucide-react";
import { getEvents, listAnalyses, type TimelineEvent, type AnalysisCase } from "@/lib/api-client";
import { domainTheme } from "@/components/chat/domain-theme";
import { PREF_KEYS, getPref } from "@/lib/preferences";

const EVENT_META: Record<string, { icon: typeof Activity; color: string; label: string }> = {
  case_created: { icon: PenLine, color: "#00e5ff", label: "Case created" },
  document_uploaded: { icon: Upload, color: "#37f29a", label: "Document uploaded" },
  appeal_drafted: { icon: FileCheck2, color: "#9b5cff", label: "Appeal drafted" },
  appeal_status_changed: { icon: ArrowUpCircle, color: "#ffc857", label: "Appeal status changed" },
  agent_run: { icon: Activity, color: "#ff6fb0", label: "Agent run" },
};

function eventMeta(type: string) {
  return EVENT_META[type] ?? { icon: Bell, color: "#a8b3c7", label: type };
}

function eventRoute(event: TimelineEvent): string {
  switch (event.event_type) {
    case "document_uploaded":
      return "/dashboard/documents";
    case "appeal_drafted":
    case "appeal_status_changed":
      return "/dashboard/appeals";
    case "case_created":
    case "agent_run":
      return `/dashboard/knowledge-graph?case=${encodeURIComponent(event.case_id)}`;
    default:
      return "/dashboard/analyses";
  }
}

function dayKey(iso: string | null): string {
  if (!iso) return "unknown";
  return new Date(iso).toDateString();
}

function groupLabel(iso: string | null): string {
  if (!iso) return "Earlier";
  const date = new Date(iso);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const eventDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const diffDays = Math.round((today.getTime() - eventDay.getTime()) / 86400000);
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return "This week";
  return "Earlier";
}

function timeAgo(iso: string | null): string {
  if (!iso) return "";
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

const LAST_SEEN_KEY = "proxy:notifications-last-seen";
const HEATMAP_WEEKS = 10;

export function NotificationsCenter() {
  const router = useRouter();
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [analyses, setAnalyses] = useState<AnalysisCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [domainFilter, setDomainFilter] = useState<string>("all");
  const [lastSeen, setLastSeen] = useState<string>("");
  // Initialize to the SSR-safe default and only read the real localStorage
  // value after mount -- reading it in the useState initializer runs during
  // both server and client render, and since localStorage only exists on
  // the client, a previously-saved "true" would make the client's first
  // render disagree with the server's, which React reports as a hydration
  // mismatch (and then throws away the whole server-rendered tree).
  const [live, setLive] = useState(false);
  useEffect(() => {
    setLive(getPref(PREF_KEYS.notificationsLive, "false") === "true");
  }, []);
  const [pulse, setPulse] = useState(false);
  const pollRef = useRef<number | null>(null);

  const domainByCaseId = useMemo(() => {
    const map = new Map<string, string>();
    for (const a of analyses) map.set(a.id, a.domains_involved[0] ?? a.domain);
    return map;
  }, [analyses]);

  async function loadInitial() {
    setLoading(true);
    try {
      const [eventsResult, analysesResult] = await Promise.all([getEvents(40), listAnalyses()]);
      setEvents(eventsResult);
      setAnalyses(analysesResult);
      setHasMore(eventsResult.length === 40);
    } catch {
      // keep whatever we last had on a transient failure
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setLastSeen(window.localStorage.getItem(LAST_SEEN_KEY) ?? new Date(0).toISOString());
    loadInitial();
  }, []);

  useEffect(() => {
    if (!live) {
      if (pollRef.current) window.clearInterval(pollRef.current);
      return;
    }
    pollRef.current = window.setInterval(async () => {
      try {
        const fresh = await getEvents(10);
        setEvents((current) => {
          const knownIds = new Set(current.map((e) => e.id));
          const newOnes = fresh.filter((e) => !knownIds.has(e.id));
          if (newOnes.length > 0) {
            setPulse(true);
            window.setTimeout(() => setPulse(false), 1200);
            return [...newOnes, ...current];
          }
          return current;
        });
      } catch {
        // transient failure -- keep polling
      }
    }, Number(getPref(PREF_KEYS.notificationsPollMs, "20000")));
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [live]);

  function toggleLive() {
    setLive((current) => {
      const next = !current;
      window.localStorage.setItem(PREF_KEYS.notificationsLive, String(next));
      return next;
    });
  }

  async function loadMore() {
    const oldest = events[events.length - 1];
    if (!oldest?.created_at) return;
    setLoadingMore(true);
    try {
      const more = await getEvents(30, oldest.created_at);
      setEvents((current) => [...current, ...more]);
      setHasMore(more.length === 30);
    } catch {
      // ignore
    } finally {
      setLoadingMore(false);
    }
  }

  function markAllRead() {
    const now = new Date().toISOString();
    setLastSeen(now);
    window.localStorage.setItem(LAST_SEEN_KEY, now);
  }

  function openEvent(event: TimelineEvent) {
    router.push(eventRoute(event));
  }

  function exportDigest() {
    const blob = new Blob([JSON.stringify(filtered, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `notifications-digest-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  const filtered = useMemo(() => {
    return events.filter((e) => {
      if (typeFilter !== "all" && e.event_type !== typeFilter) return false;
      if (domainFilter !== "all" && domainByCaseId.get(e.case_id) !== domainFilter) return false;
      if (search && !`${e.title} ${e.body ?? ""}`.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    });
  }, [events, typeFilter, domainFilter, search, domainByCaseId]);

  const unreadCount = useMemo(() => events.filter((e) => (e.created_at ?? "") > lastSeen).length, [events, lastSeen]);

  const grouped = useMemo(() => {
    const groups = new Map<string, TimelineEvent[]>();
    for (const event of filtered) {
      const label = groupLabel(event.created_at);
      const list = groups.get(label) ?? [];
      list.push(event);
      groups.set(label, list);
    }
    return Array.from(groups.entries());
  }, [filtered]);

  const heatmap = useMemo(() => {
    const counts = new Map<string, number>();
    for (const event of events) {
      if (!event.created_at) continue;
      const key = dayKey(event.created_at);
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    const days: Array<{ date: Date; count: number }> = [];
    const totalDays = HEATMAP_WEEKS * 7;
    for (let i = totalDays - 1; i >= 0; i--) {
      const date = new Date();
      date.setDate(date.getDate() - i);
      days.push({ date, count: counts.get(date.toDateString()) ?? 0 });
    }
    return days;
  }, [events]);

  const maxHeat = Math.max(1, ...heatmap.map((d) => d.count));
  const eventTypes = useMemo(() => Array.from(new Set(events.map((e) => e.event_type))), [events]);
  const involvedDomains = useMemo(() => Array.from(new Set(Array.from(domainByCaseId.values()))), [domainByCaseId]);

  return (
    <div className="flex min-h-[720px] flex-1 flex-col gap-4">
      {/* Hero: unread + live toggle + heatmap */}
      <section className="rounded-2xl border border-white/10 bg-glass p-4 backdrop-blur-2xl sm:p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="relative grid size-10 place-items-center rounded-xl border border-cyan-300/30 bg-cyan-300/10">
              <Bell className="size-4.5 text-cyan-200" />
              {unreadCount > 0 && (
                <span className="absolute -right-1.5 -top-1.5 grid min-w-[18px] place-items-center rounded-full bg-red-400 px-1 text-[10px] font-semibold text-black">
                  {unreadCount > 99 ? "99+" : unreadCount}
                </span>
              )}
            </div>
            <div>
              <p className="text-sm font-semibold text-proxy-text">Live activity feed</p>
              <p className="text-[11px] text-proxy-tertiary">{unreadCount} unread &middot; {events.length} loaded</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={toggleLive}
              className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs ${
                live ? "border-green-300/30 bg-green-300/10 text-green-100" : "border-white/10 text-proxy-muted hover:border-white/25"
              }`}
            >
              <Radio className={`size-3.5 ${live ? "animate-pulse" : ""}`} /> {live ? "Live" : "Go live"}
            </button>
            <button onClick={markAllRead} className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs text-proxy-muted hover:border-cyan-300/30 hover:text-cyan-100">
              <CheckCheck className="size-3.5" /> Mark all read
            </button>
            <button onClick={exportDigest} className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs text-proxy-muted hover:border-cyan-300/30 hover:text-cyan-100">
              <Download className="size-3.5" /> Export digest
            </button>
          </div>
        </div>

        {/* Activity heatmap */}
        <div className={`overflow-x-auto rounded-xl border border-white/5 bg-black/20 p-3 transition-all ${pulse ? "ring-1 ring-cyan-300/50" : ""}`}>
          <div className="mb-2 flex items-center justify-between text-[10px] uppercase tracking-[.16em] text-proxy-tertiary">
            <span>Activity, last {HEATMAP_WEEKS} weeks</span>
            <span>{events.length} events loaded</span>
          </div>
          <div className="grid grid-flow-col gap-1" style={{ gridTemplateRows: "repeat(7, 1fr)" }}>
            {heatmap.map((d, i) => {
              const intensity = d.count === 0 ? 0 : Math.min(1, d.count / maxHeat);
              return (
                <div
                  key={i}
                  title={`${d.date.toLocaleDateString()}: ${d.count} event${d.count === 1 ? "" : "s"}`}
                  className="size-3 rounded-[3px]"
                  style={{ backgroundColor: intensity === 0 ? "rgba(255,255,255,.06)" : `rgba(0,229,255,${0.15 + intensity * 0.75})` }}
                />
              );
            })}
          </div>
        </div>
      </section>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-white/10 bg-glass p-3 backdrop-blur-2xl">
        <div className="relative min-w-[180px] flex-1">
          <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-proxy-tertiary" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search notifications..."
            className="w-full rounded-lg border border-white/10 bg-black/30 py-1.5 pl-8 pr-2 text-xs text-proxy-text outline-none placeholder:text-proxy-tertiary focus:border-cyan-300/40"
          />
        </div>
        <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className="rounded-lg border border-white/10 bg-black/30 px-2 py-1.5 text-xs text-proxy-text outline-none">
          <option value="all">All types</option>
          {eventTypes.map((type) => <option key={type} value={type}>{eventMeta(type).label}</option>)}
        </select>
        {involvedDomains.length > 0 && (
          <select value={domainFilter} onChange={(e) => setDomainFilter(e.target.value)} className="rounded-lg border border-white/10 bg-black/30 px-2 py-1.5 text-xs text-proxy-text outline-none">
            <option value="all">All domains</option>
            {involvedDomains.map((d) => <option key={d} value={d}>{domainTheme(d).label}</option>)}
          </select>
        )}
        <span className="ml-auto text-xs text-proxy-tertiary">{filtered.length} shown</span>
      </div>

      {/* Timeline */}
      {loading ? (
        <div className="flex h-64 items-center justify-center"><Loader2 className="size-6 animate-spin text-cyan-200" /></div>
      ) : filtered.length === 0 ? (
        <div className="flex h-64 flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-white/10 text-center">
          <Bell className="size-8 text-proxy-tertiary" />
          <p className="text-sm text-proxy-tertiary">{events.length === 0 ? "No activity yet -- ask the AI Assistant a question to get started." : "No notifications match your filters."}</p>
          {events.length === 0 && (
            <button onClick={() => router.push("/dashboard/assistant")} className="inline-flex items-center gap-1.5 rounded-lg border border-cyan-300/30 bg-cyan-300/10 px-3 py-1.5 text-xs text-cyan-100">
              <Bot className="size-3.5" /> Ask the AI Assistant
            </button>
          )}
        </div>
      ) : (
        <div className="flex-1 space-y-5">
          {grouped.map(([label, items]) => (
            <div key={label}>
              <p className="mb-2 px-1 text-[10px] font-medium uppercase tracking-[.18em] text-proxy-tertiary">{label}</p>
              <div className="space-y-2">
                {items.map((event) => {
                  const meta = eventMeta(event.event_type);
                  const Icon = meta.icon;
                  const unread = (event.created_at ?? "") > lastSeen;
                  const eventDomain = domainByCaseId.get(event.case_id);
                  return (
                    <button
                      key={event.id}
                      onClick={() => openEvent(event)}
                      className={`flex w-full items-start gap-3 rounded-xl border p-3 text-left transition-colors hover:border-cyan-300/25 ${
                        unread ? "border-cyan-300/20 bg-cyan-300/[0.03]" : "border-white/5 bg-black/20"
                      }`}
                    >
                      <div className="relative mt-0.5 grid size-8 shrink-0 place-items-center rounded-full border border-white/10" style={{ backgroundColor: `${meta.color}15` }}>
                        <Icon className="size-3.5" style={{ color: meta.color }} />
                        {unread && <span className="absolute -right-0.5 -top-0.5 size-2 rounded-full bg-cyan-300" />}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <p className="truncate text-sm text-proxy-text">{event.title}</p>
                          {eventDomain && (
                            <span className="shrink-0 rounded-full px-1.5 py-0.5 text-[9px]" style={{ backgroundColor: `${domainTheme(eventDomain).color}1a`, color: domainTheme(eventDomain).color }}>
                              {domainTheme(eventDomain).label}
                            </span>
                          )}
                        </div>
                        {event.body && <p className="mt-0.5 line-clamp-1 text-xs text-proxy-tertiary">{event.body}</p>}
                        <p className="mt-1 text-[10px] text-proxy-tertiary">{event.actor} &middot; {timeAgo(event.created_at)}</p>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}

          {hasMore && (
            <button
              onClick={loadMore}
              disabled={loadingMore}
              className="mx-auto flex items-center gap-1.5 rounded-lg border border-white/10 px-4 py-2 text-xs text-proxy-muted hover:border-cyan-300/30 hover:text-cyan-100"
            >
              {loadingMore ? <Loader2 className="size-3.5 animate-spin" /> : <ChevronDown className="size-3.5" />} Load more
            </button>
          )}
        </div>
      )}
    </div>
  );
}
