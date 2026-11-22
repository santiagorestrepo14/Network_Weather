"""Local SQLite history. Synthetic demo data must use a separate database."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Self

from network_weather.models import (
    AdapterSnapshot,
    MeasurementRound,
    ProbeKind,
    ProbeResult,
    ProbeStatus,
)
from network_weather.weather import Classification, Weather


class HistoryStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
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
            """
        )

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
        return int(cursor.lastrowid)

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
        active = self.connection.execute(
            "SELECT id, evidence FROM incidents WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if active:
            evidence = json.loads(active[1])
            evidence.append({
                "code": "route_changed",
                "detail": "Observation context changed; recovery was not confirmed",
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
    )
