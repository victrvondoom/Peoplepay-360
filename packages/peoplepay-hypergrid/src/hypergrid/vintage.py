"""Bitemporal observation store.

Each observation has an *observation period* (what it measures) and a *knowledge time*
(when it became known). A revision is a new record for the same (series, period) with a later
knowledge time; nothing is overwritten. Every read is performed against a ``Snapshot`` pinned
to one knowledge time, so a whole batch of decisions sees one consistent view of the world even
while revisions arrive. This is the standard "vintage" (real-time dataset) idea from
macroeconomics (e.g. ALFRED); the only thing added here is making it a first-class compute input.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass
from typing import Iterable

ORIGINS = ("SYNTHETIC", "HISTORICAL", "DELAYED", "LIVE")


@dataclass(frozen=True)
class Observation:
    series: str
    period: int
    value: float
    known_at: float                 # knowledge time (when published / learned)
    source_id: str = "unknown"
    root_id: str = "unknown"        # provenance root, for ECHO-style source de-duplication
    quality: str = "ok"             # ok | stale | contradicted
    origin: str = "SYNTHETIC"       # never present synthetic data as real
    ingested_at: float = 0.0

    def fingerprint(self) -> int:
        """What downstream results depend on: the value and its quality, not when it was learned.
        A republished identical value therefore invalidates nothing."""
        return hash((self.value, self.quality))


class VintageStore:
    def __init__(self) -> None:
        self._data: dict[tuple[str, int], list[Observation]] = {}
        self._series_ids: dict[str, int] = {}
        self._series_names: list[str] = []

    # -- series interning (compact int keys for dependency indexes)
    def series_index(self, series: str) -> int:
        i = self._series_ids.get(series)
        if i is None:
            i = self._series_ids[series] = len(self._series_names)
            self._series_names.append(series)
        return i

    def series_name(self, idx: int) -> str:
        return self._series_names[idx]

    KEY_SPAN = 1 << 20      # period must be < KEY_SPAN

    def key(self, series: str, period: int) -> int:
        if not 0 <= period < self.KEY_SPAN:
            raise ValueError("period out of range")
        return self.series_index(series) * self.KEY_SPAN + period

    def key_parts(self, key: int) -> tuple[str, int]:
        return self._series_names[key // self.KEY_SPAN], key % self.KEY_SPAN

    # -- writes
    def append(self, obs: Observation) -> Observation:
        k = (obs.series, obs.period)
        versions = self._data.setdefault(k, [])
        if versions and obs.known_at <= versions[-1].known_at:
            raise ValueError("a revision must have a later knowledge time than the existing vintage")
        versions.append(obs)
        self.series_index(obs.series)
        return obs

    def extend(self, observations: Iterable[Observation]) -> None:
        for o in observations:
            self.append(o)

    # -- reads
    def as_of(self, series: str, period: int, t: float) -> Observation | None:
        versions = self._data.get((series, period))
        if not versions:
            return None
        i = bisect.bisect_right([v.known_at for v in versions], t)
        return versions[i - 1] if i else None

    def vintages(self, series: str, period: int) -> list[Observation]:
        return list(self._data.get((series, period), []))

    def snapshot(self, t: float) -> "Snapshot":
        return Snapshot(self, t)

    def series_names(self) -> list[str]:
        return list(self._series_names)


class Snapshot:
    """A read view pinned to one knowledge time."""

    def __init__(self, store: VintageStore, t: float):
        self.store, self.t = store, t

    def read(self, series: str, period: int) -> Observation | None:
        return self.store.as_of(series, period, self.t)


class TrackingReader:
    """Records exactly which (series, period) keys a computation read, and the fingerprint it saw.
    Dependencies are *observed*, not declared, so they cannot drift out of date with the code."""

    def __init__(self, snapshot: Snapshot):
        self.snapshot = snapshot
        self.seen: dict[int, int] = {}      # key -> fingerprint (0 for "absent")

    def read(self, series: str, period: int) -> Observation | None:
        obs = self.snapshot.read(series, period)
        self.seen[self.snapshot.store.key(series, period)] = obs.fingerprint() if obs else 0
        return obs
