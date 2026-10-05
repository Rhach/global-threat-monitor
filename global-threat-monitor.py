#!/usr/bin/env python3
"""A simulated security-operations dashboard. Python standard library only."""

import argparse
from collections import deque
import json
import math
import os
import queue
import random
import shutil
import sys
import threading
import time

from terminal_map import (
    MapViewport, border_texture, coastline_texture, load_borders, load_coastlines, project,
)
from terminal_input import InputDecoder, MOUSE_OFF, MOUSE_ON, WindowsConsoleInput
from critical_flow import CriticalIncident
from simulation_model import Organization, SessionSimulation, valid_advance

APP_NAME = "Global Threat Monitor"
APP_VERSION = "4.0.0"
APP_DESCRIPTION = "A simulated security-operations dashboard for your terminal."
RESET = "\033[0m"
MIN_WIDTH, MIN_HEIGHT = 80, 24


def get_config_path():
    if os.name == "nt":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        return os.path.join(base, "GlobalThreatMonitor", "config.json")
    base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return os.path.join(base, "global-threat-monitor", "config.json")


def load_config():
    try:
        with open(get_config_path(), encoding="utf-8") as stream:
            config = json.load(stream)
        if isinstance(config, dict):
            return config
    except (OSError, ValueError):
        pass
    return {"theme": "ice"}


def save_config(theme):
    try:
        path = get_config_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as stream:
            json.dump({"theme": theme}, stream)
    except OSError:
        pass


def make_palette(name, accent):
    return {
        "name": name, "border": "\033[90m", "border_bold": accent,
        "text": "\033[37m", "muted": "\033[90m", "accent": accent,
        "warn": "\033[91m", "success": "\033[32m", "info": "\033[33m",
        "map_land": "\033[2m" + accent, "packet": "\033[97m",
        "map_border": "\033[90m",
        "critical": "\033[1;97;41m", "critical_ok": "\033[1;97;42m",
        "critical_trail": "\033[1;91m", "critical_head": "\033[1;97m",
        "trail": accent,
    }


THEMES = {
    "matrix": make_palette("Matrix", "\033[92m"),
    "cyberpunk": make_palette("Cyberpunk", "\033[95m"),
    "amber": make_palette("Amber", "\033[93m"),
    "ice": make_palette("Ice", "\033[96m"),
}

# Longitude, latitude, city, sensor code. These same coordinates drive the map
# and routes, so nodes stay attached to their locations at any terminal size.
CITIES = [
    (-122.42, 37.77, "San Francisco", "SFO"),
    (-74.01, 40.71, "New York", "NYC"),
    (-46.63, -23.55, "Sao Paulo", "SAO"),
    (-0.13, 51.51, "London", "LON"),
    (37.62, 55.75, "Moscow", "MOW"),
    (31.24, 30.04, "Cairo", "CAI"),
    (18.42, -33.92, "Cape Town", "CPT"),
    (116.41, 39.90, "Beijing", "PEK"),
    (139.69, 35.68, "Tokyo", "TYO"),
    (151.21, -33.87, "Sydney", "SYD"),
    (72.88, 19.08, "Mumbai", "BOM"),
    (103.82, 1.35, "Singapore", "SIN"),
    (-118.24, 34.05, "Los Angeles", "LAX"),
    (-87.63, 41.88, "Chicago", "CHI"),
    (-77.04, 38.91, "Washington", "WAS"),
    (-122.33, 47.61, "Seattle", "SEA"),
    (-96.80, 32.78, "Dallas", "DAL"),
    (-79.38, 43.65, "Toronto", "TOR"),
    (-123.12, 49.28, "Vancouver", "VAN"),
    (-99.13, 19.43, "Mexico City", "MEX"),
    (-58.38, -34.60, "Buenos Aires", "BUE"),
    (-70.67, -33.45, "Santiago", "SCL"),
    (-77.04, -12.05, "Lima", "LIM"),
    (-74.07, 4.71, "Bogota", "BOG"),
    (-78.47, -0.18, "Quito", "UIO"),
    (-43.17, -22.91, "Rio de Janeiro", "RIO"),
    (2.35, 48.86, "Paris", "PAR"),
    (13.41, 52.52, "Berlin", "BER"),
    (12.50, 41.90, "Rome", "ROM"),
    (-3.70, 40.42, "Madrid", "MAD"),
    (-9.14, 38.72, "Lisbon", "LIS"),
    (4.90, 52.37, "Amsterdam", "AMS"),
    (8.54, 47.38, "Zurich", "ZRH"),
    (18.07, 59.33, "Stockholm", "STO"),
    (10.75, 59.91, "Oslo", "OSL"),
    (21.01, 52.23, "Warsaw", "WAW"),
    (16.37, 48.21, "Vienna", "VIE"),
    (14.44, 50.08, "Prague", "PRG"),
    (23.73, 37.98, "Athens", "ATH"),
    (28.98, 41.01, "Istanbul", "IST"),
    (30.52, 50.45, "Kyiv", "KYI"),
    (24.94, 60.17, "Helsinki", "HEL"),
    (3.38, 6.52, "Lagos", "LOS"),
    (36.82, -1.29, "Nairobi", "NBO"),
    (28.05, -26.20, "Johannesburg", "JNB"),
    (-7.59, 33.57, "Casablanca", "CAS"),
    (38.76, 9.03, "Addis Ababa", "ADD"),
    (-17.45, 14.69, "Dakar", "DKR"),
    (55.27, 25.20, "Dubai", "DXB"),
    (46.68, 24.71, "Riyadh", "RUH"),
    (51.39, 35.69, "Tehran", "THR"),
    (77.21, 28.61, "Delhi", "DEL"),
    (77.59, 12.97, "Bangalore", "BLR"),
    (100.50, 13.76, "Bangkok", "BKK"),
    (106.85, -6.21, "Jakarta", "JKT"),
    (126.98, 37.57, "Seoul", "SEL"),
    (114.17, 22.32, "Hong Kong", "HKG"),
    (121.57, 25.03, "Taipei", "TPE"),
    (121.47, 31.23, "Shanghai", "SHA"),
    (67.01, 24.86, "Karachi", "KHI"),
    (144.96, -37.81, "Melbourne", "MEL"),
    (174.76, -36.85, "Auckland", "AKL"),
    (174.78, -41.29, "Wellington", "WLG"),
    (115.86, -31.95, "Perth", "PER"),
    (-71.06, 42.36, "Boston", "BOS"),
    (-80.19, 25.76, "Miami", "MIA"),
    (-84.39, 33.75, "Atlanta", "ATL"),
    (-104.99, 39.74, "Denver", "DEN"),
    (-112.07, 33.45, "Phoenix", "PHX"),
    (-95.37, 29.76, "Houston", "HOU"),
    (-73.57, 45.50, "Montreal", "YUL"),
    (-75.70, 45.42, "Ottawa", "OTT"),
    (-114.07, 51.05, "Calgary", "YYC"),
    (-97.14, 49.90, "Winnipeg", "WPG"),
    (-149.90, 61.22, "Anchorage", "ANC"),
    (-157.86, 21.31, "Honolulu", "HNL"),
    (-84.09, 9.93, "San Jose", "SJO"),
    (-79.52, 8.98, "Panama City", "PTY"),
    (-66.90, 10.48, "Caracas", "CCS"),
    (-68.15, -16.50, "La Paz", "LPB"),
    (-56.16, -34.90, "Montevideo", "MVD"),
    (-47.88, -15.79, "Brasilia", "BSB"),
    (-6.26, 53.35, "Dublin", "DUB"),
    (-3.19, 55.95, "Edinburgh", "EDI"),
    (-21.94, 64.15, "Reykjavik", "REK"),
    (12.57, 55.68, "Copenhagen", "CPH"),
    (4.35, 50.85, "Brussels", "BRU"),
    (8.68, 50.11, "Frankfurt", "FRA"),
    (11.58, 48.14, "Munich", "MUC"),
    (19.04, 47.50, "Budapest", "BUD"),
    (26.10, 44.43, "Bucharest", "BUH"),
    (23.32, 42.70, "Sofia", "SOF"),
    (20.46, 44.82, "Belgrade", "BEG"),
    (15.98, 45.82, "Zagreb", "ZAG"),
    (-0.19, 5.56, "Accra", "ACC"),
    (7.49, 9.06, "Abuja", "ABV"),
    (-4.01, 5.36, "Abidjan", "ABJ"),
    (10.18, 36.81, "Tunis", "TUN"),
    (3.06, 36.75, "Algiers", "ALG"),
    (-6.85, 34.02, "Rabat", "RBA"),
    (13.23, -8.84, "Luanda", "LAD"),
    (15.27, -4.44, "Kinshasa", "FIH"),
    (30.06, -1.94, "Kigali", "KGL"),
    (32.58, 0.35, "Kampala", "KLA"),
    (39.21, -6.79, "Dar es Salaam", "DAR"),
    (32.59, -25.97, "Maputo", "MPM"),
    (31.05, -17.83, "Harare", "HRE"),
    (32.56, 15.50, "Khartoum", "KRT"),
    (120.98, 14.60, "Manila", "MNL"),
    (105.83, 21.03, "Hanoi", "HAN"),
    (106.70, 10.78, "Ho Chi Minh City", "SGN"),
    (101.69, 3.14, "Kuala Lumpur", "KUL"),
    (90.41, 23.81, "Dhaka", "DAC"),
    (85.32, 27.72, "Kathmandu", "KTM"),
    (79.86, 6.93, "Colombo", "CMB"),
    (73.04, 33.69, "Islamabad", "ISB"),
    (69.24, 41.30, "Tashkent", "TAS"),
    (76.89, 43.24, "Almaty", "ALA"),
    (106.91, 47.92, "Ulaanbaatar", "ULN"),
    (104.07, 30.57, "Chengdu", "CTU"),
    (114.06, 22.54, "Shenzhen", "SZX"),
    (135.50, 34.69, "Osaka", "OSA"),
    (34.78, 32.09, "Tel Aviv", "TLV"),
    (58.41, 23.59, "Muscat", "MCT"),
    (153.03, -27.47, "Brisbane", "BNE"),
    (138.60, -34.93, "Adelaide", "ADL"),
    (147.18, -9.44, "Port Moresby", "POM"),
    (178.45, -18.14, "Suva", "SUV"),
]

