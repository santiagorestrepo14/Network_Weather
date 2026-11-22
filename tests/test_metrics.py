from datetime import UTC, datetime, timedelta

from network_weather.metrics import summarize
from network_weather.models import ProbeKind, ProbeResult, ProbeStatus

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def sample(second, duration, status=ProbeStatus.SUCCESS, host="example.com"):
    return ProbeResult(BASE + timedelta(seconds=second), host, ProbeKind.TCP, status, duration)


def test_jitter_uses_only_adjacent_successes():
    results = [
        sample(0, 10),
        sample(1, 20),
        sample(2, None, ProbeStatus.TIMEOUT),
        sample(3, 50),
        sample(4, 70),
        sample(5, 999, host="other.example"),
    ]
    summary = summarize(results, "example.com", ProbeKind.TCP)
    assert summary.attempted == 5
    assert summary.successful == 4
    assert summary.median_ms == 35
    assert summary.jitter_ms == 15
    assert summary.failure_percent == 20


def test_absent_samples_are_unknown():
    summary = summarize([], "example.com", ProbeKind.HTTPS)
    assert summary.attempted == 0
    assert summary.median_ms is None
    assert summary.jitter_ms is None
    assert summary.failure_percent is None


def test_icmp_success_without_parsed_rtt_is_still_success():
    result = ProbeResult(BASE, "192.0.2.1", ProbeKind.ICMP, ProbeStatus.SUCCESS, None)
    summary = summarize([result], "192.0.2.1", ProbeKind.ICMP)
    assert summary.successful == 1
    assert summary.failure_percent == 0
    assert summary.median_ms is None
