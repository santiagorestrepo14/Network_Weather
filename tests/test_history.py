from datetime import UTC, datetime, timedelta

from network_weather.history import HistoryStore
from network_weather.models import (
    AdapterSnapshot,
    MeasurementRound,
    ProbeKind,
    ProbeResult,
    ProbeStatus,
)
from network_weather.weather import Classification, Evidence, Weather


def test_history_survives_reopening(tmp_path):
    at = datetime(2026, 1, 1, tzinfo=UTC)
    round_ = MeasurementRound(
        at, at,
        (ProbeResult(at, "example.com", ProbeKind.DNS, ProbeStatus.SUCCESS, 12.5),),
        (AdapterSnapshot("Ethernet", True, ("192.0.2.5",), 1000, 10, 20),),
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
        assert store.recent_weather() == [(at.isoformat(), Weather.UNKNOWN)]


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
