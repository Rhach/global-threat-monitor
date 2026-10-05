# Global Threat Monitor

A simulated security-operations dashboard for your terminal. Python standard library only.

Global Threat Monitor fills your terminal with animated traffic routes, sensor telemetry, policy actions, and a timestamped event stream. Everything runs locally with generated data. It does not monitor, scan, or connect to any network.

Version 4 replaces the flashing Hollywood panels with a calmer operations display. The renderer sends only changed cells, and animation timing is independent of simulation speed.

## Features

- Fullscreen dashboard with summary cards and readable, severity-coded events
- Braille world map with geographically positioned sensors and curved traffic routes
- MapSCII-style detailed Braille coastlines, with zoom and pan
- Country borders and 128 city sensors across the Americas, Europe, Africa, Asia and Oceania
- World, Europe, Asia, and Americas views, selected with `R`
- Simulated CPU, memory, temperature, and latency estimates tied to modeled payload throughput
- Traffic history, detection counts, and an active-flow table
- Persistent fictional sites/assets, expected communication patterns, and separate city collectors
- DNS exchanges, bursty HTTPS, persistent SSH and bulk backup sessions with directional accounting
- Critical incidents every 30–90 seconds with a camera follow and staged containment
- Interactive simulation console with `status`, `flows`, and `help` commands
- Optional containment drill with `G`
- Four color themes with a persisted selection
- Changed-cell rendering, cached maps, and configurable 10–60 FPS animation
- Non-blocking, opt-in sound chimes on Windows
- Windows, Linux, and macOS support

<details>
<summary>Earlier v3 dashboard</summary>

<img width="1892" height="1005" alt="The previous Hollywood-style dashboard, before the v4 redesign" src="https://github.com/user-attachments/assets/f36c4261-e80d-471b-a60f-6f824a7964ec" />

</details>

## Requirements

- Python 3.9 or newer
- An interactive terminal with ANSI escapes and a font supporting box-drawing and braille characters
- Terminal size of at least 80×24. 120×40 or larger gives the map and event feed more room.

## Usage

Run directly:

```bash
python global-threat-monitor.py
```

With options:

```bash
python global-threat-monitor.py --theme matrix
python global-threat-monitor.py --theme cyberpunk
python global-threat-monitor.py --theme amber
python global-threat-monitor.py --theme ice
python global-threat-monitor.py --speed 1.5
python global-threat-monitor.py --theme ice --fps 30
python global-threat-monitor.py --fps 15
python global-threat-monitor.py --theme ice --seed 12
python global-threat-monitor.py --sound
python global-threat-monitor.py --no-sound
```

## Options

```text
--theme <name>   Set startup theme: matrix, cyberpunk, amber, ice
--sound          Enable optional sound chimes
--no-sound       Mute sound chimes
--speed <mult>   Set speed multiplier. Clamped between 0.25 and 4.0
--fps <10-60>    Set rendering rate. Default 30; use 15 for slower terminals
--seed <int>     Reproduce session selection, ports and background schedule
--version        Show version information
--help           Show help
```

## Controls

```text
Q / ESC   Quit
T         Cycle theme
R         Cycle world / Europe / Asia / Americas
B         Toggle country borders
Wheel up  Zoom map in
Wheel down Zoom map out
Arrows    Pan map up / down / left / right
[ / ]     Zoom map out / in
H J K L   Pan map left / down / up / right
0         Reset the current regional view
P         Pause / resume
S         Toggle sound
A         Add a simulated traffic flow
F         Trigger a critical incident immediately
C         Open simulation console. Esc returns to the dashboard
G         Start a containment drill. Press keys to complete; Esc cancels
+ / =     Increase speed
-         Decrease speed
```

In the console, enter `help`, `status`, `flows`, `flow-history`, `sessions`, `org`, `baseline`, `unfamiliar`, `clear`, or `exit`. The old `enhance`, `ddos-localhost`, and `nuke-gibson` commands still work as local simulations. Ctrl+C quits from any view.

`--speed` changes the simulation clock, traffic, and telemetry cadence. `--fps` changes only the redraw rate. Pausing freezes the simulation, including the displayed clock.

## Organization and expected peers

The fictional Aster organization has an Athens office (`SITE-ATH`), Frankfurt
data center (`SITE-FRA`), Singapore cloud region (`SITE-SIN`), and remote users
(`SITE-REMOTE`). Assets have stable IDs, roles, owners, criticality, and addresses
from documentation ranges. `org` lists these facts and the configured source,
peer, service, and purpose of each expected relationship. Catalogs persist for
the running session across redraws and map navigation; they are not saved to disk.

Ordinary background activity and `A` choose from the same catalog, favoring
expected peer/service relationships 90% of the time. For example, `ATH-WS1`
normally reaches `FRA-APP` over HTTPS, or `FRA-DNS` for name resolution.
`NEW` means the peer/service is outside that asset's configured baseline and
needs review. It does not prove malicious intent or imply an automatic block;
ordinary unfamiliar activity ends with its assessment still pending.

