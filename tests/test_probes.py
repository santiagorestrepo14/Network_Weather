import socket
from datetime import UTC, datetime

from network_weather.models import ProbeKind, ProbeResult, ProbeStatus
from network_weather.probes import probe_destination, probe_direct_ip, probe_tcp


def test_dns_failure_does_not_invent_tcp_or_https_attempts(monkeypatch):
    def fail(*_args, **_kwargs):
        raise socket.gaierror("lookup failed")

    monkeypatch.setattr(socket, "getaddrinfo", fail)
    results = probe_destination("bad.example", 0.2)
    assert len(results) == 1
    assert results[0].kind == ProbeKind.DNS
    assert results[0].status == ProbeStatus.DNS_ERROR
    assert results[0].duration_ms is None


def test_tcp_probe_uses_a_real_local_socket():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        info = (socket.AF_INET, socket.SOCK_STREAM, 0, "", server.getsockname())
        result = probe_tcp("localhost", info, 1)
        assert result.status == ProbeStatus.SUCCESS
        assert result.duration_ms is not None
        assert result.address == "127.0.0.1"
        assert result.local_address == "127.0.0.1"


def test_direct_ip_probe_does_not_invoke_dns(monkeypatch):
    from network_weather import probes

    captured = {}

    def fake_tcp(host, info, timeout):
        captured.update(host=host, info=info, timeout=timeout)
        return "observed TCP result"

    monkeypatch.setattr(probes, "probe_tcp", fake_tcp)
    monkeypatch.setattr(socket, "getaddrinfo",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("DNS called")))
    assert probe_direct_ip("1.1.1.1", 0.5) == "observed TCP result"
    assert captured["host"] == "1.1.1.1"
    assert captured["info"][4] == ("1.1.1.1", 443)
    assert captured["timeout"] == 0.5


def test_destination_uses_second_address_when_first_is_unreachable(monkeypatch):
    from network_weather import probes

    at = datetime(2026, 1, 1, tzinfo=UTC)
    ipv6 = (socket.AF_INET6, socket.SOCK_STREAM, 0, "", ("2001:db8::1", 443, 0, 0))
    ipv4 = (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.0.2.1", 443))
    dns = ProbeResult(at, "host.example", ProbeKind.DNS, ProbeStatus.SUCCESS, 1)
    monkeypatch.setattr(probes, "probe_dns", lambda _host: (dns, [ipv6, ipv4]))
    attempts = []

    def fake_tcp(host, info, _timeout):
        attempts.append(("tcp", info[4][0]))
        ok = info == ipv4
        return ProbeResult(at, host, ProbeKind.TCP,
                           ProbeStatus.SUCCESS if ok else ProbeStatus.TIMEOUT,
                           12 if ok else None, address=info[4][0])

    def fake_https(host, info, _timeout, _path):
        attempts.append(("https", info[4][0]))
        return ProbeResult(at, host, ProbeKind.HTTPS, ProbeStatus.SUCCESS, 25,
                           address=info[4][0], http_status=200)

    monkeypatch.setattr(probes, "probe_tcp", fake_tcp)
    monkeypatch.setattr(probes, "probe_https", fake_https)
    _, tcp, https = probe_destination("host.example", 0.5)
    assert attempts == [("tcp", "2001:db8::1"), ("tcp", "192.0.2.1"),
                        ("https", "192.0.2.1")]
    assert tcp.ok and https.ok
    assert tcp.duration_ms == 12
    assert "Fallback" in tcp.detail


def test_destination_reports_failure_when_both_addresses_fail(monkeypatch):
    from network_weather import probes

    at = datetime(2026, 1, 1, tzinfo=UTC)
    addresses = [
        (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.0.2.1", 443)),
        (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.0.2.2", 443)),
    ]
    dns = ProbeResult(at, "host.example", ProbeKind.DNS, ProbeStatus.SUCCESS, 1)
    monkeypatch.setattr(probes, "probe_dns", lambda _host: (dns, addresses))
    calls = []

    def fail(kind):
        def probe(host, info, *_args):
            calls.append((kind, info[4][0]))
            return ProbeResult(at, host, kind, ProbeStatus.TCP_ERROR, None,
                               address=info[4][0])
        return probe

    monkeypatch.setattr(probes, "probe_tcp", fail(ProbeKind.TCP))
    monkeypatch.setattr(probes, "probe_https", fail(ProbeKind.HTTPS))
    _, tcp, https = probe_destination("host.example", 0.5)
    assert len(calls) == 4
    assert not tcp.ok and not https.ok
    assert "192.0.2.1" in tcp.detail and "192.0.2.2" in tcp.detail
