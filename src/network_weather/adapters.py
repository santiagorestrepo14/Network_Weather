"""Read-only adapter counters. Link speed is not Internet speed."""

import socket

import psutil

from network_weather.models import AdapterSnapshot


def get_adapters() -> tuple[AdapterSnapshot, ...]:
    stats = psutil.net_if_stats()
    addresses = psutil.net_if_addrs()
    counters = psutil.net_io_counters(pernic=True)
    result = []
    for name, state in stats.items():
        ipv4 = tuple(
            address.address
            for address in addresses.get(name, ())
            if address.family == socket.AF_INET
        )
        ipv6 = tuple(
            address.address.split("%")[0]
            for address in addresses.get(name, ())
            if address.family == socket.AF_INET6
        )
        traffic = counters.get(name)
        result.append(
            AdapterSnapshot(
                name=name,
                is_up=state.isup,
                ipv4=ipv4,
                speed_mbps=state.speed if state.speed > 0 else None,
                bytes_sent=traffic.bytes_sent if traffic else None,
                bytes_received=traffic.bytes_recv if traffic else None,
                ipv6=ipv6,
            )
        )
    return tuple(result)
