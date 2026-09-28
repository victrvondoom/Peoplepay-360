/** Pure layout math for the 3D scenes. Deterministic functions of
 * (ids, index) rather than a running physics sim, so a mode's shape is
 * stable across re-renders and cheap to memoize. */

export type Vec3 = [number, number, number];

const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

/** Reasoning Trail: the case sits at the origin, everything else spirals
 * outward in visitation order, so the graph's shape hints at the sequence
 * before Replay even starts (spec 5.2). */
export function spiralLayout(ids: string[], focalId?: string): Map<string, Vec3> {
  const positions = new Map<string, Vec3>();
  let i = 0;
  for (const id of ids) {
    if (id === focalId) {
      positions.set(id, [0, 0, 0]);
      continue;
    }
    const idx = i++;
    const radius = 2.1 + Math.sqrt(idx) * 1.5;
    const angle = idx * GOLDEN_ANGLE;
    const y = Math.sin(idx * 0.75) * 0.7;
    positions.set(id, [Math.cos(angle) * radius, y, Math.sin(angle) * radius]);
  }
  return positions;
}

/** Institution Intelligence: one gravitational cluster per queried
 * institution, offset along X so density/size/color-mix compares at a
 * glance (spec 6.2). */
export function clusterLayout(ids: string[], centerId: string, center: Vec3): Map<string, Vec3> {
  const positions = new Map<string, Vec3>();
  let i = 0;
  for (const id of ids) {
    if (id === centerId) {
      positions.set(id, center);
      continue;
    }
    const idx = i++;
    const radius = 1.5 + Math.sqrt(idx) * 1.1;
    const angle = idx * GOLDEN_ANGLE;
    const y = Math.cos(idx * 0.6) * 0.55;
    positions.set(id, [center[0] + Math.cos(angle) * radius, center[1] + y, center[2] + Math.sin(angle) * radius]);
  }
  return positions;
}

export function lerpVec3(a: Vec3, b: Vec3, t: number): Vec3 {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
}

/** My Knowledge Footprint: orbit radius = recency rank (closest = most
 * recently active), planet size = case-count share of the max. Positions
 * themselves are computed per-frame (continuous orbital motion), so this
 * only returns the static assignment each planet orbits by. */
export function orreryAssignment<T extends { mostRecentAt: string | null; caseCount: number }>(
  domains: T[]
): Array<T & { orbitRadius: number; planetScale: number; angle0: number }> {
  const sorted = [...domains].sort((a, b) => {
    if (!a.mostRecentAt && !b.mostRecentAt) return 0;
    if (!a.mostRecentAt) return 1;
    if (!b.mostRecentAt) return -1;
    return new Date(b.mostRecentAt).getTime() - new Date(a.mostRecentAt).getTime();
  });
  const maxCases = Math.max(1, ...domains.map((d) => d.caseCount));
  return sorted.map((d, i) => ({
    ...d,
    orbitRadius: 2.7 + i * 1.5,
    planetScale: 0.3 + (d.caseCount / maxCases) * 0.4,
    angle0: (i / Math.max(sorted.length, 1)) * Math.PI * 2,
  }));
}

export function hashPhase(key: string): number {
  let hash = 0;
  for (let i = 0; i < key.length; i++) hash = (hash * 31 + key.charCodeAt(i)) % 1000;
  return hash / 1000;
}
