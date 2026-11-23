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
- Added per-destination diagnostic sample counts, medians, nearest-rank P95, comparable-time variation and protocol-specific failure percentages.
- Read Windows logon startup from the per-user registry entry and keep the checkbox in sync with actual registration.
- Added an optional DNS-independent TCP/443 probe to a configured public IP, with separate evidence for DNS failure versus external connectivity.
- Applied image, fit and motion changes immediately across all weather scenes; rejected missing or disguised image files before import.
- Added subtle motion to sunny and cloudy scenes; animation timers now run only for visible, animated weather when effects are enabled.
- Reset classification after configured probe destinations change, while retaining older history and closing prior incidents without claiming recovery.
- Try one alternate resolved address when the preferred TCP or HTTPS address fails; record the retry context without counting it as an extra measurement sample.
- Reapply the SQLite retention policy hourly while monitoring continues, including after long-running sessions.
- Moved the compact widget's weather and monitoring labels onto the illustrated scene with a dark readability gradient.
- Added a short crossfade when weather changes; reduced motion and disabled effects skip it, and static states return to idle afterward.
- Added a verified WinHTTP HEAD fallback through the Windows system route after direct HTTPS failure; repeated HTTPS success can corroborate DNS trouble without claiming an outage.
- Fixed real-mode desktop startup by keeping history range fields separate from `QThread.start()`.
- Initialized missing standard output streams in the windowed Windows bundle so third-party code can run without a console.
- Shared the no-console desktop bootstrap with `pythonw.exe` startup and added a real controller start/exit integration test.
- Sequenced the first history query after monitor database initialization to avoid a cold-start SQLite lock race.
- Opened UI history queries with read-only SQLite connections, leaving schema setup and migration to the monitor.
- Prevented duplicate Windows desktop processes with a per-user lock; a second launch restores the first widget through a local socket.
- Made the floating widget resizable from its lower-left corner and restored its saved size on launch.
- Explained the initial Unknown state with measurement-round progress and candidate confirmation in Spanish and English.
- Added a Windows CI bundle build and packaged demo smoke check for scene assets, single-instance startup and demo isolation.
- Made nearby compact-chart timestamps distinguishable down to seconds and colored confirmed healthy DNS/TCP results green without treating unanswered gateway ICMP as a proven fault.
- Separated a weather candidate awaiting hysteresis from confirmed secondary phenomena; the overview now lists additional observed signals only after confirmation.
- Added complete Spanish and English user guides for controls, settings and weather meanings, plus Spanish packaging and architecture instructions.
- Added a repeatable packaged real-mode soak command that records rounds, memory and CPU using isolated app data.
- Reloaded weather images in bounded resolution steps when scenes resize, keeping enlarged custom backgrounds sharp and shrinking cached images when the widget gets smaller.
- Replaced font-dependent widget title-bar symbols with drawn pin, panel and hide icons, including a visible pinned state and accessible control names.
- Published a downloadable Windows development preview from successful `main` CI runs.

This is a development snapshot. No release or executable has been published.
