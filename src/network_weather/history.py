"""Local SQLite history. Synthetic demo data must use a separate database."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from statistics import median
from typing import Self

from network_weather.models import (
    AdapterSnapshot,
    MeasurementRound,
    ProbeKind,
    ProbeResult,
    ProbeStatus,
    WifiSnapshot,
)
from network_weather.weather import Classification, Weather


@dataclass(frozen=True, slots=True)
class WeatherPoint:
    at: datetime
    weather: Weather


@dataclass(frozen=True, slots=True)
class LatencyBin:
    start: datetime
    end: datetime
    mean_ms: float
    sample_count: int


@dataclass(frozen=True, slots=True)
class HistorySeries:
    start: datetime
    end: datetime
    weather: tuple[WeatherPoint, ...]
    latency: tuple[LatencyBin, ...]
    destinations: tuple[str, ...]
    gap_threshold_seconds: float
    truncated: bool


class HistoryStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS rounds (
                id INTEGER PRIMARY KEY,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL,
                data TEXT NOT NULL,
                weather TEXT,
                confidence REAL,
                severity REAL,
                evidence TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_rounds_started ON rounds(started_at);
            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                weather TEXT NOT NULL,
                severity REAL NOT NULL,
                evidence TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS probe_samples (
                id INTEGER PRIMARY KEY,
                round_id INTEGER NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
                at TEXT NOT NULL,
                destination TEXT NOT NULL,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                duration_ms REAL
            );
            CREATE INDEX IF NOT EXISTS idx_samples_range
                ON probe_samples(kind, destination, at);
            CREATE INDEX IF NOT EXISTS idx_samples_kind_time
                ON probe_samples(kind, at);
            """
        )
        self._backfill_samples()

    def _backfill_samples(self) -> None:
        """Copy probe rows from pre-index history once, preserving older data."""
        self.connection.execute("CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT)")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            completed = self.connection.execute(
                "SELECT value FROM schema_meta WHERE key = 'samples_backfilled'"
            ).fetchone()
            if completed:
                self.connection.commit()
                return
            rows = self.connection.execute("SELECT id, data FROM rounds ORDER BY id")
            for round_id, raw in rows:
                try:
                    probes = json.loads(raw).get("probes", [])
                except (ValueError, TypeError):
                    continue
                self.connection.executemany(
                    """INSERT INTO probe_samples
                       (round_id, at, destination, kind, status, duration_ms)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        (round_id, p["at"], p["destination"], p["kind"], p["status"],
                         p.get("duration_ms"))
                        for p in probes
                    ),
                )
            self.connection.execute(
                "INSERT INTO schema_meta (key, value) VALUES ('samples_backfilled', '1')"
            )
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise

    def save(self, round_: MeasurementRound, classification: Classification) -> int:
        with self.connection:
            cursor = self.connection.execute(
                """INSERT INTO rounds
                   (started_at, finished_at, data, weather, confidence, severity, evidence)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    round_.started_at.isoformat(), round_.finished_at.isoformat(),
                    json.dumps(round_.to_dict()), classification.weather.value,
                    classification.confidence, classification.severity,
                    json.dumps([asdict(e) for e in classification.evidence]),
                ),
            )
            self.connection.executemany(
                """INSERT INTO probe_samples
                   (round_id, at, destination, kind, status, duration_ms)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    (cursor.lastrowid, p.at.isoformat(), p.destination, p.kind.value,
                     p.status.value, p.duration_ms)
                    for p in round_.probes
                ),
            )
        return int(cursor.lastrowid)

    def history_range(
        self,
        start: datetime,
        end: datetime,
        destination: str | None = None,
        max_bins: int = 480,
        max_rounds: int = 1_000_000,
    ) -> HistorySeries:
        """Read categorical weather and observed TCP averages in bounded bins."""
        if start.tzinfo is None or end.tzinfo is None or start >= end:
            raise ValueError("History range must contain timezone-aware start < end")
        if not 1 <= max_bins <= 2000 or not 1 <= max_rounds <= 1_000_000:
            raise ValueError("History limits are out of range")
        start_iso, end_iso = start.astimezone(UTC).isoformat(), end.astimezone(UTC).isoformat()
        rows = self.connection.execute(
            """SELECT started_at, weather FROM rounds
               WHERE started_at >= ? AND started_at < ? ORDER BY started_at LIMIT ?""",
            (start_iso, end_iso, max_rounds + 1),
        ).fetchall()
        truncated = len(rows) > max_rounds
        points = tuple(
            WeatherPoint(datetime.fromisoformat(at), Weather(weather))
            for at, weather in rows[:max_rounds]
        )
        differences = [
            (b.at - a.at).total_seconds()
            for a, b in pairwise(points)
            if 0 < (b.at - a.at).total_seconds() <= 3600
        ]
        typical = median(sorted(differences)[:max(1, len(differences) // 2)]) if differences else 0
        gap_threshold = max(120.0, 2.5 * typical)
        destinations = tuple(
            row[0] for row in self.connection.execute(
                """SELECT DISTINCT destination FROM probe_samples
                   WHERE kind = 'tcp' AND at >= ? AND at < ? ORDER BY destination""",
                (start_iso, end_iso),
            )
        )
        duration = (end - start).total_seconds()
        sums = [0.0] * max_bins
        counts = [0] * max_bins
        query = (
            "SELECT at, duration_ms FROM probe_samples "
            "WHERE kind = 'tcp' AND status = 'success' AND duration_ms IS NOT NULL "
            "AND at >= ? AND at < ?"
        )
        parameters: tuple = (start_iso, end_iso)
        if destination:
            query += " AND destination = ?"
            parameters = (start_iso, end_iso, destination)
        for at, value in self.connection.execute(query, parameters):
            fraction = (datetime.fromisoformat(at) - start).total_seconds() / duration
            index = min(max_bins - 1, max(0, int(fraction * max_bins)))
            sums[index] += value
            counts[index] += 1
        bins = tuple(
            LatencyBin(
                start + timedelta(seconds=duration * index / max_bins),
                start + timedelta(seconds=duration * (index + 1) / max_bins),
                sums[index] / count,
                count,
            )
            for index, count in enumerate(counts) if count
        )
        return HistorySeries(start, end, points, bins, destinations,
                             gap_threshold, truncated)

    def recent_rounds(self, limit: int = 60) -> list[MeasurementRound]:
        rows = self.connection.execute(
            "SELECT data FROM rounds ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [_decode_round(json.loads(row[0])) for row in reversed(rows)]

    def recent_weather(self, limit: int = 100) -> list[tuple[str, Weather]]:
        rows = self.connection.execute(
            "SELECT started_at, weather FROM rounds WHERE weather IS NOT NULL ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [(at, Weather(weather)) for at, weather in reversed(rows)]

    def advance_incident(self, round_: MeasurementRound, result: Classification) -> None:
        """Keep one episode open through weather changes and uncertain gaps.

        Two observed sunny rounds confirm recovery. Unknown never means recovered.
        """
        active = self.connection.execute(
            "SELECT id, severity, evidence FROM incidents WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        problem = result.weather not in (Weather.SUNNY, Weather.UNKNOWN)
        credible = result.confidence >= 0.6
        with self.connection:
            if problem and credible:
                evidence = json.dumps([asdict(e) for e in result.evidence])
                if active:
                    self.connection.execute(
                        "UPDATE incidents SET weather = ?, severity = ?, evidence = ? WHERE id = ?",
                        (result.weather.value, max(active[1], result.severity), evidence, active[0]),
                    )
                else:
                    self.connection.execute(
                        "INSERT INTO incidents (started_at, weather, severity, evidence) VALUES (?, ?, ?, ?)",
                        (round_.started_at.isoformat(), result.weather.value, result.severity, evidence),
                    )
            elif active and result.weather == Weather.SUNNY:
                recent = self.recent_weather(2)
                if len(recent) == 2 and all(weather == Weather.SUNNY for _, weather in recent):
                    self.connection.execute(
                        "UPDATE incidents SET ended_at = ? WHERE id = ?",
                        (round_.finished_at.isoformat(), active[0]),
                    )

    def incidents(self, limit: int = 100) -> list[dict]:
        rows = self.connection.execute(
            """SELECT id, started_at, ended_at, weather, severity, evidence
               FROM incidents ORDER BY id DESC LIMIT ?""", (limit,)
        ).fetchall()
        return [
            {
                "id": row[0], "started_at": row[1], "ended_at": row[2],
                "weather": row[3], "severity": row[4], "evidence": json.loads(row[5]),
            }
            for row in rows
        ]

    def end_active_incident_for_route_change(self, at: datetime) -> None:
        self._end_active_incident_for_context_change(
            at, "route_changed", "Observation context changed; recovery was not confirmed")

    def end_active_incident_for_target_change(self, last_observed_at: datetime) -> None:
        self._end_active_incident_for_context_change(
            last_observed_at, "targets_changed",
            "Probe destinations changed; recovery was not confirmed")

    def end_active_incident_for_gap(self, last_observed_at: datetime) -> None:
        self._end_active_incident_for_context_change(
            last_observed_at, "observation_gap",
            "Monitoring was interrupted; recovery was not confirmed")

    def _end_active_incident_for_context_change(
        self, at: datetime, code: str, detail: str,
    ) -> None:
        active = self.connection.execute(
            "SELECT id, evidence FROM incidents WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if active:
            evidence = json.loads(active[1])
            evidence.append({
                "code": code,
                "detail": detail,
                "observed": None,
                "threshold": None,
            })
            with self.connection:
                self.connection.execute(
                    "UPDATE incidents SET ended_at = ?, evidence = ? WHERE id = ?",
                    (at.isoformat(), json.dumps(evidence), active[0]),
                )

    def prune(self, days: int = 30) -> int:
        if not 1 <= days <= 3650:
            raise ValueError("Retention must be between 1 and 3650 days")
        from datetime import UTC, timedelta

        cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        active = self.connection.execute(
            "SELECT started_at FROM incidents WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if active:
            latest = self.connection.execute(
                "SELECT finished_at FROM rounds ORDER BY finished_at DESC LIMIT 1"
            ).fetchone()
            last_observed = latest[0] if latest else active[0]
            if last_observed < cutoff:
                self.end_active_incident_for_gap(datetime.fromisoformat(last_observed))
        with self.connection:
            cursor = self.connection.execute("DELETE FROM rounds WHERE started_at < ?", (cutoff,))
            removed_rounds = cursor.rowcount
            cursor = self.connection.execute(
                "DELETE FROM incidents WHERE ended_at IS NOT NULL AND ended_at < ?", (cutoff,)
            )
        return removed_rounds + cursor.rowcount

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def _decode_round(data: dict) -> MeasurementRound:
    return MeasurementRound(
        started_at=datetime.fromisoformat(data["started_at"]),
        finished_at=datetime.fromisoformat(data["finished_at"]),
        probes=tuple(
            ProbeResult(
                at=datetime.fromisoformat(item["at"]),
                destination=item["destination"], kind=ProbeKind(item["kind"]),
                status=ProbeStatus(item["status"]), duration_ms=item["duration_ms"],
                detail=item["detail"], address=item["address"], http_status=item["http_status"],
                local_address=item.get("local_address"),
            )
            for item in data["probes"]
        ),
        adapters=tuple(
            AdapterSnapshot(**{
                **adapter,
                "ipv4": tuple(adapter["ipv4"]),
                "ipv6": tuple(adapter.get("ipv6", ())),
            })
            for adapter in data["adapters"]
        ),
        route_adapter=data.get("route_adapter"),
        gateway_address=data.get("gateway_address"),
        wifi=tuple(WifiSnapshot(**item) for item in data.get("wifi", ())),
    )
