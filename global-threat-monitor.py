#!/usr/bin/env python3
"""
GLOBAL THREAT MONITOR v3.9.4
A premium Hacker TUI screensaver simulator.
Requires Python 3. Runs inside terminal emulators on Windows, Linux, and macOS.
"""

import os
import sys
import time
import random
import math
import shutil
import string
import json
import argparse

APP_NAME = "Global Threat Monitor"
APP_VERSION = "3.9.4"
APP_DESCRIPTION = "A useless Hollywood-style cyber threat dashboard for your terminal."

# Global Threat Monitor is a fake Hollywood-style TUI dashboard.
# It does not perform real monitoring, scanning, exploitation, or security analysis.
# All displayed activity is randomly generated simulation data.

# Force stdout/stderr to UTF-8 to prevent UnicodeEncodeError on Windows terminals with non-UTF-8 code pages
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')


def get_config_path():
    """Retrieve platform-aware config directory path using standard library only."""
    if os.name == "nt":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        return os.path.join(base, "GlobalThreatMonitor", "config.json")

    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return os.path.join(xdg_config, "global-threat-monitor", "config.json")

    return os.path.join(os.path.expanduser("~"), ".config", "global-threat-monitor", "config.json")


def load_config():
    """Load configuration from the platform-aware path."""
    try:
        config_path = get_config_path()
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except Exception:
        pass

    return {"theme": "amber"}


def save_config(theme):
    """Save configuration to the platform-aware path."""
    try:
        config_path = get_config_path()
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump({"theme": theme}, f)
    except Exception:
        pass


# Authentic, geographically accurate Mercator projection world map
# Width: 70, Height: 23
WORLD_MAP = [
    '          . _..::__:  ,-"-"._       |]       ,     _,.__                      ',
    '  _.___ _ _<_>`!(._`.`-.    /        _._     `_ ,_/  \'  \'-._.---.-.__   ',
    '.{     " " `-==,\',._\\{  \\  / {) _   / _ ">_,-\' `                 /-/_    ',
    '\\_.:--.       `._ )`^-. "\'     / ( [_/(                       __,/-\'       ',
    '\'"\'    \\        "    _\\        -_,--\'                  )     /. (|         ',
    '       |           ,\'         _)_.\\\\._<> {}              _,\' /  \'         ',
    '       \\`.         /          [_/_\'` `"(                <\'}  )            ',
    '        \\\\    .-. )          /   `-\'"..\' `:._          _)  \'            ',
    ' `        \\  (  `(          /         `:\\  > \\  ,-^.  /\' \'             ',
    '           `._,   ""        |           \\`\'   \\|   ?_)  {\\             ',
    '              `=.---.       `._._       ,\'     "`  |\' ,- \'.              ',
    '                |    `-._        |     /          `:`<_|=--._             ',
    '                (        >       .     | ,          `=.__.`-\'\\             ',
    '                 \\.     /        |     |{|              ,-.,\\     .        ',
    '                  |   ,\'          \\   / `\'            ,"     \\            ',
    '                  |  /             |_\'                |  __  /                ',
    '                  | |                                 \'-\'  `-\'   \\.         ',
    '                  |/                                        "    /            ',
    '                  \\.                                            \'           ',
    '                                                                             ',
    '                   ,/           ______._.--._ _..---.---------.              ',
    '__,-----"-..?----_/ )\\    . ,-\'"             "                  (__--/    ',
    '                    /__/\\/                                               '
]

# Precise coordinates mapped directly to the 70x23 ASCII map grid
CITIES = [
    (7, 3, "San Francisco", "SF_NODE"),
    (16, 2, "New York", "NY_GATE"),
    (16, 9, "Sao Paulo", "SP_SRV"),
    (31, 2, "London", "LD_ROUT"),
    (42, 1, "Moscow", "MS_CORE"),
    (38, 5, "Cairo", "CA_FIRE"),
    (30, 10, "Cape Town", "CT_APX"),
    (54, 2, "Beijing", "BJ_MAIN"),
    (61, 2, "Tokyo", "TY_EDGE"),
    (61, 14, "Sydney", "SY_HUB"),
    (46, 4, "Mumbai", "MB_SWIT")
]

# Regional focus ASCII maps for continent zoom mode
REGIONS = {
    "EUROPE": {
        "name": "EUROPE SECURE GRID",
        "map": [
            "       _._     ,          ",
            "     _/   \\___/  `-._     ",
            "    (                \\    ",
            "     \\_   _.,-.__.---'    ",
            "       `-'                "
        ],
        "cities": [
            (2, 2, "London", "LON"),
            (8, 3, "Paris", "PAR"),
            (13, 1, "Berlin", "BER"),
            (12, 4, "Rome", "ROM"),
            (22, 1, "Moscow", "MSW")
        ]
    },
    "ASIA": {
        "name": "EURASIA DEEP FOCUS",
        "map": [
            "          _._.---.-.__    ",
            "       _./            \\   ",
            "      (                /  ",
            "       \\__         _,'    ",
            "          `--.__.-'       "
        ],
        "cities": [
            (1, 1, "Moscow", "MSW"),
            (5, 4, "Mumbai", "BOM"),
            (12, 2, "Beijing", "PEK"),
            (22, 1, "Tokyo", "TOK"),
            (14, 4, "Singapore", "SGP")
        ]
    },
    "NORTH_AMERICA": {
        "name": "N.AMERICA PACIFIC",
        "map": [
            "    . _..::__:  ,-\"-\"._   ",
            "   <_>`!(._`.`-.    /     ",
            "   ==,\\',._\\\\{  \\  /      ",
            "           `._ )`^-.      "
        ],
        "cities": [
            (2, 2, "San Francisco", "SFO"),
            (4, 4, "Los Angeles", "LAX"),
            (12, 1, "Chicago", "ORD"),
            (18, 1, "New York", "JFK"),
            (13, 4, "Austin", "AUS")
        ]
    }
}

THEMES = {
    "matrix": {
        "name": "Matrix Green",
        "border": "\033[32m",        # Green
        "border_bold": "\033[92m",   # Bright Green
        "text": "\033[32m",          # Green
        "accent": "\033[97m",        # White
        "warn": "\033[91m",          # Bright Red
        "success": "\033[92m",       # Bright Green
        "info": "\033[96m",          # Bright Cyan
        "map_land": "\033[32m",      # Green outline
        "map_text": "\033[32m",
        "packet": "\033[97m\033[1m",  # Bright White
        "trail": "\033[92m",         # Bright Green
    },
    "cyberpunk": {
        "name": "Cyberpunk Neon",
        "border": "\033[35m",        # Magenta
        "border_bold": "\033[95m",   # Bright Magenta
        "text": "\033[36m",          # Cyan
        "accent": "\033[95m",        # Bright Magenta
        "warn": "\033[91m",          # Bright Red
        "success": "\033[96m",       # Bright Cyan
        "info": "\033[93m",          # Bright Yellow
        "map_land": "\033[35m",      # Magenta
        "map_text": "\033[35m",
        "packet": "\033[96m\033[1m",  # Bright Cyan
        "trail": "\033[95m",         # Magenta
    },
    "amber": {
        "name": "Fallout Amber",
        "border": "\033[33m",        # Yellow/Amber
        "border_bold": "\033[93m",   # Bright Amber
        "text": "\033[33m",          # Amber
        "accent": "\033[97m",        # White
        "warn": "\033[91m",          # Bright Red
        "success": "\033[93m",       # Bright Amber
        "info": "\033[93m",          # Bright Amber
        "map_land": "\033[33m",      # Amber
        "map_text": "\033[33m",
        "packet": "\033[97m\033[1m",  # Bright White
        "trail": "\033[93m",         # Bright Amber
    },
    "ice": {
        "name": "Subzero Ice",
        "border": "\033[34m",        # Blue
        "border_bold": "\033[94m",   # Bright Blue
        "text": "\033[36m",          # Cyan
        "accent": "\033[97m",        # White
        "warn": "\033[91m",          # Bright Red
        "success": "\033[96m",       # Bright Cyan
        "info": "\033[94m",          # Bright Blue
        "map_land": "\033[34m",      # Blue
        "map_text": "\033[36m",
        "packet": "\033[97m\033[1m",  # Bright White
        "trail": "\033[94m",         # Bright Blue
    }
}

MOCK_CODE = [
    "0x4A00:  55 89 E5 83 EC 18 89 7D  U......}",
    "0x4A08:  FC 8B 45 08 89 44 24 04  ..E..D$.",
    "0x4A10:  C7 04 24 00 00 00 00 E8  ..$.....",
    "0x4A18:  E0 FE FF FF 8B 45 FC C7  .....E..",
    "0x4A20:  40 04 01 00 00 00 C7 40  @......@",
    "0x4A28:  08 00 00 00 00 C9 C3 90  ........",
    "0x4A30:  PUSH EBP",
    "0x4A31:  MOV EBP, ESP",
    "0x4A33:  SUB ESP, 0x40",
    "0x4A36:  MOV DWORD PTR [EBP-0x0C], 0x00",
    "0x4A3D:  CMP DWORD PTR [EBP+0x08], 0x00",
    "0x4A41:  JE 0x4A70",
    "0x4A43:  MOV EAX, DWORD PTR [EBP+0x08]",
    "0x4A46:  MOV EDX, DWORD PTR [EAX]",
    "0x4A48:  MOV DWORD PTR [ESP], EDX",
    "0x4A4B:  CALL 0x4C90 <_decrypt_token>",
    "0x4A50:  TEST EAX, EAX",
    "0x4A52:  JZ 0x4A78",
    "0x4A54:  MOV DWORD PTR [EBP-0x04], 0x01",
    "0x4A5B:  JMP 0x4A80",
    "0x4A5D:  NOP",
    "0x4A5E:  LEAVE",
    "0x4A5F:  RET",
    "SYS_CALL: sys_connect(addr=127.0.0.1)",
    "SYS_CALL: sys_execve('/bin/sh', argv)",
    "SYS_CALL: sys_mprotect(0x7fff000, 4096)",
    "PAYLOAD:  \\x31\\xc0\\x50\\x68\\x2f\\x2f",
    "PAYLOAD:  \\x68\\x2f\\x62\\x69\\x6e\\x89",
    "PAYLOAD:  \\x89\\xe2\\x53\\x89\\xe1\\xb0",
    "HEAP:     [ALLOCATING] 0x0804b000 -> 512b",
    "HEAP:     [FREEING]    0x0804b200 (OK)",
    "SOCKET:   binding to port 31337...",
    "SOCKET:   listening on port 31337...",
    "SOCKET:   incoming connect from 10.0.2.1"
]

