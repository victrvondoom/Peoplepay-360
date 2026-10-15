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
import hashlib
import struct
from dataclasses import dataclass
from typing import Iterable

from .validation import InvalidInput, finite

ORIGINS = ("SYNTHETIC", "HISTORICAL", "DELAYED", "LIVE")

#: Largest period index a key may carry. Periods are small integers (years, months, ticks).
PERIOD_LIMIT = 1 << 20

#: A dependency key: (series name, period). Both parts are stable values, so a key means the same thing in
#: every process, on every machine, and in every run. (It was once an index into a per-process intern
#: table, which meant the same integer named different series in a worker and in its parent.)
Key = tuple[str, int]


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

    def __post_init__(self) -> None:
        if not isinstance(self.series, str) or not self.series:
            raise InvalidInput("series must be a non-empty string")
        if isinstance(self.period, bool) or not isinstance(self.period, int) or not 0 <= self.period < PERIOD_LIMIT:
            raise InvalidInput(f"period must be an integer in [0, {PERIOD_LIMIT}), got {self.period!r}")
        finite(f"{self.series}[{self.period}].value", self.value)
        finite(f"{self.series}[{self.period}].known_at", self.known_at)
        if not isinstance(self.quality, str):
            raise InvalidInput("quality must be a string")

    def fingerprint(self) -> int:
        """What downstream results depend on: the value and its quality, not when it was learned.
        A republished identical value therefore invalidates nothing.

        A digest of the exact IEEE-754 bytes plus the quality label, so it is identical in every process
        and on every platform. (The built-in ``hash`` is salted per process, can collide, and hashes a
        NaN by object identity.) ``0`` is reserved to mean "absent", and a digest is never ``0``."""
        fp = self.__dict__.get("_fp")
        if fp is None:
            digest = hashlib.blake2b(struct.pack(">d", self.value + 0.0) + self.quality.encode("utf-8"), digest_size=8)
            fp = int.from_bytes(digest.digest(), "big") or 1
            object.__setattr__(self, "_fp", fp)
        return fp


class VintageStore:
    def __init__(self) -> None:
        self._data: dict[Key, list[Observation]] = {}
        self._series: dict[str, None] = {}          # insertion-ordered set of series names
        self._keys: dict[Key, Key] = {}             # canonical key tuples, so dependency maps share one object per key

    # -- dependency keys
    def key(self, series: str, period: int) -> Key:
        """The stable key for (series, period). Pure: it depends on nothing but its arguments, so a worker
        process, a restarted process and a different machine all compute the same key."""
        if isinstance(period, bool) or not isinstance(period, int) or not 0 <= period < PERIOD_LIMIT:
            raise InvalidInput(f"period must be an integer in [0, {PERIOD_LIMIT}), got {period!r}")
        k = (series, period)
        return self._keys.setdefault(k, k)

    @staticmethod
    def key_parts(key: Key) -> tuple[str, int]:
        return key

    # -- writes
    def append(self, obs: Observation) -> Observation:
        k = (obs.series, obs.period)
        versions = self._data.setdefault(k, [])
        if versions and obs.known_at <= versions[-1].known_at:
            raise ValueError("a revision must have a later knowledge time than the existing vintage")
        versions.append(obs)
        self._series.setdefault(obs.series)
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
        return list(self._series)


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
        self.seen: dict[Key, int] = {}      # key -> fingerprint (0 for "absent")

    def read(self, series: str, period: int) -> Observation | None:
        obs = self.snapshot.read(series, period)
        self.seen[self.snapshot.store.key(series, period)] = obs.fingerprint() if obs else 0
        return obs
