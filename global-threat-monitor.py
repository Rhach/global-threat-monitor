#!/usr/bin/env python3
"""A simulated security-operations dashboard. Python standard library only."""

import argparse
from collections import deque
from functools import lru_cache
import json
import math
import os
import queue
import random
import shutil
import sys
import threading
import time

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
]

# Simplified coastlines, rasterized once per viewport into 2x4 braille cells.
# Equirectangular projection, bounded to 80 N / 60 S in the world view.
LAND = [
    [(-168, 71), (-145, 70), (-130, 60), (-125, 50), (-123, 40),
     (-116, 32), (-109, 24), (-100, 17), (-88, 15), (-83, 9), (-77, 8),
     (-87, 21), (-81, 25), (-80, 32), (-70, 43), (-60, 47), (-55, 53),
     (-65, 60), (-80, 63), (-95, 74), (-120, 73), (-150, 72)],
    [(-73, 60), (-48, 59), (-20, 76), (-42, 83), (-62, 80)],
    [(-81, 12), (-72, 11), (-61, 8), (-50, 1), (-35, -6), (-40, -20),
     (-49, -28), (-54, -38), (-68, -55), (-75, -45), (-73, -30),
     (-80, -10)],
    [(-17, 35), (-5, 36), (10, 37), (25, 32), (33, 31), (43, 12),
     (51, 11), (42, -2), (35, -20), (28, -34), (18, -35), (11, -18),
     (8, 4), (-5, 5), (-16, 15)],
    [(-10, 36), (-10, 44), (-1, 49), (8, 54), (5, 59), (20, 71),
     (32, 70), (40, 60), (60, 69), (90, 75), (120, 72), (160, 66),
     (179, 65), (168, 55), (145, 48), (140, 38), (124, 40), (122, 25),
     (110, 19), (107, 10), (100, 1), (96, 18), (88, 22), (80, 8),
     (73, 19), (65, 25), (58, 24), (52, 13), (43, 12), (35, 30),
     (26, 40), (20, 40), (16, 38), (12, 45), (3, 43)],
    [(-8, 50), (-6, 58), (-3, 59), (1, 52)],
    [(130, 31), (136, 35), (142, 41), (145, 44), (141, 45), (137, 38)],
    [(113, -22), (123, -14), (135, -12), (141, -17), (145, -14),
     (153, -25), (150, -37), (137, -35), (130, -32), (115, -35)],
    [(47, -13), (50, -17), (46, -26), (43, -24)],
    [(95, 5), (105, -5), (114, -8), (106, -8)],
    [(109, 7), (118, 7), (119, -4), (111, -4)],
    [(130, -3), (141, -2), (151, -7), (141, -10)],
    [(166, -34), (179, -40), (173, -47), (166, -46), (174, -40)],
]
VIEWS = {
    "WORLD": (-180, 180, -60, 80),
    "EUROPE": (-15, 50, 25, 72),
    "ASIA": (45, 160, -15, 65),
    "AMERICAS": (-170, -30, -60, 75),
}


def project(lon, lat, width, height, bounds):
    west, east, south, north = bounds
    return ((lon - west) / (east - west) * (width - 1),
            (north - lat) / (north - south) * (height - 1))


@lru_cache(maxsize=8)
def map_texture(width, height, view):
    """Scanline-fill coastlines at braille resolution. No per-frame geography work."""
    sw, sh = width * 2, height * 4
    pixels = [bytearray(sw) for _ in range(sh)]
    for polygon in LAND:
        points = [project(lon, lat, sw, sh, VIEWS[view]) for lon, lat in polygon]
        for y in range(sh):
            scan_y = y + 0.5
            crossings = []
            for a, b in zip(points, points[1:] + points[:1]):
                if (a[1] <= scan_y < b[1]) or (b[1] <= scan_y < a[1]):
                    crossings.append(a[0] + (scan_y - a[1]) *
                                     (b[0] - a[0]) / (b[1] - a[1]))
            crossings.sort()
            for left, right in zip(crossings[::2], crossings[1::2]):
                start = max(0, math.ceil(left - 0.5))
                end = min(sw, math.ceil(right - 0.5))
                if end > start:
                    pixels[y][start:end] = b"\1" * (end - start)
    bits = ((1, 8), (2, 16), (4, 32), (64, 128))
    rows = []
    for y in range(height):
        row = []
        for x in range(width):
            mask = sum(bits[dy][dx] for dy in range(4) for dx in range(2)
                       if pixels[y * 4 + dy][x * 2 + dx])
            row.append(chr(0x2800 + mask) if mask else " ")
        rows.append("".join(row))
    return tuple(rows)


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


