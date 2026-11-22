"""Observed per-round TCP values for the compact, time-scaled widget chart."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise
from statistics import mean, median

from network_weather.models import MeasurementRound, ProbeKind


@dataclass(frozen=True, slots=True)
class CompactPoint:
    at: datetime
    latency_ms: float | None
    variation_ms: float | None

    def value(self, metric: str) -> float | None:
        if metric == "latency":
            return self.latency_ms
        if metric == "variation":
            return self.variation_ms
        raise ValueError(f"Unknown compact metric: {metric}")


def compact_points(rounds: list[MeasurementRound]) -> tuple[CompactPoint, ...]:
    """One observed point per round; failed/missing TCP breaks comparability."""
    points = []
    previous: dict[str, float] = {}
    ordered = sorted(rounds, key=lambda item: item.started_at)
    gap_limit = gap_threshold_seconds(tuple(
        CompactPoint(round_.started_at, None, None) for round_ in ordered))
    previous_at: datetime | None = None
    for round_ in ordered:
        if previous_at is not None and (round_.started_at - previous_at).total_seconds() > gap_limit:
            previous = {}
        per_target: dict[str, list[float]] = {}
        for probe in round_.probes:
            if probe.kind == ProbeKind.TCP and probe.ok and probe.duration_ms is not None:
                per_target.setdefault(probe.destination, []).append(probe.duration_ms)
        current = {host: median(values) for host, values in per_target.items()}
        differences = [abs(value - previous[host]) for host, value in current.items()
                       if host in previous]
        points.append(CompactPoint(
            round_.started_at,
            mean(current.values()) if current else None,
            mean(differences) if differences else None,
        ))
        previous = current
        previous_at = round_.started_at
    return tuple(points)


def gap_threshold_seconds(points: tuple[CompactPoint, ...]) -> float:
    intervals = [
        (current.at - previous.at).total_seconds()
        for previous, current in pairwise(points)
        if 0 < (current.at - previous.at).total_seconds() <= 3600
    ]
    typical = median(sorted(intervals)[:max(1, len(intervals) // 2)]) if intervals else 0
    return max(120.0, 2.5 * typical)


def visible_segments(
    points: tuple[CompactPoint, ...], metric: str,
) -> tuple[tuple[CompactPoint, CompactPoint], ...]:
    """Connect only adjacent observed values separated by an expected interval."""
    threshold = gap_threshold_seconds(points)
    return tuple(
        (previous, current)
        for previous, current in pairwise(points)
        if previous.value(metric) is not None and current.value(metric) is not None
        and 0 < (current.at - previous.at).total_seconds() <= threshold
    )
