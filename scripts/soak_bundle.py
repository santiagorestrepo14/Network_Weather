"""Run a packaged monitor for a chosen duration with isolated Windows app data."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import nullcontext
from pathlib import Path

import psutil
from PySide6.QtCore import QSettings


def main(argv: list[str] | None = None) -> int:
    if sys.platform != "win32":
        raise RuntimeError("The packaged monitor soak check requires Windows")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=Path("dist/NetworkWeather"))
    parser.add_argument("--seconds", type=int, default=3600)
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--min-rounds", type=int)
    parser.add_argument("--data-dir", type=Path, help="Empty directory to retain the test database")
    args = parser.parse_args(argv)
    if args.seconds < 30 or not 5 <= args.interval <= 3600:
        parser.error("seconds must be at least 30 and interval must be 5..3600")
    expected = (args.min_rounds if args.min_rounds is not None else
                max(2, args.seconds // (args.interval * 3)))
    if expected < 1:
        parser.error("min-rounds must be at least 1")
    executable = args.bundle.resolve() / "NetworkWeather.exe"
    if not executable.is_file():
        parser.error(f"Missing executable: {executable}")
    if args.data_dir and args.data_dir.exists() and any(args.data_dir.iterdir()):
        parser.error("data-dir must be empty so prior measurements cannot affect the result")

    context = (nullcontext(args.data_dir.resolve()) if args.data_dir else
               tempfile.TemporaryDirectory(prefix="network-weather-soak-"))
    with context as root:
        data_root = Path(root)
        app_data = data_root / "NetworkWeather"
        app_data.mkdir(parents=True, exist_ok=True)
        settings = QSettings(str(app_data / "settings.ini"), QSettings.Format.IniFormat)
        settings.setValue("interval", args.interval)
        settings.sync()
        env = os.environ.copy()
        env["LOCALAPPDATA"] = str(data_root)
        env["QT_QPA_PLATFORM"] = "offscreen"
        process = subprocess.Popen(
            [str(executable)], env=env, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        monitor = psutil.Process(process.pid)
        lock = app_data / "desktop.lock"
        memory_samples: list[int] = []
        cpu_start = None
        cpu_end = None
        try:
            startup_deadline = time.monotonic() + 20
            while not lock.exists() and time.monotonic() < startup_deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"Packaged monitor exited during startup: {process.returncode}")
                time.sleep(0.1)
            if not lock.exists():
                raise RuntimeError("Packaged monitor did not initialize within 20 seconds")
            time.sleep(2)
            started = time.monotonic()
            while time.monotonic() - started < args.seconds:
                if process.poll() is not None:
                    raise RuntimeError(f"Packaged monitor exited early with code {process.returncode}")
                memory_samples.append(monitor.memory_info().rss)
                cpu = monitor.cpu_times()
                cpu_now = cpu.user + cpu.system
                cpu_start = cpu_now if cpu_start is None else cpu_start
                cpu_end = cpu_now
                time.sleep(min(10, max(0, args.seconds - (time.monotonic() - started))))
            if process.poll() is not None:
                raise RuntimeError(f"Packaged monitor exited early with code {process.returncode}")
            memory_samples.append(monitor.memory_info().rss)
            cpu = monitor.cpu_times()
            cpu_end = cpu.user + cpu.system
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)

        database = app_data / "history.db"
        if not database.is_file():
            raise RuntimeError("The packaged monitor did not create a history database")
        with sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True) as connection:
            rounds, first_at, last_at = connection.execute(
                "SELECT COUNT(*), MIN(started_at), MAX(started_at) FROM rounds"
            ).fetchone()
        if rounds < expected:
            raise RuntimeError(f"Only {rounds} rounds were saved; expected at least {expected}")
        mib = 1024 * 1024
        print(json.dumps({
            "duration_seconds": args.seconds,
            "interval_seconds": args.interval,
            "rounds": rounds,
            "first_round": first_at,
            "last_round": last_at,
            "memory_start_mib": round(memory_samples[0] / mib, 1),
            "memory_end_mib": round(memory_samples[-1] / mib, 1),
            "memory_peak_mib": round(max(memory_samples) / mib, 1),
            "cpu_seconds": round((cpu_end or 0) - (cpu_start or 0), 2),
            "data_dir": str(data_root) if args.data_dir else "temporary (removed)",
        }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
