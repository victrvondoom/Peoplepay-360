"""The one HTTP surface (spec Sec. 25, Sec. 34).

The user meets one system, not five.  This module is the only process that
serves the browser, and it is deliberately thin: it owns no domain logic, it
holds no model, and it moves no money.  It routes, it authorizes at the
boundary, and it reports honestly what is reachable.

Why stdlib ``http.server`` rather than FastAPI: the five projects already
disagree on framework and Python version (3.11 / 3.12 / 3.13), and the audit's
conclusion was to add a service boundary rather than a shared dependency.  A
gateway that needs nothing installed cannot lose that argument later.

Three things this file exists to provide, all of which the Phase 1-4 report
listed as missing:

* ``/health/integrations`` -- the LIVE / SANDBOX / MOCK / NOT_CONFIGURED /
  UNAVAILABLE distinction, per capability, refreshed on each call.
* a request boundary, so rate limiting and authentication have somewhere to live.
* persistence, via ``InMemoryTransactionStore`` behind the ``TransactionStore``
  protocol, so swapping in DynamoDB later touches this file and nothing else.

What it does not do: it does not execute payments, and it does not grant
permissions on the user's behalf.  ``PermissionSet`` stays the authority.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import threading
import time
from pathlib import Path
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, TypeVar
from urllib.parse import urlparse
from datetime import timedelta

from beacon.assurance import EventKind, IntentMandate, Money, State
from beacon.peoplepay.agent import parse_budget
from beacon.peoplepay.evidence_gate import EvidenceGate, EvidenceRequirement
from beacon.peoplepay.authority import AuthorityError

from beacon.peoplepay.authority import Permission, TransactionType
from beacon.peoplepay.transaction import Transaction, TransactionOwnershipError

from adapters.base import (
    Capability,
    CapabilityMode,
    MarketCapability,
    PropertyCapability,
    ResolutionCapability,
    SpatialCapability,
)
from adapters.bridge import SLOT_FOR_CAPABILITY, attach_capability_result
from adapters.market import MarketAdapter
from adapters.property import PropertyAdapter
from adapters.resolution import ResolutionAdapter
from adapters.spatial import SpatialAdapter
from gateway.auth import SECRET_ENV, auth_mode, verify_caller
from gateway.commerce import save_cart, sandbox_checkout, update_delivery, create_dispute
from transaction.eventbus import EventBus
from transaction.store import InMemoryTransactionStore, TransactionNotFound, TransactionStore
from transaction.sqlite_store import SqliteTransactionStore

__all__ = [
    "GatewayState",
    "build_capabilities",
    "config_warnings",
    "make_handler",
    "serve",
]


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    """Read a positive int from the environment, falling back on nonsense.

    A deployment that typos ``BEACON_GATEWAY_RATE_LIMIT=sixty`` must not get a
    gateway that refuses to boot, and must not silently get *no* limit either.
    So an unparseable or out-of-range value keeps the default, and the fact is
    reported through :func:`config_warnings` so the health page can show it.
    """
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        _CONFIG_WARNINGS.append(f"{name}={raw!r} is not an integer; using {default}")
        return default
    if value < minimum:
        _CONFIG_WARNINGS.append(
            f"{name}={value} is below the minimum {minimum}; using {default}"
        )
        return default
    return value


def _env_float(name: str, default: float, *, minimum: float = 0.0) -> float:
    """As :func:`_env_int`, for timeouts."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        _CONFIG_WARNINGS.append(f"{name}={raw!r} is not a number; using {default}")
        return default
    if not math.isfinite(value) or value <= minimum:
        _CONFIG_WARNINGS.append(
            f"{name}={value} must be greater than {minimum}; using {default}"
        )
        return default
    return value


#: Populated by the ``_env_*`` readers above when a value is rejected.  Surfaced
#: on the health page rather than only logged: a limit that silently fell back to
#: its default is exactly the kind of thing an operator finds out too late.
_CONFIG_WARNINGS: list[str] = []


def config_warnings() -> tuple[str, ...]:
    """Every environment value that was rejected in favour of a default."""
    return tuple(_CONFIG_WARNINGS)


