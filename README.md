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
- Collector heartbeats, coverage gaps, bounded buffering, ingestion lag and loss
- CPU/RAM estimates derived from observed payload, processing work and queue occupancy
- Traffic history, detection counts, and an active-flow table
- Persistent fictional sites/assets, expected communication patterns, and separate city collectors
- DNS exchanges, bursty HTTPS, persistent SSH and bulk backup sessions with directional accounting
- Correlated critical incidents, grounded confidence, benign lookalikes, and scoped response
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
F         Trigger the correlated exfiltration scenario immediately
E         Open active flow selection (N/M previous/next; Enter inspects)
I         Open active incident selection (N/M previous/next; Enter inspects)
C         Open simulation console. Esc returns to the dashboard
G         Start a containment drill. Press keys to complete; Esc cancels
+ / =     Increase speed
-         Decrease speed
```

In the console, enter `help`, `status`, `flows`, `flow-history`, `sessions`, `org`, `baseline`, `unfamiliar`, `scenario [variant]`, `incident`, `timeline [N]`, `incidents`, `response`, `actions`, `dismiss [reason]`, `collectors [ID]`, `outage COL-ID`, `recover COL-ID`, `delay COL-ID [seconds]`, `clear`, or `exit`. `response` previews explicit action commands and their scope. The old `enhance`, `ddos-localhost`, and `nuke-gibson` commands still work as local simulations. Ctrl+C quits from any view.

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
and simulation time, independent of rendering FPS. The correlated incident
scheduler uses the same simulation clock; its evidence references these assets
and their actual sessions.

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
The `F` scenario uses `ATH-WS1` and the catalog's known Dubai peer, `EXT-DXB`.
The peer has known geography but is outside the workstation's expected peers.

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
The model permits 12 live sessions; background generation targets fewer than
five. Ordinary scenarios reserve one slot across successive sessions; the partial
variant reserves two for concurrent uploads. A trigger without sufficient capacity
is deferred without creating an incident or incrementing its count.

Directional session rates measure byte growth over the trailing one simulation
second, counting time before creation as zero. The throughput card and traffic
history use the **previous completed one-second simulation bucket**, summing
both directions across all modeled sessions, including any session that ended
in that bucket. There is no hidden background aggregate or synthetic traffic.
Consequently a newly completed DNS exchange appears in that bucket although
its current live rate is zero; a partial next bucket leaves the card unchanged.
The last 120 buckets are retained. `status` reports lifetime payload bytes so
the bucket integral can be reconciled before history eviction. Event totals and
events/sec count received observations and local control/loss messages. Collector
CPU/RAM estimates follow observed payload, processing work and queue pressure;
ingestion p95 and event loss use defined 60s measurement windows below. Missing
collector data is explicit. Temperature, fan and packet-loss placeholders have
been removed. Detection and containment counts begin at zero.

Moving map heads represent aggregate activity on an established session, using
a repeating three-second marker cycle. Their location and animation speed do
not represent physical packet transit, delivery progress or transfer throughput.
An idle session keeps its row and endpoint labels while its activity marker
disappears when the trailing rate reaches zero. Pause freezes session accounting
and markers; speed scales their simulation time. FPS changes only rendering.
The `F` scenario uses the same markers and session accounting. During
authentication and idle gaps, incident endpoints stay highlighted while the
activity head and transfer trail disappear. Camera easing uses real time.

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
session and incident progression unless paused.

## Correlated incident and retained evidence

The first scenario follows `ATH-WS1` and `EXT-DXB` through these observations.
Times below are simulation seconds relative to its start:

| Time | Observation and actual session behavior |
| --- | --- |
| 0s | Five failed logins followed by success; the stated authentication baseline is 0–1 failures per login |
| 2s | First scenario HTTPS session to `203.0.113.201`, outside the workstation's configured peer baseline |
| 16s / 30s | Further HTTPS sessions to the same peer at 14s start intervals; each connection lasts 12s |
| 44s | A fourth HTTPS session starts a 30s upload over TCP/443 with TLS encryption |
| 49s | 10,000,000 originator bytes observed in 5s, compared with 3,600 originator bytes in an expected 12s HTTPS session |
| 74s | Upload finishes naturally with 60,000,000 originator and 300,000 responder bytes; incident remains unresolved |

This supports suspected exfiltration in the sense of data removal described by
[MITRE ATT&CK TA0010](https://attack.mitre.org/tactics/TA0010/). The modeled
recurrence is an observation; the simulation makes no command-and-control
technique claim. TLS payload content is unavailable. No signature confirmation,
automatic blocking or credential revocation is inferred from this evidence.
The existing keyboard drill is a separate simulation exercise and does not
resolve this incident. The operator can apply the consequential responses below.

Every observation has an immutable incident ID, evidence ID, timestamp, asset
IDs, collector ID and (when applicable) session ID. The same session IDs appear
in `flows` and `flow-history`; the priority row shows its incident ID. At the end,
the banner clears and live flows disappear, while the last 64 incident summaries
retain up to 64 timeline records and five scenario sessions each. Ordinary completed
session history remains limited to 120; an incident's original evidence survives
that session-history eviction. History is retained only for the running process.

Console `incident` shows the active or latest incident and its sessions.
`timeline` prints its original observations with elapsed simulation timestamps;
`timeline N` selects one numbered observation so the full evidence is readable
at 80×24 (for example, `timeline 1` for authentication or `timeline 9` for volume).
`incidents` prints bounded retained summaries. An existing active incident makes
additional `F` or `scenario` triggers idempotent.

To reproduce all stages and reconcile the byte total without a terminal,
real-time waits or network access:

```bash
python3 demo_incident.py
python3 -m unittest -v test_critical_flow
```

The demo reconciles 62,470,800 payload bytes across the three ordinary HTTPS
sessions and upload; it retains 11 observations and reports zero containments.
Fixtures compare one 240s advance with 15/60 FPS partitions including scheduled
scenarios and background sessions, and check pause, speed, capacity reservation,
idle map markers, retained evidence, manual camera override and incremental
rendering at multiple terminal sizes.

For an interactive demonstration, start with `--seed 12 --speed 0.25`, press `P`
and `F`, then `C` and enter `incident` or `timeline 1`. Resume with Esc and `P`.
After 49 simulation seconds (196 real seconds at this speed), pause and inspect
`flows`, `incident`, and `timeline 9` to trace `CT-001` to its upload session.
Resume past 74 simulation seconds, then inspect `incident`, `timeline 11`,
`incidents`, and `flow-history` for its unresolved retained outcome. Automatic
scheduling starts the next scenario only after the current one finishes.

## Scoped response and verification

Enter `response` in the console to preview the current incident's flow IDs,
targets and scope. Then use an explicit command:

| Command | Applied scope |
| --- | --- |
| `block session FLOW-00004` | Stop this incident session; other and future sessions remain allowed |
| `block peer ATH-WS1 EXT-DXB` | Stop egress from that local asset to that peer, including future sessions |
| `isolate endpoint ATH-WS1` | Stop all incoming/outgoing modeled network activity on the local endpoint, including legitimate work |
| `revoke session FLOW-00004` | Revoke this incident session only |
| `revoke credential aster.ws1` | Stop current/future sessions explicitly using the scenario's modeled credential |

Use the actual flow ID printed by `response`; IDs depend on other generated
activity. Remote peers cannot be locally isolated. Unknown targets are rejected
without an action or counter change. `aster.ws1` is the modeled credential on
scenario sessions; other sessions have no credential unless explicitly assigned
in the model. Credential revocation therefore does not isolate the endpoint.

A request gets a stable `CT-...-ACT-...` ID. Ordinary variants apply exactly
**one simulation second after request** and verify their scope **one second
after application**. The delayed variant uses five seconds to apply and another
three seconds to verify.
`actions`, `incident` and `timeline` preserve phase timestamps and results; the
banner and live flow row show the same current action status. Completed/denied
session summaries link the effective action ID. `retry ACTION-ID` or repeating
the identical command returns the existing action; counters increment once on
application. `cancel ACTION-ID` cancels a pending request before application.
Retrying a cancelled action returns its cancellation; it does not apply it.

Byte totals freeze at the application timestamp, directional rates become zero,
and activity heads/trails disappear together. Historical bytes and original
observations remain available. The current throughput card still represents the
last complete one-second bucket, including bytes sent up to application; the
next full bucket reflects the stopped traffic. Unrelated traffic continues.
Pause freezes application and verification delays; speed scales these delays
with the same simulation clock as transfers. Rendering FPS changes neither.

An early session-only block verifies that scope while later recurring sessions
remain possible. Blocking the final upload with no remaining/planned incident
network activity verifies containment for this scenario. A late session action
that applies after natural completion reports no matching active transfer and
leaves the incident unresolved. Endpoint/peer/credential policies deny matching
sessions in future scenarios; those denied sessions have zero bytes and no live
map route. Verification checks all related active/planned activity: a policy on
the primary endpoint cannot cancel an unprotected alternate endpoint. Verified
containment cancels remaining protected scenario network stages. A naturally
completed, uncontained bulk transfer remains unresolved evidence even when a
late policy stops future connections.
Policies persist for the running process. There is no automatic success script:
an unchecked suspicious scenario still ends unresolved. The banner retires at
the variant's final boundary (74s ordinary/delayed, 76s partial, 32s benign), or
after outstanding responses settle if requested late.

Each incident retains at most eight response actions. The 64-record timeline
covers original scenario evidence plus their response phases. Session-only
responses create no persistent policy; persistent policies are bounded by the
finite catalog of endpoint, peer and credential scopes. Incident and session
history limits remain 64 and 120 respectively; all state is in memory.

Run the exact-clock demonstration and response fixtures:

```bash
python3 demo_response.py
python3 -m unittest -v test_response_actions
```

The demonstration requests a final-upload block at t=49s, applies it at t=50s
with 12,000,000 originator bytes, verifies at t=51s, and preserves the legitimate
backup. For interactive use, trigger `F`, wait for the unusual-volume observation,
pause with `P`, open `C`, enter `response`, and request `block session` with the
printed upload ID. Return with Esc and resume with `P`; inspect `actions` and
`flow-history` after two simulation seconds. Compare `isolate endpoint ATH-WS1`
in a fresh process to see legitimate workstation traffic stop as well.

## Evidence, confidence and response outcomes

Historical severity (`critical`, P1), qualitative confidence, assessment,
operator disposition and response phase are separate fields. The dashboard's
status line shows severity/confidence/disposition/response; its assessment card
and map heading show the hypothesis and evidence reason. `incident` and
`timeline N` show the full reason at 80×24. Immutable timeline records preserve
those facts when the observation occurred. Original critical priority survives
dismissal and containment; it describes the original alert priority.

Confidence starts `limited` on the authentication deviation, becomes
`supported` with unfamiliar/recurring peer activity, then `strong` with observed
outbound volume compared with the interactive HTTPS reference profile. These
labels express evidence support for the hypothesis, not numerical likelihood.
Encrypted content remains unknown, including after successful containment.
Confidence changes are proposed by observations and applied through a dedicated
evidence-delivery hook; neutral response/completion snapshots do not change
the assessment. Healthy collectors deliver immediately; outages and delay modes
defer evidence as described below. Stopping a benign transfer does not suppress its later approval
evidence, so legitimate service disruption can still be recognized.

Select a variant using the same simulation/session/response lifecycle:

| Command | Evidence and modeled outcome |
| --- | --- |
| `scenario exfiltration` or `F` | Original 74s scenario; unchecked upload stays unresolved; final-upload block at 49s verifies at 51s |
| `scenario benign` | Queued replication request raises a generic alert; actual `FRA-BKP>SIN-STORE` BACKUP starts at 2s; at 7s delivered owner approval matches `JOB-FRA-SIN-001`, peer/service and transfer profile |
| `scenario delayed` | Suspicious activity with 5s application delay and 3s verification window; request at 49s stops at 54s with 20,000,000 originator bytes and verifies at 57s |
| `scenario partial` | A second real upload from `ATH-ADM` starts at 46s using `aster.admin`; response limited to `ATH-WS1` leaves it active |
| `scenario seeded` | Choose a variant reproducibly using the startup seed; automatic scheduling uses the same selector |

In the benign case, matching owner approval contradicts the data-removal
hypothesis, reducing confidence to `low` and changing assessment to `authorized
transfer`. It does not rewrite the initial alert or stop the legitimate backup.
Inspect `incident` and `timeline 3`, then enter `dismiss approved JOB-FRA-SIN-001`.
The disposition becomes `dismissed`, while bytes continue until normal session
completion at 32s. This is a single modeled scheduled job; daily workload
schedules are a later slice.

`dismiss [reason]` applies no network policy. Incorrect dismissal of suspicious
activity leaves later sessions, bytes and stronger observations visible. The
retained disposition stays dismissed alongside explicit unresolved residual
risk; it never implies containment. Automatic scheduling makes no operator
decision. Without dismissal, an authorized lookalike remains unresolved for
review when its banner retires.

For partial containment, inspect both upload IDs with `response`. Blocking the
primary upload at 49s stops its bytes at 12,000,000 and verifies that scope at
51s. The alternate upload has 10,000,000 originator bytes then and continues
at 16.08 Mb/s. The action phase is `verified`, its outcome is `partial`, and
incident disposition is `partially contained`. Its flow, route and residual-risk
explanation remain visible. Verification does not label the alternate asset safe.
Block or revoke that alternate session to verify full cessation; the first
partial result stays in the timeline. If it finishes naturally, its historical
transferred bytes and unresolved risk remain.

Explicit credentials are `aster.ws1` (`ATH-WS1`), `aster.admin` (`ATH-ADM`), and
`aster.backup` (`FRA-BKP`). Policies apply to these modeled identities. Pause
freezes variant/response delays, speed scales them, and FPS changes no outcome.
An active incident makes another scenario trigger idempotent regardless of
variant. The legacy `G` exercise remains separate until the later drill slice;
these variant and response APIs are shared for that future exercise.

Run a fixed-seed comparison without sleeps, terminal, or network access:

```bash
python3 demo_assessment.py
python3 -m unittest -v test_incident_assessment
```

It compares benign dismissal, ordinary verified cessation, delayed cessation,
and actual partial containment while preserving severity and evidence. Fixtures
also check incorrect dismissal, late responses, atomic two-slot reservation,
observation delivery, minimum-size dashboard facts, and large advances against
15/60 FPS partitions.

## Collector coverage and ingestion

The 128 city collectors have separate mutable heartbeat/delivery state; asset
traffic continues on the same simulation clock when a collector loses delivery.
The coverage card counts **healthy collectors**, with degraded coverage shown
explicitly. Map nodes use `~` for delayed, `!` for stale, `x` for offline, and `r`
for recovering. Healthy nodes keep the existing city/flag symbols. Degraded cities
receive label priority even without active traffic. During a gap, dashboard and
console flow facts are labeled **modeled**, and the incident banner uses the last
delivered evidence stage. A blind incident starts with `unobserved` confidence
and `awaiting evidence`; no fresh alert, volume observation or confidence increase
appears in its feed/timeline before receipt.

| Console command | Effect on simulation time |
| --- | --- |
| `collectors COL-ATH` | Show state, last heartbeat/age, oldest queued-event lag, queue depth, lifetime drops/received records, observed payload and CPU estimate |
| `outage COL-ATH` | Interrupt delivery/heartbeats immediately; state is delayed, stale when heartbeat age reaches 6s, then offline at 10s |
| `delay COL-ATH 3` | Keep 2s heartbeats but hold each observation at least 3s; drain eligible records at two/s; delay range is greater than zero through 60s |
| `recover COL-ATH` | Restore heartbeat now; queued catchup begins 0.5s later, at two records/s, then returns to healthy when empty |

The normal heartbeat interval is two simulation seconds. Outage thresholds use
age since the **last received heartbeat**, which may predate the outage command.
Stopping delivery immediately makes coverage degraded even while that heartbeat
is recent. `collectors` without an ID lists the catalog; IDs and invalid delay
values are checked before any mode change. Pause freezes heartbeats, evidence,
queues and catchup; speed scales them; FPS changes only rendering.

Each collector has a FIFO queue of at most **32 observations** (4,096 across the
catalog). This upstream simulation buffer stores incident evidence and ordinary
session start/completion/denial telemetry. On overflow, the new record is dropped
and a local loss notice reports its stable ID and occurrence time; original queued
records remain intact. Lifetime drops never reset on recovery. Catchup processes
oldest queued records at exact half-second boundaries; new observations join
behind them. Repeated event IDs are ignored using bounded recent-ID and queued-ID
checks. Delivered evidence never reapplies response actions or increments policy
counters again.

The feed's UTC column is **receipt time**. Every telemetry record also includes
elapsed simulation occurrence/receipt times and lag. Incident timelines sort by
occurrence time, then observation ID, and expose receipt separately. Late evidence
updates its original active or retained incident, even while another incident is
active. Unknown/evicted incident destinations produce an explicit unattached-
evidence message. Assessment changes apply only when their occurrence order is
at least as new as the last applied assessment; older buffered evidence and neutral
snapshots cannot reverse newer confidence. Response application/physical cessation
remain exact during an outage, while their collector proof can arrive later.
`actions` identifies those actuator-model results during a coverage gap.

Ingestion p95 is the nearest-rank 95th percentile of receipt-minus-occurrence lag
for records **received within the last 60 simulation seconds**, capped at the
latest 256 samples per collector. The sorted percentile is cached until samples
change. `n/a` means no samples; healthy immediate delivery measures zero. It is
an event delay, not network RTT or packet transit. Event loss is dropped/submitted
observations in a trailing 60s window of one-second count buckets. The model does
not claim a packet-loss measurement. Lifetime drop totals remain available when
the measurement window expires.

Per-collector observed payload uses the previous completed one-second byte bucket;
any bucket containing an outage interval has missing observed payload, even if
delivery recovers before its sample time. The next fully covered bucket resumes
observed payload. Recovery does not turn unseen past payload
into a current traffic burst. The global throughput card remains actual **modeled**
session bytes, including activity behind a coverage gap. CPU is an estimate with
18% idle baseline, plus 0.09 percentage points per observed Mb/s, 0.6 per processed
record in the last second, and 0.15 per queued record, capped at 95%. The dashboard
shows the busiest estimate. RAM is a 62% baseline plus up to 20 points for catalog
queue occupancy. Buffer footprint estimates 2KiB per queued record; this is in
memory. These estimates describe the simulator's processing work, not measured
hardware sensors, temperature or disk usage.

Queues, feed, timelines and receipt-ID sets are bounded. Collector count buckets
retain at most 61 rows and lag samples at most 256; recent event-ID checks retain
256 IDs per collector plus queued IDs. Incident receipt dedup retains 128 IDs per
retained incident. Incident/session retention limits remain 64/120. Loss and
missing coverage stay explicit rather than implying that a quiet site is safe.

Reproduce the outage, original-incident catchup and overflow without sleeps or
network access:

```bash
python3 demo_collectors.py
python3 -m unittest -v test_collectors
```

The demo takes Athens offline before a scenario, shows stale at 6s and offline at
10s while traffic continues, archives it at 74s with no received evidence, then
recovers while another incident is active. Original observations arrive with
original times and the correct incident ID. Three actual unchecked scenarios
also fill the 32-record buffer and explicitly drop 13 records; recovery delivers
32 in 16s. Fixtures cover thresholds, exact catchup, overflow/dedup, cross-collector
assessment order, late archived/orphan delivery, load, pause/speed and 15/60 FPS.

For interactive use, start with `--seed 12`, pause with `P`, open `C`, enter
`outage COL-ATH` then `scenario`, return with Esc and resume. Inspect the coverage
card and map gap. After the upload starts, pause and enter `collectors COL-ATH`,
`flows`, and `incident`; modeled bytes have grown while evidence is unavailable.
Enter `recover COL-ATH`, resume, and use `timeline N` to compare original occurrence
and delayed receipt. The operator can independently respond during the gap using
the same explicit scopes, with collector verification evidence received later.

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

A seeded correlated variant is scheduled after 30–90 simulation seconds, and
again 30–90 seconds after the preceding scenario finishes. Its P1 banner, priority
flow row and map share the same incident and session state. The camera follows
the aggregate activity marker on the original geographic arc while traffic is
active. Pause freezes scenario evidence and session bytes; speed changes both,
and FPS changes only rendering. Console and drill views continue the simulation
unless paused; camera motion waits until the dashboard returns. Press `F` or enter
`scenario` in the console to trigger the same scenario as the scheduler.

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

The map runs offline with the Python standard library. Keep `terminal_map.py`, `terminal_input.py`, `critical_flow.py`, `simulation_model.py`, `collector_model.py`,
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
python3 -m unittest -v test_monitor test_terminal_map test_terminal_input test_critical_flow test_simulation_model test_session_simulation test_response_actions test_incident_assessment test_collectors
```