# Equirectangular projection, bounded to 80 N / 60 S in the world view.
VIEWS = {
    "WORLD": (-180, 180, -60, 80),
    "EUROPE": (-15, 50, 25, 72),
    "ASIA": (45, 160, -15, 65),
    "AMERICAS": (-170, -30, -60, 75),
}


class Canvas:
    """Cell buffer with clipped writes and a retained terminal-frame snapshot."""

    def __init__(self, w, h):
        self.width, self.height = w, h
        self.grid = [[" "] * w for _ in range(h)]
        self.colors = [[None] * w for _ in range(h)]
        self.previous = None

    def clear(self):
        for y in range(self.height):
            self.grid[y][:] = [" "] * self.width
            self.colors[y][:] = [None] * self.width

    def write_char(self, x, y, char, color=None):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.grid[y][x] = char
            self.colors[y][x] = color

    def write_str(self, x, y, text, color=None):
        if not 0 <= y < self.height:
            return
        start, end = max(0, x), min(self.width, x + len(text))
        if end > start:
            self.grid[y][start:end] = list(text[start - x:end - x])
            self.colors[y][start:end] = [color] * (end - start)

    def draw_box(self, x, y, w, h, title="", color=None):
        if w < 2 or h < 2:
            return
        self.write_str(x, y, "╭" + "─" * (w - 2) + "╮", color)
        self.write_str(x, y + h - 1, "╰" + "─" * (w - 2) + "╯", color)
        for row in range(y + 1, y + h - 1):
            self.write_char(x, row, "│", color)
            self.write_char(x + w - 1, row, "│", color)
        if title and w > 6:
            self.write_str(x + 2, y, (" " + title + " ")[:w - 4], color)

    def _segment(self, y, start, end):
        parts, active = [], ""
        for x in range(start, end):
            color = self.colors[y][x]
            if color != active:
                parts.append(RESET + (color or ""))
                active = color
            parts.append(self.grid[y][x])
        parts.append(RESET)
        return "".join(parts)

    def render(self, offset_x=0, offset_y=0):
        """Full frame, useful for previews and diagnostics."""
        return "\n" * offset_y + "\n".join(
            " " * offset_x + self._segment(y, 0, self.width)
            for y in range(self.height))

    def render_diff(self):
        """Emit only changed cell runs, including color changes and cleared text."""
        output = []
        current = [(tuple(row), tuple(colors))
                   for row, colors in zip(self.grid, self.colors)]
        for y, (row, colors) in enumerate(current):
            old = self.previous[y] if self.previous is not None else None
            if old == (row, colors):
                continue
            if old is None:
                spans = [(0, self.width)]
            else:
                changed = [x for x in range(self.width)
                           if row[x] != old[0][x] or colors[x] != old[1][x]]
                spans = []
                start = end = changed[0]
                for x in changed[1:]:
                    # A few unchanged cells cost less than another cursor command.
                    if x - end > 4:
                        spans.append((start, end + 1))
                        start = x
                    end = x
                spans.append((start, end + 1))
            for start, end in spans:
                output.append(f"\033[{y + 1};{start + 1}H")
                output.append(self._segment(y, start, end))
        self.previous = current
        return "".join(output)


