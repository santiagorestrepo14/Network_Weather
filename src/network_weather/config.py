"""Validated local probe configuration; no network settings are changed."""

import re
from dataclasses import dataclass
from ipaddress import ip_address
from pathlib import Path


def is_ip_literal(value: str) -> bool:
    try:
        ip_address(value)
    except ValueError:
        return False
    return True


@dataclass(frozen=True, slots=True)
class ProbeConfig:
    destinations: tuple[str, ...] = ("example.com", "www.wikipedia.org")
    interval_seconds: float = 30.0
    timeout_seconds: float = 3.0
    retention_days: int = 30
    https_path: str = "/"
    direct_ip_target: str | None = None

    def __post_init__(self) -> None:
        if not 1 <= len(self.destinations) <= 8:
            raise ValueError("Choose between 1 and 8 destinations")
        if any(not isinstance(host, str) for host in self.destinations):
            raise ValueError("Destinations must be hostnames")
        if len({host.rstrip(".").lower() for host in self.destinations}) != len(self.destinations):
            raise ValueError("Destinations must be unique regardless of case or trailing dot")
        for host in self.destinations:
            if (not host or len(host) > 253 or host.endswith("..")
                    or not re.fullmatch(r"[A-Za-z0-9.-]+", host)):
                raise ValueError(f"Invalid destination: {host!r}")
            if any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-")
                   for label in host.rstrip(".").split(".")):
                raise ValueError(f"Invalid destination: {host!r}")
            if re.fullmatch(r"[0-9.]+", host):
                raise ValueError("IP literals belong in direct_ip_target, not DNS destinations")
        if self.direct_ip_target is not None:
            try:
                address = ip_address(self.direct_ip_target)
            except ValueError as exc:
                raise ValueError("Direct IP target must be a numeric IP address") from exc
            if not address.is_global:
                raise ValueError("Direct IP target must be globally reachable")
        if not 5 <= self.interval_seconds <= 3600:
            raise ValueError("Interval must be between 5 and 3600 seconds")
        if not 0.2 <= self.timeout_seconds <= 30:
            raise ValueError("Timeout must be between 0.2 and 30 seconds")
        if not 1 <= self.retention_days <= 3650:
            raise ValueError("Retention must be between 1 and 3650 days")
        if not re.fullmatch(r"/[A-Za-z0-9/_?&=.%+~-]*", self.https_path):
            raise ValueError("HTTPS path must be a safe absolute path")


def default_data_dir() -> Path:
    import os

    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "NetworkWeather"
