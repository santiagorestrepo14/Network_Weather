from datetime import UTC, datetime, timedelta

from network_weather.models import MeasurementRound, ProbeKind, ProbeResult, ProbeStatus
from network_weather.weather import Weather, WeatherEngine, classify

BASE = datetime(2026, 1, 1, tzinfo=UTC)
HOSTS = ("a.example", "b.example")


def round_at(index, tcp_fail=False, dns_fail=False, https_fail=False, tcp_ms=20):
    at = BASE + timedelta(seconds=index * 30)
    probes = []
    for host in HOSTS:
        for kind, fail, duration in (
            (ProbeKind.DNS, dns_fail, 2),
            (ProbeKind.TCP, tcp_fail, tcp_ms),
            (ProbeKind.HTTPS, https_fail, 30),
        ):
            probes.append(
                ProbeResult(at, host, kind, ProbeStatus.TIMEOUT if fail else ProbeStatus.SUCCESS,
                            None if fail else duration)
            )
    return MeasurementRound(at, at, tuple(probes))


def test_requires_multiple_rounds():
    result = classify([round_at(0), round_at(1)])
    assert result.weather == Weather.UNKNOWN


def test_stable_probes_are_sunny():
    result = classify([round_at(i) for i in range(3)])
    assert result.weather == Weather.SUNNY
    assert result.confidence > result.severity


def test_one_failed_round_does_not_make_rain():
    result = classify([round_at(0), round_at(1, tcp_fail=True), round_at(2)])
    assert result.weather == Weather.UNKNOWN


def test_persistent_response_failures_make_rain():
    result = classify([round_at(0), round_at(1, tcp_fail=True), round_at(2, tcp_fail=True)])
    assert result.weather == Weather.RAINY
    assert any(e.code == "response_failures" for e in result.evidence)


def test_several_failure_types_make_storm():
    result = classify([round_at(i, tcp_fail=True, dns_fail=True, https_fail=False)
                       for i in range(3)])
    assert result.weather == Weather.STORMY
    assert Weather.RAINY in result.secondary
    assert Weather.FOGGY in result.secondary


def test_engine_requires_hysteresis():
    engine = WeatherEngine()
    assert engine.add(round_at(0)).weather == Weather.UNKNOWN
    assert engine.add(round_at(1)).weather == Weather.UNKNOWN
    assert engine.add(round_at(2)).weather == Weather.UNKNOWN
    assert engine.add(round_at(3)).weather == Weather.SUNNY


def test_route_change_resets_classification_window():
    engine = WeatherEngine()
    for index in range(4):
        original = round_at(index)
        round_ = MeasurementRound(original.started_at, original.finished_at,
                                  original.probes, route_adapter="Wi-Fi")
        engine.add(round_)
    changed = round_at(5)
    result = engine.add(MeasurementRound(changed.started_at, changed.finished_at,
                                        changed.probes, route_adapter="Ethernet"))
    assert result.weather == Weather.UNKNOWN
    assert result.sample_rounds == 1
