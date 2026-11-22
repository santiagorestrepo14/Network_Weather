# Windows packaging / Empaquetado para Windows

From PowerShell with Python 3.12+:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,desktop]"
python -m pip install pyinstaller
python -m pytest -q
pyinstaller --noconsole --onedir --name NetworkWeather --add-data "src\network_weather\assets;network_weather\assets" scripts\run_desktop.py
.\dist\NetworkWeather\NetworkWeather.exe --demo
```

The `--onedir` build with all eight illustrated assets completed on Windows 11 with Python 3.12 and PyInstaller 6.22.3. The bundled executable stayed open for a four-second demo smoke check, and the archive contains the executable and all eight PNG files. It has **not** yet been validated on a clean Windows machine, nor have tray exit, real monitoring and image persistence been verified in the bundle. Do not publish a release until those checks pass.

Desde PowerShell, ejecuta los mismos comandos en Windows. El empaquetado local terminó correctamente, pero todavía necesita validación en una máquina limpia antes de publicar un ejecutable.
