"""A measurement round; each recorded result corresponds to an actual probe."""

from network_weather.adapters import get_adapters
from network_weather.config import ProbeConfig
from network_weather.models import MeasurementRound, utc_now
from network_weather.probes import probe_destination
from network_weather.windows_network import GatewayCache, ping_gateway

_gateways = GatewayCache()
_last_route_adapter: str | None = None


def collect_once(config: ProbeConfig) -> MeasurementRound:
    global _last_route_adapter

    started = utc_now()
    results = []
    for host in config.destinations:
        results.extend(probe_destination(host, config.timeout_seconds, config.https_path))
    try:
        adapters = get_adapters()
    except OSError:
        adapters = ()
    local_addresses = {result.local_address for result in results if result.local_address}
    matching = {
        adapter.name for adapter in adapters
        if any(address in adapter.ipv4 or address in adapter.ipv6 for address in local_addresses)
    }
    route_adapter = next(iter(matching)) if len(matching) == 1 else None
    if route_adapter and route_adapter != _last_route_adapter:
        _gateways.invalidate()
    _last_route_adapter = route_adapter
    gateway = _gateways.for_adapter(route_adapter)
    if gateway:
        results.append(ping_gateway(gateway))
    return MeasurementRound(started, utc_now(), tuple(results), adapters, route_adapter, gateway)
