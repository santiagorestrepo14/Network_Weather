"""Comparable recent probe statistics for the technical diagnostics panel."""

from __future__ import annotations

from dataclasses import dataclass

from network_weather.metrics import MetricSummary, summarize
from network_weather.models import MeasurementRound, ProbeKind


@dataclass(frozen=True, slots=True)
class DiagnosticSummary:
    rounds: int
    rows: tuple[MetricSummary, ...]


def recent_diagnostics(
    rounds: list[MeasurementRound], interval_seconds: float,
) -> DiagnosticSummary:
    """Keep up to 30 rounds from the latest uninterrupted route context."""
    if not rounds:
        return DiagnosticSummary(0, ())
    ordered = sorted(rounds, key=lambda round_: round_.started_at)[-30:]
    limit = max(120.0, 3.0 * interval_seconds)
    first = len(ordered) - 1
    while first > 0:
        previous, current = ordered[first - 1], ordered[first]
        gap = (current.started_at - previous.finished_at).total_seconds()
        if gap < 0 or gap > limit:
            break
        if (previous.route_adapter and current.route_adapter and
                previous.route_adapter != current.route_adapter):
            break
        first -= 1
    selected = ordered[first:]
    results = [probe for round_ in selected for probe in round_.probes]
    keys = sorted({(probe.destination, probe.kind) for probe in results},
                  key=lambda item: (item[0], item[1].value))
    rows = tuple(summarize(results, destination, kind) for destination, kind in keys
                 if kind in (ProbeKind.DNS, ProbeKind.TCP, ProbeKind.HTTPS, ProbeKind.ICMP))
    return DiagnosticSummary(len(selected), rows)
