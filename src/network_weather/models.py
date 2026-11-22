"""Measurement contracts. A failed probe is never a latency measurement."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class ProbeKind(StrEnum):
    DNS = "dns"
    TCP = "tcp"
    HTTPS = "https"


class ProbeStatus(StrEnum):
    SUCCESS = "success"
    DNS_ERROR = "dns_error"
    TCP_ERROR = "tcp_error"
    TLS_ERROR = "tls_error"
    HTTP_ERROR = "http_error"
    TIMEOUT = "timeout"


@dataclass(frozen=True, slots=True)
class ProbeResult:
    at: datetime
    destination: str
    kind: ProbeKind
    status: ProbeStatus
    duration_ms: float | None
    detail: str = ""
    address: str | None = None
    http_status: int | None = None
    local_address: str | None = None

    def __post_init__(self) -> None:
        if self.at.tzinfo is None:
            raise ValueError("ProbeResult.at must have a timezone")
        if self.duration_ms is not None and self.duration_ms < 0:
            raise ValueError("duration_ms cannot be negative")
        if self.status != ProbeStatus.SUCCESS and self.duration_ms is not None:
            raise ValueError("failed probes cannot report successful latency")

    @property
    def ok(self) -> bool:
        return self.status == ProbeStatus.SUCCESS

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["at"] = self.at.isoformat()
        result["kind"] = self.kind.value
        result["status"] = self.status.value
        return result


@dataclass(frozen=True, slots=True)
class AdapterSnapshot:
    name: str
    is_up: bool
    ipv4: tuple[str, ...] = ()
    speed_mbps: int | None = None
    bytes_sent: int | None = None
    bytes_received: int | None = None


@dataclass(frozen=True, slots=True)
class MeasurementRound:
    started_at: datetime
    finished_at: datetime
    probes: tuple[ProbeResult, ...]
    adapters: tuple[AdapterSnapshot, ...] = field(default_factory=tuple)
    # The OS route/interface actually used by each socket is not inferred here.
    route_adapter: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "probes": [probe.to_dict() for probe in self.probes],
            "adapters": [asdict(adapter) for adapter in self.adapters],
            "route_adapter": self.route_adapter,
        }


def utc_now() -> datetime:
    return datetime.now(UTC)
