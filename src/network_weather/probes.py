"""Small, read-only DNS, TCP and HTTPS probes using the Python standard library."""

from __future__ import annotations

import socket
import ssl
import time

from network_weather.models import ProbeKind, ProbeResult, ProbeStatus, utc_now

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
        return (dns,)
    # One resolved address keeps the three results comparable. Other addresses are
    # retained by the resolver but are not silently counted as successful probes.
    info = infos[0]
    return dns, probe_tcp(host, info, timeout), probe_https(host, info, timeout, path)
