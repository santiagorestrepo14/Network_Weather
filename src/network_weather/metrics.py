"""Statistics for comparable successful samples only."""

from dataclasses import dataclass
from itertools import pairwise
from statistics import median

from network_weather.models import ProbeKind, ProbeResult


@dataclass(frozen=True, slots=True)
class MetricSummary:
    destination: str
    kind: ProbeKind
    attempted: int
    successful: int
    median_ms: float | None
    jitter_ms: float | None
    failure_percent: float | None


def summarize(results: list[ProbeResult], destination: str, kind: ProbeKind) -> MetricSummary:
    """Jitter = mean absolute difference between successive successful RTTs.

    Only adjacent successful probes of the same destination and protocol count.
    This is RTT variation, not one-way network jitter. Failure rate is the share
    of actual probes without a successful response; it is protocol-specific.
    """
    selected = sorted(
        (r for r in results if r.destination == destination and r.kind == kind),
        key=lambda r: r.at,
    )
    successful = [r.duration_ms for r in selected if r.ok and r.duration_ms is not None]
    pairs = [
        abs(previous.duration_ms - current.duration_ms)
        for previous, current in pairwise(selected)
        if previous.ok and current.ok
        and previous.duration_ms is not None and current.duration_ms is not None
    ]
    return MetricSummary(
        destination=destination,
        kind=kind,
        attempted=len(selected),
        successful=len(successful),
        median_ms=median(successful) if successful else None,
        jitter_ms=sum(pairs) / len(pairs) if pairs else None,
        failure_percent=100 * (len(selected) - len(successful)) / len(selected) if selected else None,
    )
