import json
from types import SimpleNamespace

from network_weather.models import ProbeKind, ProbeStatus
from network_weather.windows_network import GatewayCache, discover_gateways, ping_gateway


def test_gateway_discovery_ignores_invalid_addresses(monkeypatch):
    from network_weather import windows_network

    data = [
        {"name": "Ethernet", "gateway": ["192.0.2.1"]},
        {"name": "VPN", "gateway": [None, "bad"]},
        {"name": "Other", "gateway": ["0.0.0.0"]},
    ]
    monkeypatch.setattr(windows_network.sys, "platform", "win32")
    monkeypatch.setattr(windows_network.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(
        returncode=0, stdout=json.dumps(data),
    ))
    assert discover_gateways() == {"Ethernet": "192.0.2.1"}


def test_gateway_cache_avoids_repeated_powershell_calls(monkeypatch):
    from network_weather import windows_network

    calls = []
    monkeypatch.setattr(windows_network, "discover_gateways", lambda: calls.append(1) or {"Ethernet": "192.0.2.1"})
    monkeypatch.setattr(windows_network.time, "monotonic", lambda: 100.0)
    cache = GatewayCache(ttl_seconds=300)
    assert cache.for_adapter("Ethernet") == "192.0.2.1"
    assert cache.for_adapter("Ethernet") == "192.0.2.1"
    assert len(calls) == 1
    cache.invalidate()
    assert cache.for_adapter("Ethernet") == "192.0.2.1"
    assert len(calls) == 2


def test_unanswered_icmp_is_not_reported_as_rtt(monkeypatch):
    from network_weather import windows_network

    monkeypatch.setattr(windows_network.sys, "platform", "win32")
    monkeypatch.setattr(windows_network.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(
        returncode=1,
    ))
    result = ping_gateway("192.0.2.1")
    assert result.kind == ProbeKind.ICMP
    assert result.status == ProbeStatus.ICMP_ERROR
    assert result.duration_ms is None
    assert "filter" in result.detail

