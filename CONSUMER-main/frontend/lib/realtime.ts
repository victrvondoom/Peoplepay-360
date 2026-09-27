import { API_BASE, getAnalysis } from "./api-client";
import type { Analysis } from "./proxy-analysis-data";

export type RealtimeMode = "websocket" | "sse" | "polling" | "offline";
export type RealtimeHandlers = { onMode?: (mode: RealtimeMode) => void; onUpdate: (analysis: Analysis) => void; onError?: (message: string) => void };

export function connectAnalysisRealtime(id: string, handlers: RealtimeHandlers) {
  let stopped = false;
  let pollTimer: ReturnType<typeof setInterval> | undefined;
  const wsUrl = API_BASE.replace(/^http/, "ws") + `/case/${id}/ws`;

  function startPolling() {
    handlers.onMode?.("polling");
    async function tick() {
      // getAnalysis() is a legacy bridge that returns the raw /case/{id}
      // response as Record<string, unknown> -- this whole polling path only
      // ever fed the pre-migration mock Analysis shape, so bridge the type.
      try { handlers.onUpdate((await getAnalysis(id)) as unknown as Analysis); }
      catch { handlers.onError?.("Polling failed. Showing offline cache."); handlers.onMode?.("offline"); }
    }
    void tick();
    pollTimer = setInterval(tick, 3000);
  }

  try {
    const socket = new WebSocket(wsUrl);
    const fallback = setTimeout(() => { if (socket.readyState !== WebSocket.OPEN) socket.close(); }, 1200);
    socket.onopen = () => { clearTimeout(fallback); if (!stopped) handlers.onMode?.("websocket"); };
    socket.onmessage = (event) => { try { handlers.onUpdate(JSON.parse(event.data) as Analysis); } catch { handlers.onError?.("Malformed realtime update ignored."); } };
    socket.onerror = () => undefined;
    socket.onclose = () => {
      clearTimeout(fallback);
      if (stopped) return;
      try {
        const events = new EventSource(`${API_BASE}/case/${id}/events`);
        const sseFallback = setTimeout(() => { events.close(); startPolling(); }, 1200);
        events.onopen = () => { clearTimeout(sseFallback); handlers.onMode?.("sse"); };
        events.onmessage = (event) => { try { handlers.onUpdate(JSON.parse(event.data) as Analysis); } catch { handlers.onError?.("Malformed SSE update ignored."); } };
        events.onerror = () => { events.close(); clearTimeout(sseFallback); if (!pollTimer) startPolling(); };
      } catch { startPolling(); }
    };
    return () => { stopped = true; clearInterval(pollTimer); socket.close(); };
  } catch {
    startPolling();
    return () => { stopped = true; clearInterval(pollTimer); };
  }
}
