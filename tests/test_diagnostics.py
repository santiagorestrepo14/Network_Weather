from datetime import UTC, datetime, timedelta

from network_weather.diagnostics import recent_diagnostics
from network_weather.models import MeasurementRound, ProbeKind, ProbeResult, ProbeStatus

START = datetime(2026, 11, 22, tzinfo=UTC)


def a_round(index: int, value: float | None, adapter: str = "Ethernet") -> MeasurementRound:
    at = START + timedelta(seconds=index * 30)
    probe = ProbeResult(at, "example.com", ProbeKind.TCP,
                        ProbeStatus.SUCCESS if value is not None else ProbeStatus.TIMEOUT,
                        value)
    return MeasurementRound(at, at, (probe,), route_adapter=adapter)


def test_recent_diagnostics_exposes_sample_counts_and_percentile():
    summary = recent_diagnostics([
        a_round(0, 10), a_round(1, 20), a_round(2, None),
        a_round(3, 50), a_round(4, 70),
    ], 30)
    row = summary.rows[0]
    assert summary.rounds == 5
    assert row.attempted == 5
    assert row.successful == 4
    assert row.median_ms == 35
    assert row.p95_ms == 70
    assert row.jitter_ms == 15
    assert row.variation_pairs == 2
    assert row.failure_percent == 20


def test_diagnostic_window_excludes_previous_route_and_long_pause():
    summary = recent_diagnostics([
        a_round(0, 10, "Wi-Fi"),
        a_round(1, 20, "Ethernet"),
        a_round(100, 30, "Ethernet"),
        a_round(101, 40, "Ethernet"),
    ], 30)
    assert summary.rounds == 2
    assert summary.rows[0].attempted == 2
    assert summary.rows[0].jitter_ms == 10


def test_empty_diagnostics_have_no_invented_metrics():
    assert recent_diagnostics([], 30).rows == ()
