"""Bootstrap the desktop app for pythonw.exe and windowed Windows bundles."""

import os
import sys

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115 - process lifetime
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115 - process lifetime

from network_weather.desktop import main  # noqa: I001 - import after stream bootstrap


if __name__ == "__main__":
    raise SystemExit(main())
