# Windows packaging / Empaquetado para Windows

From PowerShell with Python 3.12+:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,desktop]"
python -m pip install pyinstaller
python -m pytest -q
pyinstaller NetworkWeather.spec
.\dist\NetworkWeather\NetworkWeather.exe --demo
```

The spec includes all eight illustrated assets and excludes an incompatible Poppler ICU DLL if that unrelated tool is on the build machine's `PATH`. An earlier command-line bundle failed to start because that DLL shadowed Windows ICU. The spec build now starts in demo mode and, in a real-mode smoke check, wrote a SQLite round with the detected gateway. The preview archive was inspected to confirm the executable, eight PNG files and absence of the conflicting ICU DLL. It has **not** yet been validated on a clean Windows machine. Tray exit and image persistence in the bundle also need direct checks before a public release.
The `desktop_launcher` module initializes absent `stdout` and `stderr` streams before importing the desktop app, as recommended for [PyInstaller windowed builds](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html). The same module is used by `pythonw.exe` at Windows logon, so both no-console launch paths have the same bootstrap.
An isolated `pythonw.exe -m network_weather.desktop_launcher` run wrote a real round to SQLite. A separate real controller run exercised **Salir**, stopped the monitor thread and hid the tray icon. The initial history query starts after monitor database initialization to avoid a lock race during first launch.

Desde PowerShell, ejecuta los mismos comandos en Windows. El empaquetado local terminó correctamente, pero todavía necesita validación en una máquina limpia antes de publicar un ejecutable.