def enable_windows_ansi():
    if WINDOWS:
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        if kernel.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel.SetConsoleMode(handle, mode.value | 0x0004)


def init_keyboard():
    global old_settings
    if not WINDOWS and sys.stdin.isatty():
        old_settings = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())


def restore_keyboard():
    if not WINDOWS and old_settings is not None:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)


def get_key():
    """Read raw bytes: TextIO buffering otherwise hides pasted/burst input."""
    if WINDOWS:
        if not msvcrt.kbhit():
            return None
        key = msvcrt.getwch()
        if key in ("\x00", "\xe0"):
            msvcrt.getwch()
            return None
    else:
        if not select.select([sys.stdin], [], [], 0)[0]:
            return None
        data = os.read(sys.stdin.fileno(), 1)
        if not data:
            return None
        key = data.decode("ascii", errors="ignore")
        if not key:
            return None
    if key == "\x03":
        return "quit"
    if key == "\x1b":
        return "escape"
    if key in ("\x7f", "\x08"):
        return "backspace"
    if key in ("\r", "\n"):
        return "enter"
    return key.lower()


class AttackVector:
    def __init__(self, src, dst, theme_palette):
        self.src_city, self.dst_city = src, dst
        self.palette = theme_palette
        self.duration = 3.0
        self.progress = 0.0
        self.age = 0.0
        self.complete = False
        self.kind = random.choices(
            ["TLS", "DNS", "HTTPS", "SSH"], weights=[4, 2, 5, 1])[0]
        self.flagged = random.random() < 0.23
        self.rate = random.uniform(0.8, 18.0)

    def update(self, dt=1 / 30):
        self.age += dt
        self.progress = min(1.0, self.age / self.duration)
        self.complete = self.age >= self.duration + 0.45


