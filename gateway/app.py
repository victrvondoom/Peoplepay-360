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
import os
import threading
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from beacon.peoplepay.authority import Permission, TransactionType
from beacon.peoplepay.transaction import Transaction, TransactionOwnershipError

from adapters.base import Capability, CapabilityMode
from adapters.bridge import SLOT_FOR_CAPABILITY, attach_capability_result
from adapters.market import MarketAdapter
from adapters.property import PropertyAdapter
from adapters.spatial import SpatialAdapter
from gateway.auth import SECRET_ENV, auth_mode, verify_caller
from transaction.eventbus import EventBus
from transaction.store import InMemoryTransactionStore, TransactionNotFound

__all__ = ["GatewayState", "build_capabilities", "make_handler", "serve"]

#: Requests allowed per user per window.  Crude on purpose: a real deployment
#: puts this at the edge, but "no limit at all" is not a defensible default for
#: a surface that fronts money.
RATE_LIMIT = 60
RATE_WINDOW_SECONDS = 60.0


def build_capabilities() -> dict[str, Capability]:
    """Every capability the gateway can route to, configured from the env.

    A capability with no endpoint is still listed.  ``NOT_CONFIGURED`` is a
    reportable state, and hiding an unconfigured capability would make the
    health page a lie by omission.
    """
    return {
        "spatial": SpatialAdapter(),
        "market": MarketAdapter(),
        "property": PropertyAdapter(),
    }


class GatewayState:
    """Everything the handler needs, in one injectable object.

    Exists so tests can build a gateway without binding a socket, and so the
    handler class stays free of module-level globals.
    """

    def __init__(
        self,
        *,
        store: InMemoryTransactionStore | None = None,
        bus: EventBus | None = None,
        capabilities: dict[str, Capability] | None = None,
    ) -> None:
        self.store = store or InMemoryTransactionStore()
        self.bus = bus or EventBus()
        self.capabilities = (
            capabilities if capabilities is not None else build_capabilities()
        )
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

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
            self.end_headers()
            self.wfile.write(raw)

        def _fail(self, code: int, message: str, **extra: Any) -> None:
            self._send(code, {"error": message, **extra})

        def _body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return {}
            try:
                parsed = json.loads(self.rfile.read(length).decode("utf-8"))
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

            user = self._caller()
            if user is None:
                self._fail(401, "X-Beacon-User header is required")
                return
            if not state.allow_request(user):
                self._fail(429, "rate limit exceeded", limit=RATE_LIMIT)
                return

            parts = [p for p in path.split("/") if p]
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
                if parts[2] == "timeline":
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
            if parts == ["transactions"]:
                self._create_transaction(user, body)
                return
            if (
                len(parts) == 4
                and parts[0] == "transactions"
                and parts[2] == "capabilities"
            ):
                self._run_capability(user, parts[1], parts[3], body)
                return
            self._fail(404, f"no route for POST {path}")

        # --- handlers --------------------------------------------------

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
            utterance = str(body.get("raw_utterance") or "").strip()
            if not utterance:
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
                raw_utterance=utterance,
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
                return capability.room_context(room, brief=body.get("brief"))
            if name == "market":
                query = str(body.get("item_query") or "").strip()
                if not query:
                    raise NotImplementedError("market requires 'item_query'")
                return capability.price_evidence(
                    item_query=query, city_id=body.get("city_id")
                )
            if name == "property":
                address = str(body.get("address") or "").strip()
                if not address:
                    raise NotImplementedError("property requires 'address'")
                lookup = str(body.get("lookup") or "location").strip().lower()
                if lookup == "location":
                    return capability.location_intelligence(address=address)
                if lookup == "reports":
                    return capability.property_reports(address=address)
                raise NotImplementedError(
                    f"unknown property lookup {lookup!r}; use 'location' or 'reports'"
                )
            raise NotImplementedError(f"capability {name!r} has no gateway dispatch")

    return Handler


def serve(port: int | None = None, *, state: GatewayState | None = None) -> None:
    """Run the gateway.  Blocks."""
    bound = port or int(os.getenv("BEACON_GATEWAY_PORT", "8080"))
    gateway_state = state or GatewayState()
    httpd = ThreadingHTTPServer(("127.0.0.1", bound), make_handler(gateway_state))
    health = gateway_state.integrations()
    print(f"beacon-gateway on http://127.0.0.1:{bound}")
    for row in health["capabilities"]:
        print(f"  {row['name']:<10} {row['mode']}")
    # Loud at boot, not only in the JSON: an operator who forgot the secret
    # should not have to curl the health page to find out.
    print(f"  auth       {health['auth']['mode']} - {health['auth']['detail']}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()


if __name__ == "__main__":
    serve()
