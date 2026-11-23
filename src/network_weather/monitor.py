"""Small orchestrator shared by the future desktop UI and CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Self

from network_weather.collector import collect_once
from network_weather.config import ProbeConfig, default_data_dir
from network_weather.history import HistoryStore
from network_weather.models import MeasurementRound, ProbeKind
from network_weather.weather import Classification, WeatherEngine


class Monitor:
    def __init__(self, config: ProbeConfig, database: Path | None = None) -> None:
        self.config = config
        self.history = HistoryStore(database or default_data_dir() / "history.db")
        self.history.prune(config.retention_days)
        self.engine = WeatherEngine(config.interval_seconds)
        recent = self.history.recent_rounds(60)
        expected = (frozenset(config.destinations), config.direct_ip_target)
        matching_start = len(recent)
        while matching_start and _targets(recent[matching_start - 1]) == expected:
            matching_start -= 1
        if recent and matching_start == len(recent):
            self.history.end_active_incident_for_target_change(
                recent[-1].finished_at)
        for round_ in recent[matching_start:]:
            self.engine.add(round_)

    def measure(self) -> tuple[MeasurementRound, Classification]:
        round_ = collect_once(self.config)
        if self.engine.observation_gap(round_):
            self.history.end_active_incident_for_gap(self.engine.rounds[-1].finished_at)
        elif (self.engine.rounds and self.engine.rounds[-1].route_adapter and round_.route_adapter
              and self.engine.rounds[-1].route_adapter != round_.route_adapter):
            self.history.end_active_incident_for_route_change(round_.started_at)
        result = self.engine.add(round_)
        self.history.save(round_, result)
        self.history.advance_incident(round_, result)
        return round_, result

    def close(self) -> None:
        self.history.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def _targets(round_: MeasurementRound) -> tuple[frozenset[str], str | None]:
    dns = frozenset(probe.destination for probe in round_.probes
                    if probe.kind == ProbeKind.DNS)
    direct = frozenset(probe.destination for probe in round_.probes
                       if probe.kind == ProbeKind.TCP and probe.destination not in dns)
    return dns, next(iter(direct)) if len(direct) == 1 else None