Flow rows and events use compact `SITE:asset` labels such as `ATH:ws>FRA:app`.
`OK` identifies an expected relationship. A trailing `?`, as in `EXT:peer?` or
`REM:roam?`, explicitly marks unknown geography. Such activity remains in the
flow table and events, while the map omits a route whose coordinates are missing.
The `flows` console command shows full site/asset IDs, addresses, collector ID,
connection ID and assessment. Compact rows prioritize these endpoint labels;
wider panels also show rate and service. Event timestamps remain UTC.

All 128 existing cities remain separate observation collectors (`COL-ATH`,
`COL-FRA`, etc.), with their original coordinates and city labels. A collector
is not an organization asset. In particular, a roaming user's activity observed
by `COL-FRA` does not assign Frankfurt coordinates to that user. The seed applies
to session choices, source ports and background scheduling for the same inputs
and simulation time, independent of rendering FPS. Legacy priority-incident
pacing and its marker stages still use the earlier script; correlation and
consequential response are follow-up slices.

To reproduce the baseline demonstration without an interactive terminal:

```bash
python3 demo_organization.py
python3 -m unittest -v test_simulation_model
```

The demonstration prints `ATH:ws>FRA:app expected`, followed by
`ATH:ws>EXT:peer? unfamiliar; review baseline / geography unknown`, and an
expected roaming-user connection with unknown geography. No packets are sent.

For the dashboard demonstration, run with `--seed 12`, press `P`, then `C`.
Enter `baseline`, `unfamiliar`, and `flows` to compare the same Athens workstation
and collector across its expected Frankfurt service and an unfamiliar peer.
Press Esc to inspect both flow rows while paused; `R` changes the map region
without changing asset identities. Enter `org` in the console for the catalog.
The existing `F` incident animation now uses `ATH-WS1` and the catalog's known
Dubai peer; its legacy scripted lifecycle is retained until the incident slice.

## Sessions and reconciled traffic

