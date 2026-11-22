from datetime import UTC, datetime

from network_weather.config import ProbeConfig
from network_weather.models import AdapterSnapshot, ProbeKind, ProbeResult, ProbeStatus


def test_ipv6_socket_identifies_adapter_and_gateway(monkeypatch):
    from network_weather import collector

    at = datetime(2026, 1, 1, tzinfo=UTC)
    adapter = AdapterSnapshot("Ethernet", True, ("192.0.2.5",), ipv6=("2001:db8::5",))
    monkeypatch.setattr(collector, "get_adapters", lambda: (adapter,))
    monkeypatch.setattr(collector, "probe_destination", lambda host, *_args: (
        ProbeResult(at, host, ProbeKind.DNS, ProbeStatus.SUCCESS, 1),
        ProbeResult(at, host, ProbeKind.TCP, ProbeStatus.SUCCESS, 10,
                    local_address="2001:db8::5"),
        ProbeResult(at, host, ProbeKind.HTTPS, ProbeStatus.SUCCESS, 20,
                    local_address="2001:db8::5"),
    ))

    class FakeCache:
        def invalidate(self):
            pass

        def for_adapter(self, name):
            assert name == "Ethernet"
            return "192.0.2.1"

    monkeypatch.setattr(collector, "_gateways", FakeCache())
    monkeypatch.setattr(collector, "_last_route_adapter", None)
    monkeypatch.setattr(collector, "ping_gateway", lambda address: ProbeResult(
        at, address, ProbeKind.ICMP, ProbeStatus.SUCCESS, None,
    ))
    round_ = collector.collect_once(ProbeConfig())
    assert round_.route_adapter == "Ethernet"
    assert round_.gateway_address == "192.0.2.1"
    assert round_.probes[-1].kind == ProbeKind.ICMP

