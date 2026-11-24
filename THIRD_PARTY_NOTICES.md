# Third-party notices / Avisos de terceros

Network Weather's own source and artwork are licensed under `LICENSE` (MIT).
The Windows preview also includes the following independently licensed software.

- **Qt / PySide6 Essentials / Shiboken6 6.12.0**: Copyright The Qt Company Ltd.
  and contributors. The bundled libraries are used under LGPL version 3.
  `licenses/LGPL-3.0.txt` and `licenses/GPL-3.0.txt` contain the license texts.
  Qt and PySide6 source for the matching version can be obtained from
  [Qt's source archive](https://download.qt.io/official_releases/qt/6.12/6.12.0/single/)
  and [Qt for Python's source repository](https://code.qt.io/cgit/pyside/pyside-setup.git/).
  The package uses dynamically loaded Qt DLLs and Python extension modules in
  `_internal/PySide6` and `_internal/shiboken6`. You may replace those files with
  ABI-compatible modified builds, then run `NetworkWeather.exe` again. No code
  signing or installation lock prevents this. Qt's component-specific third-party
  notices are listed in its [license documentation](https://doc.qt.io/qt-6/licenses-used-in-qt.html).
- **psutil 7.2.2**: Copyright the psutil contributors. BSD 3-Clause license;
  the copyright, conditions and disclaimer are in `licenses/psutil-LICENSE`.

This notice applies to the portable preview. Build dependencies such as
PyInstaller, pytest and Ruff are not runtime components of the preview.

El código y las ilustraciones propios de Network Weather tienen licencia MIT.
La vista previa para Windows incluye Qt/PySide6/Shiboken6 bajo LGPLv3 y psutil
bajo BSD de tres cláusulas. Los textos de licencia están en `licenses/`.
Las bibliotecas Qt del paquete se cargan dinámicamente y pueden sustituirse
por versiones modificadas compatibles, sin firma ni bloqueo de instalación.
