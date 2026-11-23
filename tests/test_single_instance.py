"""Check the desktop's process lock across real Windows processes."""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="Windows desktop integration")
def test_second_desktop_process_exits_and_stale_lock_recovers(tmp_path):
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(tmp_path)
    env["QT_QPA_PLATFORM"] = "offscreen"
    command = [sys.executable, "-m", "network_weather.desktop_launcher", "--demo"]
    processes: list[subprocess.Popen] = []
    try:
        first = subprocess.Popen(command, env=env)
        processes.append(first)
        lock_path = Path(tmp_path) / "NetworkWeather" / "desktop.lock"
        deadline = time.monotonic() + 10
        while not lock_path.exists() and first.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert lock_path.exists() and first.poll() is None
        # Let the first process finish opening its local restore socket.
        time.sleep(0.5)

        second = subprocess.Popen(command, env=env)
        processes.append(second)
        assert second.wait(timeout=10) == 0
        assert first.poll() is None

        first.kill()
        first.wait(timeout=5)
        third = subprocess.Popen(command, env=env)
        processes.append(third)
        time.sleep(2)
        assert third.poll() is None
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