try:
    import msvcrt
    WINDOWS = True
except ImportError:
    WINDOWS = False
    import select
    import termios
    import tty

try:
    import winsound
except ImportError:
    winsound = None


class AudioEngine:
    """A bounded worker keeps Windows Beep calls off the animation thread."""

    def __init__(self):
        self.muted = True
        self.pending = queue.Queue(maxsize=4)
        self.worker = None

    def play(self, frequency, duration):
        if self.muted or winsound is None:
            return
        if self.worker is None:
            self.worker = threading.Thread(target=self._run, daemon=True)
            self.worker.start()
        try:
            self.pending.put_nowait((frequency, duration))
        except queue.Full:
            pass

    def _run(self):
        while True:
            frequency, duration = self.pending.get()
            try:
                if not self.muted:
                    winsound.Beep(frequency, duration)
            except RuntimeError:
                pass

    def play_click(self):
        self.play(1000, 8)

    def play_packet(self):
        self.play(2300, 10)

    def play_success(self):
        self.play(1400, 30)


audio = AudioEngine()
old_settings = None
console_input = None
input_decoder = InputDecoder()


def enable_windows_ansi():
    if WINDOWS:
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        if kernel.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel.SetConsoleMode(handle, mode.value | 0x0004)


def init_keyboard():
    global old_settings, console_input, input_decoder
    input_decoder = InputDecoder()
    if WINDOWS:
        try:
            console_input = WindowsConsoleInput()
        except OSError:
            console_input = None
    elif sys.stdin.isatty():
        old_settings = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())


def restore_keyboard():
    global console_input
    if console_input is not None:
        console_input.restore()
        console_input = None
    elif not WINDOWS and old_settings is not None:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)


def get_key():
    """Decode complete input events without blocking the animation loop."""
    if WINDOWS:
        if console_input is not None:
            return console_input.read()
        if not msvcrt.kbhit():
            return input_decoder.read()
        key = msvcrt.getwch()
        if key in ("\x00", "\xe0"):
            return {"H": "up", "P": "down", "M": "right", "K": "left"}.get(msvcrt.getwch())
        input_decoder.feed(key)
    else:
        if select.select([sys.stdin], [], [], 0)[0]:
            data = os.read(sys.stdin.fileno(), 4096)
            if data:
                input_decoder.feed(data.decode("latin1"))
    return input_decoder.read()


class AttackVector:
    MARKER_PERIOD = 3.0

    def __init__(self, src, dst, theme_palette, connection=None, session=None):
        self.src_city, self.dst_city = src, dst
        self.palette = theme_palette
        self.duration = 3.0
        self.progress = 0.0
        self.age = 0.0
        self.complete = False
        self.kind = "HTTPS"
        self.flagged = False
        self.rate = 0.0
        self.critical = False
        self.connection = connection
        self.session = session
        if connection is not None:
            self.kind = connection.service
            self.flagged = not connection.expected
        if session is not None:
            self.duration = session.lifetime

    def update(self, dt=1 / 30):
        self.age += valid_advance(dt)
        # Repeating aggregate activity marker, never packet transit or bytes.
        self.progress = (self.age % self.MARKER_PERIOD) / self.MARKER_PERIOD
        if self.session is not None:
            self.age = self.session.duration
            self.progress = (self.age % self.MARKER_PERIOD) / self.MARKER_PERIOD
            self.rate = self.session.rate
            self.complete = self.session.complete
        else:
            self.complete = self.age >= self.duration


RULES = ["SSH brute force", "SYN scan", "WAF / injection", "DNS anomaly"]


def sparkline(values, width):
    if width <= 0 or not values:
        return ""
    samples = list(values)[-width:]
    low, high = min(samples), max(samples)
    chars = "▁▂▃▄▅▆▇█"
    span = max(1.0, high - low)
    return "".join(chars[min(7, int((v - low) / span * 7))] for v in samples)


