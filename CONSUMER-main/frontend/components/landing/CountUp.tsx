"use client";

import { useEffect, useState } from "react";

// Counts up once from 0 to a real fetched value on mount/change -- not an
// ever-incrementing fake counter. If the value is still loading, renders
// the placeholder instead of a made-up number.
export default function CountUp({ value, durationMs = 900 }: { value: number | null; durationMs?: number }) {
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    if (value == null) return;
    const start = performance.now();
    const from = 0;
    let raf: number;
    const tick = (now: number) => {
      const t = Math.min((now - start) / durationMs, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplay(Math.round(from + (value - from) * eased));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, durationMs]);

  if (value == null) return <span style={{ opacity: 0.4 }}>--</span>;
  return <span>{display.toLocaleString("en-IN")}</span>;
}
