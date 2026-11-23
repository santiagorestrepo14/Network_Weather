import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from network_weather.history import HistoryStore
from network_weather.history_chart import weather_segments
from network_weather.models import (
    AdapterSnapshot,
    MeasurementRound,
    ProbeKind,
    ProbeResult,
    ProbeStatus,
    WifiSnapshot,
)
from network_weather.weather import Classification, Evidence, Weather


def test_history_survives_reopening(tmp_path):
    at = datetime(2026, 1, 1, tzinfo=UTC)
    round_ = MeasurementRound(
        at, at,
        (ProbeResult(at, "example.com", ProbeKind.DNS, ProbeStatus.SUCCESS, 12.5),),
        (AdapterSnapshot("Ethernet", True, ("192.0.2.5",), 1000, 10, 20,
                         ("2001:db8::5",)),),
        route_adapter="Ethernet",
        gateway_address="192.0.2.1",
        wifi=(WifiSnapshot("Test radio", 70, -60, 44),),
    )
    classification = Classification(
        Weather.UNKNOWN, (), 0.2, 0.0,
        (Evidence("insufficient_rounds", "Need more samples", 1, 3),), 1,
    )
    path = tmp_path / "history.db"
    with HistoryStore(path) as store:
        store.save(round_, classification)
    with HistoryStore(path) as store:
        loaded = store.recent_rounds()
        assert len(loaded) == 1
        assert loaded[0].probes == round_.probes
        assert loaded[0].adapters == round_.adapters
        assert loaded[0].gateway_address == "192.0.2.1"
        assert loaded[0].wifi == round_.wifi
        assert store.recent_weather() == [(at.isoformat(), Weather.UNKNOWN)]


def test_read_only_history_queries_existing_database_without_writing(tmp_path):
    path = tmp_path / "history with spaces.db"
    with HistoryStore(path):
        pass
    with HistoryStore(path, read_only=True) as store:
        assert store.recent_rounds() == []
        assert store.incidents() == []
        with pytest.raises(sqlite3.OperationalError):
            store.connection.execute("INSERT INTO schema_meta VALUES ('read_only', '1')")


def test_read_only_history_does_not_create_missing_database(tmp_path):
    path = tmp_path / "missing" / "history.db"
    with pytest.raises(sqlite3.OperationalError):
        HistoryStore(path, read_only=True)
    assert not path.parent.exists()


def test_incident_stays_open_through_uncertainty_and_closes_after_recovery(tmp_path):
    path = tmp_path / "incidents.db"
    with HistoryStore(path) as store:
        for index, weather in enumerate((Weather.RAINY, Weather.UNKNOWN, Weather.SUNNY, Weather.SUNNY)):
            at = datetime(2026, 1, 1, 0, index, tzinfo=UTC)
            round_ = MeasurementRound(at, at, ())
            classification = Classification(
                weather, (), 0.8, 0.5 if weather == Weather.RAINY else 0.0,
                (Evidence("test", "test evidence"),), 3,
            )
            store.save(round_, classification)
            store.advance_incident(round_, classification)
            if index in (0, 1, 2):
                assert store.incidents()[0]["ended_at"] is None
        incidents = store.incidents()
        assert len(incidents) == 1
        assert incidents[0]["ended_at"] == datetime(2026, 1, 1, 0, 3, tzinfo=UTC).isoformat()


def test_route_change_ends_incident_without_claiming_recovery(tmp_path):
    at = datetime(2026, 1, 1, tzinfo=UTC)
    with HistoryStore(tmp_path / "route.db") as store:
        round_ = MeasurementRound(at, at, (), route_adapter="Wi-Fi")
        result = Classification(Weather.RAINY, (), 0.8, 0.5,
                                (Evidence("response_failures", "timeouts"),), 3)
        store.save(round_, result)
        store.advance_incident(round_, result)
        store.end_active_incident_for_route_change(at + timedelta(minutes=1))
        incident = store.incidents()[0]
        assert incident["ended_at"] is not None
        assert incident["evidence"][-1]["code"] == "route_changed"