Each connection has a stable flow ID and originator/responder ports. Transport,
application service and encryption are separate fields. The vocabulary follows
[Zeek's connection log](https://docs.zeek.org/en/master/reference/logs/conn.html);
the dashboard does not integrate Zeek or inspect encrypted payloads. `flows`
prints duration, state, directional payload bytes, payload-bearing packet counts,
and directional rates. Compact dashboard rows preserve endpoint and service
labels; wider rows also show transport/encryption, rate and connection state.

| Service | Transport / peer port | Encryption | Activity |
| --- | --- | --- | --- |
| DNS | UDP / 53 | none | 0.2s exchange: 72B request, then 220B response |
| HTTPS | TCP / 443 | TLS | 12s connection: three 1.2KB requests and 240KB responses, separated by idle gaps |
| SSH | TCP / 22 | SSH | 180s interactive connection with small bidirectional keepalives and command bursts |
| BACKUP | TCP / 443 | TLS | 30s upload: 2,000,000 originator B/s and 10,000 responder B/s; 60,300,000B total |

Bytes count modeled payload, excluding headers and retransmissions. Packet
counts are modeled payload-bearing datagrams/segments; they exclude TCP setup,
ACK-only packets and teardown. DNS has one request and one response packet.
Live connection state is `S0` before a DNS reply, otherwise `S1`; normal
completion is `SF`. Completed sessions stop accumulating and have zero live
rates. The last 120 completed summaries remain available through `flow-history`.
The model permits 12 live sessions; manual generation reserves one slot for the
legacy priority incident and background generation targets fewer than five.

Directional session rates measure byte growth over the trailing one simulation
second, counting time before creation as zero. The throughput card and traffic
history use the **previous completed one-second simulation bucket**, summing
both directions across all modeled sessions, including any session that ended
in that bucket. There is no hidden background aggregate or synthetic traffic.
Consequently a newly completed DNS exchange appears in that bucket although
its current live rate is zero; a partial next bucket leaves the card unchanged.
The last 120 buckets are retained. `status` reports lifetime payload bytes so
the bucket integral can be reconciled before history eviction. Event totals and
events/sec count actual emitted observations; CPU, temperature and latency are
explicit load estimates, with RAM/disk fixed baseline estimates. Detection and
containment counts begin at zero.

Moving map heads represent aggregate activity on an established session, using
a repeating three-second marker cycle. Their location and animation speed do
not represent physical packet transit, delivery progress or transfer throughput.
An idle session keeps its row and endpoint labels while its activity marker
disappears when the trailing rate reaches zero. Pause freezes session accounting
and markers; speed scales their simulation time. FPS changes only rendering.
The legacy `F` priority marker retains its scripted camera/lifecycle timing,
while its session uses the same HTTPS accounting; its scripted containment will
be replaced by correlated incident and response modeling in later slices.

Run the reproducible demonstration without a terminal or real-time waits:

```bash
python3 demo_sessions.py
python3 -m unittest -v test_session_simulation
```

It shows DNS's request before its response, HTTPS's idle gaps, SSH remaining
active, the backup ending with 60,300,000B, and the 31s bucket integral matching
all transferred bytes. Fixtures compare one large advance against 15/60 FPS
partitions, seeded schedules, pause, speed and marker speed independence.

For a dashboard demonstration, start with `--seed 12 --speed 0.25`, press `P`,
then `C`, and enter `sessions` and `flows`. This creates the four named sessions
at one simulation instant. Press Esc and `P` to resume. DNS finishes after 0.8
real seconds at this speed; HTTPS bursts while SSH and backup remain visible.
Pause after ten simulation seconds and use `flows` and `status` to compare the
backup's 20,000,000 originator bytes with its 16 Mb/s outgoing rate. Other live
sessions contribute their displayed directional bytes to the aggregate. Resume
past 30 simulation seconds, then inspect `flow-history` for the completed backup
and `flows` for the persistent SSH session. Console time continues ordinary
session progression unless paused; only the legacy priority script stops there.

## Braille map

The dashboard always uses detailed Braille coastlines inspired by
[MapSCII](https://github.com/rastapasta/mapscii). The renderer uses the same
projection as v4's sensors and curved traffic routes, and keeps the changed-cell
rendering. Zoom and pan work while paused. `R`
switches regions and resets the selected region's viewport; `0` resets the current
view. `+` and `-` still change simulation speed.

Scroll the mouse wheel up to zoom in and down to zoom out anywhere in the
dashboard. Arrow keys pan the map. The existing `[` / `]` and `H J K L` controls
also work. Mouse scrolling is ignored in the simulation console and drill.

After 10 seconds without a map interaction, the map gradually zooms out and
recenters toward the current region's overview. Zooming, panning, changing
regions, resetting the map or toggling borders restarts the timer. This camera
behavior uses real time and continues while the simulation is paused; it stops
while the console or drill is open. Scroll or pan to stop the automatic zoom-out.

Every 30–90 seconds of active dashboard time, a simulated priority incident
triggers a red P1 banner and focuses the map on an exfiltration flow. The camera
zooms in and follows the packet along a persistent trail, with a target reticle,
priority flow row and timestamped acquisition, tracing and quarantine events.
After containment, the banner turns green and the map resumes gradual zoom-out.
Each sequence lasts about 21 seconds. Incident timing is independent of simulation
speed and freezes while paused or while the console or drill is open.
Press `F` to preview a critical incident immediately.

Map controls immediately stop the automatic follow and leave the incident
running with a manual camera. Idle zoom-out waits while the camera is tracking
the incident. The underlying traffic remains a local simulation.

Country borders are shown by default; press `B` to hide or
restore them. Borders use a muted color beneath city markers and traffic routes.
The map has 128 city sensors, including Athens, Paris, Toronto, Lagos, Seoul and
Auckland. Cities appear as dots. A city's code appears only while it is the source
or destination of an active trace and disappears when that trace completes.
Labels avoid each other and city markers; when multiple cities share a terminal
cell, active or flagged sensors take priority.

The map runs offline with the Python standard library. Keep `terminal_map.py`, `terminal_input.py`, `critical_flow.py`, `simulation_model.py`,
`world_coastlines.json` and `world_borders.json` alongside the main script. Missing
or invalid coastline data records an event; sensors, routes and available borders
continue to render.
Unavailable border data leaves the map usable without country borders.

The bundled data is [Natural Earth's 1:110m coastline](https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_110m_coastline.geojson),
rounded to three decimal places. Natural Earth data is
[public domain](https://www.naturalearthdata.com/about/terms-of-use/). This is a
world and regional overview with zoom capped at 8x; it has no street tiles or
points of interest. Borders use [Natural Earth's 1:110m Admin 0 land boundary lines](https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_110m_admin_0_boundary_lines_land.geojson),
also rounded to three decimal places.

## Configuration

Global Threat Monitor stores the selected theme in a local config file.
The default for a new installation is `ice`; an existing saved theme takes precedence.

Config locations:

```text
Windows: %APPDATA%/GlobalThreatMonitor/config.json
Linux:   ~/.config/global-threat-monitor/config.json
macOS:   ~/.config/global-threat-monitor/config.json
```

## Disclaimer

This is not a cybersecurity tool.
This is fake.
All displayed activity and metrics are simulated.

Do not use it to assess security posture, impress auditors, diagnose incidents, or convince management that the blinking red thing means progress.
Or do, but in that case, it is between you, your conscience, and the very tired incident response team that will eventually be asked why the DNA decrypter panel is not in Splunk.

## Disclaimer 2

I did not write a single line of code on this. Because burning forests and expending energy in 2026 is not about productivity. It is about sending a message. Peak humanity.

## Disclaimer 3

If you can find anything weird in it, Gemini 3.5 flash (high) injected it. Take it up with Google.

## Development

Run the rendering, timing, and keyboard checks with:

```bash
python3 -m unittest -v test_monitor test_terminal_map test_terminal_input test_critical_flow test_simulation_model test_session_simulation
```

The tests replay incremental ANSI output to check for stale characters and exercise resize, pause, console input, and terminal restoration through a pseudo-terminal on macOS and Linux.

## License

MIT
