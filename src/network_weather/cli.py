"""CLI for one real measurement round or continuous JSON Lines monitoring."""

import argparse
import json
import time

from network_weather.collector import collect_once
from network_weather.config import ProbeConfig
from network_weather.monitor import Monitor


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="network-weather")
    parser.add_argument("--destination", action="append", dest="destinations")
    parser.add_argument("--direct-ip", help="Optional numeric public IP for DNS-independent TCP/443")
    parser.add_argument("--interval", type=float, default=30)
    parser.add_argument("--timeout", type=float, default=3)
    parser.add_argument("--once", action="store_true", help="Run one round and exit")
    parser.add_argument("--raw", action="store_true", help="Probe without storing history")
    args = parser.parse_args(argv)
    try:
        config = ProbeConfig(
            destinations=tuple(args.destinations) if args.destinations else ProbeConfig().destinations,
            interval_seconds=args.interval,
            timeout_seconds=args.timeout,
            direct_ip_target=args.direct_ip,
        )
    except ValueError as exc:
        parser.error(str(exc))
    try:
        if args.raw:
            while True:
                started = time.monotonic()
                print(json.dumps(collect_once(config).to_dict(), ensure_ascii=False), flush=True)
                if args.once:
                    return 0
                time.sleep(max(0, config.interval_seconds - (time.monotonic() - started)))
        with Monitor(config) as monitor:
            while True:
                started = time.monotonic()
                round_, result = monitor.measure()
                output = round_.to_dict()
                output["classification"] = {
                    "weather": result.weather.value,
                    "secondary": [weather.value for weather in result.secondary],
                    "pending_weather": (result.pending_weather.value
                                        if result.pending_weather is not None else None),
                    "confidence": result.confidence,
                    "severity": result.severity,
                    "evidence": [
                        {"code": e.code, "detail": e.detail, "observed": e.observed,
                         "threshold": e.threshold}
                        for e in result.evidence
                    ],
                    "cause": result.cause,
                }
                print(json.dumps(output, ensure_ascii=False), flush=True)
                if args.once:
                    return 0
                time.sleep(max(0, config.interval_seconds - (time.monotonic() - started)))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
