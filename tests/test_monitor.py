from datetime import UTC, datetime, timedelta

from network_weather.config import ProbeConfig
from network_weather.models import MeasurementRound, ProbeKind, ProbeResult, ProbeStatus
from network_weather.monitor import Monitor
from network_weather.weather import Weather


def test_monitor_persists_and_restores_classification_window(tmp_path, monkeypatch):
    rounds = []
    start = datetime.now(UTC)
    for index in range(4):
        at = start + timedelta(seconds=index * 30)
        probes = tuple(
            ProbeResult(at, host, kind, ProbeStatus.SUCCESS, 10.0)
            for host in ("a.example", "b.example")
            for kind in (ProbeKind.DNS, ProbeKind.TCP, ProbeKind.HTTPS)
        )
        rounds.append(MeasurementRound(at, at, probes))
    iterator = iter(rounds)
    monkeypatch.setattr("network_weather.monitor.collect_once", lambda _config: next(iterator))
    database = tmp_path / "history.db"
    config = ProbeConfig(destinations=("a.example", "b.example"))
    with Monitor(config, database) as monitor:
        for _ in range(3):
            monitor.measure()
        assert len(monitor.history.recent_rounds()) == 3
    with Monitor(config, database) as monitor:
        _, classification = monitor.measure()
        assert classification.weather == Weather.SUNNY
        assert len(monitor.history.recent_rounds()) == 4


def test_monitor_closes_incident_at_last_observation_after_long_gap(tmp_path, monkeypatch):
    start = datetime.now(UTC) - timedelta(hours=3)

    def failed_round(at):
        probes = tuple(
            ProbeResult(at, host, kind, ProbeStatus.TIMEOUT, None)
            for host in ("a.example", "b.example")
            for kind in (ProbeKind.DNS, ProbeKind.TCP, ProbeKind.HTTPS)
        )
        return MeasurementRound(at, at, probes)

    rounds = [failed_round(start + timedelta(seconds=30 * index)) for index in range(4)]
    resumed = failed_round(start + timedelta(hours=2))
    iterator = iter([*rounds, resumed])
    monkeypatch.setattr("network_weather.monitor.collect_once", lambda _config: next(iterator))
    database = tmp_path / "history.db"
    config = ProbeConfig(destinations=("a.example", "b.example"))
    with Monitor(config, database) as monitor:
        for _ in rounds:
            monitor.measure()
        assert monitor.history.incidents()[0]["ended_at"] is None
    with Monitor(config, database) as monitor:
        _, classification = monitor.measure()
        assert classification.weather == Weather.UNKNOWN
        incident = monitor.history.incidents()[0]
        assert incident["ended_at"] == rounds[-1].finished_at.isoformat()
        assert incident["evidence"][-1]["code"] == "observation_gap"