def clamp_speed(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 1.0
    return max(0.25, min(number, 4.0)) if math.isfinite(number) else 1.0


class CyberMonitor:
    def __init__(self, initial_theme=None, initial_sound=False, initial_speed=1.0,
                 seed=None):
        theme = initial_theme or load_config().get("theme", "ice")
        self.theme_key = theme if theme in THEMES else "ice"
        self.palette = THEMES[self.theme_key]
        self.organization = Organization(CITIES, seed=seed)
        self.simulation = SessionSimulation(self.organization, seed=seed)
        self.canvas = Canvas(100, 35)
        self.paused = False
        self.speed_multiplier = clamp_speed(initial_speed)
        self.active_mode = "dashboard"
        self.view = "WORLD"
        self.map_views = {name: MapViewport(bounds) for name, bounds in VIEWS.items()}
        self.elapsed = 0.0
        self.boot_time = time.monotonic()
        self.last_map_interaction = self.boot_time
        self.last_auto_zoom = self.boot_time
        self.clock_base = time.time()
        self.attacks = []
        self.critical_incident = None
        self.critical_cooldown = random.uniform(30.0, 90.0)
        self.incident_count = 0
        self.threat_logs = deque(maxlen=80)
        self.shell_history = deque(maxlen=100)
        self.shell_input = ""
        self.breach_time_left = 10.0
        self.breach_taps = 0
        self.metrics = {"CPU": 18.0, "RAM": 62.0, "DISK": 41.0,
                        "TEMP": 44.4, "NET": 0.0, "LATENCY": 15.0}
        self.traffic_history = self.simulation.traffic_history
        self.latency_history = deque([15.0], maxlen=120)
        self.total_events = 0
        self._sample_events = 0
        self.blocked = 0
        self.rule_hits = [0, 0, 0, 0]
        self.last_eps = 0
        self.sensors_online = len(self.organization.collectors)
        audio.muted = not initial_sound
        self.log("Offline simulation ready / session payload traffic; no background aggregate")
        self.borders_visible = False
        self.enable_borders()
        self.enable_coastlines()

    def enable_borders(self):
        try:
            load_borders()
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.borders_visible = False
            self.log(f"Country borders unavailable / {error}", "warn", "LOW")
        else:
            self.borders_visible = True

    def enable_coastlines(self):
        try:
            load_coastlines()
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.coastlines_available = False
            self.log(f"Coastlines unavailable / {error}", "warn", "LOW")
        else:
            self.coastlines_available = True

    def handle_map_key(self, key):
        viewport = self.map_views[self.view]
        if key == "b":
            if self.borders_visible:
                self.borders_visible = False
            else:
                self.enable_borders()
        elif key in ("[", "]", "wheel_up", "wheel_down"):
            viewport.zoom_by(1.5 if key in ("]", "wheel_up") else 1 / 1.5)
        elif key in ("h", "j", "k", "l", "left", "down", "up", "right"):
            dx, dy = {"h": (-1, 0), "j": (0, 1), "k": (0, -1), "l": (1, 0),
                      "left": (-1, 0), "down": (0, 1), "up": (0, -1), "right": (1, 0)}[key]
            viewport.pan(dx, dy)
        elif key == "0":
            viewport.reset()
        else:
            return False
        self.touch_map()
        return True

    def touch_map(self):
        self.last_map_interaction = self.last_auto_zoom = time.monotonic()
        if self.critical_incident is not None:
            self.critical_incident.following = False

    def update_map(self, now=None):
        """Map camera uses wall time, independently of pause and simulation speed."""
        now = time.monotonic() if now is None else now
        if self.active_mode != "dashboard":
            self.last_auto_zoom = now
            return
        if self.critical_incident is not None and self.critical_incident.following:
            if self.paused:
                self.last_auto_zoom = now
            elif now - self.last_auto_zoom >= 0.1:
                self.critical_incident.follow(self.map_views[self.view], min(now - self.last_auto_zoom, 0.25))
                self.last_auto_zoom = now
            return
        start = max(self.last_auto_zoom, self.last_map_interaction + 10.0)
        dt = now - start
        # Ten small steps per second keep map rasterization off most frames.
        if dt >= 0.1:
            self.map_views[self.view].ease_out(min(dt, 0.25))
            self.last_auto_zoom = now

    def timestamp(self):
        return time.strftime("%H:%M:%S", time.gmtime(self.clock_base + self.simulation.now))

    @property
    def attack_cooldown(self):
        return self.simulation.next_spawn - self.simulation.now

    @attack_cooldown.setter
    def attack_cooldown(self, value):
        self.simulation.next_spawn = self.simulation.now + max(0.0, value)

    def log(self, message, status="info", severity="INFO", sensor="SYS"):
        self.threat_logs.append((self.timestamp(), severity, sensor, message, status))
        self.total_events += 1

    def generate_threat_log(self, init=False, timestamp=None):
        routes = [route for route in self.attacks if route.connection is not None]
        connection = (self.organization.rng.choice(routes).connection if routes else
                      self.organization.choose_connection())
        self.log_connection(connection, timestamp)

    def log_connection(self, connection, timestamp=None):
        """A peer observation shares the same persistent context as its route."""
        stamp = self.timestamp() if timestamp is None else time.strftime(
            "%H:%M:%S", time.gmtime(timestamp))
        collector = self.organization.collectors[connection.collector_id]
        self.threat_logs.append((stamp, "INFO" if connection.expected else "MED",
                                 collector.city[3],
                                 self.organization.describe(connection),
                                 "info" if connection.expected else "warn"))
        self.total_events += 1

    def toggle_theme(self):
        keys = list(THEMES)
        self.theme_key = keys[(keys.index(self.theme_key) + 1) % len(keys)]
        self.palette = THEMES[self.theme_key]
        save_config(self.theme_key)

    def toggle_sound(self):
        audio.muted = not audio.muted
        self.log("Audio muted" if audio.muted else "Audio enabled", "success")

    def trigger_attack(self, connection=None):
        if len(self.attacks) >= 11:
            return
        session = self.simulation.create(connection)
        if session is None:
            return
        return self.add_session_route(session)

    def add_session_route(self, session):
        connection = session.connection
        route = AttackVector(self.organization.city_for(connection.source_id),
                             self.organization.city_for(connection.peer_id),
                             self.palette, connection, session)
        self.attacks.append(route)
        self.log_connection(connection)
        audio.play_packet()
        return route

    def complete_session(self, session):
        route = next((r for r in self.attacks if r.session is session), None)
        if route is not None and route.critical:
            return  # Legacy incident marker remains until its scripted cleanup.
        if route is not None:
            route.update(0)
            self.attacks.remove(route)
        collector = self.organization.collectors[session.connection.collector_id]
        assessment = " / assessment pending" if not session.connection.expected else ""
        self.log(f"{self.organization.context(session.connection)} / {session.summary()}{assessment}",
                 "info", "INFO", collector.city[3])

    def sample_telemetry(self):
        traffic = self.simulation.throughput
        self.metrics.update({"NET": traffic, "CPU": 18 + traffic * 0.09,
                             "RAM": 62, "DISK": 41, "LATENCY": 15 + traffic * 0.04})
        self.metrics["TEMP"] = 39 + self.metrics["CPU"] * 0.3
        self.latency_history.append(self.metrics["LATENCY"])
        self.last_eps = self.total_events - self._sample_events
        self._sample_events = self.total_events

    def start_critical_incident(self):
        if self.critical_incident is not None:
            return
        # Keep the legacy incident lifecycle until the correlated scenario slice;
        # its endpoints already refer to the same catalog as ordinary traffic.
        connection = self.organization.connect("ATH-WS1", "EXT-DXB", "HTTPS")
        session = self.simulation.create(connection)
        if session is None:
            return
        route = AttackVector(self.organization.city_for(connection.source_id),
                             self.organization.city_for(connection.peer_id),
                             self.palette, connection, session)
        self.attacks.append(route)
        self.incident_count += 1
        self.critical_incident = CriticalIncident(route, self.incident_count)
        self.critical_cooldown = random.uniform(30.0, 90.0)
        self.last_auto_zoom = time.monotonic()
        self.log_connection(connection)
        self.log(f"{self.organization.context(connection)} / "
                 f"{self.critical_incident.identifier} / Data exfiltration detected / "
                 f"{route.src_city[3]} > {route.dst_city[3]}", "warn", "CRIT", route.dst_city[3])
        audio.play_success()

    def update_critical_incident(self, dt):
        if self.paused or self.active_mode != "dashboard":
            return
        self.critical_cooldown -= max(0.0, dt)
        incident = self.critical_incident
        if incident is None:
            if self.critical_cooldown <= 0:
                self.start_critical_incident()
            return
        for stage in incident.update(dt):
            messages = {
                "TRACING FLOW": "Payload signature confirmed; tracing exfiltration route",
                "QUARANTINING": "Destination isolated; revoking session credentials",
                "CONTAINED": "Exfiltration contained; egress blocked and session revoked",
            }
            self.log(f"{self.organization.context(incident.route.connection)} / "
                     f"{incident.identifier} / {messages[stage]}",
                     "success" if stage == "CONTAINED" else "warn",
                     "LOW" if stage == "CONTAINED" else "CRIT", incident.route.dst_city[3])
            if stage == "CONTAINED":
                self.blocked += 1
                self.rule_hits[3] += 1
                audio.play_success()
        if incident.complete:
            self.attacks[:] = [route for route in self.attacks if route is not incident.route]
            self.critical_incident = None
            self.last_auto_zoom = time.monotonic()

    def update(self, dt=1 / 30):
        dt = valid_advance(dt)
        self.update_critical_incident(dt)
        self.update_map()
        if self.paused:
            return
        if self.active_mode == "breach":
            self.breach_time_left = max(0.0, self.breach_time_left - dt)
            if self.breach_time_left == 0:
                self.active_mode = "dashboard"
                self.log("Exercise timed out; recovery policy applied", "warn", "HIGH")
        sim_dt = dt * self.speed_multiplier
        self.simulation.advance(sim_dt, self.add_session_route,
                                self.complete_session, self.sample_telemetry)
        self.elapsed = self.simulation.now
        for attack in self.attacks:
            if attack.critical:
                attack.rate = attack.session.rate
                continue
            attack.update(0)

    def panel(self, x, y, w, h, title):
        self.canvas.draw_box(x, y, w, h, title, self.palette["border"])
        return x + 2, y + 1, w - 4, h - 2

    def text(self, x, y, width, value, color="text"):
        self.canvas.write_str(x, y, str(value)[:max(0, width)], self.palette[color])

    def draw_kpis(self, y):
        width = self.canvas.width
        cards = [
            ("EVENTS / SEC", f"{self.last_eps:,}", "observations / 1s", "accent"),
            ("CONTAINED", f"{self.blocked:,}", "policy actions", "success"),
            ("THROUGHPUT", f"{self.metrics['NET']:.1f} Mb/s", "payload / last 1s", "accent"),
            ("SENSORS", f"{self.sensors_online:02d} / {len(CITIES):02d}", "all regions online", "success"),
        ]
        if self.critical_incident is not None:
            incident = self.critical_incident
            cards[0] = ("PRIORITY INCIDENT", "CONTAINED" if incident.contained else "CRITICAL P1",
                        f"{incident.identifier} / EXFILTRATION", "success" if incident.contained else "warn")
        for i, (title, value, hint, color) in enumerate(cards):
            x = i * (width + 1) // 4
            end = (i + 1) * (width + 1) // 4 - 1
            px, py, pw, _ = self.panel(x, y, end - x, 5, title)
            self.text(px, py + 1, pw, value, color)
            self.text(px, py + 2, pw, hint, "muted")

    def draw_map(self, x, y, w, h):
        incident = self.critical_incident
        title = f"PRIORITY TRACK / {incident.identifier}" if incident else f"GLOBAL TRAFFIC / {self.view}"
        px, py, pw, ph = self.panel(x, y, w, h, title)
        visible_routes = [route for route in self.attacks if not route.complete]
        flagged = sum(route.flagged for route in visible_routes)
        if incident:
            route = incident.route
            self.text(px, py, pw, f"{incident.stage} / {route.src_city[3]} > {route.dst_city[3]} / "
                      f"{round(route.progress * 100):02d}%", "success" if incident.contained else "warn")
        else:
            unknown = sum(r.src_city is None or r.dst_city is None for r in visible_routes)
            summary = f"{len(visible_routes):02d} flows / {flagged:02d} review"
            if unknown:
                summary += f" / {unknown} geo unknown"
            self.text(px, py, pw, summary, "muted")
        mh = ph - 2
        if mh < 2:
            return
        my = py + 1
        viewport = self.map_views[self.view]
        bounds = viewport.bounds
        textures = (coastline_texture(pw, mh, bounds) if self.coastlines_available
                    else (" " * pw,) * mh)
        for row, texture in enumerate(textures):
            self.text(px, my + row, pw, texture, "map_land")
        if self.borders_visible:
            for row, borders in enumerate(border_texture(pw, mh, bounds)):
                for col, border in enumerate(borders):
                    if border == " ":
                        continue
                    coastline = textures[row][col]
                    if coastline != " ":
                        mask = (ord(coastline) - 0x2800) | (ord(border) - 0x2800)
                        char, color = chr(0x2800 + mask), "map_land"
                    else:
                        char, color = border, "map_border"
                    self.canvas.write_char(px + col, my + row, char, self.palette[color])
        # Routes use a shallow Bezier arc in screen coordinates. Land remains
        # dim while active flow heads carry the brightest color on the map.
        for route in visible_routes:
            if route.critical or route.src_city is None or route.dst_city is None:
                continue
            if route.session is not None and route.session.rate == 0:
                continue  # Established but idle; endpoints/row remain visible.
            sx, sy = project(*route.src_city[:2], pw, mh, bounds)
            dx, dy = project(*route.dst_city[:2], pw, mh, bounds)
            cx = (sx + dx) / 2
            cy = max(-1, (sy + dy) / 2 - min(3, abs(dx - sx) * 0.06))
            progress = route.progress
            steps = max(12, min(100, int(abs(dx - sx) + abs(dy - sy))))
            for step in range(max(0, int(progress * steps) - 9), int(progress * steps) + 1):
                t = min(progress, step / steps)
                fx = round((1 - t) ** 2 * sx + 2 * (1 - t) * t * cx + t * t * dx)
                fy = round((1 - t) ** 2 * sy + 2 * (1 - t) * t * cy + t * t * dy)
                if 0 <= fx < pw and 0 <= fy < mh:
                    color = "warn" if route.flagged else "trail"
                    self.canvas.write_char(px + fx, my + fy, "·", self.palette[color])
            t = progress
            fx = round((1 - t) ** 2 * sx + 2 * (1 - t) * t * cx + t * t * dx)
            fy = round((1 - t) ** 2 * sy + 2 * (1 - t) * t * cy + t * t * dy)
            if 0 <= fx < pw and 0 <= fy < mh:
                self.canvas.write_char(px + fx, my + fy, "●", self.palette["warn" if route.flagged else "packet"])
        # A persistent geographic trail stays attached to the tracked packet
        # while the camera moves. It remains above ordinary traffic and borders.
        if incident:
            steps = 180
            for step in range(steps + 1):
                t = step / steps
                if t > incident.route.progress:
                    if step % 3:
                        continue
                    char, color = "·", "muted"
                else:
                    char = "•"
                    color = "success" if incident.contained else "critical_trail"
                fx, fy = project(*incident.position(t), pw, mh, bounds)
                fx, fy = round(fx), round(fy)
                if 0 <= fx < pw and 0 <= fy < mh:
                    self.canvas.write_char(px + fx, my + fy, char, self.palette[color])
        # Place only labels that fit without covering another label or node.
        occupied = set()
        groups = {}
        for city in CITIES:
            nx, ny = project(*city[:2], pw, mh, bounds)
            nx, ny = round(nx), round(ny)
            if 0 <= nx < pw and 0 <= ny < mh:
                groups.setdefault((nx, ny), []).append(city)
                occupied.add((nx, ny))
        flagged_codes = {r.src_city[3] for r in visible_routes if r.flagged and r.src_city is not None}
        flagged_codes.update(r.dst_city[3] for r in visible_routes
                             if r.flagged and r.dst_city is not None)
        active_codes = {c[3] for r in visible_routes for c in (r.src_city, r.dst_city)
                        if c is not None}

        def priority(city):
            return (incident is not None and city in (incident.route.src_city, incident.route.dst_city),
                    city[3] in flagged_codes, city[3] in active_codes)

        # Several cities can share a cell at world scale. Show the busiest node
        # in each cell and place its label before quieter neighbors.
        nodes = [(nx, ny, max(cities, key=priority)) for (nx, ny), cities in groups.items()]
        nodes.sort(key=lambda node: priority(node[2]), reverse=True)
        for nx, ny, city in nodes:
            flagged = city[3] in flagged_codes
            self.canvas.write_char(px + nx, my + ny, "◆" if flagged else "•",
                                   self.palette["warn" if flagged else "accent"])
            if city[3] not in active_codes:
                continue
            for lx, ly in ((nx + 2, ny), (nx - 4, ny), (nx - 1, ny + 1)):
                cells = {(lx + i, ly) for i in range(3)}
                if (0 <= lx and lx + 3 <= pw and 0 <= ly < mh
                        and not occupied.intersection(cells)):
                    self.text(px + lx, my + ly, 3, city[3], "text")
                    occupied.update(cells)
                    break
        if incident:
            fx, fy = project(*incident.position(), pw, mh, bounds)
            fx, fy = round(fx), round(fy)
            color = "success" if incident.contained else "critical_head"
            # Target reticle and packet head are drawn last, above node labels.
            for ox, oy, char in ((-1, 0, "["), (1, 0, "]"), (0, -1, "│"),
                                 (0, 1, "│"), (0, 0, "◉")):
                if 0 <= fx + ox < pw and 0 <= fy + oy < mh:
                    self.canvas.write_char(px + fx + ox, my + fy + oy, char, self.palette[color])
        latitude = f"{abs(viewport.latitude):.2f}°{'N' if viewport.latitude >= 0 else 'S'}"
        longitude = f"{abs(viewport.longitude):.2f}°{'E' if viewport.longitude >= 0 else 'W'}"
        self.text(px, py + ph - 1, pw,
                  f"{latitude}  {longitude}  /  {viewport.zoom:.1f}x", "muted")

    def draw_health(self, x, y, w, h):
        px, py, pw, ph = self.panel(x, y, w, h, "COLLECTOR HEALTH")
        rows = []
        for key, label in (("CPU", "CPU load"), ("RAM", "Memory"), ("DISK", "Disk")):
            value = self.metrics[key]
            bw = max(3, pw - 17)
            fill = min(bw, max(0, round(value / 100 * bw)))
            rows.append((f"{label:<8} {'━' * fill}{'·' * (bw - fill)} {value:4.1f}%", "text"))
        rows.extend([
            (f"Temp     {self.metrics['TEMP']:.1f} C   Fan 1,420 RPM", "muted"),
            (f"Latency  {self.metrics['LATENCY']:.1f} ms p95", "accent"),
            ("Packet loss  0.02%", "muted"),
            ("", "muted"),
            ("PAYLOAD / 1s BUCKETS", "muted"),
            (sparkline(self.traffic_history, pw), "accent"),
            (f"{self.metrics['NET']:.1f} Mb/s  /  peak {max(self.traffic_history):.1f}", "muted"),
            ("", "muted"),
            ("DETECTION COUNTS", "muted"),
        ])
        max_hits = max(1, max(self.rule_hits))
        for label, hits in zip(RULES, self.rule_hits):
            bw = max(2, pw - 22)
            rows.append((f"{label:<16} {'━' * round(hits / max_hits * bw):<{bw}} {hits:3d}", "info"))
        rows.append((f"Processed  {self.total_events:,} events", "muted"))
        for i, (value, color) in enumerate(rows[:ph]):
            self.text(px, py + i, pw, value, color)

    def draw_events(self, x, y, w, h):
        px, py, pw, ph = self.panel(x, y, w, h, "EVENT STREAM")
        compact = pw < 60
        self.text(px, py, pw, "TIME UTC  SITE:ASSET / PEER" if compact else
                  "TIME UTC  LEVEL COL   SITE:ASSET / OBSERVATION", "muted")
        visible = list(self.threat_logs)[-max(0, ph - 1):]
        for i, (stamp, severity, sensor, message, status) in enumerate(visible[:ph - 1]):
            ry = py + i + 1
            self.text(px, ry, 8, stamp, "muted")
            if compact:
                self.text(px + 10, ry, pw - 10, message, "warn" if status == "warn" else "text")
                continue
            color = "warn" if severity in ("MED", "HIGH", "CRIT") else "success" if severity == "LOW" else "muted"
            self.text(px + 10, ry, 4, severity, color)
            self.text(px + 15, ry, 3, sensor, "accent")
            self.text(px + 20, ry, pw - 20, message, "text")

    def draw_flows(self, x, y, w, h):
        px, py, pw, ph = self.panel(x, y, w, h, "ACTIVE FLOWS")
        self.text(px, py, pw, "SITE:ASSET > PEER / SERVICE / Mb/s", "muted")
        routes = sorted(self.attacks, key=lambda route: route.critical, reverse=True)
        for i, route in enumerate(routes[:max(0, ph - 2)]):
            if i + 1 >= ph - 1:
                break
            policy = ("BLOCKED" if self.critical_incident.contained else "TRACE") if route.critical else (
                "REVIEW" if route.flagged else "ALLOW")
            if route.connection is None:
                context = f"{route.src_city[3]}>{route.dst_city[3]}"
                assessment = policy
            else:
                context = self.organization.context(route.connection)
                assessment = policy if route.critical else ("OK" if route.connection.expected else "NEW")
            value = (f"{context} {assessment} {route.kind}" if pw < 40 else
                     f"{context:<22} {route.kind:<6} {route.rate:4.1f} {assessment}")
            if pw >= 58 and route.session is not None:
                session = route.session
                value = (f"{context:<22} {session.proto}/{session.service}/{session.encryption} "
                         f"{session.rate:.2f} {session.conn_state} {assessment}")
                if pw >= 85:
                    value += f" {session.duration:.1f}s {session.orig_bytes}/{session.resp_bytes}B"
            color = "critical_ok" if route.critical and self.critical_incident.contained else (
                "critical" if route.critical else "warn" if route.flagged else "text")
            self.text(px, py + i + 1, pw, value, color)
        if not self.attacks and ph > 2:
            self.text(px, py + 2, pw, "Waiting for next flow...", "muted")
        if ph > 2:
            self.text(px, py + ph - 1, pw, "? geo unknown; NEW review" if pw < 40 else
                      "Mb/s: trailing 1s; markers: activity", "muted")

    def draw(self):
        self.canvas.clear()
        width, height = self.canvas.width, self.canvas.height
        if self.active_mode == "shell":
            self.draw_shell_screen()
            return
        if self.active_mode == "breach":
            self.draw_breach_screen()
            return
        self.text(1, 0, width - 2, "GLOBAL THREAT MONITOR", "accent")
        state = "PAUSED" if self.paused else "LIVE"
        header = f"{state}  /  {self.timestamp()} UTC"
        self.text(width - len(header) - 1, 0, len(header), header, "muted")
        if self.critical_incident is not None:
            incident = self.critical_incident
            banner = f" P1 {incident.identifier} / {incident.stage} / "
            banner += f"{incident.route.src_city[2]} > {incident.route.dst_city[2]}"
            self.text(1, 1, width - 2, banner.ljust(width - 2),
                      "critical_ok" if incident.contained else "critical")
        else:
            self.text(1, 1, width - 2, "ASTER OPERATIONS / ATH office / FRA data center / SIN cloud / REM users", "muted")
        self.draw_kpis(3)
        left_w = int(width * 0.64)
        right_x = left_w + 1
        right_w = width - right_x
        content_h = height - 11
        top_h = max(7, int(content_h * 0.61))
        lower_y = 9 + top_h
        lower_h = height - 2 - lower_y
        self.draw_map(0, 8, left_w, top_h)
        self.draw_health(right_x, 8, right_w, top_h)
        self.draw_events(0, lower_y, left_w, lower_h)
        self.draw_flows(right_x, lower_y, right_w, lower_h)

    def draw_shell_screen(self):
        width, height = self.canvas.width, self.canvas.height
        px, py, pw, ph = self.panel(0, 0, width, height - 2, "OPERATIONS CONSOLE")
        for i, line in enumerate(list(self.shell_history)[-max(0, ph - 2):]):
            self.text(px, py + i, pw, line, "text")
        self.text(px, height - 4, pw, f"analyst@monitor:~$ {self.shell_input}▏", "accent")

    def process_shell_command(self, cmd):
        command = cmd.strip().lower()
        self.shell_history.append(f"analyst@monitor:~$ {cmd}")
        if command == "help":
            self.shell_history.extend([
                "status          Sensor health and current telemetry",
                "flows           Session identity, ports, state, bytes, packets and 1s rates",
                "sessions        Start DNS, HTTPS, SSH and backup demonstration",
                "flow-history    Completed session summaries (last 120)",
                "org             List sites, assets, expected peers and collectors",
                "baseline        Athens workstation > expected Frankfurt service",
                "unfamiliar      Athens workstation > peer with unknown geography",
                "clear           Clear console history",
                "enhance         Focus the regional map",
                "ddos-localhost  Simulate a blocked loopback burst",
                "nuke-gibson     Start the containment drill",
                "exit            Return to dashboard",
            ])
        elif command in ("exit", "quit"):
            self.active_mode = "dashboard"
        elif command == "status":
            self.shell_history.extend([
                f"Sensors: {self.sensors_online}/{len(CITIES)} online",
                f"Payload: {self.metrics['NET']:.4f} Mb/s / previous complete 1s bucket; "
                f"total {self.simulation.total_bytes:,} bytes; no hidden aggregate",
                f"Latency: {self.metrics['LATENCY']:.1f} ms / modeled load estimate",
                f"Processed: {self.total_events:,}; contained: {self.blocked:,}",
            ])
        elif command == "flows":
            for route in self.attacks:
                self.shell_history.append(self.organization.describe(route.connection))
                self.shell_history.extend(route.session.detail_lines())
        elif command == "flow-history":
            for session in self.simulation.history:
                self.shell_history.append(self.organization.context(session.connection))
                self.shell_history.extend(session.detail_lines())
            if not self.simulation.history:
                self.shell_history.append("No completed sessions yet")
        elif command == "sessions":
            for source, peer, service in (("ATH-WS1", "FRA-DNS", "DNS"),
                                          ("ATH-WS1", "FRA-APP", "HTTPS"),
                                          ("ATH-ADM", "FRA-APP", "SSH"),
                                          ("FRA-BKP", "SIN-STORE", "BACKUP")):
                if len(self.attacks) >= 11:
                    self.shell_history.append("Flow limit reached; wait for activity to finish")
                    break
                route = self.trigger_attack(self.organization.connect(source, peer, service))
                self.shell_history.append(self.organization.context(route.connection))
                self.shell_history.extend(route.session.detail_lines())
        elif command == "org":
            self.shell_history.append(f"Aster: {len(self.organization.collectors)} city collectors; "
                                      "collector location does not locate a remote peer")
            for site in self.organization.sites.values():
                self.shell_history.append(f"{site.identifier}: {site.name} / {site.role} / "
                                          f"owner {site.owner} / criticality {site.criticality}")
            for asset in self.organization.assets.values():
                self.shell_history.append(f"{asset.identifier}@{asset.site_id}: {asset.role} / "
                                          f"owner {asset.owner} / criticality {asset.criticality} / "
                                          f"{asset.address} / city {asset.city_code or 'unknown'} / "
                                          f"collector {asset.collector_id or 'none'}")
            for entry in self.organization.expected_connections:
                self.shell_history.append(f"Expected {entry.source_id}>{entry.peer_id} "
                                          f"{entry.service} / {entry.purpose}")
        elif command in ("baseline", "unfamiliar"):
            peer = "FRA-APP" if command == "baseline" else "EXT-UNK"
            if len(self.attacks) >= 11:
                self.shell_history.append("Flow limit reached; wait for activity to finish")
            else:
                connection = self.organization.connect("ATH-WS1", peer, "HTTPS")
                self.trigger_attack(connection)
                self.shell_history.append(self.organization.describe(connection))
        elif command == "clear":
            self.shell_history.clear()
        elif command == "enhance":
            self.view = "EUROPE"
            self.map_views[self.view].reset()
            self.touch_map()
            self.active_mode = "dashboard"
        elif command == "ddos-localhost":
            self.shell_history.append("Loopback burst simulated. Rate-limit policy applied. No packets sent.")
        elif command == "nuke-gibson":
            self.start_drill()
        elif command:
            self.shell_history.append(f"Unknown command: {command}")

    def start_drill(self):
        self.active_mode = "breach"
        self.breach_time_left = 10.0
        self.breach_taps = 0

    def draw_breach_screen(self):
        width, height = self.canvas.width, self.canvas.height
        bw, bh = min(66, width - 4), 13
        x, y = (width - bw) // 2, (height - bh) // 2
        px, py, pw, _ = self.panel(x, y, bw, bh, "CONTAINMENT DRILL")
        self.text(px, py + 1, pw, "Unusual egress activity detected", "warn")
        self.text(px, py + 3, pw, f"Response window  {self.breach_time_left:4.1f} seconds", "accent")
        self.text(px, py + 5, pw, "CONTAINMENT PIPELINE", "text")
        filled = round(self.breach_taps / 15 * (pw - 8))
        self.text(px, py + 7, pw, f"{'━' * filled}{'·' * (pw - 8 - filled)} {self.breach_taps:02d}/15", "success")

    def handle_key(self, key):
        """Return False to quit. Escape and q stay distinct inside the console."""
        if key == "quit":
            return False
        if key in ("wheel_up", "wheel_down") and self.active_mode != "dashboard":
            return True
        if self.active_mode == "shell":
            if key == "escape":
                self.active_mode = "dashboard"
            elif key == "enter":
                self.process_shell_command(self.shell_input)
                self.shell_input = ""
            elif key == "backspace":
                self.shell_input = self.shell_input[:-1]
            elif len(key) == 1 and key.isprintable() and len(self.shell_input) < 160:
                self.shell_input += key
            return True
        if key == "q":
            return False
        if self.active_mode == "breach":
            if key == "escape":
                self.active_mode = "dashboard"
            else:
                self.breach_taps += 1
                audio.play_click()
                if self.breach_taps >= 15:
                    self.active_mode = "dashboard"
                    self.log("Containment drill complete; egress isolated", "success", "LOW")
                    audio.play_success()
            return True
        if key == "escape":
            return False
        if key == "t":
            self.toggle_theme()
        elif key == "p":
            self.paused = not self.paused
        elif key == "r":
            keys = list(VIEWS)
            self.view = keys[(keys.index(self.view) + 1) % len(keys)]
            self.map_views[self.view].reset()
            self.touch_map()
        elif self.handle_map_key(key):
            pass
        elif key == "s":
            self.toggle_sound()
        elif key == "a":
            self.trigger_attack()
        elif key == "f":
            self.start_critical_incident()
        elif key == "c":
            self.active_mode = "shell"
            self.shell_input = ""
            if not self.shell_history:
                self.shell_history.append(f"Session established / {self.sensors_online} collectors online")
        elif key == "g":
            self.start_drill()
        elif key in ("+", "=", "-"):
            self.speed_multiplier = clamp_speed(
                self.speed_multiplier + (-0.25 if key == "-" else 0.25))
        return True


def main():
    parser = argparse.ArgumentParser(
        prog="global-threat-monitor", description=f"{APP_NAME} v{APP_VERSION}. {APP_DESCRIPTION}",
        epilog="Keys: Q/Esc quit, P pause, T theme, R region, B borders, wheel/[ ] zoom, arrows/HJKL pan, "
               "0 reset, A flow, F critical incident, C console, G drill, +/- speed, S audio.")
    parser.add_argument("-t", "--theme", choices=list(THEMES), help="Set startup theme.")
    parser.add_argument("-s", "--sound", action="store_true", help="Enable optional Windows chimes.")
    parser.add_argument("-n", "--no-sound", action="store_true", help="Mute chimes.")
    parser.add_argument("--speed", type=float, default=1.0, help="Simulation speed, clamped to 0.25–4.0.")
    parser.add_argument("--seed", type=int, help="Reproduce organization peer/service selection.")
    parser.add_argument("--fps", type=int, choices=range(10, 61), metavar="10-60", default=30,
                        help="Rendering rate. Default: 30. Independent of simulation speed.")
    parser.add_argument("-v", "--version", action="version", version=f"{APP_NAME} v{APP_VERSION}")
    args = parser.parse_args()
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        parser.exit(1, "Run this dashboard in an interactive terminal.\n")
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    monitor = CyberMonitor(args.theme, args.sound and not args.no_sound, args.speed, args.seed)
    enable_windows_ansi()
    interval = 1 / args.fps
    last_size = None
    previous_time = time.monotonic()
    deadline = previous_time
    try:
        init_keyboard()
        sys.stdout.write("\033[?1049h\033[?25l\033[H\033[2J" + (MOUSE_ON if not WINDOWS else ""))
        sys.stdout.flush()
        running = True
        while running:
            now = time.monotonic()
            # Clamp stalls after suspend/resizing instead of racing to catch up.
            dt = min(0.1, now - previous_time)
            previous_time = now
            for _ in range(64):
                key = get_key()
                if key is None:
                    break
                if not monitor.handle_key(key):
                    running = False
                    break
            if not running:
                break
            size = shutil.get_terminal_size()
            resized = size != last_size
            if resized:
                monitor.canvas = Canvas(max(1, size.columns - 1), max(1, size.lines))
                last_size = size
            if size.columns < MIN_WIDTH or size.lines < MIN_HEIGHT:
                monitor.canvas.clear()
                monitor.text(0, 1, monitor.canvas.width, "Global Threat Monitor", "accent")
                monitor.text(0, 3, monitor.canvas.width, f"Resize to at least {MIN_WIDTH}x{MIN_HEIGHT}. Current: {size.columns}x{size.lines}.")
            else:
                monitor.update(dt)
                monitor.draw()
            frame = monitor.canvas.render_diff()
            if frame or resized:
                # One write/flush per frame. Absolute cursors avoid newline
                # scrolling, including when writing the terminal's bottom row.
                sys.stdout.write(("\033[H\033[2J" if resized else "") + frame)
                sys.stdout.flush()
            deadline += interval
            delay = deadline - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            else:
                deadline = time.monotonic()
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write((MOUSE_OFF if not WINDOWS else "") + "\033[0m\033[?25h\033[?1049l")
        sys.stdout.flush()
        restore_keyboard()


if __name__ == "__main__":
    main()
