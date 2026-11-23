"""Small, read-only DNS, TCP and HTTPS probes using the Python standard library."""

from __future__ import annotations

import socket
import ssl
import time
from collections.abc import Callable
from dataclasses import replace
from ipaddress import ip_address

from network_weather.models import ProbeKind, ProbeResult, ProbeStatus, utc_now
from network_weather.windows_http import https_head_system_route

AddressInfo = tuple[int, int, int, str, tuple]


def _result(
    host: str,
    kind: ProbeKind,
    status: ProbeStatus,
    start: float,
    *,
    detail: str = "",
    address: str | None = None,
    http_status: int | None = None,
    local_address: str | None = None,
) -> ProbeResult:
    return ProbeResult(
        at=utc_now(),
        destination=host,
        kind=kind,
        status=status,
        duration_ms=round((time.perf_counter() - start) * 1000, 3)
        if status == ProbeStatus.SUCCESS
        else None,
        detail=detail[:300],
        address=address,
        http_status=http_status,
        local_address=local_address,
    )


def probe_dns(host: str) -> tuple[ProbeResult, list[AddressInfo]]:
    """Resolve with the OS resolver. OS caching can affect the measured duration."""
    start = time.perf_counter()
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        if not infos:
            raise socket.gaierror("No addresses returned")
        return _result(host, ProbeKind.DNS, ProbeStatus.SUCCESS, start), infos
    except socket.gaierror as exc:
        return _result(host, ProbeKind.DNS, ProbeStatus.DNS_ERROR, start, detail=str(exc)), []
    except OSError as exc:
        return _result(host, ProbeKind.DNS, ProbeStatus.DNS_ERROR, start, detail=str(exc)), []


def _connect(info: AddressInfo, timeout: float) -> socket.socket:
    family, socktype, proto, _, sockaddr = info
    sock = socket.socket(family, socktype, proto)
    try:
        sock.settimeout(timeout)
        sock.connect(sockaddr)
        return sock
    except BaseException:
        sock.close()
        raise


def probe_tcp(host: str, info: AddressInfo, timeout: float) -> ProbeResult:
    """Time a TCP connect to port 443, excluding the DNS probe."""
    start = time.perf_counter()
    address = str(info[4][0])
    try:
        with _connect(info, timeout) as sock:
            local_address = str(sock.getsockname()[0])
        return _result(host, ProbeKind.TCP, ProbeStatus.SUCCESS, start,
                       address=address, local_address=local_address)
    except TimeoutError as exc:
        return _result(host, ProbeKind.TCP, ProbeStatus.TIMEOUT, start, detail=str(exc), address=address)
    except OSError as exc:
        return _result(host, ProbeKind.TCP, ProbeStatus.TCP_ERROR, start, detail=str(exc), address=address)


def probe_https(host: str, info: AddressInfo, timeout: float, path: str = "/") -> ProbeResult:
    """Time connect + TLS + a HEAD response. Any valid HTTP status confirms connectivity."""
    start = time.perf_counter()
    address = str(info[4][0])
    local_address = None
    phase = "tcp"
    try:
        with _connect(info, timeout) as raw:
            local_address = str(raw.getsockname()[0])
            phase = "tls"
            context = ssl.create_default_context()
            with context.wrap_socket(raw, server_hostname=host) as secure:
                phase = "http"
                request = (
                    f"HEAD {path} HTTP/1.1\r\nHost: {host}\r\n"
                    "User-Agent: NetworkWeather/0.1\r\nConnection: close\r\n\r\n"
                )
                secure.sendall(request.encode("ascii"))
                line = bytearray()
                while len(line) < 1024 and not line.endswith(b"\n"):
                    part = secure.recv(1)
                    if not part:
                        break
                    line.extend(part)
                parts = bytes(line).decode("ascii", "replace").split()
                if len(parts) < 2 or not parts[0].startswith("HTTP/") or not parts[1].isdigit():
                    return _result(
                        host, ProbeKind.HTTPS, ProbeStatus.HTTP_ERROR, start,
                        detail="Malformed HTTP status line", address=address,
                        local_address=local_address,
                    )
                status = int(parts[1])
                return _result(
                    host, ProbeKind.HTTPS, ProbeStatus.SUCCESS, start,
                    address=address, http_status=status, local_address=local_address,
                )
    except TimeoutError as exc:
        return _result(host, ProbeKind.HTTPS, ProbeStatus.TIMEOUT, start,
                       detail=f"{phase}: {exc}", address=address,
                       local_address=local_address)
    except ssl.SSLError as exc:
        return _result(host, ProbeKind.HTTPS, ProbeStatus.TLS_ERROR, start,
                       detail=str(exc), address=address, local_address=local_address)
    except OSError as exc:
        status = {
            "tcp": ProbeStatus.TCP_ERROR,
            "tls": ProbeStatus.TLS_ERROR,
            "http": ProbeStatus.HTTP_ERROR,
        }[phase]
        return _result(host, ProbeKind.HTTPS, status, start,
                       detail=f"{phase}: {exc}", address=address,
                       local_address=local_address)


