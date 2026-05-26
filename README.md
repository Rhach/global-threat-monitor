<img width="1892" height="1005" alt="image" src="https://github.com/user-attachments/assets/f36c4261-e80d-471b-a60f-6f824a7964ec" />


# Global Threat Monitor

A completely useless Hollywood-style cyber threat dashboard for your terminal.

Global Threat Monitor is a Python TUI screensaver simulator that fills your terminal with fake attacks, fake breach logs, fake port scans, fake packet movement, fake decryption, fake thermals, and fake authority.

It does not monitor real threats.
It does not scan networks.
It does not hack anything.
It just looks like it might, which is somehow enough for the human visual cortex.

## Features

- Fullscreen terminal dashboard
- Animated world-map attack vectors
- Fake threat logs
- Fake subnet port sweeper
- Fake tunnel manager
- Fake password/decryption panel
- Fake biometric/DNA override animation
- Multiple color themes
- Optional sound chimes on Windows
- Cross-platform terminal support
- Keyboard controls
- Config persistence for selected theme

## Requirements

- Python 3.9 or newer recommended
- A terminal that supports ANSI escape sequences
- Terminal size of at least 100x35

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
python global-threat-monitor.py --sound
python global-threat-monitor.py --no-sound
```

## Options

```text
--theme <name>   Set startup theme: matrix, cyberpunk, amber, ice
--sound          Enable optional sound chimes
--no-sound       Mute sound chimes
--speed <mult>   Set speed multiplier. Clamped between 0.25 and 4.0
--version        Show version information
--help           Show help
```

## Controls

```text
Q / ESC   Quit
T         Cycle theme
P         Pause / resume
S         Toggle sound
A         Trigger fake attack
+ / =     Increase speed
-         Decrease speed
```

## Configuration

Global Threat Monitor stores the selected theme in a local config file.

Config locations:

```text
Windows: %APPDATA%/GlobalThreatMonitor/config.json
Linux:   ~/.config/global-threat-monitor/config.json
macOS:   ~/.config/global-threat-monitor/config.json
```

## Disclaimer

This is not a cybersecurity tool.
This is fake.
All displayed activity is randomly generated nonsense and should be treated as such.

Do not use it to assess security posture, impress auditors, diagnose incidents, or convince management that the blinking red thing means progress.
Or do, but in that case, it is between you, your conscience, and the very tired incident response team that will eventually be asked why the DNA decrypter panel is not in Splunk.

## Disclaimer 2

I did not write a single line of code on this. Because burning forests and expending energy in 2026 is not about productivity. It is about sending a message. Peak humanity.

## Disclaimer 3

If you can find anything weird in it, Gemini 3.5 flash (high) injected it. Take it up with Google.

## License

MIT