EVENTS = [
    ("INFO", "dns", "DNS response cached", "info"),
    ("INFO", "tls", "TLS 1.3 session negotiated", "info"),
    ("LOW", "policy", "Egress policy matched", "success"),
    ("MED", "recon", "Repeated SYN probes; rate limited", "warn"),
    ("HIGH", "auth", "SSH credential retries; source blocked", "warn"),
    ("MED", "waf", "SQLi signature matched; request denied", "warn"),
    ("LOW", "edr", "Endpoint heartbeat received", "success"),
    ("INFO", "policy", "Sensor policy synchronized", "success"),
]
EVENT_WEIGHTS = [12, 16, 12, 4, 2, 3, 18, 8]
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
    def __init__(self, initial_theme=None, initial_sound=False, initial_speed=1.0):
        theme = initial_theme or load_config().get("theme", "ice")
        self.theme_key = theme if theme in THEMES else "ice"
        self.palette = THEMES[self.theme_key]
        self.canvas = Canvas(100, 35)
        self.paused = False
        self.speed_multiplier = clamp_speed(initial_speed)
        self.active_mode = "dashboard"
        self.view = "WORLD"
        self.elapsed = 0.0
        self.boot_time = time.monotonic()
        self.clock_base = time.time()
        self.telemetry_timer = 0.0
        self.attack_cooldown = 0.0
        self.event_cooldown = 1.5
        self.attacks = []
        self.threat_logs = deque(maxlen=80)
        self.shell_history = deque(maxlen=100)
        self.shell_input = ""
        self.breach_time_left = 10.0
        self.breach_taps = 0
        self.metrics = {"CPU": 34.0, "RAM": 62.0, "DISK": 41.0,
                        "TEMP": 49.0, "NET": 184.0, "LATENCY": 23.0}
        self.traffic_history = deque(
            (184 + 24 * math.sin(i / 8) + random.uniform(-7, 7)
             for i in range(90)), maxlen=120)
        self.latency_history = deque([23.0] * 90, maxlen=120)
        self.total_events = 12842
        self.blocked = 284
        self.rule_hits = [97, 84, 62, 41]
        self.last_eps = 246
        self.sensors_online = len(CITIES)
        audio.muted = not initial_sound
        # Seed the feed with a chronological window, rather than dozens of
        # identical timestamps. All addresses are documentation-only ranges.
        for i in range(18):
            self.generate_threat_log(timestamp=self.clock_base - (18 - i) * 3)

    def timestamp(self):
        return time.strftime("%H:%M:%S", time.gmtime(self.clock_base + self.elapsed))

    def log(self, message, status="info", severity="INFO", sensor="SYS"):
        self.threat_logs.append((self.timestamp(), severity, sensor, message, status))

    def generate_threat_log(self, init=False, timestamp=None):
        severity, category, message, status = random.choices(
            EVENTS, weights=EVENT_WEIGHTS)[0]
        sensor = random.choice(CITIES)[3]
        address = f"{random.choice(['192.0.2', '198.51.100', '203.0.113'])}.{random.randint(1, 254)}"
        stamp = self.timestamp() if timestamp is None else time.strftime(
            "%H:%M:%S", time.gmtime(timestamp))
        self.threat_logs.append((stamp, severity, sensor,
                                 f"{message} / {address}", status))
        if status == "warn" and timestamp is None:
            self.blocked += 1
            idx = {"auth": 0, "recon": 1, "waf": 2}.get(category, 3)
            self.rule_hits[idx] += 1

    def toggle_theme(self):
        keys = list(THEMES)
        self.theme_key = keys[(keys.index(self.theme_key) + 1) % len(keys)]
        self.palette = THEMES[self.theme_key]
        save_config(self.theme_key)

    def toggle_sound(self):
        audio.muted = not audio.muted
        self.log("Audio muted" if audio.muted else "Audio enabled", "success")

    def trigger_attack(self):
        if len(self.attacks) >= 12:
            return
        src, dst = random.sample(CITIES, 2)
        route = AttackVector(src, dst, self.palette)
        self.attacks.append(route)
        if route.flagged:
            self.log(f"Anomalous {route.kind} flow / {src[3]} > {dst[3]}",
                     "warn", "MED", dst[3])
        audio.play_packet()

    def update(self, dt=1 / 30):
        if self.paused:
            return
        if self.active_mode == "breach":
            self.breach_time_left = max(0.0, self.breach_time_left - dt)
            if self.breach_time_left == 0:
                self.active_mode = "dashboard"
                self.log("Exercise timed out; recovery policy applied", "warn", "HIGH")
        sim_dt = max(0.0, dt) * self.speed_multiplier
        self.elapsed += sim_dt
        for attack in self.attacks:
            attack.update(sim_dt)
            if attack.complete and attack.flagged:
                self.blocked += 1
                self.rule_hits[3] += 1
                self.log(f"Anomalous {attack.kind} flow contained / {attack.src_city[3]}",
                         "success", "LOW", attack.dst_city[3])
        self.attacks[:] = [attack for attack in self.attacks if not attack.complete]
        self.attack_cooldown -= sim_dt
        if self.attack_cooldown <= 0:
            if len(self.attacks) < 5:
                self.trigger_attack()
            self.attack_cooldown += random.uniform(0.7, 1.6)
        self.event_cooldown -= sim_dt
        if self.event_cooldown <= 0:
            self.generate_threat_log()
            self.event_cooldown += random.uniform(1.8, 3.8)
        self.telemetry_timer += sim_dt
        while self.telemetry_timer >= 1.0:
            self.telemetry_timer -= 1.0
            # Correlated, gently mean-reverting load. Samples change once a second.
            traffic = self.metrics["NET"]
            traffic += (184 - traffic) * 0.06 + random.uniform(-12, 12)
            self.metrics["NET"] = max(70, min(320, traffic))
            targets = {"CPU": 18 + traffic * 0.09, "RAM": 62,
                       "DISK": 41, "TEMP": 39 + self.metrics["CPU"] * 0.3,
                       "LATENCY": 15 + traffic * 0.04}
            for key, target in targets.items():
                jitter = 0.3 if key in ("RAM", "DISK", "TEMP") else 1.2
                self.metrics[key] += (target - self.metrics[key]) * 0.12 + random.uniform(-jitter, jitter)
            self.traffic_history.append(self.metrics["NET"])
            self.latency_history.append(self.metrics["LATENCY"])
            self.last_eps = int(self.metrics["NET"] * 1.35)
            self.total_events += self.last_eps

    def panel(self, x, y, w, h, title):
        self.canvas.draw_box(x, y, w, h, title, self.palette["border"])
        return x + 2, y + 1, w - 4, h - 2

    def text(self, x, y, width, value, color="text"):
        self.canvas.write_str(x, y, str(value)[:max(0, width)], self.palette[color])

    def draw_kpis(self, y):
        width = self.canvas.width
        cards = [
            ("EVENTS / SEC", f"{self.last_eps:,}", "normalized telemetry", "accent"),
            ("CONTAINED", f"{self.blocked:,}", "policy actions", "success"),
            ("THROUGHPUT", f"{self.metrics['NET']:.1f} Mb/s", "aggregate ingress", "accent"),
            ("SENSORS", f"{self.sensors_online:02d} / {len(CITIES):02d}", "all regions online", "success"),
        ]
        for i, (title, value, hint, color) in enumerate(cards):
            x = i * (width + 1) // 4
            end = (i + 1) * (width + 1) // 4 - 1
            px, py, pw, _ = self.panel(x, y, end - x, 5, title)
            self.text(px, py + 1, pw, value, color)
            self.text(px, py + 2, pw, hint, "muted")

    def draw_map(self, x, y, w, h):
        px, py, pw, ph = self.panel(x, y, w, h, f"GLOBAL TRAFFIC / {self.view}")
        flagged = sum(route.flagged for route in self.attacks)
        self.text(px, py, pw, f"{len(self.attacks):02d} active flows   {flagged:02d} under review", "muted")
        mh = ph - 2
        if mh < 2:
            return
        my = py + 1
        for row, texture in enumerate(map_texture(pw, mh, self.view)):
            self.text(px, my + row, pw, texture, "map_land")
        # Routes use a shallow Bezier arc in screen coordinates. Land remains
        # dim while active flow heads carry the brightest color on the map.
        for route in self.attacks:
            sx, sy = project(*route.src_city[:2], pw, mh, VIEWS[self.view])
            dx, dy = project(*route.dst_city[:2], pw, mh, VIEWS[self.view])
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
        # Place only labels that fit without covering another label or node.
        occupied = set()
        nodes = []
        for city in CITIES:
            nx, ny = project(*city[:2], pw, mh, VIEWS[self.view])
            nx, ny = round(nx), round(ny)
            if 0 <= nx < pw and 0 <= ny < mh:
                nodes.append((nx, ny, city))
                occupied.add((nx, ny))
        for nx, ny, city in nodes:
            flagged = any(r.flagged and r.dst_city == city for r in self.attacks)
            self.canvas.write_char(px + nx, my + ny, "◆" if flagged else "•",
                                   self.palette["warn" if flagged else "accent"])
            for lx, ly in ((nx + 2, ny), (nx - 4, ny), (nx - 1, ny + 1)):
                cells = {(lx + i, ly) for i in range(3)}
                if (0 <= lx and lx + 3 <= pw and 0 <= ly < mh
                        and not occupied.intersection(cells)):
                    self.text(px + lx, my + ly, 3, city[3], "text")
                    occupied.update(cells)
                    break
        self.text(px, py + ph - 1, pw, "• sensor   ● flow   ◆ review   R change region", "muted")

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
            ("INGRESS / 120 SAMPLES", "muted"),
            (sparkline(self.traffic_history, pw), "accent"),
            (f"{self.metrics['NET']:.1f} Mb/s  /  peak {max(self.traffic_history):.1f}", "muted"),
            ("", "muted"),
            ("DETECTION COUNTS", "muted"),
        ])
        max_hits = max(self.rule_hits)
        for label, hits in zip(RULES, self.rule_hits):
            bw = max(2, pw - 22)
            rows.append((f"{label:<16} {'━' * max(1, round(hits / max_hits * bw)):<{bw}} {hits:3d}", "info"))
        rows.append((f"Processed  {self.total_events:,} events", "muted"))
        for i, (value, color) in enumerate(rows[:ph]):
            self.text(px, py + i, pw, value, color)

    def draw_events(self, x, y, w, h):
        px, py, pw, ph = self.panel(x, y, w, h, "EVENT STREAM")
        self.text(px, py, pw, "TIME UTC  LEVEL NODE  OBSERVATION", "muted")
        visible = list(self.threat_logs)[-max(0, ph - 1):]
        for i, (stamp, severity, sensor, message, status) in enumerate(visible[:ph - 1]):
            ry = py + i + 1
            self.text(px, ry, 8, stamp, "muted")
            color = "warn" if severity in ("MED", "HIGH") else "success" if severity == "LOW" else "muted"
            self.text(px + 10, ry, 4, severity, color)
            self.text(px + 15, ry, 3, sensor, "accent")
            self.text(px + 20, ry, pw - 20, message, "text")

    def draw_flows(self, x, y, w, h):
        px, py, pw, ph = self.panel(x, y, w, h, "ACTIVE FLOWS")
        self.text(px, py, pw, "ROUTE      PROTO  Mb/s  POLICY", "muted")
        for i, route in enumerate(self.attacks[-max(0, ph - 2):]):
            if i + 1 >= ph - 1:
                break
            policy = "REVIEW" if route.flagged else "ALLOW"
            value = f"{route.src_city[3]} > {route.dst_city[3]}  {route.kind:<5} {route.rate:4.1f}  {policy}"
            self.text(px, py + i + 1, pw, value, "warn" if route.flagged else "text")
        if not self.attacks and ph > 2:
            self.text(px, py + 2, pw, "Waiting for next flow...", "muted")
        if ph > 2:
            self.text(px, py + ph - 1, pw, "TLS 1.3  /  egress policy enforced", "muted")

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
        header = f"{state}  /  SIMULATION  /  {self.timestamp()} UTC"
        self.text(width - len(header) - 1, 0, len(header), header, "muted")
        self.text(1, 1, width - 2, "SECURITY OPERATIONS  /  Distributed sensor telemetry", "muted")
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
        footer = "Q quit  P pause  T theme  R region  A flow  C shell  G drill  +/- speed  S audio"
        self.text(1, height - 1, width - 2, footer, "muted")
        if width >= 105:
            detail = f"{self.palette['name']}  {self.speed_multiplier:.2f}x"
            self.text(width - len(detail) - 1, height - 1, len(detail), detail, "accent")

    def draw_shell_screen(self):
        width, height = self.canvas.width, self.canvas.height
        px, py, pw, ph = self.panel(0, 0, width, height - 2, "SIMULATION CONSOLE")
        for i, line in enumerate(list(self.shell_history)[-max(0, ph - 2):]):
            self.text(px, py + i, pw, line, "text")
        self.text(px, height - 4, pw, f"analyst@monitor:~$ {self.shell_input}▏", "accent")
        self.text(1, height - 1, width - 2, "Enter run command  /  Esc return  /  Ctrl+C quit  /  help list commands", "muted")

    def process_shell_command(self, cmd):
        command = cmd.strip().lower()
        self.shell_history.append(f"analyst@monitor:~$ {cmd}")
        if command == "help":
            self.shell_history.extend([
                "status          Sensor health and current telemetry",
                "flows           List simulated traffic routes",
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
                f"Ingress: {self.metrics['NET']:.1f} Mb/s; p95: {self.metrics['LATENCY']:.1f} ms",
                f"Processed: {self.total_events:,}; contained: {self.blocked:,}",
            ])
        elif command == "flows":
            self.shell_history.extend(
                f"{r.src_city[2]} > {r.dst_city[2]} / {r.kind} / {r.rate:.1f} Mb/s"
                for r in self.attacks)
        elif command == "clear":
            self.shell_history.clear()
        elif command == "enhance":
            self.view = "EUROPE"
            self.active_mode = "dashboard"
        elif command == "ddos-localhost":
            self.shell_history.append("Loopback burst simulated. Rate-limit policy applied. No packets sent.")
        elif command == "nuke-gibson":
            self.start_drill()
        elif command:
            self.shell_history.append(f"Unknown command: {command}. Type help.")

    def start_drill(self):
        self.active_mode = "breach"
        self.breach_time_left = 10.0
        self.breach_taps = 0

    def draw_breach_screen(self):
        width, height = self.canvas.width, self.canvas.height
        bw, bh = min(66, width - 4), 13
        x, y = (width - bw) // 2, (height - bh) // 2
        px, py, pw, _ = self.panel(x, y, bw, bh, "CONTAINMENT DRILL / SIMULATED")
        self.text(px, py + 1, pw, "Unusual egress activity detected", "warn")
        self.text(px, py + 3, pw, f"Response window  {self.breach_time_left:4.1f} seconds", "accent")
        self.text(px, py + 5, pw, "Press any key to apply containment steps", "text")
        filled = round(self.breach_taps / 15 * (pw - 8))
        self.text(px, py + 7, pw, f"{'━' * filled}{'·' * (pw - 8 - filled)} {self.breach_taps:02d}/15", "success")
        self.text(px, py + 9, pw, "Esc cancel  /  Q quit", "muted")

    def handle_key(self, key):
        """Return False to quit. Escape and q stay distinct inside the console."""
        if key == "quit":
            return False
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
        elif key == "s":
            self.toggle_sound()
        elif key == "a":
            self.trigger_attack()
        elif key == "c":
            self.active_mode = "shell"
            self.shell_input = ""
            if not self.shell_history:
                self.shell_history.extend(["Simulation console. Type help for commands.",
                                           "Telemetry is generated locally. Commands do not access the network."])
        elif key == "g":
            self.start_drill()
        elif key in ("+", "=", "-"):
            self.speed_multiplier = clamp_speed(
                self.speed_multiplier + (-0.25 if key == "-" else 0.25))
        return True


