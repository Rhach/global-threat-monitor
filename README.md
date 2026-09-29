# Global Threat Monitor

A simulated security-operations dashboard for your terminal. Python standard library only.

Global Threat Monitor fills your terminal with animated traffic routes, sensor telemetry, policy actions, and a timestamped event stream. Everything runs locally with generated data. It does not monitor, scan, or connect to any network.

Version 4 replaces the flashing Hollywood panels with a calmer operations display. The renderer sends only changed cells, and animation timing is independent of simulation speed.

## Features

- Fullscreen dashboard with summary cards and readable, severity-coded events
- Braille world map with geographically positioned sensors and curved traffic routes
- World, Europe, Asia, and Americas views, selected with `R`
- Plausible simulated CPU, memory, temperature, latency, and ingress telemetry
- Traffic history, detection counts, and an active-flow table
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
--version        Show version information
--help           Show help
```

## Controls

```text
Q / ESC   Quit
T         Cycle theme
R         Cycle world / Europe / Asia / Americas
P         Pause / resume
S         Toggle sound
A         Add a simulated traffic flow
C         Open simulation console. Esc returns to the dashboard
G         Start a containment drill. Press keys to complete; Esc cancels
+ / =     Increase speed
-         Decrease speed
```

In the console, enter `help`, `status`, `flows`, `clear`, or `exit`. The old `enhance`, `ddos-localhost`, and `nuke-gibson` commands still work as local simulations. Ctrl+C quits from any view.

`--speed` changes the simulation clock, traffic, and telemetry cadence. `--fps` changes only the redraw rate. Pausing freezes the simulation, including the displayed clock.

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
python -m unittest -v test_monitor
```

The tests replay incremental ANSI output to check for stale characters and exercise resize, pause, console input, and terminal restoration through a pseudo-terminal on macOS and Linux.

## License

MIT
