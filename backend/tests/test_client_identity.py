from types import SimpleNamespace

from app.client_identity import canonical_client_ip, request_client_ip, scope_client_ip


class Headers(dict):
    def get(self, key, default=None):
        return super().get(key.lower(), default)


def test_canonical_client_ip_normalizes_ipv4_mapped_ipv6() -> None:
    assert canonical_client_ip(peer_ip="::ffff:192.0.2.7") == "192.0.2.7"


def test_canonical_client_ip_uses_edge_real_ip_before_forwarded_chain() -> None:
    assert canonical_client_ip(
        real_ip="203.0.113.8",
        forwarded_for="198.51.100.4, 172.18.0.2",
        peer_ip="172.18.0.3",
    ) == "203.0.113.8"


def test_invalid_forwarding_values_fall_back_to_peer() -> None:
    assert canonical_client_ip(
        real_ip="not-an-address",
        forwarded_for="also-invalid",
        peer_ip="2001:db8::4",
    ) == "2001:db8::4"


def test_request_and_asgi_scope_resolve_the_same_address() -> None:
    request = SimpleNamespace(
        headers=Headers({"x-real-ip": "198.51.100.14"}),
        client=SimpleNamespace(host="172.18.0.4"),
    )
    scope = {
        "headers": [(b"x-real-ip", b"198.51.100.14")],
        "client": ("172.18.0.4", 54321),
    }
    assert request_client_ip(request) == "198.51.100.14"
    assert scope_client_ip(scope) == "198.51.100.14"
