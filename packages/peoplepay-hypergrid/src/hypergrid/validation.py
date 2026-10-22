"""Boundary validation for the HYPERGRID numerics.

A NaN that gets past the boundary does not fail where it entered: it turns into a ``nan`` cost, an
arbitrary ``argsort`` winner and, much later, a crash in ``summary()``. Every number is therefore checked
where it enters, and a number that cannot be given a meaning is refused with a message that names it.
"""
from __future__ import annotations

import math
from numbers import Integral, Real


class InvalidInput(ValueError):
    """A value that cannot be given a meaning: NaN, infinity, a wrong sign, an unsupported unit."""


class InsufficientData(ValueError):
    """The evidence a computation needs is not available. Nothing is invented to fill the gap."""


def finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise InvalidInput(f"{name} must be a number, got {type(value).__name__}")
    out = float(value)
    if not math.isfinite(out):
        raise InvalidInput(f"{name} must be finite, got {value!r}")
    return out


def positive(name: str, value: object) -> float:
    out = finite(name, value)
    if out <= 0.0:
        raise InvalidInput(f"{name} must be > 0, got {value!r}")
    return out


def positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or int(value) < 1:
        raise InvalidInput(f"{name} must be an integer >= 1, got {value!r}")
    return int(value)