The tests replay incremental ANSI output to check for stale characters and exercise resize, pause, console input, and terminal restoration through a pseudo-terminal on macOS and Linux.

## License

MIT

## Keyboard investigation

From the dashboard, **E** opens the active flow list and **I** opens the active
incident list. **N/M** select the previous/next row, wrapping at the ends;
**Enter** opens the selected ID. The `>` marker and selected-ID footer show the
selection. Flow rows prioritize incident sessions, then current throughput; a
selected ID stays selected as these rows reorder. Lists include sessions even
when their geography is unknown and there is no map route.

In details, **U/D** scroll a page up/down. **E** in incident details opens its
related session list, including completed related sessions; **I** in a related
flow's details opens its incident. These links use the same IDs as observations
and response actions. **Esc** returns one level, preserving the previous list's
selection or detail scroll. Reopening an already open linked detail returns to
that frame and its scroll, keeping navigation bounded to five frames. Esc from
the outer list returns to the prior regional map and exact viewport. Map arrows,
H/J/K/L, wheel zoom, brackets and region controls continue to work on the dashboard;
inspection uses its dedicated controls. Console text entry keeps its existing
meaning. **Q** or Ctrl+C quits; dashboard Esc continues to quit.

Inspection remains live. **P** pauses/resumes and **+/-** changes simulation speed
while inspecting. A selected session that completes or is stopped stays selected
and exposes a final summary: duration, final bytes and packets, zero final rates,
connection state and policy action. A selected incident remains inspectable after
completion and while a subsequent incident starts. Completed selections remain
available while the existing bounded model history retains them (120 ordinary
sessions, 64 incidents, and each retained incident's related sessions). If a record
is evicted, its selected ID shows an explicit unavailable message and never
silently points to a replacement row. Historical browsing and filters are a later
slice; these entry lists select active records plus the retained selection.

Flow details show assets/sites, example addresses and ports, application service,
transport, encryption, directional payload totals and trailing-one-second Mb/s,
baseline context, credentials, matching policy lifecycle and received evidence.
Incident details show severity, confidence/reason, assessment, disposition, response
outcome, related session IDs, affected session/action links and a chronological,
scrollable timeline. All times are elapsed simulation seconds. Each observation
shows its original occurrence separately from actual receipt and lag. Collector
gaps and losses stay explicit; session rates and actuator results are labeled
modeled facts. Buffered evidence appears only after receipt, including late
receipts for retained completed incidents. Long evidence wraps and scrolls at
80×24; resize uses the same canvas erasure and full-resize clearing as the dashboard.

Run the deterministic keyboard demonstration:

```sh
python3 demo_investigation.py
python3 -m unittest test_investigation -v
```

The demo selects the transfer at 49 seconds with E/Enter, advances traffic while
inspecting, applies the existing session response API, verifies the stopped
transfer and action evidence, follows I into the timeline, scrolls at 80×24, and
returns to the exact Europe viewport. A second run shows the coverage gap and
original occurrence versus delayed receipt without real-time sleeps.

For an interactive run, use `--seed 12`, trigger **F**, pause with **P** during the
outbound transfer, then **E**, **Enter** to inspect. Return with Esc twice, open
**C**, and use `response` to preview the current target before entering
`block session FLOW-ID`. Leave the console with Esc and resume with P. To inspect
the completed transfer afterward, use **I**, **Enter**, **E**, select its stable
flow ID with N/M, then Enter; D scrolls to the policy history and received evidence.