FAKE_SHELL_CODE = [
    "/* Initialize kernel stack override */",
    "void mainframe_bypass() {",
    "    int port = 31337;",
    "    char *buffer = malloc(4096);",
    "    if (buffer == NULL) return;",
    "    sys_mprotect(0x7fff000, 4096, PROT_READ|PROT_WRITE|PROT_EXEC);",
    "    memcpy(buffer, payload_bin, sizeof(payload_bin));",
    "    asm(\"jmp *%%rax\" : : \"a\"(buffer));",
    "}",
    "/* Decrypting satellite payload key */",
    "int satellite_decrypt(char *cipher, int len) {",
    "    for (int i = 0; i < len; i++) {",
    "        cipher[i] ^= 0x4A;",
    "        cipher[i] = (cipher[i] >> 3) | (cipher[i] << 5);",
    "    }",
    "    return 1; // Integrity Check Passed",
    "}",
    "/* Establishing socket tunneling bypass */",
    "int sys_connect(char *ip, int port) {",
    "    struct sockaddr_in server;",
    "    int sock = socket(AF_INET, SOCK_STREAM, 0);",
    "    server.sin_addr.s_addr = inet_addr(ip);",
    "    server.sin_family = AF_INET;",
    "    server.sin_port = htons(port);",
    "    connect(sock, (struct sockaddr *)&server, sizeof(server));",
    "    write(sock, \"GET BACKDOOR / HTTP/1.1\\r\\n\\r\\n\", 30);",
    "    return sock;",
    "}",
    "/* Injecting CSS-grid layout matrix overflow */",
    "#define CORE_FLUX_DISSIPATION 1210000000ULL",
    "void trigger_layout_overflow() {",
    "    volatile uint64_t *flux_register = (uint64_t *)0xDEADBEEF;",
    "    *flux_register = CORE_FLUX_DISSIPATION;",
    "    __asm__ __volatile__(\"cli; hlt\");",
    "}",
    "/* Quantum cryptography core stabiliser */",
    "double quantum_stabilise(double density, double entropy) {",
    "    double factor = sin(density * M_PI) + cos(entropy * M_PI);",
    "    return factor * 1.21;",
    "}"
]

CUBE_VERTICES = [
    [-1, -1, -1],
    [1, -1, -1],
    [1, 1, -1],
    [-1, 1, -1],
    [-1, -1, 1],
    [1, -1, 1],
    [1, 1, 1],
    [-1, 1, 1]
]

CUBE_EDGES = [
    (0, 1), (1, 2), (2, 3), (3, 0), # Back face
    (4, 5), (5, 6), (6, 7), (7, 4), # Front face
    (0, 4), (1, 5), (2, 6), (3, 7)  # Connecting edges
]

# Keyboard & Console Setup (Cross-Platform)
try:
    import msvcrt
    WINDOWS = True
    
    def enable_windows_ansi():
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            hOut = kernel32.GetStdHandle(-11)
            if hOut != -1:
                dwMode = ctypes.c_ulong()
                if kernel32.GetConsoleMode(hOut, ctypes.byref(dwMode)):
                    kernel32.SetConsoleMode(hOut, dwMode.value | 0x0004)
            hErr = kernel32.GetStdHandle(-12)
            if hErr != -1:
                dwMode = ctypes.c_ulong()
                if kernel32.GetConsoleMode(hErr, ctypes.byref(dwMode)):
                    kernel32.SetConsoleMode(hErr, dwMode.value | 0x0004)
        except Exception:
            pass
except ImportError:
    WINDOWS = False
    import select
    import termios
    import tty
    
    def enable_windows_ansi():
        pass

# Winsound Audio Setup
try:
    import winsound
    SOUND_ENABLED = True
except ImportError:
    SOUND_ENABLED = False


class AudioEngine:
    def __init__(self):
        # Sound is muted by default (opt-in)
        self.muted = True

    def play_click(self):
        if SOUND_ENABLED and not self.muted:
            try:
                winsound.Beep(1000, 8)
            except Exception:
                pass

    def play_packet(self):
        if SOUND_ENABLED and not self.muted:
            try:
                winsound.Beep(2300, 10)
            except Exception:
                pass

    def play_success(self):
        if SOUND_ENABLED and not self.muted:
            try:
                winsound.Beep(1400, 30)
                winsound.Beep(1800, 30)
            except Exception:
                pass


audio = AudioEngine()
old_settings = None


def init_keyboard():
    global old_settings
    if not WINDOWS:
        try:
            old_settings = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
        except Exception:
            pass


def restore_keyboard():
    if not WINDOWS and old_settings is not None:
        try:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
        except Exception:
            pass


def get_key():
    if WINDOWS:
        if msvcrt.kbhit():
            try:
                ch = msvcrt.getch()
                if ch in (b'\x03', b'\x1b'): # Ctrl+C or ESC
                    return 'q'
                if ch == b'\x08':
                    return 'backspace'
                if ch in (b'\r', b'\n'):
                    return 'enter'
                audio.play_click()
                return ch.decode('utf-8').lower()
            except Exception:
                return None
    else:
        try:
            dr, dw, de = select.select([sys.stdin], [], [], 0)
            if dr:
                ch = sys.stdin.read(1)
                if ch in ('\x03', '\x1b'):
                    return 'q'
                if ch in ('\x7f', '\x08'):
                    return 'backspace'
                if ch in ('\r', '\n'):
                    return 'enter'
                return ch.lower()
        except Exception:
            return None
    return None