def product_modules() -> list[dict[str, str | None]]:
    """Return the PeoplePay suite directory with only configured app URLs."""
    modules = (
        (
            "evidence", "PeoplePay ECHO", "Audit evidence lineage and supplier decisions",
            "PEOPLEPAY_ECHO_URL",
        ),
        (
            "sourcing", "GreenChain", "Compare suppliers and sourcing impact",
            "PEOPLEPAY_GREENCHAIN_URL",
        ),
        (
            "spaces", "Rumi", "Plan a room and discover furniture",
            "PEOPLEPAY_RUMI_URL",
        ),
        (
            "prices", "InflationForge", "Explore sourced regional price trends",
            "PEOPLEPAY_INFLATIONFORGE_URL",
        ),
        (
            "property", "InHeir.AI", "Manage property cases and reports",
            "PEOPLEPAY_INHEIR_URL",
        ),
        (
            "resolution", "PROXY", "Prepare consumer dispute evidence",
            "PEOPLEPAY_PROXY_URL",
        ),
        (
            "operations", "Beacon", "Operator incident response",
            "PEOPLEPAY_BEACON_URL",
        ),
    )
    result: list[dict[str, str | None]] = []
    for module_id, name, description, env_name in modules:
        raw_url = os.getenv(env_name, "").strip()
        url: str | None = None
        if raw_url:
            parsed = urlparse(raw_url)
            if (
                parsed.scheme in {"http", "https"}
                and parsed.netloc
                and not parsed.username
                and not parsed.password
            ):
                # Never reflect URL credentials, query parameters or fragments into the browser.
                url = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"
        result.append(
            {
                "id": module_id,
                "name": name,
                "description": description,
                "url": url,
                "status": "AVAILABLE" if url else "NOT_CONFIGURED",
            }
        )
    return result


#: Requests allowed per user per window.  Crude on purpose: a real deployment
#: puts this at the edge, but "no limit at all" is not a defensible default for
#: a surface that fronts money.
RATE_LIMIT = _env_int("BEACON_GATEWAY_RATE_LIMIT", 60)
RATE_WINDOW_SECONDS = _env_float("BEACON_GATEWAY_RATE_WINDOW_SECONDS", 60.0)

#: Largest request body the gateway will read, in bytes.  ``Content-Length``
#: is attacker-controlled, so it is a budget to check against rather than an
#: allocation size to trust.
MAX_BODY_BYTES = _env_int("BEACON_GATEWAY_MAX_BODY_BYTES", 1_048_576, minimum=1024)

#: How much of a refused body the gateway will read and discard so that the
#: client can finish writing and read the 400.  Bounded well above the body
#: limit but far below anything that would matter: draining is a courtesy to a
#: well-behaved client, not an obligation to a hostile one.
DRAIN_LIMIT = _env_int("BEACON_GATEWAY_DRAIN_LIMIT", 8 * 1_048_576, minimum=1024)

#: Chunk size for that drain, so no refused body is ever held whole in memory.
_DRAIN_CHUNK = 65_536

#: Interface the gateway binds.  Loopback by default -- this surface fronts
#: money and has an ``OPEN`` auth mode, so it must not become reachable off
#: the host just because it was deployed somewhere with a public interface.
BIND_HOST = os.getenv("BEACON_GATEWAY_HOST") or "127.0.0.1"

#: Type variable for :func:`_as`.  The protocols it narrows to are structural,
#: so there is no common base to bind against.
_P = TypeVar("_P")


def _as(capability: Capability, shape: type[_P], name: str) -> _P:
    """Narrow an adapter to the call shape its route needs.

    ``shape`` is one of the ``*Capability`` protocols and is used only as an
    ``isinstance`` argument -- it is never instantiated.  mypy still reports
    ``type-abstract`` at each call site because ``type[P]`` for a protocol ``P``
    normally implies constructibility; those four call sites carry a scoped
    ignore for exactly that, which is narrower than widening ``shape`` to
    ``Any`` and losing the return-type narrowing this function exists to give.

    The dispatch below is explicit per capability rather than a generic
    ``getattr``, so the route name already decides which method is called.  What
    this adds is the check that the adapter *behind* that name actually offers
    it: capabilities are injectable (``GatewayState(capabilities=...)``), so a
    substituted or half-built adapter is reachable in practice.

    Raising ``NotImplementedError`` puts that case on the 400 path -- the route
    was asked for something this adapter cannot do -- instead of letting an
    ``AttributeError`` fall through to the 502 handler, where it would be
    reported as an upstream provider failure that never happened.
    """
    if not isinstance(capability, shape):
        raise NotImplementedError(
            f"capability {name!r} ({type(capability).__name__}) does not implement "
            f"{shape.__name__}"
        )
    return capability


