"use client";

import { useEffect, useState } from "react";
import { getSystemHealth, type SystemHealth } from "@/lib/api-client";

interface HealthState {
  health: SystemHealth | null;
  latencyMs: number | null;
  loading: boolean;
  error: string | null;
  checkedAt: number | null;
}

// Single real call to the backend's /health endpoint, shared by the hero's
// credibility line, the live demo panel, and the metrics section -- no
// fabricated numbers anywhere on this page, only what the backend reports.
export function useSystemHealth() {
  const [state, setState] = useState<HealthState>({
    health: null,
    latencyMs: null,
    loading: true,
    error: null,
    checkedAt: null,
  });

  useEffect(() => {
    let cancelled = false;
    getSystemHealth()
      .then(({ health, latencyMs }) => {
        if (cancelled) return;
        setState({ health, latencyMs, loading: false, error: null, checkedAt: Date.now() });
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setState({ health: null, latencyMs: null, loading: false, error: err.message, checkedAt: Date.now() });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}
