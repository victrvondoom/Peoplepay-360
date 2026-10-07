"""SSRF guard for user-supplied base URLs (hosted-platform risk).

Policy by deployment mode:
* ``cloud``: https only; any host resolving to loopback, private, link-local,
  CGNAT, multicast, reserved or cloud-metadata ranges is BLOCKED, unless the host
  is on an explicit admin allowlist. Local runtimes (Ollama on a user's laptop) are
  not reachable from here by design -- use a bridge or a reachable endpoint.
* ``self_hosted``: private/loopback permitted (that is the point), but cloud
  metadata addresses stay blocked, and URLs with embedded credentials are refused.

Resolution is pinned: the transport connects to the IP that was validated, so a DNS
answer that changes between check and connect cannot redirect the request.
"""
from __future__ import annotations

import ipaddress
import os
import socket
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .errors import ErrorCode, GatewayError

_METADATA = {ipaddress.ip_address(a) for a in ("169.254.169.254", "fd00:ec2::254", "100.100.100.200", "168.63.129.16")}


@dataclass
class NetPolicy:
    mode: str = "cloud"                       # cloud | self_hosted
    allowlist: frozenset[str] = frozenset()   # hosts an admin explicitly approved
    allow_http: bool = False

    @classmethod
    def from_env(cls) -> "NetPolicy":
        mode = os.environ.get("PEOPLEPAY_DEPLOYMENT", "self_hosted").lower()
        if mode not in ("cloud", "self_hosted"):
            mode = "cloud"  # unknown value: choose the safer one
        allow = frozenset(h.strip().lower() for h in os.environ.get("PEOPLEPAY_MODELS_HOST_ALLOWLIST", "").split(",") if h.strip())
        return cls(mode=mode, allowlist=allow)


def _blocked_reason(ip: ipaddress._BaseAddress, policy: NetPolicy) -> str | None:
    if ip in _METADATA or (ip.version == 6 and ip.ipv4_mapped in _METADATA):
        return "cloud metadata address"
    if policy.mode == "self_hosted":
        return None
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
            or ip.is_reserved or ip.is_unspecified
            or (ip.version == 4 and ip in ipaddress.ip_network("100.64.0.0/10"))):
        return "private or non-public address"
    return None


def validate_url(url: str, policy: NetPolicy, *, resolver=socket.getaddrinfo) -> tuple[str, int, str]:
    """Return (host, port, validated_ip). Raises CUSTOM_ENDPOINT_BLOCKED."""
    def block(msg: str) -> GatewayError:
        return GatewayError(ErrorCode.CUSTOM_ENDPOINT_BLOCKED, msg)

    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise block("only http(s) endpoints are supported")
    if p.username or p.password:
        raise block("credentials must not be embedded in the URL")
    host = (p.hostname or "").lower()
    if not host:
        raise block("URL has no host")
    port = p.port or (443 if p.scheme == "https" else 80)
    allowed = host in policy.allowlist
    if p.scheme == "http" and not (policy.allow_http or allowed or policy.mode == "self_hosted"):
        raise block("plain http is not allowed on this deployment")
    try:
        infos = resolver(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise GatewayError(ErrorCode.PROVIDER_UNAVAILABLE, f"cannot resolve {host}") from exc
    ips = []
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        reason = _blocked_reason(ip, policy)
        if reason and not (allowed and "metadata" not in reason):
            raise block(f"{host} resolves to a {reason}")
        ips.append(str(ip))
    if not ips:
        raise GatewayError(ErrorCode.PROVIDER_UNAVAILABLE, f"cannot resolve {host}")
    return host, port, ips[0]
