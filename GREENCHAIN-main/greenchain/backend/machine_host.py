"""
machine_host.py
---------------
Provisions and manages a persistent Dedalus Machine (KVM-isolated Linux VM)
that the agent swarm uses as an isolated network-egress host for `fetch_url`.

Only active when GREENCHAIN_USE_DEDALUS_MACHINE=1. Falls back to local httpx
on any error so the demo never breaks.

The current Python SDK on PyPI does not expose the DCS Machines API yet, so
this module talks to the documented DCS HTTP endpoints directly.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from typing import Any, Optional

import httpx


class MachineFetchError(RuntimeError):
    """Raised when a fetch inside the Dedalus Machine fails for any reason."""


_FLAG_ENV = "GREENCHAIN_USE_DEDALUS_MACHINE"
_API_KEY_ENV = "DEDALUS_API_KEY"
_ORG_ID_ENV = "DEDALUS_ORG_ID"
_DCS_BASE_URL = "https://dcs.dedaluslabs.ai"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_lock = threading.Lock()
_client: Optional[httpx.Client] = None
_machine_id: Optional[str] = None
_machine_revision: Optional[str] = None
_init_failed: bool = False


def _flag_set() -> bool:
    return os.environ.get(_FLAG_ENV, "").strip() in ("1", "true", "yes")


def _headers(*, idempotency: bool = False, if_match: str | None = None) -> dict[str, str]:
    api_key = os.environ.get(_API_KEY_ENV, "").strip()
    if not api_key:
        raise RuntimeError(f"{_API_KEY_ENV} is not set")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    org_id = os.environ.get(_ORG_ID_ENV, "").strip()
    if org_id:
        headers["X-Dedalus-Org-Id"] = org_id
    if idempotency:
        headers["Idempotency-Key"] = str(uuid.uuid4())
    if if_match:
        headers["If-Match"] = if_match
    return headers


def _load_sync_client() -> httpx.Client:
    return httpx.Client(base_url=_DCS_BASE_URL, timeout=30.0)


def _raise_api_error(resp: httpx.Response) -> None:
    try:
        detail = resp.json()
    except ValueError:
        detail = resp.text
    raise RuntimeError(f"DCS API {resp.status_code}: {detail}")


def _get_machine(client: httpx.Client, machine_id: str) -> dict[str, Any]:
    resp = client.get(
        f"/v1/machines/{machine_id}",
        headers=_headers(),
    )
    if resp.status_code != 200:
        _raise_api_error(resp)
    machine = resp.json()
    etag = resp.headers.get("ETag")
    if etag:
        machine["_etag"] = etag
    return machine


def _create_machine(
    client: httpx.Client,
    *,
    vcpu: int,
    memory_mib: int,
    storage_gib: int,
) -> dict[str, Any]:
    resp = client.post(
        "/v1/machines",
        headers=_headers(idempotency=True),
        json={
            "vcpu": float(vcpu),
            "memory_mib": int(memory_mib),
            "storage_gib": int(storage_gib),
        },
    )
    if resp.status_code not in (200, 202):
        _raise_api_error(resp)
    machine = resp.json()
    etag = resp.headers.get("ETag")
    if etag:
        machine["_etag"] = etag
    return machine


def _delete_machine(client: httpx.Client, machine_id: str, revision: str) -> None:
    resp = client.delete(
        f"/v1/machines/{machine_id}",
        headers=_headers(idempotency=True, if_match=revision),
    )
    if resp.status_code not in (200, 202):
        _raise_api_error(resp)


def init_machine(
    vcpu: int = 1,
    memory_mib: int = 1024,
    storage_gib: int = 10,
    boot_timeout_s: float = 60.0,
) -> None:
    """
    Provision a Dedalus Machine and wait for it to reach the running phase.

    Safe to call when the flag is off (no-op). Safe to call twice (idempotent).
    Never raises — on failure, stores an internal flag so is_enabled() returns False.
    """
    global _client, _machine_id, _machine_revision, _init_failed

    if not _flag_set():
        return

    with _lock:
        if _machine_id is not None or _init_failed:
            return
        try:
            client = _load_sync_client()
            dm = _create_machine(
                client,
                vcpu=vcpu,
                memory_mib=memory_mib,
                storage_gib=storage_gib,
            )
            mid = dm.get("machine_id")
            if not mid:
                raise RuntimeError(f"machine create returned no id: {dm!r}")

            deadline = time.monotonic() + boot_timeout_s
            while True:
                status = dm.get("status") or {}
                phase = status.get("phase")
                if phase == "running":
                    break
                if phase in {"failed", "destroyed"}:
                    raise RuntimeError(
                        f"machine {mid} entered terminal phase {phase!r}: "
                        f"{status.get('last_error') or status.get('reason') or 'unknown error'}"
                    )
                if time.monotonic() > deadline:
                    raise TimeoutError(
                        f"machine {mid} did not reach 'running' within {boot_timeout_s}s "
                        f"(last phase={phase!r})"
                    )
                time.sleep(1.0)
                dm = _get_machine(client, mid)

            _client = client
            _machine_id = mid
            _machine_revision = (dm.get("status") or {}).get("revision") or dm.get("_etag")
            print(f"[machine_host] Dedalus Machine created: {mid}", flush=True)
        except Exception as exc:  # noqa: BLE001
            _init_failed = True
            client_to_close = _client or locals().get("client")
            if client_to_close is not None:
                client_to_close.close()
            _client = None
            print(
                f"[machine_host] init failed ({type(exc).__name__}: {exc}) — "
                "falling back to local httpx for fetch_url.",
                flush=True,
            )


def destroy_machine() -> None:
    """Delete the provisioned Machine if any. Never raises."""
    global _client, _machine_id, _machine_revision

    with _lock:
        if _client is None or _machine_id is None:
            return
        mid = _machine_id
        try:
            revision = _machine_revision
            if revision is None:
                dm = _get_machine(_client, mid)
                revision = (dm.get("status") or {}).get("revision") or dm.get("_etag")
            if revision is None:
                raise RuntimeError("machine revision unavailable for delete")
            _delete_machine(_client, mid, revision)
            print(f"[machine_host] Dedalus Machine deleted: {mid}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(
                f"[machine_host] destroy failed for {mid} "
                f"({type(exc).__name__}: {exc})",
                flush=True,
            )
        finally:
            _client.close()
            _client = None
            _machine_id = None
            _machine_revision = None


def is_enabled() -> bool:
    """True iff the flag is set AND a Machine is currently provisioned."""
    return _flag_set() and _client is not None and _machine_id is not None


def fetch_via_machine(url: str, timeout: float = 15.0, poll_cap_s: float = 30.0) -> str:
    """
    Run `curl -sL --max-time <timeout> -A <UA> <url>` inside the Dedalus Machine
    and return stdout as text.

    Raises MachineFetchError on any failure (non-zero exit, timeout, SDK error).
    The URL is passed as a separate argv element so shell metacharacters cannot
    break out — the Executions API uses execve(2), not a shell.
    """
    if not is_enabled():
        raise MachineFetchError("machine not enabled")

    client = _client
    mid = _machine_id
    assert client is not None and mid is not None  # narrowed by is_enabled()

    try:
        resp = client.post(
            f"/v1/machines/{mid}/executions",
            headers=_headers(idempotency=True),
            json={
                "command": [
                    "/usr/bin/curl",
                    "-sL",
                    "--max-time",
                    str(int(timeout)),
                    "-A",
                    _UA,
                    url,
                ],
                "timeout_ms": int(poll_cap_s * 1000),
            },
        )
        if resp.status_code != 200:
            _raise_api_error(resp)
        exc = resp.json()
    except Exception as e:  # noqa: BLE001
        raise MachineFetchError(f"exec create failed: {type(e).__name__}: {e}") from e

    exec_id = exc.get("execution_id")
    if not exec_id:
        raise MachineFetchError(f"exec create returned no id: {exc!r}")

    deadline = time.monotonic() + poll_cap_s
    status = exc.get("status")
    while status not in ("succeeded", "failed", "cancelled", "expired"):
        if time.monotonic() > deadline:
            raise MachineFetchError(f"exec {exec_id} timed out after {poll_cap_s}s")
        time.sleep(0.25)
        try:
            resp = client.get(
                f"/v1/machines/{mid}/executions/{exec_id}",
                headers=_headers(),
            )
            if resp.status_code != 200:
                _raise_api_error(resp)
            exc = resp.json()
        except Exception as e:  # noqa: BLE001
            raise MachineFetchError(
                f"exec retrieve failed: {type(e).__name__}: {e}"
            ) from e
        status = exc.get("status")

    if status != "succeeded":
        raise MachineFetchError(f"exec {exec_id} status={status}")

    try:
        resp = client.get(
            f"/v1/machines/{mid}/executions/{exec_id}/output",
            headers=_headers(),
        )
        if resp.status_code != 200:
            _raise_api_error(resp)
        out = resp.json()
    except Exception as e:  # noqa: BLE001
        raise MachineFetchError(f"exec output failed: {type(e).__name__}: {e}") from e

    stdout = out.get("stdout")
    if stdout is None:
        raise MachineFetchError(f"exec {exec_id} returned no stdout")

    print(f"[machine_host] fetch_url via machine {mid} exec {exec_id}", flush=True)
    return stdout if isinstance(stdout, str) else stdout.decode("utf-8", errors="replace")
