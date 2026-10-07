from __future__ import annotations

import ipaddress
from typing import Any


def canonical_client_ip(
    *,
    real_ip: str | None = None,
    forwarded_for: str | None = None,
    peer_ip: str | None = None,
) -> str:
    """Return a stable IP after the trusted edge has rewritten proxy headers."""

    forwarded = (forwarded_for or "").split(",", 1)[0].strip()
    for raw in (real_ip, forwarded, peer_ip):
        candidate = str(raw or "").strip()
        if not candidate:
            continue
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            return address.ipv4_mapped.compressed
        return address.compressed
    return "anonymous"


def request_client_ip(request: Any) -> str:
    peer = request.client.host if request.client is not None else None
    return canonical_client_ip(
        real_ip=request.headers.get("x-real-ip"),
        forwarded_for=request.headers.get("x-forwarded-for"),
        peer_ip=peer,
    )


def scope_client_ip(scope: dict[str, Any]) -> str:
    headers = {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in scope.get("headers", [])
    }
    client = scope.get("client")
    peer = str(client[0]) if client else None
    return canonical_client_ip(
        real_ip=headers.get("x-real-ip"),
        forwarded_for=headers.get("x-forwarded-for"),
        peer_ip=peer,
    )