class Canvas:
    """A virtual double-buffered screen grid supporting positional color cells."""
    def __init__(self, w, h):
        self.width = w
        self.height = h
        self.grid = [[' ' for _ in range(w)] for _ in range(h)]
        self.colors = [[None for _ in range(w)] for _ in range(h)]

    def clear(self):
        for y in range(self.height):
            for x in range(self.width):
                self.grid[y][x] = ' '
                self.colors[y][x] = None

    def write_char(self, x, y, char, color=None):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.grid[y][x] = char
            self.colors[y][x] = color

    def write_str(self, x, y, s, color=None):
        for i, char in enumerate(s):
            self.write_char(x + i, y, char, color)

    def draw_box(self, x, y, w, h, title="", color=None, style="double"):
        if style == "double":
            tl, tr, bl, br = "╔", "╗", "╚", "╝"
            hl, vl = "═", "║"
        else:
            tl, tr, bl, br = "┌", "┐", "└", "┘"
            hl, vl = "─", "│"

        if w <= 0 or h <= 0:
            return

        self.write_char(x, y, tl, color)
        self.write_char(x + w - 1, y, tr, color)
        self.write_char(x, y + h - 1, bl, color)
        self.write_char(x + w - 1, y + h - 1, br, color)

        for xi in range(x + 1, x + w - 1):
            self.write_char(xi, y, hl, color)
            self.write_char(xi, y + h - 1, hl, color)
        for yi in range(y + 1, y + h - 1):
            self.write_char(x, yi, vl, color)
            self.write_char(x + w - 1, yi, vl, color)

        if title and w > 4:
            padded = f" {title} "
            tx = x + max(1, (w - len(padded)) // 2)
            self.write_str(tx, y, padded[:w-2], color)

    def render(self, offset_x=0, offset_y=0):
        output = []
        if offset_y > 0:
            output.append("\n" * offset_y)
        
        spacing = " " * offset_x
        active_color = None
        
        for y in range(self.height):
            line = [spacing]
            for x in range(self.width):
                char = self.grid[y][x]
                cell_color = self.colors[y][x]
                
                if cell_color != active_color:
                    if cell_color is None:
                        line.append("\033[0m")
                    else:
                        line.append(cell_color)
                    active_color = cell_color
                line.append(char)
                
            if active_color is not None:
                line.append("\033[0m")
                active_color = None
                
            output.append("".join(line))
            
        return "\n".join(output)


def get_line_path(x0, y0, x1, y1):
    points = []
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    
    cx, cy = x0, y0
    while True:
        points.append((cx, cy))
        if cx == x1 and cy == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            cx += sx
        if e2 < dx:
            err += dx
            cy += sy
    return points


class AttackVector:
    def __init__(self, src, dst, theme_palette):
        self.src_city = src
        self.dst_city = dst
        self.src_x, self.src_y = src[0], src[1]
        self.dst_x, self.dst_y = dst[0], dst[1]
        self.path = get_line_path(self.src_x, self.src_y, self.dst_x, self.dst_y)
        self.progress = 0.0
        self.speed = 1.0 / max(10, len(self.path))
        self.trail_len = 5
        self.palette = theme_palette
        self.complete = False
        self.explosion_frame = -1

    def update(self):
        if not self.complete:
            if self.explosion_frame == -1:
                self.progress += self.speed
                if self.progress >= 1.0:
                    self.progress = 1.0
                    self.explosion_frame = 0
                    audio.play_success()
            else:
                self.explosion_frame += 1
                if self.explosion_frame > 5:
                    self.complete = True

    def draw(self, canvas, base_x, base_y, crop_left=0, crop_top=0, max_w=999, max_h=999):
        if self.complete:
            return
        
        path_idx = int(self.progress * (len(self.path) - 1))
        
        if self.explosion_frame == -1:
            for i in range(max(0, path_idx - self.trail_len), path_idx):
                px, py = self.path[i]
                cx = base_x + (px - crop_left)
                cy = base_y + (py - crop_top)
                if base_x <= cx < base_x + max_w and base_y <= cy < base_y + max_h:
                    canvas.write_char(cx, cy, "·", self.palette["trail"])
            px, py = self.path[path_idx]
            cx = base_x + (px - crop_left)
            cy = base_y + (py - crop_top)
            if base_x <= cx < base_x + max_w and base_y <= cy < base_y + max_h:
                canvas.write_char(cx, cy, "●", self.palette["packet"])
        else:
            ex, ey = self.dst_x, self.dst_y
            cx = base_x + (ex - crop_left)
            cy = base_y + (ey - crop_top)
            
            if base_x <= cx < base_x + max_w and base_y <= cy < base_y + max_h:
                ripple_chars = ["*", "○", "☼", "( )", " . "]
                if self.explosion_frame < len(ripple_chars):
                    char = ripple_chars[self.explosion_frame]
                    color = self.palette["warn"] if self.explosion_frame % 2 == 0 else self.palette["success"]
                    if len(char) == 1:
                        canvas.write_char(cx, cy, char, color)
                    else:
                        canvas.write_str(cx - len(char)//2, cy, char, color)


class LocalAttackVector:
    def __init__(self, src, dst, theme_palette):
        self.src_city = src
        self.dst_city = dst
        self.src_x, self.src_y = src[0], src[1]
        self.dst_x, self.dst_y = dst[0], dst[1]
        self.path = get_line_path(self.src_x, self.src_y, self.dst_x, self.dst_y)
        self.progress = 0.0
        self.speed = 1.0 / max(5, len(self.path))
        self.trail_len = 3
        self.palette = theme_palette
        self.complete = False
        self.explosion_frame = -1

    def update(self):
        if not self.complete:
            if self.explosion_frame == -1:
                self.progress += self.speed
                if self.progress >= 1.0:
                    self.progress = 1.0
                    self.explosion_frame = 0
            else:
                self.explosion_frame += 1
                if self.explosion_frame > 3:
                    self.complete = True

    def draw(self, canvas, base_x, base_y, max_w, max_h):
        if self.complete:
            return
        
        path_idx = int(self.progress * (len(self.path) - 1))
        
        if self.explosion_frame == -1:
            for i in range(max(0, path_idx - self.trail_len), path_idx):
                px, py = self.path[i]
                cx = base_x + px
                cy = base_y + py
                if base_x <= cx < base_x + max_w and base_y <= cy < base_y + max_h:
                    canvas.write_char(cx, cy, "·", self.palette["trail"])
            px, py = self.path[path_idx]
            cx = base_x + px
            cy = base_y + py
            if base_x <= cx < base_x + max_w and base_y <= cy < base_y + max_h:
                canvas.write_char(cx, cy, "●", self.palette["packet"])
        else:
            ex, ey = self.dst_x, self.dst_y
            cx = base_x + ex
            cy = base_y + ey
            if base_x <= cx < base_x + max_w and base_y <= cy < base_y + max_h:
                ripple_chars = ["*", "○", "•"]
                if self.explosion_frame < len(ripple_chars):
                    char = ripple_chars[self.explosion_frame]
                    canvas.write_char(cx, cy, char, self.palette["warn"])


class PortScanner:
    def __init__(self, theme_palette):
        self.palette = theme_palette
        self.ips = ["192.168.1.42", "10.0.0.138", "172.16.0.5", "10.0.2.15", "185.190.140.4", "203.0.113.195"]
        self.ports = [21, 22, 80, 443, 8080, 31337]
        self.history = []
        self.timer = 0

    def update(self, speed_mult):
        self.timer += 1 * speed_mult
        if self.timer >= 6:
            self.timer = 0
            ip = random.choice(self.ips)
            port = random.choice(self.ports)
            status = random.choice(["CLOSED", "CLOSED", "OPEN", "FILTERED"])
            cur_time = time.strftime("%H:%M:%S")
            self.history.append((cur_time, ip, port, status))
            if len(self.history) > 50:
                self.history.pop(0)

    def draw(self, canvas, start_x, start_y, max_w, max_h):
        canvas.write_str(start_x, start_y, "SUBNET SWEEPER INTERCEPTS:", self.palette["info"])
        inside_h = max_h - 1
        start_idx = max(0, len(self.history) - inside_h)
        for idx, i in enumerate(range(start_idx, len(self.history))):
            t, ip, p, stat = self.history[i]
            color = self.palette["text"]
            if stat == "OPEN":
                color = self.palette["success"]
            elif stat == "FILTERED":
                color = self.palette["warn"]
            
            line = f"[{t}] {ip}:{p} -> {stat}"
            canvas.write_str(start_x, start_y + 1 + idx, line[:max_w-2].ljust(max_w-2), color)


class ScrollingCrackEngine:
    """Simulates a fully scrolling history of password cracking attempts that can succeed or fail."""
    def __init__(self, theme_palette):
        self.palette = theme_palette
        self.targets = [
            "ROOT_ACCESS.KEY", "MAIN_FIREWALL.CFG", "CORP_DATABASE.SQL", 
            "SATELLITE_LINK.KEY", "ADMIN_SHELL.EXE", "DEFENSE_MAIN.BAK"
        ]
        self.history = []
        
        # Current active crack
        self.active_target = self.targets[0]
        self.active_cipher = "AES-256"
        self.active_progress = 0.0
        # Random speed multiplier per target
        self.active_speed = random.uniform(0.015, 0.04) 

    def update(self, speed_mult):
        self.active_progress += self.active_speed * speed_mult
        if self.active_progress >= 1.0:
            self.active_progress = 1.0
            
            # Determine outcome (80% Success, 20% Fail)
            success = random.random() < 0.8
            cur_time = time.strftime("%H:%M:%S")
            
            if success:
                outcome = f"[{cur_time}] SUCCESS: {self.active_target} cracked (Locked: " + "".join(random.choices(string.ascii_uppercase + string.digits, k=6)) + ")"
                color_key = "success"
                audio.play_success()
            else:
                reasons = ["AUTH_TIMEOUT", "INTEGRITY_ERR", "HASH_MISMATCH"]
                outcome = f"[{cur_time}] FAILED: {self.active_target} ({random.choice(reasons)})"
                color_key = "warn"
            
            self.history.append((outcome, color_key))
            if len(self.history) > 15:
                self.history.pop(0)
                
            # Load new target
            self.active_target = random.choice(self.targets)
            self.active_cipher = random.choice(["RSA-4096", "AES-GCM", "ChaCha20", "Blowfish", "ECC-384"])
            self.active_progress = 0.0
            self.active_speed = random.uniform(0.012, 0.035)

    def draw(self, canvas, start_x, start_y, max_w, max_h):
        # 1. Historical crack scrolls
        scroll_rows = max_h - 4
        canvas.write_str(start_x, start_y, "DECRYPTER HISTORY DATABASE:", self.palette["info"])
        
        start_idx = max(0, len(self.history) - scroll_rows)
        for idx, i in enumerate(range(start_idx, len(self.history))):
            text, status = self.history[i]
            color = self.palette["success"] if status == "success" else self.palette["warn"]
            canvas.write_str(start_x, start_y + 1 + idx, text[:max_w-2].ljust(max_w-2), color)

        # 2. Live active crack widget
        active_y = start_y + max_h - 3
        if active_y > start_y + 1:
            canvas.write_str(start_x, active_y, f"DECRYPTING: {self.active_target} ({self.active_cipher})", self.palette["accent"])
            
            bar_w = max(5, max_w - 9)
            filled = int(self.active_progress * bar_w)
            bar_str = "█" * filled + "░" * (bar_w - filled)
            canvas.write_str(start_x, active_y + 1, bar_str, self.palette["success"])
            canvas.write_str(start_x + bar_w + 1, active_y + 1, f"{int(self.active_progress*100):3d}%", self.palette["accent"])


def rotate_x(x, y, z, angle):
    rad = math.radians(angle)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    return x, y * cos_a - z * sin_a, y * sin_a + z * cos_a


def rotate_y(x, y, z, angle):
    rad = math.radians(angle)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    return x * cos_a + z * sin_a, y, -x * sin_a + z * cos_a


def rotate_z(x, y, z, angle):
    rad = math.radians(angle)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    return x * cos_a - y * sin_a, x * sin_a + y * cos_a, z


class CyberMonitor:
    def __init__(self, initial_theme=None, initial_sound=False, initial_speed=1.0):
        # Load theme from config file, fallback to Fallout Amber
        config = load_config()
        self.theme_key = initial_theme if initial_theme else config.get("theme", "amber")
        if self.theme_key not in THEMES:
            self.theme_key = "amber"
            
        self.palette = THEMES[self.theme_key]
        self.canvas = Canvas(100, 35)
        self.attacks = []
        self.attack_cooldown = 0
        self.threat_logs = []
        self.code_stream = []
        self.port_scanner = PortScanner(self.palette)
        self.crack_engine = ScrollingCrackEngine(self.palette)
        self.signal_heights = []
        self.boot_time = time.time()
        self.helix_tick = 0.0 # Time tick for double helix animation!
        self.slow_tick = 0 # Slow ticker for metrics walk
        
        # Slow-moving, smoothly fluctuating metrics
        self.metrics = {
            "CPU0": 45.0,
            "CPU1": 60.0,
            "CPU2": 35.0,
            "CPU3": 50.0,
            "CPU4": 25.0,
            "CPU5": 65.0,
            "CPU6": 55.0,
            "CPU7": 40.0,
            "RAM": 72.0,
            "NET": 15.0,
            "DISK": 81.0,
            "TEMP": 52.0,
            "GPU": 42.0,
            "BUFF": 21.0
        }
        
        # Expanding active socket connection tunnels!
        self.sockets = [
            ("10.0.2.15:4444", "198.51.100.42:http ", "ESTABLISHED", 14.2, 88.4, 0), # (l_ip, r_ip, stat, tx, rx, new_tag_timer)
            ("10.0.2.15:53  ", "8.8.8.8:domain      ", "CONNECTED  ", 1.8, 4.2, 0),
            ("127.0.0.1:31337", "[PORT SWEEPER]    ", "LISTENING  ", 0.0, 0.0, 0)
        ]

        self.paused = False
        self.speed_multiplier = initial_speed
        self.log_timer = 0
        self.code_timer = 0

        # Initialize audio engine state based on initial sound argument
        audio.muted = not initial_sound

        # Interactive / Absurdity States
        self.active_mode = "dashboard"  # "dashboard", "shell", "breach"
        self.hacker_intensity = 0.0
        self.shell_input = ""
        self.shell_history = []
        self.shell_type_index = 0
        self.breach_time_left = 10.0
        self.breach_taps = 0

        # Continent focus mode configuration
        self.continent_mode_active = False
        self.continent_mode_duration = 0
        self.continent_cooldown = random.randint(15 * 16, 30 * 16)
        self.current_continent = None
        self.local_attacks = []

        # Prepopulate scroll lists
        for _ in range(35):
            self.generate_threat_log(init=True)
        for _ in range(35):
            self.scroll_code()
        for _ in range(8):
            self.crack_engine.update(10.0)

    def toggle_theme(self):
        themes = list(THEMES.keys())
        current_idx = themes.index(self.theme_key)
        self.theme_key = themes[(current_idx + 1) % len(themes)]
        self.palette = THEMES[self.theme_key]
        self.port_scanner.palette = self.palette
        self.crack_engine.palette = self.palette
        save_config(self.theme_key) # Persist selection

    def toggle_sound(self):
        audio.muted = not audio.muted
        cur_time = time.strftime("%H:%M:%S")
        if audio.muted:
            self.threat_logs.append((f"[{cur_time}] [AUDIO] Chimes MUTED", "warn"))
        else:
            self.threat_logs.append((f"[{cur_time}] [AUDIO] Chimes ENABLED", "success"))
            audio.play_success()

    def generate_threat_log(self, init=False):
        ips = [
            "104.244.42.1", "192.168.1.105", "10.0.2.15", "8.8.8.8",
            "45.22.189.12", "172.16.0.42", "203.0.113.195", "198.51.100.4"
        ]
        ports = ["22", "80", "443", "8080", "31337", "21"]
        threats = [
            ("DDoS ATTACK IN PROGRESS -> {ip} (Port {port})", "warn"),
            ("PORT SCAN DETECTED on {ip}", "info"),
            ("SQL INJECTION ATTEMPT blocked from {ip}", "warn"),
            ("MALWARE BEACON detected on proxy {ip}", "warn"),
            ("OVERRIDE INJECT: Node {shorthand} auth bypassed", "success"),
            ("SYS_HANDSHAKE: key decrypted for node {shorthand}", "success"),
            ("BUFFER OVERFLOW payload deployed to {shorthand}", "success"),
            ("PING SWEEP scanning gateway subnet", "info"),
            ("EXFIL DATASTREAM initiated to remote {ip}", "info"),
            ("FIREWALL BYPASS verified: routing through {shorthand}", "success"),
            ("[WARNING] Hacker identified as typing on two keyboards simultaneously!", "warn"),
            ("[ALERT] Firewall bypassed using HTML parsing via regular expressions!", "warn"),
            ("[NOTICE] External IP trying to download more physical RAM from secure subnet.", "info"),
            ("[SYSTEM] Bypassing gateway security using butterflies (xkcd 378)", "success"),
            ("[DANGER] Flux capacitor core temperature exceeding 1.21 Gigawatts!", "warn"),
            ("[EXPLOIT] Cyber-nanites detected in the liquid cooling pipeline!", "warn"),
            ("[OVERRIDE] Proxy tunnel breached via CSS grid layout manipulation.", "success")
        ]
        
        cur_time = time.strftime("%H:%M:%S")
        ip = random.choice(ips)
        port = random.choice(ports)
        shorthand = random.choice(CITIES)[3]
        
        fmt, status = random.choice(threats)
        msg = fmt.format(ip=ip, port=port, shorthand=shorthand)
        
        log_entry = (f"[{cur_time}] {msg}", status)
        self.threat_logs.append(log_entry)
        if len(self.threat_logs) > 60:
            self.threat_logs.pop(0)

    def scroll_code(self):
        new_line = random.choice(MOCK_CODE)
        self.code_stream.append(new_line)
        if len(self.code_stream) > 60:
            self.code_stream.pop(0)

    def trigger_attack(self):
        src, dst = random.sample(CITIES, 2)
        cur_time = time.strftime("%H:%M:%S")
        self.threat_logs.append((
            f"[{cur_time}] [ATTACK LAUNCHED] {src[2]} ({src[3]}) => {dst[2]} ({dst[3]})", 
            "info"
        ))
        vector = AttackVector(src, dst, self.palette)
        self.attacks.append(vector)
        audio.play_packet()

    def update(self):
        if self.paused:
            return

        # Decay hacker intensity field
        self.hacker_intensity = max(0.0, self.hacker_intensity - 0.15)

        # Handle emergency countdown in breach mode
        if self.active_mode == "breach":
            self.breach_time_left -= 0.06
            if self.breach_time_left <= 0:
                self.breach_time_left = 0
                trigger_meltdown(self.canvas.width, self.canvas.height)

        # Increment helix ticks for 3D rotation
        self.helix_tick += 0.25 * self.speed_multiplier

        # Update attack vectors
        for attack in self.attacks[:]:
            attack.update()
            if attack.complete:
                cur_time = time.strftime("%H:%M:%S")
                outcome = random.choice([
                    (f"[{cur_time}] [BREACH] Connection established at {attack.dst_city[2]} ({attack.dst_city[3]})", "success"),
                    (f"[{cur_time}] [BREACH] Node payload successfully executed at {attack.dst_city[2]}", "success"),
                    (f"[{cur_time}] [DEFENSE] Attack intercepted by firewall at {attack.dst_city[2]}", "warn")
                ])
                self.threat_logs.append(outcome)
                self.attacks.remove(attack)

        # Automated concurrent map attacks
        if len(self.attacks) < 4:
            if self.attack_cooldown <= 0:
                self.trigger_attack()
                self.attack_cooldown = random.randint(15, 35)
            else:
                self.attack_cooldown -= 1 * self.speed_multiplier
        else:
            self.attack_cooldown = random.randint(20, 50)

        # Update scrolling password decrypter
        self.crack_engine.update(self.speed_multiplier)

        # Update live port sweeper
        self.port_scanner.update(self.speed_multiplier)

        # Update socket channel transfer stats and new-tag timers
        for i in range(len(self.sockets)):
            l_ip, r_ip, stat, tx, rx, timer = self.sockets[i]
            if timer > 0:
                timer = max(0, timer - 1)
            if "ESTABLISHED" in stat or "CONNECTED" in stat:
                tx = max(0.1, tx + random.uniform(-1.0, 1.0))
                rx = max(0.1, rx + random.uniform(-3.0, 3.0))
            self.sockets[i] = (l_ip, r_ip, stat, tx, rx, timer)

        # Actively expanding established socket connection tunnels!
        if random.random() < 0.08:
            socket_ips = ["192.168.1.42", "10.0.0.138", "172.16.0.5", "10.0.2.15", "185.190.140.4", "203.0.113.195"]
            socket_ip = random.choice(socket_ips)
            socket_port = random.choice([21, 22, 80, 443, 8080, 31337])
            
            # Formulate new established socket with green blinking [NEW] tag active for 30 ticks
            new_socket = (
                f"10.0.2.15:{random.randint(1024, 9999)}",
                f"{socket_ip}:{socket_port}".ljust(18),
                "ESTABLISHED",
                random.uniform(0.5, 8.0),
                random.uniform(1.0, 35.0),
                30 # 30 ticks timer for [NEW] tag
            )
            
            cur_time = time.strftime("%H:%M:%S")
            self.threat_logs.append((f"[{cur_time}] [NETWORK] NEW CHANNEL TUNNEL OPENED: {new_socket[0]} -> {new_socket[1].strip()}", "success"))
            
            self.sockets.append(new_socket)
            if len(self.sockets) > 50:
                # Mark oldest socket as closed/disconnecting before removing it
                self.sockets.pop(0)

        # Slow-moving walk for Hardware loads and thermals (move slower)
        self.slow_tick += 1
        if self.slow_tick >= 3:
            self.slow_tick = 0
            for key in self.metrics:
                if key == "TEMP":
                    self.metrics[key] = max(40.0, min(95.0, self.metrics[key] + random.uniform(-0.5, 0.5)))
                else:
                    self.metrics[key] = max(10.0, min(98.0, self.metrics[key] + random.uniform(-1.0, 1.0)))

        # Update threat logs periodically
        self.log_timer += 1 * self.speed_multiplier
        if self.log_timer >= 12:
            self.generate_threat_log()
            self.log_timer = 0

        # Update code streaming periodically
        self.code_timer += 1 * self.speed_multiplier
        if self.code_timer >= 2:
            self.scroll_code()
            self.code_timer = 0

        # Update regional continent focus mode
        if self.continent_mode_active:
            self.continent_mode_duration -= 1 * self.speed_multiplier
            if self.continent_mode_duration <= 0:
                self.continent_mode_active = False
                self.continent_cooldown = random.randint(15 * 16, 30 * 16)
                self.local_attacks = []
                cur_time = time.strftime("%H:%M:%S")
                self.threat_logs.append((f"[{cur_time}] [REGION] FOCUS RESTORED TO WORLD MAP", "success"))
            else:
                # Update local attack vectors
                for attack in self.local_attacks[:]:
                    attack.update()
                    if attack.complete:
                        self.local_attacks.remove(attack)
                
                # Spawn local attack vectors
                if len(self.local_attacks) < 3 and random.random() < 0.15:
                    region_data = REGIONS[self.current_continent]
                    if len(region_data["cities"]) >= 2:
                        src, dst = random.sample(region_data["cities"], 2)
                        vector = LocalAttackVector(src, dst, self.palette)
                        self.local_attacks.append(vector)
        else:
            self.continent_cooldown -= 1 * self.speed_multiplier
            if self.continent_cooldown <= 0:
                self.continent_mode_active = True
                self.continent_mode_duration = 10 * 16 # 10 seconds focus
                self.current_continent = random.choice(list(REGIONS.keys()))
                self.local_attacks = []
                
                # Pre-spawn 1 or 2 attacks
                region_data = REGIONS[self.current_continent]
                if len(region_data["cities"]) >= 2:
                    for _ in range(random.randint(1, 2)):
                        src, dst = random.sample(region_data["cities"], 2)
                        vector = LocalAttackVector(src, dst, self.palette)
                        self.local_attacks.append(vector)
                
                cur_time = time.strftime("%H:%M:%S")
                self.threat_logs.append((f"[{cur_time}] [REGION] FOCUS DEPLOYED: ZOOM ON {self.current_continent}", "warn"))


    def draw_junctions(self, W, split_x1, split_x2_1, split_x2_2, split_x3_1, split_x3_2, top_h, mid_h, H):
        """Draws junction overrides to blend all eight dynamic responsive grid frames nicely."""
        # Top divider intersections (y=2)
        self.canvas.write_char(0, 2, "╠", self.palette["border"])
        self.canvas.write_char(split_x1, 2, "╦", self.palette["border"])
        self.canvas.write_char(W - 1, 2, "╣", self.palette["border"])
        
        # Row 1 divider intersections (y = 2 + top_h)
        mid_y1 = 2 + top_h
        self.canvas.write_char(0, mid_y1, "╠", self.palette["border"])
        self.canvas.write_char(split_x1, mid_y1, "╩", self.palette["border"])
        self.canvas.write_char(split_x2_1, mid_y1, "╦", self.palette["border"])
        self.canvas.write_char(split_x2_2, mid_y1, "╦", self.palette["border"])
        self.canvas.write_char(W - 1, mid_y1, "╣", self.palette["border"])

        # Row 2 divider intersections (y = 2 + top_h + mid_h)
        mid_y2 = 2 + top_h + mid_h
        self.canvas.write_char(0, mid_y2, "╠", self.palette["border"])
        self.canvas.write_char(split_x2_1, mid_y2, "╩", self.palette["border"])
        self.canvas.write_char(split_x2_2, mid_y2, "╩", self.palette["border"])
        self.canvas.write_char(split_x3_1, mid_y2, "╦", self.palette["border"])
        self.canvas.write_char(split_x3_2, mid_y2, "╦", self.palette["border"])
        self.canvas.write_char(W - 1, mid_y2, "╣", self.palette["border"])

        # Bottom divider intersections (y = H - 1)
        self.canvas.write_char(0, H - 1, "╚", self.palette["border"])
        self.canvas.write_char(split_x3_1, H - 1, "╩", self.palette["border"])
        self.canvas.write_char(split_x3_2, H - 1, "╩", self.palette["border"])
        self.canvas.write_char(W - 1, H - 1, "╝", self.palette["border"])

    def draw_spectrum_analyzer(self, start_x, start_y, max_w):
        """Draws dynamic live pulsing waveform frequency analyzer."""
        self.canvas.write_str(start_x, start_y, "CYBER FREQ SPECTRUM:", self.palette["info"])
        bar_chars = [" ", " ", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
        
        analyzer_w = max_w - 4
        
        if len(self.signal_heights) != analyzer_w:
            self.signal_heights = [random.randint(0, 8) for _ in range(analyzer_w)]
        else:
            self.signal_heights.pop(0)
            prev = self.signal_heights[-1]
            next_val = max(0, min(8, prev + random.choice([-1, 0, 1])))
            self.signal_heights.append(next_val)
            
        for i in range(analyzer_w):
            h = self.signal_heights[i]
            self.canvas.write_char(start_x + i, start_y + 1, bar_chars[h], self.palette["accent"])

    def draw_dna_decrypter(self, start_x, start_y, max_w, max_h):
        """Over-the-top Hollywood spinning 3D double-helix biometric override decrypter!"""
        if max_w >= 24:
            self.canvas.write_str(start_x + 1, start_y - 1, " BIOMETRIC DNA OVERRIDE ", self.palette["warn"])
        
        inside_w = max_w
        inside_h = max_h
        
        center_x = start_x + (inside_w // 2)
        amplitude = min(12, (inside_w - 6) // 2)
        freq = 0.5
        
        base_pairs = [("A", "T"), ("G", "C"), ("C", "G"), ("T", "A")]
        
        for y in range(inside_h):
            cy = start_y + y
            # Sine wave offsets for left/right strands
            x_offset = amplitude * math.sin(y * freq + self.helix_tick)
            
            lx = int(center_x + x_offset)
            rx = int(center_x - x_offset)
            
            # Cosine offset to determine 3D depth layer
            depth = math.cos(y * freq + self.helix_tick)
            
            # Left strand style (front = bold/bright, back = dim)
            left_char = "●" if depth > 0 else "·"
            left_color = self.palette["success"] if depth > 0 else self.palette["map_land"]
            
            # Right strand style (opposite layer)
            right_char = "·" if depth > 0 else "●"
            right_color = self.palette["map_land"] if depth > 0 else self.palette["success"]
            
            # Draw horizontal bonds connecting strands every 2 lines
            if y % 2 == 0:
                bx_start = min(lx, rx)
                bx_end = max(lx, rx)
                for bx in range(bx_start + 1, bx_end):
                    self.canvas.write_char(bx, cy, "═", self.palette["border"])
                
                # Overlay matching base pairs (A-T, G-C) in the exact center!
                if bx_end - bx_start > 5:
                    pair = base_pairs[(y + int(self.helix_tick)) % len(base_pairs)]
                    pair_str = f"{pair[0]}═{pair[1]}"
                    px = bx_start + (bx_end - bx_start - 3) // 2
                    self.canvas.write_str(px, cy, pair_str, self.palette["accent"])
            
            # Write strands overlaying the bonds
            self.canvas.write_char(lx, cy, left_char, left_color)
            self.canvas.write_char(rx, cy, right_char, right_color)
            
        # Hollywood status banners!
        if inside_w >= 20:
            dec_status = "GENOME CODE DECRYPTION ACTIVE..." if int(self.helix_tick * 2) % 2 == 0 else ">>> BIOMETRIC MATCH IN PROGRESS <<<"
        else:
            dec_status = "DECRYPTING..." if int(self.helix_tick * 2) % 2 == 0 else "MATCHING..."
        self.canvas.write_str(start_x + 1, start_y + inside_h - 1, dec_status[:inside_w-2], self.palette["warn"])

    def draw_3d_cube(self, start_x, start_y, max_w, max_h):
        """Draw a live, mathematically projected rotating 3D wireframe cube."""
        self.canvas.write_str(start_x, start_y, "QUANTUM VECTOR STACK (3D):", self.palette["info"])
        
        # Center coordinates
        cx = start_x + (max_w // 2)
        cy = start_y + (max_h // 2)
        
        # Sizing and scaling calculations
        scale = min(max_w, max_h * 2) * 0.45
        angle = self.helix_tick * 7.0
        
        projected = []
        for vx, vy, vz in CUBE_VERTICES:
            # Multi-axis coordinate rotation
            rx, ry, rz = rotate_x(vx, vy, vz, angle)
            rx, ry, rz = rotate_y(rx, ry, rz, angle * 1.3)
            rx, ry, rz = rotate_z(rx, ry, rz, angle * 0.6)
            
            # Perspective projection mathematics
            d = 3.2
            factor = scale / (rz + d)
            px = int(cx + rx * factor)
            py = int(cy + ry * factor * 0.5)  # Squish vertically to correct console cell aspect ratio
            projected.append((px, py))
            
        # Draw edges using Bresenham lines
        for e1, e2 in CUBE_EDGES:
            p1 = projected[e1]
            p2 = projected[e2]
            path = get_line_path(p1[0], p1[1], p2[0], p2[1])
            for lx, ly in path:
                if start_x < lx < start_x + max_w - 1 and start_y < ly < start_y + max_h:
                    self.canvas.write_char(lx, ly, "#", self.palette["success"])
                    
        # Render vertex nodes in bright accent colors
        for px, py in projected:
            if start_x < px < start_x + max_w - 1 and start_y < py < start_y + max_h:
                self.canvas.write_char(px, py, "●", self.palette["packet"])

    def process_shell_command(self, cmd):
        """Processes fake shell prompt inputs inside Direct Gibson Override shell."""
        cmd = cmd.strip().lower()
        if not cmd:
            return
            
        if cmd == "help":
            self.shell_history.append("Available Direct Gibson Overrides:")
            self.shell_history.append("  enhance         - Trigger pixel enhancement matrix")
            self.shell_history.append("  ddos-localhost  - Initiate loopback stress simulation")
            self.shell_history.append("  nuke-gibson     - Force critical mainframe breach")
            self.shell_history.append("  exit            - Return to visual security dashboard")
        elif cmd == "exit":
            self.active_mode = "dashboard"
        elif cmd == "enhance":
            self.shell_history.append("[SYSTEM] Initiating pixel enhancement matrix...")
            self.shell_history.append("[DATABASE] Resolving CCTV coordinates 37.7749,-122.4194...")
            self.shell_history.append("[ENGINE] Enhance. Enhance. Enhance.")
            self.shell_history.append("Compilation successful. Magnifying target...")
            self.shell_history.append("      .-.")
            self.shell_history.append("     (   )")
            self.shell_history.append("      `-' \\")
            self.shell_history.append("           \\")
            self.shell_history.append("            \\")
            self.shell_history.append("[SUCCESS] 4K IMAGE COMPILATION COMPLETE! TARGET CONFIRMED.")
        elif cmd == "ddos-localhost":
            self.shell_history.append("[PING] Flooding 127.0.0.1 with 65535 bytes of raw sarcasm...")
            self.shell_history.append("[PING] Loopback routing resolved.")
            self.shell_history.append("[ALERT] Localhost is attacking itself!")
            self.shell_history.append("[FIREWALL] Mainframe locked itself out in confusion!")
            self.shell_history.append("[FAIL] System self-mitigated via local firewall panic.")
        elif cmd == "nuke-gibson":
            self.active_mode = "breach"
            self.breach_time_left = 10.0
            self.breach_taps = 0
        else:
            self.shell_history.append(f"Error: Command '{cmd}' unrecognized by root supervisor.")
            self.shell_history.append("Type 'help' to see list of valid bypasses.")

    def draw_shell_screen(self):
        """Renders fully interactive, retro Hollywood Hacker shell console."""
        self.canvas.clear()
        W = self.canvas.width
        H = self.canvas.height
        
        self.canvas.draw_box(0, 0, W, H, " GIBSON DIRECT BACKDOOR OVERRIDE SHELL ", self.palette["border_bold"])
        
        # Display history scrolling lines
        max_rows = H - 5
        visible_lines = self.shell_history[-max_rows:]
        for idx, line in enumerate(visible_lines):
            self.canvas.write_str(2, 2 + idx, line[:W-4], self.palette["success"])
            
        # Draw current input prompt at the bottom
        prompt = f"root@gibson-mainframe:~# {self.shell_input}█"
        self.canvas.write_str(2, H - 2, prompt[:W-4], self.palette["accent"])

    def draw_breach_screen(self):
        """Renders high-intensity emergency Gibson Breach manual stabilization console."""
        self.canvas.clear()
        W = self.canvas.width
        H = self.canvas.height
        
        # Rapid flashing border between bright warning red and black
        blink_color = self.palette["warn"] if int(time.time() * 8) % 2 == 0 else "\033[30m"
        
        # Center panel
        box_w = 66
        box_h = 13
        bx = (W - box_w) // 2
        by = (H - box_h) // 2
        
        # Fill whole canvas with low-intensity noise to highlight breach danger
        for y in range(H):
            for x in range(W):
                if random.random() < 0.04:
                    self.canvas.write_char(x, y, random.choice(["!", "@", "#", "$", "%", "?", "*"]), "\033[31m")
        
        self.canvas.draw_box(bx, by, box_w, box_h, " !!! SYSTEM CRITICAL MELTDOWN WARNING !!! ", blink_color)
        
        self.canvas.write_str(bx + 4, by + 2, "GIBSON MAINFRAME BREACH IN PROGRESS - SYSTEM INJECT DETECTED", self.palette["warn"])
        self.canvas.write_str(bx + 4, by + 4, f"CORE FLUX OVERFLOW IN:  [ {self.breach_time_left:5.2f}s ]", self.palette["accent"])
        self.canvas.write_str(bx + 4, by + 5, "FLUX CORE DISSIPATION:  1.21 GW CRITICAL FLUX LIQUID LEAK", self.palette["warn"])
        
        # Taps stabilization bar
        bar_w = 38
        filled_taps = int(self.breach_taps * bar_w / 15)
        bar_str = "█" * filled_taps + "░" * (bar_w - filled_taps)
        self.canvas.write_str(bx + 4, by + 7, f"OVERRIDE PROGRESS: [ {bar_str} ] {self.breach_taps}/15 TAPS", self.palette["success"])
        self.canvas.write_str(bx + 4, by + 9, "SLAM KEYBOARD KEYS REPEATEDLY TO DISSIPATE CAPACITOR ENERGY", self.palette["accent"])
        self.canvas.write_str(bx + 4, by + 10, "[OR PRESS 'ESC' to abort and accept mainframe destruction]", "\033[2m")

        # Flashing red border over the screen
        self.canvas.draw_box(0, 0, W, H, " MAINFRAME MELTDOWN MODE ", blink_color)

    def draw(self):
        # Delegate rendering if in non-dashboard modes
        if self.active_mode == "shell":
            self.draw_shell_screen()
            return
        elif self.active_mode == "breach":
            self.draw_breach_screen()
            return

        self.canvas.clear()
        W = self.canvas.width
        H = self.canvas.height

        # Calculate dynamic responsive three-row layout splits (utilizing 100% of vertical screen!)
        rem_h = H - 3
        top_h = int(rem_h * 0.44)
        mid_h = int(rem_h * 0.28)
        bottom_h = rem_h - top_h - mid_h

        # Horizontal splits per row
        split_x1 = max(55, int(W * 0.64))   # Top Row (smaller map box!)
        split_x2_1 = max(30, int(W * 0.35)) # Middle Row Split 1
        split_x2_2 = max(60, int(W * 0.70)) # Middle Row Split 2
        split_x3_1 = max(35, int(W * 0.38)) # Bottom Row Split 1
        split_x3_2 = max(65, int(W * 0.70)) # Bottom Row Split 2

        mid_y1 = 2 + top_h
        mid_y2 = 2 + top_h + mid_h

        # 1. Header Pane (Title & Globals)
        self.canvas.draw_box(0, 0, W, 3, f"{APP_NAME.upper()} v{APP_VERSION}", self.palette["border_bold"])
        status_text = "[SYS STATUS: SECURE]" if len(self.attacks) == 0 else "[SYS STATUS: ACTIVE_INTRUSIONS]"
        status_color = self.palette["success"] if len(self.attacks) == 0 else self.palette["warn"]
        self.canvas.write_str(2, 1, status_text, status_color)
        
        theme_info = f"[THEME: {self.palette['name'].upper()}]"
        self.canvas.write_str(split_x2_1 - 10, 1, theme_info, self.palette["info"])
        
        sound_status = "[CHIMES: MUTED]" if audio.muted else "[CHIMES: ENABLED]"
        sound_color = self.palette["warn"] if audio.muted else self.palette["success"]
        self.canvas.write_str(split_x2_2 - 14, 1, sound_status, sound_color)

        time_str = f"[MATRIX_TIME: {time.strftime('%Y-%m-%d %H:%M:%S')}]"
        # Dynamic placement to eliminate far-right border and text clipping
        self.canvas.write_str(W - len(time_str) - 2, 1, time_str, self.palette["accent"])


        # 2. PANEL 1: Cyber Threat Map Panel (Top Left)
        self.canvas.draw_box(0, 2, split_x1 + 1, top_h + 1, "CYBER MAP THREAT TARGETS", self.palette["border"])
        
        map_inside_w = split_x1 - 1
        map_inside_h = top_h - 1

        # Centering & bounds-safe cropping calculation
        if map_inside_w >= 70:
            map_x_offset = 1 + (map_inside_w - 70) // 2
            crop_left = 0
            draw_w = 70
        else:
            map_x_offset = 1
            crop_left = (70 - map_inside_w) // 2
            draw_w = map_inside_w

        if map_inside_h >= 23:
            map_y_offset = 3 + (map_inside_h - 23) // 2
            crop_top = 0
            draw_h = 23
        else:
            map_y_offset = 3
            crop_top = (23 - map_inside_h) // 2
            draw_h = map_inside_h

        blink_frame = int(time.time() * 2) % 2

        if self.continent_mode_active:
            # 2a. SPLIT CONTINENT FOCUS MODE
            split_col = map_inside_w // 2
            left_w = split_col - 1
            right_w = map_inside_w - split_col - 1
            right_x = split_col + 1
            
            # Draw vertical divider line
            self.canvas.write_char(split_col, 2, "╦", self.palette["border"])
            self.canvas.write_char(split_col, mid_y1, "╩", self.palette["border"])
            for y in range(3, mid_y1):
                self.canvas.write_char(split_col, y, "│", self.palette["border"])

            # Cropped world map on the left
            if left_w >= 70:
                left_map_x = 1 + (left_w - 70) // 2
                left_crop = 0
                left_draw_w = 70
            else:
                left_map_x = 1
                left_crop = (70 - left_w) // 2
                left_draw_w = left_w

            # Draw left cropped world map
            for i in range(draw_h):
                line = WORLD_MAP[crop_top + i]
                chopped = line[left_crop : left_crop + left_draw_w]
                chopped = chopped.ljust(left_draw_w)
                self.canvas.write_str(left_map_x, map_y_offset + i, chopped, self.palette["map_land"])

            # Left cities
            for x, y, name, code in CITIES:
                cx = left_map_x + (x - left_crop)
                cy = map_y_offset + (y - crop_top)
                if 1 <= cx < split_col and 3 <= cy < 2 + top_h:
                    color = self.palette["accent"] if blink_frame == 0 else self.palette["text"]
                    self.canvas.write_char(cx, cy, "¤", color)
                    
                    node_state = "[ON]"
                    node_color = self.palette["success"]
                    for attack in self.attacks:
                        if attack.dst_city[3] == code:
                            node_state = "[ALT]"
                            node_color = self.palette["warn"]
                            
                    label = f"{code[:4]}{node_state}"
                    self.canvas.write_str(cx - 2, cy + 1, label, node_color)

            # Left attacks
            for attack in self.attacks:
                attack.draw(self.canvas, left_map_x, map_y_offset, left_crop, crop_top, left_draw_w, draw_h)

            # Right Continent Focus view
            region_data = REGIONS[self.current_continent]
            title_str = f" FOCUS: {region_data['name']} "
            self.canvas.write_str(right_x + (right_w - len(title_str)) // 2, 2, title_str, self.palette["warn"])

            cont_w = 26
            cont_h = len(region_data["map"])
            cont_x = right_x + max(0, (right_w - cont_w) // 2)
            cont_y = 3 + max(0, (map_inside_h - cont_h) // 2)

            # Draw continent ASCII map
            for i in range(min(cont_h, map_inside_h)):
                line = region_data["map"][i]
                self.canvas.write_str(cont_x, cont_y + i, line[:right_w], self.palette["success"])

            # Draw local cities
            for lx, ly, name, code in region_data["cities"]:
                cx = cont_x + lx
                cy = cont_y + ly
                if right_x <= cx < right_x + right_w and 3 <= cy < 2 + top_h:
                    color = self.palette["accent"] if blink_frame == 0 else self.palette["warn"]
                    self.canvas.write_char(cx, cy, "✦", color)
                    label = f"{code}"
                    self.canvas.write_str(cx - 1, cy + 1, label, self.palette["info"])

            # Draw local attacks
            for attack in self.local_attacks:
                attack.draw(self.canvas, cont_x, cont_y, right_w, map_inside_h)

        else:
            # 2b. STANDARD WORLD MAP MODE (FULLSCREEN)
            # Render flat Mercator map outline
            for i in range(draw_h):
                line = WORLD_MAP[crop_top + i]
                chopped = line[crop_left : crop_left + draw_w]
                chopped = chopped.ljust(draw_w)
                self.canvas.write_str(map_x_offset, map_y_offset + i, chopped, self.palette["map_land"])

            # Plot major city targets with active status flags!
            for x, y, name, code in CITIES:
                cx = map_x_offset + (x - crop_left)
                cy = map_y_offset + (y - crop_top)
                
                if 1 <= cx < split_x1 and 3 <= cy < 2 + top_h:
                    color = self.palette["accent"] if blink_frame == 0 else self.palette["text"]
                    self.canvas.write_char(cx, cy, "¤", color)
                    
                    node_state = "[ON]"
                    node_color = self.palette["success"]
                    for attack in self.attacks:
                        if attack.dst_city[3] == code:
                            node_state = "[ALT]"
                            node_color = self.palette["warn"]
                            
                    label = f"{code[:4]}{node_state}"
                    self.canvas.write_str(cx - 2, cy + 1, label, node_color)

            # Draw active attacks over map
            for attack in self.attacks:
                attack.draw(self.canvas, map_x_offset, map_y_offset, crop_left, crop_top, draw_w, draw_h)

        # Draw the restored border for Panel 2 System Diagnostics
        self.canvas.draw_box(split_x1, 2, W - split_x1, top_h + 1, "SYSTEM DIAGNOSTICS & THERMALS", self.palette["border"])

        diag_inside_w = W - split_x1 - 2
        diag_inside_h = top_h - 1

        dy = 4
        # Draw CPU Cores (8 Cores in 2 rows)
        self.canvas.write_str(split_x1 + 2, dy, "GIBSON MATRIX CORES:", self.palette["info"])
        dy += 1
        
        cores_per_row = 4 if diag_inside_w >= 28 else 2
        num_rows = (8 + cores_per_row - 1) // cores_per_row
        
        for row in range(num_rows):
            if dy >= 2 + top_h:
                break
            cx = split_x1 + 2
            for col in range(cores_per_row):
                core_id = row * cores_per_row + col
                if core_id >= 8:
                    break
                val = self.metrics[f"CPU{core_id}"]
                core_lbl = f"C{core_id}:"
                self.canvas.write_str(cx, dy, core_lbl, self.palette["text"])
                cx += len(core_lbl)
                
                val_str = f"{int(val):2d}%"
                val_color = self.palette["success"]
                if val > 85.0:
                    val_color = self.palette["warn"]
                elif val > 70.0:
                    val_color = self.palette["info"]
                
                self.canvas.write_str(cx, dy, val_str, val_color)
                cx += len(val_str)
                
                # Dynamic Hollywood core status tag injection!
                if diag_inside_w >= 44:
                    if self.hacker_intensity > 7.0:
                        tag = random.choice(["[BRN]", "[FLX]", "[OVR]", "[MLT]", "[TNT]"])
                        tag_color = self.palette["warn"]
                    else:
                        if val < 30.0:
                            tag = "[IDL]"
                            tag_color = "\033[2m"
                        elif val < 60.0:
                            tag = "[OK ]"
                            tag_color = self.palette["success"]
                        elif val < 80.0:
                            tag = "[CLK]"
                            tag_color = self.palette["info"]
                        else:
                            tag = "[ERR]"
                            tag_color = self.palette["warn"]
                    self.canvas.write_str(cx, dy, tag, tag_color)
                    cx += len(tag) + 1
                else:
                    cx += 1
            dy += 1
        
        # Draw dynamic metrics HOODIE, COFFEE, and FBI TRK (100% reactive to hacker intensity slam speed!)
        self.metrics["RAM"] = min(100.0, self.hacker_intensity * 10.0 + 35.0 + random.uniform(-2.0, 2.0))
        
        if self.hacker_intensity > 5.0:
            self.metrics["DISK"] = min(120.0, self.metrics["DISK"] + 8.0)
        else:
            self.metrics["DISK"] = max(45.0, self.metrics["DISK"] - 0.4 + random.uniform(-0.2, 0.2))
            
        self.metrics["GPU"] = min(99.9, self.hacker_intensity * 11.5 + 4.2 + random.uniform(-1.0, 1.0))
            
        for metric, label, warning_lbl in [
            ("RAM", "HOODIE: ", "COZY "),
            ("DISK", "COFFEE: ", "ALERT"),
            ("GPU", "FBI TRK:", "RUN!!")
        ]:
            if dy >= 2 + top_h:
                break
            val = self.metrics[metric]
            self.canvas.write_str(split_x1 + 2, dy, label, self.palette["text"])
            
            bar_len = max(4, diag_inside_w - 17)
            filled = int(val * bar_len / 100) if val <= 100.0 else bar_len
            bar_str = "█" * filled + "░" * (bar_len - filled)
            
            bar_color = self.palette["success"]
            if val > 90.0:
                bar_color = self.palette["warn"]
            elif val > 65.0:
                bar_color = self.palette["info"]
                
            self.canvas.write_str(split_x1 + 10, dy, bar_str, bar_color)
            
            if val > 99.0:
                val_str = f" {warning_lbl}"
            else:
                val_str = f" {int(val):2d}%"
            self.canvas.write_str(split_x1 + 10 + bar_len, dy, val_str, self.palette["accent"])
            dy += 1
            
        # Draw dynamic thermal deck (fully interactive temperature scales and coolant states!)
        therm_y = dy
        if therm_y + 2 < 2 + top_h:
            t1 = int(self.metrics["TEMP"])
            
            # Ridiculous, cycle-based cinematic coolant fluid types
            coolants = ["MNT. DEW (BAJA BLAST)", "LIQ. N2 DEEP CHILL", "PIZZA GREASE v2.0", "BOBA MILK TEA 25%", "HOT POCKET LIQUID", "BOBA COFFEE INJECT"]
            coolant_type = coolants[int(time.time() / 3.0) % len(coolants)]
            
            # Temperature scale reactively spikes under heavy hacking slam speeds
            coolant_temp = 24.2 + (t1 * 0.25) + (self.hacker_intensity * 120.0)
            
            if coolant_temp > 500.0:
                temp_status = " [MOLTEN LAVA!]"
                temp_color = self.palette["warn"]
            elif coolant_temp > 100.0:
                temp_status = " [BOILING!]"
                temp_color = self.palette["warn"]
            else:
                temp_status = " [STABLE]"
                temp_color = self.palette["success"]
                
            pressure = 1000 + int(t1 * 50) + int(self.hacker_intensity * 800)
            
            # Fan speed reacts dramatically to cooling requirements
            if self.hacker_intensity > 8.0:
                fan_speed = "MELTDOWN INBOUND (99999 RPM)"
                fan_color = self.palette["warn"]
            elif self.hacker_intensity > 4.0:
                fan_speed = "HYPERVENTILATE (25000 RPM)"
                fan_color = self.palette["info"]
            else:
                fan_speed = "OVERDRIVE (9999 RPM)"
                fan_color = self.palette["accent"]
                
            self.canvas.write_str(split_x1 + 2, therm_y, f"COOLANT: {coolant_type[:24]}", self.palette["success"])
            self.canvas.write_str(split_x1 + 2, therm_y + 1, f"TEMP: {coolant_temp:.1f}°C{temp_status}", temp_color)
            
            if therm_y + 3 < 2 + top_h:
                self.canvas.write_str(split_x1 + 2, therm_y + 2, f"PSI: {pressure} kPa | FAN: {fan_speed}", fan_color)
                dy += 3
            else:
                dy += 2
            
        # Draw Hacker Force Field intensity bar at the bottom of the panel!
        intensity_y = dy
        if intensity_y + 1 < 2 + top_h:
            val = self.hacker_intensity
            label = "HACK DECK: "
            self.canvas.write_str(split_x1 + 2, intensity_y, label, self.palette["accent"])
            
            bar_len = max(4, diag_inside_w - 15)
            filled = int(val * bar_len / 10.0)
            bar_str = "█" * filled + "░" * (bar_len - filled)
            
            if val < 2.0:
                status = "[STATUS: SLEEPY / COFFEE REQUIRED]"
                status_color = self.palette["map_land"]
            elif val < 5.0:
                status = "[STATUS: HOODIE COZINESS 100%]"
                status_color = self.palette["info"]
            elif val < 8.0:
                status = "[STATUS: SLICING SUBNET VIA DUAL-KEYBOARDS]"
                status_color = self.palette["warn"]
            else:
                status = "[STATUS: MAXIMUM HACKER OVERDRIVE!!!]"
                status_color = self.palette["warn"]
                
            self.canvas.write_str(split_x1 + 13, intensity_y, bar_str, status_color)
            self.canvas.write_str(split_x1 + 2, intensity_y + 1, status[:diag_inside_w - 2].ljust(diag_inside_w - 2), status_color)
            dy += 2


        # 4. PANEL 3: Scrolling Password Cracker Panel (Middle Left)
        self.canvas.draw_box(0, mid_y1, split_x2_1 + 1, mid_h + 1, "DECRYPTER CODES OVERRIDE", self.palette["border"])
        self.crack_engine.draw(self.canvas, 2, mid_y1 + 1, split_x2_1 - 1, mid_h - 1)


        # 5. PANEL 4: IP Netstat Tunnels (Middle Center)
        self.canvas.draw_box(split_x2_1, mid_y1, split_x2_2 - split_x2_1 + 1, mid_h + 1, "IP NETSTAT TUNNEL MANAGER", self.palette["border"])
        
        tunnel_inside_w = split_x2_2 - split_x2_1 - 1
        tunnel_inside_h = mid_h - 1
        
        self.canvas.write_str(split_x2_1 + 2, mid_y1 + 1, "ESTABLISHED CHANNEL TUNNELS:", self.palette["info"])
        
        # Display socket list (takes up to 8 rows inside height!)
        socket_rows = tunnel_inside_h - 1
        start_sock_idx = max(0, len(self.sockets) - socket_rows)
        
        for idx, i in enumerate(range(start_sock_idx, len(self.sockets))):
            if mid_y1 + 2 + idx >= mid_y1 + tunnel_inside_h:
                break
            l_ip, r_ip, stat, tx, rx, new_timer = self.sockets[i]
            
            # Visual new connection blink!
            if new_timer > 0 and int(time.time() * 4) % 2 == 0:
                color = self.palette["success"]
                new_flag = " [NEW]"
            else:
                color = self.palette["success"] if "ESTABLISHED" in stat or "CONNECTED" in stat else self.palette["text"]
                new_flag = ""
                
            line = f"{l_ip} => {r_ip[:10]} [{stat.strip()}]{new_flag}"
            self.canvas.write_str(split_x2_1 + 2, mid_y1 + 2 + idx, line[:tunnel_inside_w-2].ljust(tunnel_inside_w-2), color)


        # 6. PANEL 5: Hollywood DNA Override Decrypter (Middle Right)
        self.canvas.draw_box(split_x2_2, mid_y1, W - split_x2_2, mid_h + 1, "BIOMETRIC CODES OVERRIDE", self.palette["border"])
        
        # Split the inside space of the panel down the middle
        inside_w = W - split_x2_2 - 2
        half_w = inside_w // 2
        div_x = split_x2_2 + 1 + half_w
        
        # Draw vertical separator line
        for y in range(mid_y1 + 1, mid_y1 + mid_h):
            self.canvas.write_char(div_x, y, "│", self.palette["border"])
        self.canvas.write_char(div_x, mid_y1, "╦", self.palette["border"])
        self.canvas.write_char(div_x, mid_y1 + mid_h, "╩", self.palette["border"])
        
        # Draw sub-titles on the top border
        self.canvas.write_str(split_x2_2 + 2, mid_y1, "[Q-CORE]", self.palette["info"])
        self.canvas.write_str(div_x + 2, mid_y1, "[DNA]", self.palette["warn"])
        
        # Draw 3D cube on the left, and DNA helix on the right
        self.draw_3d_cube(split_x2_2 + 1, mid_y1 + 1, half_w, mid_h - 1)
        self.draw_dna_decrypter(div_x + 1, mid_y1 + 1, inside_w - half_w - 1, mid_h - 1)


        # 7. PANEL 6: Intercept Threat alerts (Bottom Left)
        self.canvas.draw_box(0, mid_y2, split_x3_1 + 1, bottom_h + 1, "INTERCEPT THREAT ALERTS DATABASE", self.palette["border"])
        
        log_inside_h = bottom_h - 1
        log_inside_w = split_x3_1 - 1
        
        start_log_idx = max(0, len(self.threat_logs) - log_inside_h)
        for idx, i in enumerate(range(start_log_idx, len(self.threat_logs))):
            log_text, status = self.threat_logs[i]
            color = self.palette["text"]
            if status == "warn":
                color = self.palette["warn"]
            elif status == "success":
                color = self.palette["success"]
            elif status == "info":
                color = self.palette["info"]
            
            self.canvas.write_str(2, mid_y2 + 1 + idx, log_text[:log_inside_w-2].ljust(log_inside_w-2), color)


        # 8. PANEL 7: Subnet Port Sweeper (Bottom Center)
        self.canvas.draw_box(split_x3_1, mid_y2, split_x3_2 - split_x3_1 + 1, bottom_h + 1, "SUBNET PORT SWEEPER INTERCEPTS", self.palette["border"])
        self.port_scanner.draw(self.canvas, split_x3_1 + 2, mid_y2 + 1, split_x3_2 - split_x3_1 - 2, bottom_h - 1)


        # 9. PANEL 8: Freq & Payload Inject Stack (Bottom Right)
        self.canvas.draw_box(split_x3_2, mid_y2, W - split_x3_2, bottom_h + 1, "FREQ & PAYLOAD INJECT STACK", self.palette["border"])
        
        code_inside_w = W - split_x3_2 - 2
        
        # Render original spectrum analyzer and code streams natively (always visible, no alternation)
        if bottom_h >= 10:
            self.draw_spectrum_analyzer(split_x3_2 + 2, mid_y2 + 1, code_inside_w)
            code_start_y = mid_y2 + 4
            code_inside_h = bottom_h - 4
        else:
            code_start_y = mid_y2 + 1
            code_inside_h = bottom_h - 1
            
        start_code_idx = max(0, len(self.code_stream) - code_inside_h)
        for idx, i in enumerate(range(start_code_idx, len(self.code_stream))):
            if code_start_y + idx >= mid_y2 + bottom_h:
                break
            code_line = self.code_stream[i]
            self.canvas.write_str(split_x3_2 + 2, code_start_y + idx, code_line[:code_inside_w].ljust(code_inside_w), self.palette["text"])

        # Blended junction grid lines
        self.draw_junctions(W, split_x1, split_x2_1, split_x2_2, split_x3_1, split_x3_2, top_h, mid_h, H)


def trigger_meltdown(canvas_w, term_h):
    """Executes a glorious TUI self-destruct character drop fall meltdown sequence and exits."""
    sys.stdout.write("\033[H\033[2J") # Clear TUI
    sys.stdout.flush()
    columns = [0] * canvas_w
    chars = ["@", "#", "$", "%", "&", "?", "!", "*", "+", "x", "1", "0", "A", "F"]
    
    try:
        for _ in range(45):
            for col in range(canvas_w):
                if random.random() < 0.15:
                    columns[col] = min(term_h - 1, columns[col] + random.randint(1, 3))
                
                cy = columns[col]
                char = random.choice(chars)
                # Print green characters descending
                sys.stdout.write(f"\033[{cy};{col}H\033[91m{char}\033[0m")
            sys.stdout.flush()
            time.sleep(0.04)
    except Exception:
        pass
    
    # Final clear screen and exit message
    sys.stdout.write("\033[?1049l\033[?25h\033[0m")
    sys.stdout.flush()
    print("\n[CRITICAL FAILURE] Gibson Mainframe has melted down.")
    print("Core Operations deactivated permanently. Good luck.")
    sys.exit(1)


def clamp_speed(value):
    """Clamp speed values strictly between 0.25 and 4.0."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 1.0
    return max(0.25, min(value, 4.0))


def main():
    parser = argparse.ArgumentParser(
        prog="global-threat-monitor",
        description=f"{APP_NAME} v{APP_VERSION} - {APP_DESCRIPTION}",
        epilog=(
            "Controls while running:\n"
            "  Q / ESC   Quit\n"
            "  T         Cycle theme\n"
            "  P         Pause / resume\n"
            "  S         Toggle sound\n"
            "  A         Trigger fake attack\n"
            "  C         Initiate Direct Backdoor Shell override\n"
            "  G         Initiate critical mainframe breach event\n"
            "  + / =     Increase speed\n"
            "  -         Decrease speed"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "-t", "--theme",
        choices=list(THEMES.keys()),
        help="Set the UI theme."
    )

    parser.add_argument(
        "-s", "--sound",
        action="store_true",
        help="Enable optional sound chimes."
    )

    parser.add_argument(
        "-n", "--no-sound",
        action="store_true",
        help="Mute sound chimes."
    )

    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Set simulation speed multiplier. Clamped between 0.25 and 4.0."
    )

    parser.add_argument(
        "-v", "--version",
        action="store_true",
        help="Show version information and exit."
    )

    args = parser.parse_args()

    if args.version:
        print(f"{APP_NAME} v{APP_VERSION}")
        print(APP_DESCRIPTION)
        sys.exit(0)

    # Sound preference logic with warnings for mutually contradicting inputs
    sound_preference = False
    if args.sound and args.no_sound:
        print("Warning: both --sound and --no-sound were provided; sound will remain muted.")
        sound_preference = False
    elif args.sound:
        sound_preference = True
    elif args.no_sound:
        sound_preference = False

    initial_speed = clamp_speed(args.speed)

    monitor = CyberMonitor(
        initial_theme=args.theme,
        initial_sound=sound_preference,
        initial_speed=initial_speed
    )
    
    init_keyboard()
    enable_windows_ansi()
    
    # Alternate screen, hide cursor, home coordinates, clear screen
    sys.stdout.write("\033[?1049h\033[?25l\033[H\033[2J")
    sys.stdout.flush()

    try:
        while True:
            term_w, term_h = shutil.get_terminal_size()
            
            if term_w < 100 or term_h < 35:
                sys.stdout.write("\033[H\033[2J")
                warning_lines = [
                    "\033[91m════════════════════════════════════════════════════════════════════════════════",
                    "                !!! TERMINAL SHELL MONITOR CALIBRATION FAILURE !!!              ",
                    "════════════════════════════════════════════════════════════════════════════════\033[0m",
                    "",
                    f"  Current Terminal Dimensions: \033[97m{term_w}x{term_h}\033[0m",
                    "  Required Matrix Dimensions:  \033[92mAt least 100x35\033[0m",
                    "",
                    "  Please expand your terminal window coordinates to initialize TUI screen...",
                    "",
                    "  Controls: Q/ESC quit | T theme | P pause | S sound | A attack | C shell | G breach | +/- speed",
                    "",
                    "\033[2m  [Press 'Q' or 'ESC' to deactivate operations]\033[0m"
                ]
                warning_y = max(0, (term_h - len(warning_lines)) // 2)
                sys.stdout.write("\n" * warning_y)
                for line in warning_lines:
                    sys.stdout.write(" " * max(0, (term_w - 80) // 2) + line + "\n")
                sys.stdout.flush()
                
                key = get_key()
                if key == 'q':
                    break
                time.sleep(0.15)
                continue

            # Dynamically size canvas buffer to terminal size minus 1 to prevent far-right border and text clipping
            canvas_w = term_w - 1
            if monitor.canvas.width != canvas_w or monitor.canvas.height != term_h:
                monitor.canvas = Canvas(canvas_w, term_h)

            # Sound sirens beep during critical Gibson breach modes!
            if monitor.active_mode == "breach" and SOUND_ENABLED and not audio.muted:
                try:
                    # Rises in frequency as countdown closes
                    freq = 1000 + int((10.0 - monitor.breach_time_left) * 150)
                    winsound.Beep(freq, 40)
                except Exception:
                    pass

            monitor.update()
            monitor.draw()

            # Compile grid and flush output cleanly
            frame_buffer = monitor.canvas.render(0, 0)
            sys.stdout.write("\033[H")
            sys.stdout.write(frame_buffer)
            sys.stdout.flush()

            # Handle interactive keys based on the active simulator mode
            key = get_key()
            
            # Increase keyboard intensity field on key detection
            if key:
                monitor.hacker_intensity = min(10.0, monitor.hacker_intensity + 1.5)

            if monitor.active_mode == "shell":
                if key:
                    if key in ('q', 'exit') or key == '\x1b':
                        monitor.active_mode = "dashboard"
                        monitor.shell_input = ""
                    elif key == 'enter':
                        cmd = monitor.shell_input.strip()
                        monitor.shell_history.append(f"root@gibson-mainframe:~# {cmd}")
                        monitor.process_shell_command(cmd)
                        monitor.shell_input = ""
                    elif key == 'backspace':
                        monitor.shell_input = monitor.shell_input[:-1]
                    else:
                        if len(key) == 1:
                            # Auto-type realistic coding elements into the shell log scroll
                            code_line = FAKE_SHELL_CODE[monitor.shell_type_index % len(FAKE_SHELL_CODE)]
                            monitor.shell_history.append(code_line)
                            monitor.shell_type_index += 1
                            # Add character to command buffer
                            monitor.shell_input += key
                            audio.play_click()
            
            elif monitor.active_mode == "breach":
                if key:
                    if key == '\x1b': # Esc aborts breach
                        monitor.active_mode = "dashboard"
                    else:
                        monitor.breach_taps += 1
                        audio.play_click()
                        if monitor.breach_taps >= 15:
                            monitor.active_mode = "dashboard"
                            cur_time = time.strftime("%H:%M:%S")
                            monitor.threat_logs.append((f"[{cur_time}] [SUCCESS] Mainframe stabilized. Firewall breach isolated.", "success"))
                            audio.play_success()
            
            else:
                # Dashboard standard interactive key binders
                if key == 'q':
                    break
                elif key == 't':
                    monitor.toggle_theme()
                elif key == 'p':
                    monitor.paused = not monitor.paused
                    cur_time = time.strftime("%H:%M:%S")
                    if monitor.paused:
                        monitor.threat_logs.append((f"[{cur_time}] [SYSTEM] Operations PAUSED", "warn"))
                    else:
                        monitor.threat_logs.append((f"[{cur_time}] [SYSTEM] Operations RESUMED", "success"))
                elif key == 's':
                    monitor.toggle_sound()
                elif key == 'a':
                    monitor.trigger_attack()
                elif key == 'c':
                    monitor.active_mode = "shell"
                    monitor.shell_input = ""
                    monitor.shell_history = []
                    monitor.shell_history.append("[SYSTEM] Initiating Gibson core shell bypass...")
                    monitor.shell_history.append("Type 'help' to see active overrides. Type 'exit' to quit.")
                elif key == 'g':
                    monitor.active_mode = "breach"
                    monitor.breach_time_left = 10.0
                    monitor.breach_taps = 0
                    cur_time = time.strftime("%H:%M:%S")
                    monitor.threat_logs.append((f"[{cur_time}] [ALERT] Mainframe breach override initiated!", "warn"))
                elif key in ('+', '='):
                    monitor.speed_multiplier = clamp_speed(monitor.speed_multiplier + 0.25)
                    cur_time = time.strftime("%H:%M:%S")
                    monitor.threat_logs.append((f"[{cur_time}] [SYSTEM] Warp Speed: x{monitor.speed_multiplier:.2f}", "info"))
                elif key == '-':
                    monitor.speed_multiplier = clamp_speed(monitor.speed_multiplier - 0.25)
                    cur_time = time.strftime("%H:%M:%S")
                    monitor.threat_logs.append((f"[{cur_time}] [SYSTEM] Warp Speed: x{monitor.speed_multiplier:.2f}", "info"))

            time.sleep(0.06)

    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\033[?1049l\033[?25h\033[0m")
        sys.stdout.flush()
        restore_keyboard()
        print("Threat Monitor Core Operations deactivated successfully.")


if __name__ == "__main__":
    main()
