"""Conservative weather classification from observed, comparable probe rounds."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise
from statistics import median

from network_weather.models import MeasurementRound, ProbeKind, ProbeResult


class Weather(StrEnum):
    SUNNY = "sunny"
    CLOUDY = "cloudy"
    WINDY = "windy"
    RAINY = "rainy"
    FOGGY = "foggy"
    STORMY = "stormy"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Evidence:
    code: str
    detail: str
    observed: float | None = None
    threshold: float | None = None


@dataclass(frozen=True, slots=True)
class Classification:
    weather: Weather
    secondary: tuple[Weather, ...]
    confidence: float
    severity: float
    evidence: tuple[Evidence, ...]
    sample_rounds: int
    # A cause is never assigned from these probes alone.
    cause: str | None = None


def _rate(results: list[ProbeResult]) -> float | None:
    return (sum(not r.ok for r in results) / len(results)) if results else None


def _comparable_jitter(results: list[ProbeResult]) -> float | None:
    by_destination: dict[str, list[ProbeResult]] = {}
    for result in results:
        by_destination.setdefault(result.destination, []).append(result)
    differences = []
    for sequence in by_destination.values():
        sequence.sort(key=lambda r: r.at)
        for previous, current in pairwise(sequence):
            if previous.ok and current.ok and previous.duration_ms is not None and current.duration_ms is not None:
                differences.append(abs(current.duration_ms - previous.duration_ms))
    return median(differences) if differences else None


def classify(rounds: list[MeasurementRound], baseline_ms: float | None = None) -> Classification:
    """Classify the last five rounds. A single event never yields a problem state.

    HTTPS/TCP failures are response failures, not a measured IP packet-loss rate.
    DNS-only failures do not prove that Internet access is unavailable. TLS
    errors do not prove an outage either. Severity and confidence are separate.
    """
    recent = rounds[-5:]
    if len(recent) < 3:
        return Classification(
            Weather.UNKNOWN, (), 0.0, 0.0,
            (Evidence("insufficient_rounds", "At least three rounds are required", len(recent), 3),),
            len(recent),
        )
    probes = [probe for round_ in recent for probe in round_.probes]
    dns = [p for p in probes if p.kind == ProbeKind.DNS]
    tcp = [p for p in probes if p.kind == ProbeKind.TCP]
    https = [p for p in probes if p.kind == ProbeKind.HTTPS]
    if not dns or not tcp or not https:
        return Classification(
            Weather.UNKNOWN, (), 0.2, 0.0,
            (Evidence("missing_protocol", "DNS, TCP and HTTPS evidence required"),), len(recent),
        )
    destinations = {p.destination for p in dns}
    if len(destinations) < 2:
        return Classification(
            Weather.UNKNOWN, (), 0.3, 0.0,
            (Evidence("single_destination", "At least two destinations required for classification"),),
            len(recent),
        )

    dns_rate = _rate(dns) or 0.0
    tcp_rate = _rate(tcp) or 0.0
    https_rate = _rate(https) or 0.0
    tcp_success = [p.duration_ms for p in tcp if p.ok and p.duration_ms is not None]
    latency = median(tcp_success) if tcp_success else None
    jitter = _comparable_jitter(tcp)
    evidence: list[Evidence] = []
    problems: list[Weather] = []

    # A failed destination alone cannot establish an Internet outage.
    all_destinations_failed = all(
        not any(p.ok for p in https if p.destination == host)
        for host in destinations
    )
    tcp_all_failed = not any(p.ok for p in tcp)
    if all_destinations_failed and tcp_all_failed and dns_rate >= 0.5:
        evidence.append(Evidence("multi_target_outage", "No TCP or HTTPS response from multiple destinations", https_rate, 1.0))
        return Classification(Weather.OFFLINE, (), 0.8, 1.0, tuple(evidence), len(recent))

    if dns_rate >= 0.4:
        problems.append(Weather.FOGGY)
        evidence.append(Evidence("dns_failures", "DNS resolution failed for several probes", dns_rate, 0.4))
    if tcp_rate >= 0.2 or https_rate >= 0.2:
        # TLS errors are not response loss; record the contradiction separately.
        network_https = [p for p in https if p.status.value in {"timeout", "tcp_error", "http_error"}]
        network_rate = len(network_https) / len(https)
        failed_rounds = sum(
            any(p.kind in (ProbeKind.TCP, ProbeKind.HTTPS)
                and p.status.value in {"timeout", "tcp_error", "http_error"}
                for p in round_.probes)
            for round_ in recent
        )
        if failed_rounds >= 2 and (tcp_rate >= 0.2 or network_rate >= 0.2):
            problems.append(Weather.RAINY)
            evidence.append(Evidence("response_failures", "TCP/HTTPS response failures observed", max(tcp_rate, network_rate), 0.2))
    if latency is not None:
        threshold = max(150.0, baseline_ms * 2 if baseline_ms else 150.0)
        if latency >= threshold:
            problems.append(Weather.CLOUDY)
            evidence.append(Evidence("high_latency", "TCP connection time is elevated", latency, threshold))
    if jitter is not None and jitter >= 30:
        problems.append(Weather.WINDY)
        evidence.append(Evidence("rtt_variation", "Variation between comparable TCP times", jitter, 30))

    tls_errors = sum(p.status.value == "tls_error" for p in https)
    if tls_errors:
        evidence.append(Evidence("tls_errors", "TLS verification/handshake errors observed", tls_errors, None))

    if len(problems) >= 2:
        return Classification(Weather.STORMY, tuple(problems), 0.75, 0.8, tuple(evidence), len(recent))
    if problems:
        problem = problems[0]
        confidence = 0.75 if baseline_ms is not None or problem != Weather.CLOUDY else 0.6
        return Classification(problem, (), confidence, 0.5, tuple(evidence), len(recent))
    if tls_errors or any(not p.ok for p in dns + tcp + https):
        evidence.append(Evidence("conflicting_results", "Some probes failed while others succeeded"))
        return Classification(Weather.UNKNOWN, (), 0.45, 0.0, tuple(evidence), len(recent))
    counts = Counter(p.kind for p in probes)
    if min(counts.values()) < len(recent):
        return Classification(Weather.UNKNOWN, (), 0.4, 0.0,
                              (Evidence("sparse_samples", "Insufficient protocol coverage"),), len(recent))
    return Classification(Weather.SUNNY, (), 0.8, 0.0,
                          (Evidence("all_probes_ok", "DNS, TCP and HTTPS responded across multiple destinations"),),
                          len(recent))


class WeatherEngine:
    """Two consecutive candidate classifications are required for a transition."""

    def __init__(self) -> None:
        self.rounds: list[MeasurementRound] = []
        self.current = Weather.UNKNOWN
        self._candidate = Weather.UNKNOWN
        self._candidate_count = 0

    def add(self, round_: MeasurementRound) -> Classification:
        if (self.rounds and round_.route_adapter and self.rounds[-1].route_adapter
                and round_.route_adapter != self.rounds[-1].route_adapter):
            self.rounds.clear()
            self.current = Weather.UNKNOWN
            self._candidate = Weather.UNKNOWN
            self._candidate_count = 0
        self.rounds.append(round_)
        self.rounds = self.rounds[-60:]
        baseline = self._baseline()
        raw = classify(self.rounds, baseline)
        if raw.weather == self.current:
            self._candidate = self.current
            self._candidate_count = 0
            return raw
        if raw.weather == self._candidate:
            self._candidate_count += 1
        else:
            self._candidate = raw.weather
            self._candidate_count = 1
        if self._candidate_count >= 2:
            self.current = raw.weather
            self._candidate_count = 0
            return raw
        return Classification(
            self.current, (raw.weather,) if raw.weather != Weather.UNKNOWN else (),
            min(raw.confidence, 0.5), raw.severity, raw.evidence, raw.sample_rounds,
        )

    def _baseline(self) -> float | None:
        # Prior successful TCP samples only; never train from the current round.
        prior = [p.duration_ms for round_ in self.rounds[:-1]
                 for p in round_.probes if p.kind == ProbeKind.TCP and p.ok
                 and p.duration_ms is not None]
        return median(prior[-40:]) if len(prior) >= 20 else None
