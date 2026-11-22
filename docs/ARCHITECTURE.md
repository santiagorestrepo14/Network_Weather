# Architecture / Arquitectura

`probes.py` performs DNS, TCP and HTTPS checks without changing network settings. `collector.py` groups actual probes into a round and records local adapter snapshots. `metrics.py` computes protocol- and destination-specific statistics. `weather.py` classifies a rolling window using explicit evidence and two-candidate hysteresis. `history.py` stores rounds and incidents in SQLite. `monitor.py` coordinates those components. `desktop.py` keeps this monitor in a `QThread` so the Qt event loop remains responsive. The visual demo mode never starts the monitor.

`probes.py` hace comprobaciones DNS, TCP y HTTPS sin modificar la red. `collector.py` reúne sondas reales y adaptadores locales. `metrics.py` calcula estadísticas por destino y protocolo. `weather.py` clasifica una ventana temporal con evidencias e histéresis. `history.py` guarda rondas e incidentes en SQLite. `monitor.py` coordina estos componentes. `desktop.py` ejecuta el monitor en un `QThread` para no bloquear Qt. El modo demostración no inicia el monitor.

The event loop does not call network probes or use the worker's SQLite connection. A second SQLite connection reads history in the UI thread using WAL mode. Settings and custom images live under `%LOCALAPPDATA%\NetworkWeather`. Synthetic demo visuals are not written to the measurement database.
