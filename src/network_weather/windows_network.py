"""Read-only Windows gateway discovery and ICMP echo reachability."""

from __future__ import annotations

import ipaddress
import json
import subprocess
import sys
import time

from network_weather.models import ProbeKind, ProbeResult, ProbeStatus, utc_now

_GATEWAY_SCRIPT = r"""
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
Get-NetIPConfiguration | ForEach-Object {
    [pscustomobject]@{
        name = $_.InterfaceAlias
        gateway = @($_.IPv4DefaultGateway | ForEach-Object { $_.NextHop })
    }
} | ConvertTo-Json -Depth 3 -Compress
"""


def _hidden_process_flag() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def discover_gateways() -> dict[str, str]:
    """Return validated IPv4 gateways by interface alias, or no data on failure."""
    if sys.platform != "win32":
        return {}
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _GATEWAY_SCRIPT],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=12, check=False, creationflags=_hidden_process_flag(),
        )
        if result.returncode != 0:
            return {}
        data = json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return {}
    rows = data if isinstance(data, list) else [data]
    gateways = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            continue
        for candidate in row.get("gateway") or []:
            try:
                address = ipaddress.ip_address(candidate)
            except (ValueError, TypeError):
                continue
            if isinstance(address, ipaddress.IPv4Address) and not address.is_unspecified:
                gateways[row["name"]] = str(address)
                break
    return gateways


class GatewayCache:
    def __init__(self, ttl_seconds: float = 300) -> None:
        self.ttl_seconds = ttl_seconds
        self.last_refresh = float("-inf")
        self.gateways: dict[str, str] = {}

    def for_adapter(self, name: str | None) -> str | None:
        if not name:
            return None
        now = time.monotonic()
        if now - self.last_refresh >= self.ttl_seconds:
            self.gateways = discover_gateways()
            self.last_refresh = now
        return self.gateways.get(name)

    def invalidate(self) -> None:
        self.last_refresh = float("-inf")


def ping_gateway(address: str, timeout_ms: int = 1000) -> ProbeResult:
    """Use ping exit status only. A missing echo reply is not proof of link failure."""
    ip = ipaddress.IPv4Address(address)
    if not 200 <= timeout_ms <= 5000:
        raise ValueError("ICMP timeout must be 200–5000 ms")
    if sys.platform != "win32":
        return ProbeResult(utc_now(), str(ip), ProbeKind.ICMP, ProbeStatus.ICMP_ERROR,
                           None, "Windows ICMP probe unavailable")
    try:
        process = subprocess.run(
            ["ping.exe", "-n", "1", "-w", str(timeout_ms), str(ip)],
            capture_output=True, timeout=timeout_ms / 1000 + 2,
            check=False, creationflags=_hidden_process_flag(),
        )
    except subprocess.TimeoutExpired:
        return ProbeResult(utc_now(), str(ip), ProbeKind.ICMP, ProbeStatus.TIMEOUT,
                           None, "Gateway ICMP echo timed out; filtering is possible")
    except OSError as exc:
        return ProbeResult(utc_now(), str(ip), ProbeKind.ICMP, ProbeStatus.ICMP_ERROR,
                           None, f"ICMP probe could not start: {exc}"[:300])
    if process.returncode == 0:
        return ProbeResult(utc_now(), str(ip), ProbeKind.ICMP, ProbeStatus.SUCCESS,
                           None, "Gateway answered ICMP echo; no RTT parsed")
    return ProbeResult(utc_now(), str(ip), ProbeKind.ICMP, ProbeStatus.ICMP_ERROR,
                       None, "No gateway ICMP echo reply; filtering is possible")
