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


def test_gateway_ping_failure_does_not_override_external_success():
    rounds = []
    for index in range(3):
        base = round_at(index)
        icmp = ProbeResult(base.started_at, "192.0.2.1", ProbeKind.ICMP,
                           ProbeStatus.ICMP_ERROR, None)
        rounds.append(MeasurementRound(base.started_at, base.finished_at,
                                       (*base.probes, icmp)))
    result = classify(rounds)
    assert result.weather == Weather.SUNNY
    assert any(e.code == "gateway_echo_unanswered" for e in result.evidence)


def test_one_failed_round_does_not_make_rain():
    result = classify([round_at(0), round_at(1, tcp_fail=True), round_at(2)])
    assert result.weather == Weather.UNKNOWN


def test_persistent_response_failures_make_rain():
    result = classify([round_at(0), round_at(1, tcp_fail=True), round_at(2, tcp_fail=True)])
    assert result.weather == Weather.RAINY
    assert any(e.code == "response_failures" for e in result.evidence)


def test_cached_dns_success_does_not_hide_repeated_external_outage():
    rounds = [round_at(0), round_at(1, tcp_fail=True, https_fail=True),
              round_at(2, tcp_fail=True, https_fail=True)]
    result = classify(rounds)
    assert result.weather == Weather.OFFLINE
    assert any(e.code == "multi_target_outage" for e in result.evidence)
    assert result.cause is None


def test_one_outage_round_or_missing_probes_cannot_confirm_offline():
    one_failure = [round_at(0), round_at(1),
                   round_at(2, tcp_fail=True, https_fail=True)]
    assert classify(one_failure).weather != Weather.OFFLINE
    incomplete = round_at(2, tcp_fail=True, https_fail=True)
    incomplete = MeasurementRound(
        incomplete.started_at, incomplete.finished_at,
        tuple(p for p in incomplete.probes
              if not (p.destination == "b.example" and p.kind == ProbeKind.HTTPS)),
    )
    assert classify([round_at(0), round_at(1, tcp_fail=True, https_fail=True),
                     incomplete]).weather != Weather.OFFLINE


def test_tls_error_is_evidence_of_external_contact_not_offline():
    rounds = [round_at(0)]
    for index in (1, 2):
        original = round_at(index, tcp_fail=True, https_fail=True)
        probes = tuple(
            ProbeResult(p.at, p.destination, p.kind, ProbeStatus.TLS_ERROR, None)
            if p.kind == ProbeKind.HTTPS else p for p in original.probes
        )
        rounds.append(MeasurementRound(original.started_at, original.finished_at, probes))
    assert classify(rounds).weather != Weather.OFFLINE


def test_latency_baselines_keep_targets_separate():
    rounds = []
    for index in range(3):
        original = round_at(index)
        probes = tuple(
            ProbeResult(p.at, p.destination, p.kind, p.status, 300.0)
            if p.kind == ProbeKind.TCP and p.destination == "a.example" else p
            for p in original.probes
        )
        rounds.append(MeasurementRound(original.started_at, original.finished_at, probes))
    result = classify(rounds, {"a.example": 300.0, "b.example": 20.0})
    assert result.weather == Weather.SUNNY
    uncertain = classify(rounds)
    assert uncertain.weather == Weather.UNKNOWN
    assert any(e.code == "single_target_latency" for e in uncertain.evidence)


def test_multi_target_latency_uses_each_targets_baseline():
    rounds = [round_at(index, tcp_ms=220) for index in range(3)]
    result = classify(rounds, {"a.example": 30.0, "b.example": 40.0})
    assert result.weather == Weather.CLOUDY
    assert len([e for e in result.evidence if e.code == "high_latency"]) == 2


def test_engine_baseline_uses_prior_samples_only_per_target():
    engine = WeatherEngine()
    for index in range(11):
        engine.add(round_at(index, tcp_ms=20))
    assert engine._baseline() == {"a.example": 20.0, "b.example": 20.0}


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


def test_long_observation_gap_resets_classification_and_baseline():
    engine = WeatherEngine(interval_seconds=30)
    for index in range(12):
        engine.add(round_at(index))
    assert engine.current == Weather.SUNNY
    assert engine._baseline() == {"a.example": 20.0, "b.example": 20.0}
    resumed = round_at(100, tcp_fail=True, https_fail=True)
    assert engine.observation_gap(resumed)
    result = engine.add(resumed)
    assert result.weather == Weather.UNKNOWN
    assert result.sample_rounds == 1
    assert engine._baseline() == {}


def test_configured_slow_interval_is_not_mistaken_for_sleep():
    engine = WeatherEngine(interval_seconds=3600)
    first = round_at(0)
    later = round_at(200)
    engine.add(first)
    assert not engine.observation_gap(later)
    assert engine.add(later).sample_rounds == 2


def test_dns_failure_with_repeated_direct_ip_success_is_foggy():
    def blocked_dns(index, direct_ok):
        at = BASE + timedelta(seconds=index * 30)
        probes = [
            ProbeResult(at, host, ProbeKind.DNS, ProbeStatus.DNS_ERROR, None)
            for host in HOSTS
        ]
        probes.append(ProbeResult(
            at, "1.1.1.1", ProbeKind.TCP,
            ProbeStatus.SUCCESS if direct_ok else ProbeStatus.TIMEOUT,
            15.0 if direct_ok else None,
        ))
        return MeasurementRound(at, at, tuple(probes))

    rounds = [blocked_dns(index, True) for index in range(3)]
    result = classify(rounds)
    assert result.weather == Weather.FOGGY
    assert {e.code for e in result.evidence} == {"dns_failures", "direct_ip_tcp_replied"}
    assert classify([blocked_dns(index, False) for index in range(3)]).weather == Weather.UNKNOWN
    engine = WeatherEngine()
    for index in range(4):
        result = engine.add(blocked_dns(index, True))
    assert result.weather == Weather.FOGGY


def test_verified_https_via_system_route_supports_foggy_when_local_dns_fails():
    rounds = []
    for index in range(3):
        at = BASE + timedelta(seconds=index * 30)
        probes = tuple(
            ProbeResult(at, host, ProbeKind.DNS, ProbeStatus.DNS_ERROR, None)
            for host in HOSTS
        ) + tuple(
            ProbeResult(at, host, ProbeKind.HTTPS, ProbeStatus.SUCCESS, 40.0,
                        detail="WinHTTP system route", http_status=200)
            for host in HOSTS
        )
        rounds.append(MeasurementRound(at, at, probes))
    result = classify(rounds)
    assert result.weather == Weather.FOGGY
    assert {e.code for e in result.evidence} == {"dns_failures", "https_without_local_dns"}


def test_direct_ip_success_vetoes_offline_even_when_name_targets_fail():
    rounds = [round_at(0)]
    for index in (1, 2):
        failed = round_at(index, tcp_fail=True, https_fail=True)
        direct = ProbeResult(failed.started_at, "1.1.1.1", ProbeKind.TCP,
                             ProbeStatus.SUCCESS, 14.0)
        rounds.append(MeasurementRound(failed.started_at, failed.finished_at,
                                       (*failed.probes, direct)))
    result = classify(rounds)
    assert result.weather != Weather.OFFLINE
    assert any(e.code == "direct_ip_tcp_replied" for e in result.evidence)