def probe_destination(host: str, timeout: float, path: str = "/") -> tuple[ProbeResult, ...]:
    dns, infos = probe_dns(host)
    if not infos:
        system = _system_https_result(host, path, timeout, "Local DNS did not resolve")
        return (dns, system) if system else (dns,)
    candidates = _candidate_infos(infos)
    tcp, tcp_info = _probe_with_fallback(
        candidates, lambda info: probe_tcp(host, info, timeout))
    https_candidates = (tcp_info, *(info for info in candidates if info != tcp_info))
    https, _ = _probe_with_fallback(
        https_candidates, lambda info: probe_https(host, info, timeout, path))
    if not https.ok:
        system = _system_https_result(
            host, path, timeout, f"Direct HTTPS failed ({https.status.value})")
        if system:
            https = system
    return dns, tcp, https


def _system_https_result(
    host: str, path: str, timeout: float, context: str,
) -> ProbeResult | None:
    observed = https_head_system_route(host, path, timeout)
    if observed is None:
        return None
    duration_ms, http_status = observed
    return ProbeResult(
        utc_now(), host, ProbeKind.HTTPS, ProbeStatus.SUCCESS, duration_ms,
        detail=f"WinHTTP system route; {context}", http_status=http_status,
    )


def _candidate_infos(infos: list[AddressInfo]) -> tuple[AddressInfo, ...]:
    """Bound retries to the OS-preferred address and one distinct alternative."""
    first = infos[0]
    alternatives = [info for info in infos[1:]
                    if (info[0], info[4]) != (first[0], first[4])]
    if not alternatives:
        return (first,)
    other_family = next((info for info in alternatives if info[0] != first[0]), None)
    return first, other_family or alternatives[0]


def _probe_with_fallback(
    candidates: tuple[AddressInfo, ...], probe: Callable[[AddressInfo], ProbeResult],
) -> tuple[ProbeResult, AddressInfo]:
    failed: list[ProbeResult] = []
    for info in candidates:
        result = probe(info)
        if result.ok:
            if failed:
                previous = ", ".join(f"{item.address}: {item.status.value}" for item in failed)
                result = replace(result, detail=f"Fallback after {previous}"[:300])
            return result, info
        failed.append(result)
    first = failed[0]
    if len(failed) > 1:
        attempts = ", ".join(f"{item.address}: {item.status.value}" for item in failed)
        prefix = f"{first.detail}; " if first.detail else ""
        first = replace(first, detail=f"{prefix}tried {attempts}"[:300])
    return first, candidates[0]


def probe_direct_ip(address: str, timeout: float) -> ProbeResult:
    """Check an explicitly configured numeric IP on TCP/443 without DNS."""
    parsed = ip_address(address)
    if parsed.version == 6:
        info: AddressInfo = (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "",
                             (str(parsed), 443, 0, 0))
    else:
        info = (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "",
                (str(parsed), 443))
    return probe_tcp(str(parsed), info, timeout)
