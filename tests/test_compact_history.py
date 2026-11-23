from datetime import UTC, datetime, timedelta

import pytest

from network_weather.compact_history import (
    CompactPoint,
    compact_points,
    compact_time_labels,
    visible_segments,
)
from network_weather.models import MeasurementRound, ProbeKind, ProbeResult, ProbeStatus

START = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)


def a_round(seconds: int, timings: dict[str, float | None]) -> MeasurementRound:
    at = START + timedelta(seconds=seconds)
    return MeasurementRound(at, at, tuple(
        ProbeResult(at, destination, ProbeKind.TCP,
                    ProbeStatus.SUCCESS if duration is not None else ProbeStatus.TIMEOUT,
                    duration)
        for destination, duration in timings.items()
    ))


def test_compact_values_compare_same_destination_in_adjacent_rounds():
    points = compact_points([
        a_round(0, {"a": 20, "b": 100}),
        a_round(30, {"a": 35, "b": 90}),
    ])
    assert points[0].latency_ms == 60
    assert points[0].variation_ms is None
    assert points[1].latency_ms == 62.5
    assert points[1].variation_ms == 12.5


def test_failure_and_long_pause_break_variation_and_visible_line():
    points = compact_points([
        a_round(0, {"a": 20}),
        a_round(30, {"a": None}),
        a_round(60, {"a": 30}),
        a_round(90, {"a": 35}),
        a_round(900, {"a": 80}),
    ])
    assert [point.variation_ms for point in points] == [None, None, None, 5, None]
    assert [(a.at, b.at) for a, b in visible_segments(points, "latency")] == [
        (points[2].at, points[3].at)]
    assert visible_segments(points, "variation") == ()


def test_unknown_metric_is_rejected():
    with pytest.raises(ValueError):
        CompactPoint(START, 20, None).value("unknown")


def test_optional_direct_ip_does_not_change_hostname_tcp_chart():
    at = START
    round_ = MeasurementRound(at, at, (
        ProbeResult(at, "example.com", ProbeKind.TCP, ProbeStatus.SUCCESS, 20.0),
        ProbeResult(at, "1.1.1.1", ProbeKind.TCP, ProbeStatus.SUCCESS, 500.0),
    ))
    assert compact_points([round_])[0].latency_ms == 20.0


def test_nearby_chart_endpoints_show_seconds():
    first, last = compact_time_labels(START, START + timedelta(seconds=30))
    assert first != last
    assert first.endswith(":00")
    assert last.endswith(":30")
