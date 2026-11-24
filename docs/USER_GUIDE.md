# User guide · Network Weather

Network Weather is a local Windows 10/11 desktop app. The preview ZIP is portable: extract the complete folder and run `NetworkWeather.exe`. For a source installation, follow [README.md](../README.md). It needs no account or project server.

## First launch

By default, the app checks `example.com` and `www.wikipedia.org` every 30 seconds. Each round attempts DNS, TCP/443 and a certificate-verified HTTPS `HEAD /` request. A direct probe to a public IP is optional and off by default.

You may see **Unknown** even after metric cards have values. The engine requires at least three rounds, two destinations and a second consecutive candidate classification before changing weather. The text under the weather shows measurement progress or a pending confirmation. If Unknown persists, open **Panel → Diagnostics** to inspect probes and evidence.

`NetworkWeather.exe --demo` cycles through all eight weather scenes without probes or stored measurements. Its cards are marked as demo data.

## Widget and panel

- Drag the top bar to move the widget and the lower-left corner to resize it. Both values persist.
- The pin button keeps the widget above other windows until disabled.
- The panel button opens **Overview, Diagnostics, History, Incidents and Settings**.
- Minimizing or closing the widget hides it in the tray while monitoring continues. Use the tray icon to restore it; choose **Exit** to stop probing and close the app.
- Choose **Latency** or **Variation** for the compact chart. It plots real samples at their observed times and leaves missing intervals blank.

**Overview** shows the primary weather, confirmed additional signals, observed status cards, the last hour, the active incident and technical explanation. **Diagnostics** separates destinations and protocols, with attempts, successes, median, P95, variation and failures. **History** offers one hour, 24 hours, seven days, 30 days and a custom range. **Incidents** retains start, end, duration, severity and available evidence.

## Settings

| Control | Default and effect |
|---|---|
| Language | Spanish; English is available. Restart to apply. |
| Interval | 30 seconds; allowed range is 5 to 3600 seconds. Restart to apply. |
| Destinations | `example.com, www.wikipedia.org`; use 1 to 8 comma-separated domains. At least two are needed to classify weather. Restart to apply. |
| Direct TCP probe without DNS | Empty/off. Accepts a public IP answering TCP/443; it is not treated as a DNS destination. Restart to apply. |
| History retention | 30 days; allowed range is 1 to 3650 days. Pruning runs at startup and hourly. Restart to apply the new period. |
| Start with Windows | Off. Enabling it adds one entry for the current Windows user only. |
| Reduced motion and weather effects | Independent options that apply immediately. |
| Image fit | `cover` fills the area, `contain` shows the whole image and `center` centers it without distortion. |

Under **Appearance → Weather**, each of the eight states has its own row. Choose **Choose image…**, inspect the preview and confirm. **Reset** restores the bundled background. PNG, JPG and WebP files up to 10 MB and 4096 pixels per dimension are accepted; the app validates and copies the file into `%LOCALAPPDATA%\NetworkWeather\images` without changing the original. Animated effects remain independent of the selected background. Settings and history remain under `%LOCALAPPDATA%\NetworkWeather`.

## Weather meanings

| Weather | Technical reading |
|---|---|
| Clear | DNS, TCP and HTTPS answered across multiple destinations without enough degradation for another state. |
| Cloudy | TCP connection time is elevated toward at least two destinations. |
| Windy | Variation between comparable TCP times is elevated; this is not one-way jitter. |
| Rain | Intermittent TCP/HTTPS response failures across repeated rounds; it is not measured IP packet loss. |
| Fog | DNS resolution failures, with other connectivity evidence where available. |
| Storm | Two or more observed degradation types; Overview lists additional signals. |
| Offline | Two complete rounds without TCP or HTTPS responses from every configured destination, subject to the engine's normal confirmation. |
| Unknown | Insufficient, incomplete or contradictory evidence. It does not mean stable connectivity. |

Weather confidence describes how well measurements support the classification; severity describes the observed magnitude. Cause confidence is shown separately and remains unestablished when the probes cannot identify a root cause. The app does not automatically assign fault to an Internet provider. A gateway may filter ICMP echo while Internet access works. See [architecture](ARCHITECTURE.md) for the internal flow and [packaging](PACKAGING.md) to reproduce the Windows executable.
