# Windows packaging / Empaquetado para Windows

From PowerShell with Python 3.12+:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,desktop]"
python -m pip install pyinstaller
python -m pytest -q
pyinstaller NetworkWeather.spec
python scripts/smoke_bundle.py
.\dist\NetworkWeather\NetworkWeather.exe --demo
```

The spec includes all eight illustrated assets and excludes an incompatible Poppler ICU DLL if that unrelated tool is on the build machine's `PATH`. An earlier command-line bundle failed to start because that DLL shadowed Windows ICU. The spec build now starts in demo mode and, in a real-mode smoke check, wrote a SQLite round with the detected gateway. The preview archive was inspected to confirm the executable, eight PNG files and absence of the conflicting ICU DLL. It has **not** yet been validated on a clean Windows machine. Tray exit and image persistence in the bundle also need direct checks before a public release.
The `desktop_launcher` module initializes absent `stdout` and `stderr` streams before importing the desktop app, as recommended for [PyInstaller windowed builds](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html). The same module is used by `pythonw.exe` at Windows logon, so both no-console launch paths have the same bootstrap.
An isolated `pythonw.exe -m network_weather.desktop_launcher` run wrote a real round to SQLite. A separate real controller run exercised **Salir**, stopped the monitor thread and hid the tray icon. The initial history query starts after monitor database initialization to avoid a lock race during first launch.
The v25 Windows preview also started in real mode with isolated app data and saved one measurement round. UI history queries now use SQLite read-only connections; monitor initialization remains responsible for schema setup and migration.
With a five-second configured interval, the same preview remained running for 42 seconds and saved six real rounds in an isolated database. Its working set at the end of that local check was about 133 MiB; this is one observation, not a long-duration performance benchmark.
The v26 preview passed a two-process check: the second `--demo` launch exited with code 0 while the first remained running. A fresh launch also succeeded after the first process was forcibly stopped. This covers duplicate launch and stale-lock recovery on the local Windows machine.
The v27 preview repeated the duplicate-launch check after adding explicit lock release and startup error reporting; the first copy remained running and the second exited with code 0.
It also remained running in real mode for an isolated 18-second smoke check and saved one measurement round.
The v28 preview started with a saved 620×560 widget size, retained that preference, remained running for 18 seconds and saved one real round. A separate Qt drag check expanded both widget dimensions from the lower-left grip; the full automated suite passed with the new size persistence and initial Unknown-state descriptions.
The Windows CI workflow builds the PyInstaller bundle after unit tests and runs `scripts/smoke_bundle.py`. The smoke check verifies all eight scene images, demo startup, single-instance behavior and absence of synthetic measurements in the real SQLite database. It passed locally against the v28 bundle and in the first hosted GitHub Actions run for the v32 source.
The same bundle smoke check passed locally against v29 after the compact time-label and status-color changes; the v29 ZIP integrity check found no errors.
The v30 bundle smoke check and ZIP integrity check passed after separating pending weather from confirmed secondary phenomena. The automated suite contained 111 passing tests.
In a separate local real-mode run with isolated app data and the default 30-second interval, the v30 executable remained active for 155 seconds and saved five rounds. Its working set at the end was about 131 MiB. This short check does not establish stability over hours or across different networks.
The v31 bundle passed the demo smoke check and ZIP integrity check after the image-resize cache change; the full source suite passed 112 tests. A source-level Qt test verified that a large custom image is decoded at a larger useful resolution after growing the scene and reduced again when shrinking it.
The v32 bundle passed the demo smoke check after replacing the widget header symbols with drawn icons; the full source suite passed 113 tests and Ruff passed. The icon state and accessible labels have a Qt regression test. The first hosted GitHub Actions Windows job passed on commit `2c609c5`.
The v33 bundle passed the demo smoke check and ZIP integrity check after fixing image fit in tall and centered scenes. The full source suite passed 114 tests and Ruff passed.
The v33 hosted Windows CI run also passed and uploaded a downloadable preview artifact. The v34 local bundle passed the demo smoke and ZIP integrity checks after the monitor cadence change; the full source suite passed 115 tests and Ruff passed.
The v34 hosted Windows CI run passed and uploaded a preview artifact. The v35 local bundle passed the demo smoke and ZIP integrity checks after the panel navigation and high-DPI icon fixes. The full source suite passed 116 tests and Ruff passed; an offscreen visual inspection confirmed complete icons in both windows, although that renderer did not show the installed UI font correctly.
The v35 hosted Windows CI run passed and uploaded a preview artifact. The v36 local bundle passed the demo smoke and ZIP integrity checks after tightening the weather history gap display. The full source suite passed 117 tests and Ruff passed.
A source-level Qt integration test now hides the widget, observes another saved real-mode round, then triggers **Exit** through the tray menu and checks that the monitor thread stops. This still leaves interactive tray verification of the packaged executable on a clean Windows profile as a release gate.
Before a final release, perform and record the interactive checks in [Windows release acceptance](RELEASE_CHECKLIST.md) on a clean Windows profile.

For a repeatable real-mode endurance check on a Windows machine, run `python scripts/soak_bundle.py --seconds 3600 --interval 30 --data-dir ..\NetworkWeather-soak-results` after building the bundle. Choose an empty data directory. The script measures actual default destinations, records rounds, memory and CPU, and keeps the isolated SQLite database when `--data-dir` is given. It uses Qt's offscreen platform and force-stops the test process after the interval, so it does not verify tray interaction or a graceful exit. A short local check of this harness on v30 saved seven rounds in 45 seconds at a five-second interval, with memory from 67.7 to 71.1 MiB and 2.3 CPU seconds after startup. A one-hour run has not yet been completed.

## Instrucciones de empaquetado en español

Desde PowerShell, con Python 3.12 o superior:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,desktop]"
python -m pip install pyinstaller
python -m ruff check .
python -m pytest -q
python -m PyInstaller --noconfirm NetworkWeather.spec
python scripts/smoke_bundle.py
.\dist\NetworkWeather\NetworkWeather.exe --demo
```

El ejecutable portátil queda en `dist\NetworkWeather`; conserva toda esa carpeta al copiarlo. El script de comprobación verifica las ocho imágenes, el arranque en demostración, la instancia única y que el modo demo no escriba mediciones reales. La CI de Windows ejecuta esos pasos y publica un artefacto descargable por cada envío correcto a `main`, conservado 30 días. El paquete todavía necesita una prueba interactiva en un Windows limpio y verificar directamente la salida por bandeja y la persistencia de imágenes dentro del ejecutable antes de una publicación pública.

Para repetir una prueba de funcionamiento continuo en modo real, ejecuta `python scripts/soak_bundle.py --seconds 3600 --interval 30 --data-dir ..\NetworkWeather-soak-results` tras compilar. Usa una carpeta de datos vacía. El script consulta los destinos predeterminados, registra rondas, memoria y CPU, y conserva la base SQLite aislada si indicas `--data-dir`. Utiliza Qt sin pantalla y detiene el proceso de prueba al terminar; no comprueba la bandeja ni una salida normal. Se validó localmente con una ejecución corta, pero todavía falta la prueba de una hora.