def main():
    parser = argparse.ArgumentParser(
        prog="global-threat-monitor", description=f"{APP_NAME} v{APP_VERSION}. {APP_DESCRIPTION}",
        epilog="Keys: Q/Esc quit, P pause, T theme, R region, A flow, C console, G drill, +/- speed, S audio.")
    parser.add_argument("-t", "--theme", choices=list(THEMES), help="Set startup theme.")
    parser.add_argument("-s", "--sound", action="store_true", help="Enable optional Windows chimes.")
    parser.add_argument("-n", "--no-sound", action="store_true", help="Mute chimes.")
    parser.add_argument("--speed", type=float, default=1.0, help="Simulation speed, clamped to 0.25–4.0.")
    parser.add_argument("--fps", type=int, choices=range(10, 61), metavar="10-60", default=30,
                        help="Rendering rate. Default: 30. Independent of simulation speed.")
    parser.add_argument("-v", "--version", action="version", version=f"{APP_NAME} v{APP_VERSION}")
    args = parser.parse_args()
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        parser.exit(1, "Run this dashboard in an interactive terminal.\n")
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    monitor = CyberMonitor(args.theme, args.sound and not args.no_sound, args.speed)
    enable_windows_ansi()
    interval = 1 / args.fps
    last_size = None
    previous_time = time.monotonic()
    deadline = previous_time
    try:
        init_keyboard()
        sys.stdout.write("\033[?1049h\033[?25l\033[H\033[2J")
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
                monitor.text(0, 5, monitor.canvas.width, "Q / Esc quit", "muted")
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
        sys.stdout.write("\033[0m\033[?25h\033[?1049l")
        sys.stdout.flush()
        restore_keyboard()


if __name__ == "__main__":
    main()
