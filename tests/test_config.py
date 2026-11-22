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
