import pytest

from network_weather.config import ProbeConfig


@pytest.mark.parametrize("host", ["", "bad host", "https://example.com", "bad\r\nHost:x", "a..b", "-bad.com"])
def test_rejects_invalid_destination(host):
    with pytest.raises(ValueError):
        ProbeConfig(destinations=(host,))


def test_rejects_header_injection_path():
    with pytest.raises(ValueError):
        ProbeConfig(https_path="/\r\nX-Test: injected")


def test_defaults_are_lightweight():
    config = ProbeConfig()
    assert config.interval_seconds >= 5
    assert len(config.destinations) == 2
    assert config.direct_ip_target is None


@pytest.mark.parametrize("target", ["example.com", "192.168.1.1", "127.0.0.1", "0.0.0.0"])
def test_direct_target_requires_public_numeric_ip(target):
    with pytest.raises(ValueError):
        ProbeConfig(direct_ip_target=target)


def test_ip_literal_is_not_misreported_as_dns_lookup():
    with pytest.raises(ValueError, match="direct_ip_target"):
        ProbeConfig(destinations=("1.1.1.1",))
    assert ProbeConfig(direct_ip_target="1.1.1.1").direct_ip_target == "1.1.1.1"