def build_capabilities() -> dict[str, Capability]:
    """Every capability the gateway can route to, configured from the env.

    A capability with no endpoint is still listed.  ``NOT_CONFIGURED`` is a
    reportable state, and hiding an unconfigured capability would make the
    health page a lie by omission.

    Each timeout is read from the environment because the four upstreams have
    genuinely different shapes -- PROXY runs a multi-agent case workflow and is
    slow by nature, while a price lookup either answers quickly or is down -- and
    a deployment tuning one must not have to edit code to do it.  The defaults
    match each adapter's own default, so an unset environment changes nothing.
    """
    return {
        "spatial": SpatialAdapter(
            timeout=_env_float("BEACON_SPATIAL_TIMEOUT", 15.0),
        ),
        "market": MarketAdapter(
            timeout=_env_float("BEACON_MARKET_TIMEOUT", 15.0),
        ),
        "property": PropertyAdapter(
            timeout=_env_float("BEACON_PROPERTY_TIMEOUT", 20.0),
        ),
        "resolution": ResolutionAdapter(
            timeout=_env_float("BEACON_RESOLUTION_TIMEOUT", 60.0),
        ),
    }


class GatewayState:
    """Everything the handler needs, in one injectable object.

    Exists so tests can build a gateway without binding a socket, and so the
    handler class stays free of module-level globals.
    """

    def __init__(
        self,
        *,
        store: TransactionStore | None = None,
        bus: EventBus | None = None,
        capabilities: dict[str, Capability] | None = None,
        journey: Any = None,
    ) -> None:
        self.store = store if store is not None else InMemoryTransactionStore()
        self.workflow_lock = threading.RLock()
        self.bus = bus or EventBus()
        self.capabilities = (
            capabilities if capabilities is not None else build_capabilities()
        )
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._journey = journey

    def journey_service(self):
        """Load the concrete journey only when requested, preserving legacy startup."""
        with self.workflow_lock:
            if self._journey is None:
                from journey.service import JourneyService
                self._journey = JourneyService(self)
        return self._journey

    # --- rate limiting -------------------------------------------------

    def allow_request(self, who: str) -> bool:
        """Sliding-window limit, per caller."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[who]
            while hits and now - hits[0] > RATE_WINDOW_SECONDS:
                hits.popleft()
            if len(hits) >= RATE_LIMIT:
                return False
            hits.append(now)
            return True

    # --- health --------------------------------------------------------

    def integrations(self, *, authenticated: bool = False) -> dict[str, Any]:
        """Per-capability health, plus what the system can therefore do.

        ``health()`` is contractually non-raising, but a broken adapter must not
        take the health page down with it, so a raise is reported as
        ``UNAVAILABLE`` rather than propagated.

        ``endpoint`` names an internal service URL, and this route is reachable
        without credentials so that liveness probes keep working.  So it is only
        included for an authenticated caller: an unauthenticated reader learns
        *that* a capability is configured (``endpoint_configured``), never
        *where* it lives.  ``missing_config`` stays visible either way -- it names
        environment variables, which is a deployment hint rather than a target.

        The omission happens inside ``HealthReport.to_dict``, so the value is
        never serialized rather than being written and then blanked.
        """
        reports = []
        for name, capability in sorted(self.capabilities.items()):
            try:
                reports.append(
                    capability.health().to_dict(include_endpoint=authenticated)
                )
            except Exception as exc:  # noqa: BLE001 - health must never 500
                reports.append(
                    {
                        "name": name,
                        "mode": str(CapabilityMode.UNAVAILABLE),
                        "detail": (
                            f"health check itself raised: {type(exc).__name__}: {exc}"
                        ),
                        "usable": False,
                        "decision_grade": False,
                    }
                )
        decision_grade = [r["name"] for r in reports if r.get("decision_grade")]
        return {
            "capabilities": reports,
            "summary": {
                "total": len(reports),
                "usable": sum(1 for r in reports if r.get("usable")),
                "decision_grade": len(decision_grade),
            },
            # Stated plainly so the UI cannot imply real-money readiness that
            # the capability modes do not support (Sec. 24).
            "real_money_ready": "payment" in decision_grade,
            # An OPEN gateway trusts whatever user id it is handed.  Saying so
            # here means a deployment that forgot the secret is visible rather
            # than quietly insecure.
            "auth": {
                "mode": str(auth_mode()),
                "detail": (
                    "signed bearer tokens required"
                    if str(auth_mode()) == "VERIFIED"
                    else f"no {SECRET_ENV} set: caller identity is unverified, "
                    "local use only"
                ),
            },
            # A limit that fell back to its default because the environment
            # said something unparseable is a deployment fault, and silence
            # about it is how a "rate limited" gateway turns out not to be.
            "config_warnings": list(config_warnings()),
            "note": (
                "A transaction may be planned on SANDBOX evidence, but no "
                "SANDBOX or MOCK source can satisfy a real-money decision."
            ),
        }


def make_handler(state: GatewayState) -> type[BaseHTTPRequestHandler]:
    """Build the request handler bound to *state*."""

    class Handler(BaseHTTPRequestHandler):
        server_version = "BeaconGateway/1.0"
        protocol_version = "HTTP/1.1"

        # --- plumbing --------------------------------------------------

        def log_message(self, fmt: str, *args: Any) -> None:
            # Quiet by default; the ledger is the audit record, not stderr.
            if os.getenv("BEACON_GATEWAY_VERBOSE"):
                super().log_message(fmt, *args)

        def _send(self, code: int, body: dict[str, Any]) -> None:
            raw = json.dumps(body, default=str).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            # This surface is JSON for a first-party UI; no cross-origin grant.
            self.send_header("X-Content-Type-Options", "nosniff")
            # When a handler has decided this connection cannot continue -- a
            # body refused without being read, so the request stream is still
            # mid-message -- the client has to be told.  ``send_response`` emits
            # keep-alive for HTTP/1.1 regardless of ``close_connection``, so
            # without this header the socket would simply be closed underneath a
            # client that believed it could send another request on it.
            if self.close_connection:
                self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(raw)

        def _fail(self, code: int, message: str, **extra: Any) -> None:
            self._send(code, {"error": message, **extra})

        def _drain(self, length: int) -> None:
            """Read and discard a refused body so the caller can read our reply.

            Bounded twice over: never more than ``DRAIN_LIMIT`` in total, and
            never more than one chunk in memory at a time.  A client whose body
            is larger than that gets the reset it was always going to get -- the
            alternative is reading an unbounded stream on its say-so.
            """
            remaining = min(length, DRAIN_LIMIT)
            while remaining > 0:
                chunk = self.rfile.read(min(_DRAIN_CHUNK, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)

        def _body(self) -> dict[str, Any]:
            """Parse the request body, trusting nothing the client declared.

            ``Content-Length`` arrives from the caller, so each step treats it as
            a claim: a non-numeric or negative value is a bad request rather than
            an unhandled ``ValueError``, and a value over ``MAX_BODY_BYTES`` is
            refused on the strength of the header alone, so a declared length
            never sizes a buffer.  A refused body is then drained in bounded
            chunks (see :meth:`_drain`) -- read and discarded, never held whole --
            because a client mid-write must be able to read the 400.  A body
            shorter than declared is reported rather than parsed as truncated
            JSON.
            """
            raw_length = self.headers.get("Content-Length")
            if raw_length is None or not raw_length.strip():
                return {}
            try:
                length = int(raw_length)
            except ValueError:
                # Unlike the size limit below, there is no trustworthy length to
                # drain against here, so the connection simply ends.  The client
                # has sent its headers and is told why before the close.
                self.close_connection = True
                raise ValueError("Content-Length is not an integer") from None
            if length < 0:
                self.close_connection = True
                raise ValueError("Content-Length is negative")
            if not length:
                return {}
            if length > MAX_BODY_BYTES:
                # Refused -- but the client is still writing those bytes, and a
                # socket closed with unread data in its receive buffer is reset
                # rather than closed (RST on Windows), which destroys the 400
                # before the caller can read it.  So the rest is drained in
                # bounded chunks and discarded: the point of the limit is to
                # never *buffer* an oversized body, not to never read one.
                # ``DRAIN_LIMIT`` keeps that bounded for a client that lied
                # about its length, and the connection closes either way.
                self._drain(length)
                self.close_connection = True
                raise ValueError(
                    f"body of {length} bytes exceeds the {MAX_BODY_BYTES}-byte limit"
                )
            data = self.rfile.read(length)
            if len(data) != length:
                self.close_connection = True
                raise ValueError(
                    f"body is {len(data)} bytes but Content-Length declared {length}"
                )
            try:
                parsed = json.loads(data.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise ValueError(f"body is not valid JSON: {exc}") from exc
            if not isinstance(parsed, dict):
                raise ValueError("body must be a JSON object")
            return parsed

        def _caller(self) -> str | None:
            """Who is asking, as far as it can be verified.

            With ``BEACON_GATEWAY_SECRET`` set this requires a signed bearer
            token and ignores ``X-Beacon-User`` entirely; without one it accepts
            the bare header so local development still works, and the health page
            reports ``OPEN`` so the weaker mode is visible.  See
            ``gateway/auth.py``.

            Every transaction read and write is *additionally* checked against
            ``assert_owned_by``, so identity is defence in depth rather than the
            only thing between two users' data.
            """
            return verify_caller(
                authorization=self.headers.get("Authorization"),
                user_header=self.headers.get("X-Beacon-User"),
            )

        # --- routing ---------------------------------------------------

        def do_GET(self) -> None:
            path = urlparse(self.path).path.rstrip("/") or "/"
            if path == "/favicon.ico":
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            assets = {"/": ("index.html", "text/html"),
                      "/journey": ("journey.html", "text/html"),
                      "/journey.js": ("journey.js", "text/javascript"),
                      "/journey.css": ("journey.css", "text/css"),
                      "/app.js": ("app.js", "text/javascript"),
                      "/styles.css": ("styles.css", "text/css")}
            if path in assets:
                filename, mime = assets[path]
                raw = (Path(__file__).parent / "web" / filename).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mime + "; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'")
                self.end_headers()
                self.wfile.write(raw)
                return
            if path == "/health":
                self._send(200, {"status": "ok", "service": "beacon-gateway"})
                return
            if path == "/health/integrations":
                # Open on purpose, for liveness probes.  An authenticated caller
                # additionally sees each capability's endpoint.
                self._send(
                    200,
                    state.integrations(authenticated=self._caller() is not None),
                )
                return
            if path == "/product/modules":
                self._send(200, {"modules": product_modules()})
                return

            user = self._caller()
            if user is None:
                self._fail(401, "X-Beacon-User header is required")
                return
            if not state.allow_request(user):
                self._fail(429, "rate limit exceeded", limit=RATE_LIMIT)
                return

            parts = [p for p in path.split("/") if p]
            if parts[:3] == ["api", "v1", "journeys"]:
                self._journey_route(user, parts[3:], None)
                return
            if parts == ["transactions"]:
                self._send(
                    200,
                    {"transactions": [t.to_dict() for t in state.store.for_user(user)]},
                )
                return
            if len(parts) >= 2 and parts[0] == "transactions":
                txn = self._owned_or_404(parts[1], user)
                if txn is None:
                    return
                if len(parts) == 2:
                    self._send(200, txn.to_dict())
                    return
                if len(parts) == 3 and parts[2] == "evidence":
                    self._send(200, txn.graph.reconstruct())
                    return
                if len(parts) == 3 and parts[2] == "context":
                    self._send(200, {"context": txn.context})
                    return
                if len(parts) == 3 and parts[2] == "timeline":
                    intact, message = txn.ledger.verify_chain()
                    self._send(
                        200,
                        {
                            "transaction_id": txn.transaction_id,
                            "state": str(txn.state),
                            "timeline": txn.ledger.timeline(),
                            "integrity": {"intact": intact, "message": message},
                        },
                    )
                    return
            self._fail(404, f"no route for GET {path}")

        def do_POST(self) -> None:
            path = urlparse(self.path).path.rstrip("/") or "/"
            user = self._caller()
            if user is None:
                self._fail(401, "X-Beacon-User header is required")
                return
            if not state.allow_request(user):
                self._fail(429, "rate limit exceeded", limit=RATE_LIMIT)
                return
            try:
                body = self._body()
            except ValueError as exc:
                self._fail(400, str(exc))
                return

            parts = [p for p in path.split("/") if p]
            if parts[:3] == ["api", "v1", "journeys"]:
                with state.workflow_lock:
                    self._journey_route(user, parts[3:], body)
                return
            if parts == ["transactions"]:
                self._create_transaction(user, body)
                return
            if len(parts) == 3 and parts[0] == "transactions":
                with state.workflow_lock:
                    self._workflow(user, parts[1], parts[2], body)
                return
            if (
                len(parts) == 4
                and parts[0] == "transactions"
                and parts[2] == "capabilities"
            ):
                with state.workflow_lock:
                    self._run_capability(user, parts[1], parts[3], body)
                return
            self._fail(404, f"no route for POST {path}")

        # --- handlers --------------------------------------------------

        def _journey_route(self, user: str, parts: list[str], body: dict[str, Any] | None) -> None:
            try:
                from journey.service import JourneyUnavailable
                service = state.journey_service()
                authorization = self.headers.get("Authorization")
                if body is None:
                    if not parts:
                        result = {"journeys": service.store.list(user)}
                    elif len(parts) == 1:
                        result = service.store.get(parts[0], user)
                    elif len(parts) == 2 and parts[1] == "explain":
                        result = service.explain(parts[0], user, authorization)
                    else:
                        self._fail(404, "unknown journey route")
                        return
                elif not parts:
                    result = service.create(user, body, authorization)
                elif len(parts) == 2 and parts[1] == "approve":
                    result = service.approve(parts[0], user, body, authorization)
                elif len(parts) == 2 and parts[1] == "delivery":
                    result = service.delivery(parts[0], user, body)
                elif len(parts) == 2 and parts[1] == "retry-dispute":
                    if body:
                        raise ValueError("draft retry takes no evidence override data")
                    result = service.retry_dispute(parts[0], user)
                elif len(parts) == 2 and parts[1] == "refresh":
                    if body:
                        raise ValueError("refresh takes no provider override data")
                    result = service.refresh(parts[0], user, authorization)
                else:
                    self._fail(404, "unknown journey route")
                    return
                self._send(201 if body is not None and not parts else 200, result)
            except KeyError:
                self._fail(404, "journey or decision not found")
            except (ValueError, TypeError) as exc:
                self._fail(409, str(exc))
            except ImportError:
                self._fail(503, "Journey dependencies are missing. Install the local Extension SDK and journey requirements.")
            except JourneyUnavailable as exc:
                self._fail(503, str(exc))
            except sqlite3.Error:
                self._fail(503, "Journey storage is unavailable; existing orders and evidence are retained. Reload before retrying.")

        def _workflow(
            self, user: str, transaction_id: str, action: str, body: dict[str, Any]
        ) -> None:
            txn = self._owned_or_404(transaction_id, user)
            if txn is None:
                return
            actor = f"gateway:{user}"
            result: dict[str, Any]
            try:
                if action == "plan":
                    txn.require_permission(Permission.PLANNING, actor=actor)
                    if txn.state is State.CANCELLED:
                        raise ValueError("cancelled transactions cannot be planned")
                    summary = body.get("summary")
                    steps = body.get("steps")
                    if not isinstance(summary, str) or not summary.strip():
                        raise ValueError("summary is required")
                    if not isinstance(steps, list) or not steps or any(
                        not isinstance(step, str) or not step.strip() for step in steps
                    ):
                        raise ValueError("steps must be a non-empty list of text")
                    amount = body.get("amount_minor")
                    if type(amount) is not int or amount < 0:
                        raise ValueError("amount_minor must be a non-negative integer")
                    currency = body.get("currency", "INR")
                    if not isinstance(currency, str):
                        raise ValueError("currency must be text")
                    estimate = Money(amount, currency)
                    if txn.state is State.DRAFT:
                        mandate = IntentMandate.create(
                            user_id=user, raw_utterance=txn.raw_utterance,
                            product_query=summary,
                            max_amount=parse_budget(txn.raw_utterance),
                        )
                        txn.capture_intent(mandate, normalized_intent=summary, actor=actor)
                    txn.plan = {
                        "summary": summary, "steps": steps,
                        "estimated_amount": estimate.to_dict(), "executed": False,
                    }
                    txn.ledger.append(EventKind.POLICY_EVALUATED, actor=actor,
                                      detail={"plan": txn.plan})
                    result = {"plan": txn.plan}
                elif action == "validate":
                    txn.require_permission(Permission.PLANNING, actor=actor)
                    problems = []
                    if not txn.plan:
                        problems.append("Create a plan first")
                    if txn.state is State.CANCELLED:
                        problems.append("Transaction is cancelled")
                    if txn.plan and txn.mandate and txn.mandate.max_amount:
                        estimate = Money.from_dict(txn.plan["estimated_amount"])
                        budget = txn.mandate.max_amount
                        if estimate.currency != budget.currency or estimate.minor > budget.minor:
                            problems.append("Plan exceeds the budget or uses another currency")
                    passport = EvidenceGate().evaluate(
                        txn,
                        tuple(EvidenceRequirement(field, timedelta(minutes=5))
                              for field in ("price_minor", "stock", "merchant_id")),
                        actor=actor,
                    )
                    if not passport.decision_grade:
                        problems.append("Required checkout evidence is missing or insufficient")
                    result = {"valid": not problems, "problems": problems,
                              "passport": passport.to_dict(), "executed": False,
                              "payment_status": "NOT_CONFIGURED"}
                elif action == "cart":
                    result = {"cart": save_cart(txn, body, actor)}
                elif action == "sandbox-checkout":
                    result = sandbox_checkout(txn, body, actor)
                elif action == "delivery":
                    result = update_delivery(txn, body, actor)
                elif action == "dispute":
                    result = create_dispute(txn, body, actor)
                elif action == "checkout":
                    self._fail(503, "Live payments are not configured; no money moved")
                    return
                elif action == "cancel":
                    if txn.state is not State.CANCELLED:
                        txn.transition_to(State.CANCELLED, actor=actor)
                    result = txn.to_dict()
                else:
                    self._fail(404, f"unknown workflow {action!r}")
                    return
                state.store.put(txn)
                self._send(200, result)
            except AuthorityError as exc:
                self._fail(403, str(exc))
            except (ValueError, KeyError, TypeError) as exc:
                self._fail(400, str(exc))

        def _owned_or_404(self, transaction_id: str, user: str) -> Transaction | None:
            """Fetch a transaction the caller owns, or answer 404.

            404 rather than 403 on an ownership failure: confirming the id
            exists would leak that another user holds it.
            """
            try:
                txn = state.store.get(transaction_id)
                txn.assert_owned_by(user)
            except TransactionNotFound:
                self._fail(404, f"no transaction {transaction_id!r}")
                return None
            except TransactionOwnershipError:
                self._fail(404, f"no transaction {transaction_id!r}")
                return None
            return txn

        def _create_transaction(self, user: str, body: dict[str, Any]) -> None:
            utterance = body.get("raw_utterance")
            if not isinstance(utterance, str) or not utterance.strip():
                self._fail(
                    400,
                    "raw_utterance is required: a transaction needs the user's "
                    "own words as its consent record",
                )
                return
            raw_type = str(body.get("transaction_type") or "PURCHASE").upper()
            try:
                txn_type = TransactionType(raw_type)
            except ValueError:
                self._fail(
                    400,
                    f"unknown transaction_type {raw_type!r}",
                    known=[str(t) for t in TransactionType],
                )
                return
            txn = Transaction.create(
                user_id=user,
                raw_utterance=utterance.strip(),
                transaction_type=txn_type,
                language=body.get("language"),
                actor=f"gateway:{user}",
            )
            state.store.put(txn)
            state.bus.publish_ledger_tail(txn.ledger, source="gateway")
            self._send(201, txn.to_dict())

        def _run_capability(
            self, user: str, transaction_id: str, name: str, body: dict[str, Any]
        ) -> None:
            """Invoke one capability and attach its result to the transaction.

            Discovery-grade work only.  Nothing here can move money: the
            adapters read, and ``PermissionSet`` is untouched by this route.
            """
            txn = self._owned_or_404(transaction_id, user)
            if txn is None:
                return

            capability = state.capabilities.get(name)
            if capability is None:
                self._fail(
                    404, f"no capability {name!r}", known=sorted(state.capabilities)
                )
                return

            # Reading the world is DISCOVERY. Held by default, but checked
            # rather than assumed -- a revoked grant must actually stop this.
            if not txn.permissions.allows(Permission.DISCOVERY):
                self._fail(403, "DISCOVERY permission is not granted")
                return

            before = len(txn.ledger)
            try:
                result = self._dispatch(capability, name, body)
            except NotImplementedError as exc:
                self._fail(400, str(exc))
                return
            except Exception as exc:  # noqa: BLE001 - report, never fabricate
                self._fail(
                    502, f"capability {name!r} failed: {type(exc).__name__}: {exc}"
                )
                return

            node_id = attach_capability_result(txn, result, actor=f"gateway:{user}")
            state.store.put(txn)
            state.bus.publish_ledger_tail(txn.ledger, source=name, since_seq=before)
            self._send(
                200,
                {
                    "transaction_id": txn.transaction_id,
                    "capability": name,
                    "mode": str(result.mode),
                    "evidence_node_id": node_id,
                    "gaps": list(result.gaps),
                    "sandbox": result.is_sandbox,
                    "context": txn.context.get(SLOT_FOR_CAPABILITY[name]),
                },
            )

        @staticmethod
        def _dispatch(capability: Capability, name: str, body: dict[str, Any]) -> Any:
            """Map a route to one adapter call.

            Explicit per capability: a generic ``getattr`` dispatch would let a
            request name any method on the adapter.
            """
            if name == "spatial":
                room = body.get("room")
                if not isinstance(room, dict):
                    raise NotImplementedError(
                        "spatial requires a 'room' object in Rumi's roomSchema shape"
                    )
                spatial = _as(capability, SpatialCapability, name)  # type: ignore[type-abstract]
                return spatial.room_context(room, brief=body.get("brief"))
            if name == "market":
                query = str(body.get("item_query") or "").strip()
                if not query:
                    raise NotImplementedError("market requires 'item_query'")
                market = _as(capability, MarketCapability, name)  # type: ignore[type-abstract]
                return market.price_evidence(
                    item_query=query, city_id=body.get("city_id")
                )
            if name == "property":
                address = str(body.get("address") or "").strip()
                if not address:
                    raise NotImplementedError("property requires 'address'")
                lookup = str(body.get("lookup") or "location").strip().lower()
                prop = _as(capability, PropertyCapability, name)  # type: ignore[type-abstract]
                if lookup == "location":
                    return prop.location_intelligence(address=address)
                if lookup == "reports":
                    return prop.property_reports(address=address)
                raise NotImplementedError(
                    f"unknown property lookup {lookup!r}; use 'location' or 'reports'"
                )
            if name == "resolution":
                # Two distinct calls, chosen explicitly. A dispute workflow is
                # consequential enough that the caller must name which one.
                action = str(body.get("action") or "").strip().lower()
                resolution = _as(capability, ResolutionCapability, name)  # type: ignore[type-abstract]
                if action == "run_case":
                    case_id = str(body.get("case_id") or "").strip()
                    if not case_id:
                        raise NotImplementedError(
                            "resolution run_case requires 'case_id'"
                        )
                    return resolution.run_case(
                        case_id=case_id,
                        include_draft=bool(body.get("include_draft", True)),
                    )
                if action == "ask":
                    question = str(body.get("question") or "").strip()
                    if not question:
                        raise NotImplementedError("resolution ask requires 'question'")
                    try:
                        return resolution.ask(
                            question=question,
                            domain=str(body.get("domain") or "ecommerce"),
                            institution_name=str(body.get("institution_name") or ""),
                        )
                    except ValueError as exc:
                        # An unknown domain is a caller error, not a 502.
                        raise NotImplementedError(str(exc)) from exc
                raise NotImplementedError(
                    f"unknown resolution action {action!r}; use 'run_case' or 'ask'"
                )
            raise NotImplementedError(f"capability {name!r} has no gateway dispatch")

    return Handler


def serve(port: int | None = None, *, state: GatewayState | None = None) -> None:
    """Run the gateway.  Blocks."""
    bound = port or _env_int("BEACON_GATEWAY_PORT", 8080, minimum=1)
    gateway_state = state if state is not None else GatewayState(
        store=SqliteTransactionStore(
            os.getenv("BEACON_GATEWAY_DB", "peoplepay.sqlite3")
        )
    )
    httpd = ThreadingHTTPServer((BIND_HOST, bound), make_handler(gateway_state))
    health = gateway_state.integrations()
    print(f"beacon-gateway on http://{BIND_HOST}:{bound}")
    for row in health["capabilities"]:
        print(f"  {row['name']:<10} {row['mode']}")
    # Loud at boot, not only in the JSON: an operator who forgot the secret
    # should not have to curl the health page to find out.
    print(f"  auth       {health['auth']['mode']} - {health['auth']['detail']}")
    for warning in config_warnings():
        print(f"  config     WARNING: {warning}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()


if __name__ == "__main__":
    serve()