def test_range_keeps_weather_categorical_and_filters_latency_destination(tmp_path):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    with HistoryStore(tmp_path / "series.db") as store:
        for minute, weather, first_ms in (
            (0, Weather.SUNNY, 10.0),
            (1, Weather.RAINY, 20.0),
            (15, Weather.UNKNOWN, 30.0),
        ):
            at = start + timedelta(minutes=minute)
            probes = (
                ProbeResult(at, "one.example", ProbeKind.TCP, ProbeStatus.SUCCESS, first_ms),
                ProbeResult(at, "two.example", ProbeKind.TCP, ProbeStatus.SUCCESS, 1000.0),
            )
            round_ = MeasurementRound(at, at, probes)
            classification = Classification(weather, (), 0.8, 0.0, (), 3)
            store.save(round_, classification)
        series = store.history_range(start, start + timedelta(hours=1),
                                     destination="one.example", max_bins=60)
        assert [point.weather for point in series.weather] == [
            Weather.SUNNY, Weather.RAINY, Weather.UNKNOWN,
        ]
        assert [bucket.mean_ms for bucket in series.latency] == [10.0, 20.0, 30.0]
        assert series.destinations == ("one.example", "two.example")
        assert series.gap_threshold_seconds < 14 * 60
        segments = weather_segments(series)
        assert [state for _, _, state in segments] == [
            Weather.SUNNY, Weather.RAINY, Weather.UNKNOWN,
        ]
        assert segments[0][1] == start + timedelta(minutes=1)
        assert segments[1][1] < start + timedelta(minutes=15)


def test_last_weather_observation_does_not_fill_a_long_unobserved_gap(tmp_path):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    with HistoryStore(tmp_path / "gap.db") as store:
        for seconds in (0, 30, 60, 90):
            at = start + timedelta(seconds=seconds)
            store.save(MeasurementRound(at, at, ()),
                       Classification(Weather.SUNNY, (), 0.8, 0.0, (), 4))
        series = store.history_range(start, start + timedelta(minutes=5))
    segments = weather_segments(series)
    assert series.typical_interval_seconds == 30
    assert [end for _, end, _ in segments[:3]] == [
        start + timedelta(seconds=value) for value in (30, 60, 90)
    ]
    assert segments[-1][1] == start + timedelta(seconds=135)
    assert segments[-1][1] < series.end


def test_preexisting_rounds_backfill_samples_once(tmp_path):
    path = tmp_path / "legacy.db"
    at = datetime(2026, 1, 1, tzinfo=UTC)
    round_ = MeasurementRound(
        at, at,
        (ProbeResult(at, "example.com", ProbeKind.TCP, ProbeStatus.SUCCESS, 42.0),),
    )
    connection = sqlite3.connect(path)
    connection.execute("""CREATE TABLE rounds (
        id INTEGER PRIMARY KEY, started_at TEXT, finished_at TEXT, data TEXT,
        weather TEXT, confidence REAL, severity REAL, evidence TEXT)""")
    connection.execute("INSERT INTO rounds VALUES (1, ?, ?, ?, 'sunny', 0.8, 0, '[]')",
                       (at.isoformat(), at.isoformat(), json.dumps(round_.to_dict())))
    connection.commit()
    connection.close()
    for _ in range(2):
        with HistoryStore(path) as store:
            series = store.history_range(at - timedelta(minutes=1), at + timedelta(minutes=1))
            assert len(series.latency) == 1
            count = store.connection.execute("SELECT COUNT(*) FROM probe_samples").fetchone()[0]
            assert count == 1


def test_retention_removes_indexed_samples_with_old_rounds(tmp_path):
    at = datetime(2020, 1, 1, tzinfo=UTC)
    with HistoryStore(tmp_path / "retention.db") as store:
        round_ = MeasurementRound(
            at, at,
            (ProbeResult(at, "example.com", ProbeKind.TCP, ProbeStatus.SUCCESS, 5),),
        )
        store.save(round_, Classification(Weather.SUNNY, (), 0.8, 0, (), 3))
        assert store.prune(30) == 1
        assert store.connection.execute("SELECT COUNT(*) FROM probe_samples").fetchone()[0] == 0


def test_retention_does_not_leave_stale_incident_active(tmp_path):
    at = datetime(2020, 1, 1, tzinfo=UTC)
    with HistoryStore(tmp_path / "stale-incident.db") as store:
        round_ = MeasurementRound(at, at, ())
        result = Classification(Weather.RAINY, (), 0.8, 0.5, (), 3)
        store.save(round_, result)
        store.advance_incident(round_, result)
        assert store.incidents()[0]["ended_at"] is None
        store.prune(30)
        assert store.incidents() == []
