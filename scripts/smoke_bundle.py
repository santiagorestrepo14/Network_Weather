"""Smoke-check a Windows PyInstaller bundle without network measurements."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ASSETS = {
    "sunny.png", "cloudy.png", "windy.png", "rainy.png",
    "foggy.png", "stormy.png", "offline.png", "unknown.png",
}


def main() -> int:
    if sys.platform != "win32":
        raise RuntimeError("The bundle smoke check requires Windows")
    bundle = Path(sys.argv[1] if len(sys.argv) > 1 else "dist/NetworkWeather").resolve()
    executable = bundle / "NetworkWeather.exe"
    assets = bundle / "_internal" / "network_weather" / "assets"
    if not executable.is_file() or not all((assets / name).is_file() for name in ASSETS):
        raise RuntimeError(f"Incomplete Windows bundle: {bundle}")

    processes: list[subprocess.Popen] = []
    with tempfile.TemporaryDirectory(prefix="network-weather-smoke-") as data_root:
        env = os.environ.copy()
        env["LOCALAPPDATA"] = data_root
        env["QT_QPA_PLATFORM"] = "offscreen"
        command = [str(executable), "--demo"]
        try:
            first = subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            processes.append(first)
            app_data = Path(data_root) / "NetworkWeather"
            lock = app_data / "desktop.lock"
            deadline = time.monotonic() + 15
            while not lock.exists() and first.poll() is None and time.monotonic() < deadline:
                time.sleep(0.1)
            if not lock.exists() or first.poll() is not None:
                raise RuntimeError(f"Bundled demo did not start (exit={first.poll()})")
            time.sleep(1)

            second = subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL,
                                      creationflags=subprocess.CREATE_NO_WINDOW)
            processes.append(second)
            if second.wait(timeout=10) != 0 or first.poll() is not None:
                raise RuntimeError("Bundled demo allowed a second desktop instance")
            if (app_data / "history.db").exists():
                raise RuntimeError("Demo mode wrote to the real measurement database")
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
    print("Windows bundle: eight scenes, demo startup, single instance, no measurements")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
