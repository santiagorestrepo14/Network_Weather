import socket

from network_weather.models import ProbeKind, ProbeStatus
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
