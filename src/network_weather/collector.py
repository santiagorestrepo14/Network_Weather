"""A measurement round; each recorded result corresponds to an actual probe."""

from network_weather.adapters import get_adapters
from network_weather.config import ProbeConfig
from network_weather.models import MeasurementRound, utc_now
from network_weather.probes import probe_destination


def collect_once(config: ProbeConfig) -> MeasurementRound:
    started = utc_now()
    results = []
    for host in config.destinations:
        results.extend(probe_destination(host, config.timeout_seconds, config.https_path))
    try:
        adapters = get_adapters()
    except OSError:
        adapters = ()
    local_addresses = {result.local_address for result in results if result.local_address}
    matching = {adapter.name for adapter in adapters
                if any(address in adapter.ipv4 for address in local_addresses)}
    route_adapter = next(iter(matching)) if len(matching) == 1 else None
    return MeasurementRound(started, utc_now(), tuple(results), adapters, route_adapter)
