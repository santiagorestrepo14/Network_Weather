# Changelog / Registro de cambios

## Unreleased / Sin publicar

- Added real DNS, TCP and verified HTTPS probes, plus adapter snapshots.
- Added conservative weather rules with hysteresis, SQLite history and incident tracking.
- Added a Windows widget, tray icon, expanded diagnostic view and visual demo mode.
- Added configurable probe destinations, interval, reduced motion and per-weather custom images.
- Added IPv4/IPv6 route-adapter matching, cached Windows gateway discovery and honest ICMP echo evidence.
- Added a reproducible PyInstaller spec that avoids bundling an incompatible third-party ICU DLL.
- Added indexed historical probe samples, legacy backfill, time and destination filters, categorical weather timeline and observed TCP latency chart.
- Added incident details with duration, peak severity and measured evidence, without unsupported cause attribution.
- Tightened outage classification across repeated complete rounds and separated latency baselines by destination.
- Added a persistent Spanish/English language setting for the widget, panel, charts, incident details and tray.
- Added optional read-only Native Wi-Fi quality, RSSI and channel context without scanning nearby networks.
- Added a time-scaled compact chart with persisted latency/variation selection and gaps for missing observations.
- Recover a floating widget whose saved position is outside the current display layout.
- Reset classification after long observation gaps and end prior incidents at the last observed sample without claiming recovery.
- Redesigned the expanded overview around the weather scene, observed status cards, last-hour history, active incident and evidence.

This is a development snapshot. No release or executable has been published.
