"""Nonblocking keyboard and wheel input for ANSI and Windows terminals."""

from collections import deque
import re
import time


MOUSE_ON = "\033[?1000h\033[?1006h"
MOUSE_OFF = "\033[?1006l\033[?1000l"
ARROWS = {"A": "up", "B": "down", "C": "right", "D": "left"}
WINDOWS_ARROWS = {0x26: "up", 0x28: "down", 0x27: "right", 0x25: "left"}


def normalize_key(key):
    return {"\x03": "quit", "\x1b": "escape", "\x7f": "backspace",
            "\x08": "backspace", "\r": "enter", "\n": "enter"}.get(key, key.lower())


def wheel_key(button):
    # Modifier bits may accompany a wheel report. Horizontal scrolling is ignored.
    return {64: "wheel_up", 65: "wheel_down"}.get(button & ~28)


class InputDecoder:
    """Keep fragmented escape sequences separate from a standalone Escape."""
    def __init__(self):
        self.buffer = ""
        self.pending_since = None

    def feed(self, data, now=None):
        if not self.buffer:
            self.pending_since = time.monotonic() if now is None else now
        self.buffer += data

    def read(self, now=None):
        now = time.monotonic() if now is None else now
        while self.buffer:
            if self.buffer[0] != "\x1b":
                key, self.buffer = self.buffer[0], self.buffer[1:]
                self.pending_since = now
                return normalize_key(key)
            if len(self.buffer) == 1:
                if now - self.pending_since < 0.05:
                    return None
                self.buffer = ""
                return "escape"
            if self.buffer[1] not in "[O":
                self.buffer = self.buffer[1:]
                self.pending_since = now
                return "escape"
            if self.buffer.startswith("\x1b[M"):
                if len(self.buffer) < 6:
                    if now - self.pending_since < 0.05:
                        return None
                    self.buffer = ""
                    return None
                button = ord(self.buffer[3]) - 32
                self.buffer = self.buffer[6:]
                self.pending_since = now
                key = wheel_key(button)
                if key:
                    return key
                continue
            if self.buffer.startswith("\x1b[<"):
                mouse = re.match(r"\x1b\[<([^Mm]*)([Mm])", self.buffer)
                if mouse is None:
                    if now - self.pending_since < 0.05 and len(self.buffer) < 128:
                        return None
                    self.buffer = ""
                    return None
                params, final = mouse.groups()
                self.buffer = self.buffer[mouse.end():]
                self.pending_since = now
                fields = params.split(";")
                if final == "M" and len(fields) == 3 and all(v.isdigit() for v in fields):
                    key = wheel_key(int(fields[0]))
                    if key:
                        return key
                continue
            # CSI and SS3 end with a byte in the range @ through ~.
            match = re.match(r"\x1b[\[O]([ -?]*)([@-~])", self.buffer)
            if match is None:
                if now - self.pending_since < 0.05 and len(self.buffer) < 128:
                    return None
                self.buffer = ""
                return None
            params, final = match.groups()
            self.buffer = self.buffer[match.end():]
            self.pending_since = now
            if final in ARROWS and (not params or all(v.isdigit() for v in params.split(";"))):
                return ARROWS[final]
            # Consume clicks, releases and unsupported control sequences whole.
        return None


class WindowsConsoleInput:
    """ReadConsoleInput preserves wheel events that character reads discard."""
    def __init__(self, kernel=None):
        import ctypes
        from ctypes import wintypes
        self.ctypes = ctypes
        self.kernel = kernel if kernel is not None else ctypes.windll.kernel32

        class Coord(ctypes.Structure):
            _fields_ = [("x", wintypes.SHORT), ("y", wintypes.SHORT)]

        class KeyEvent(ctypes.Structure):
            _fields_ = [("down", wintypes.BOOL), ("repeat", wintypes.WORD),
                        ("vk", wintypes.WORD), ("scan", wintypes.WORD),
                        ("char", wintypes.WCHAR), ("controls", wintypes.DWORD)]

        class MouseEvent(ctypes.Structure):
            _fields_ = [("position", Coord), ("buttons", wintypes.DWORD),
                        ("controls", wintypes.DWORD), ("flags", wintypes.DWORD)]

        class Event(ctypes.Union):
            _fields_ = [("key", KeyEvent), ("mouse", MouseEvent)]

        class InputRecord(ctypes.Structure):
            _fields_ = [("kind", wintypes.WORD), ("event", Event)]

        self.record_type = InputRecord
        self.pending = deque()
        self.kernel.GetStdHandle.restype = wintypes.HANDLE
        self.kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel.GetNumberOfConsoleInputEvents.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.ReadConsoleInputW.argtypes = [wintypes.HANDLE, ctypes.POINTER(InputRecord),
                                                wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        self.handle = self.kernel.GetStdHandle(-10)
        mode = wintypes.DWORD()
        if not self.kernel.GetConsoleMode(self.handle, ctypes.byref(mode)):
            raise OSError("Console input events unavailable")
        self.original_mode = mode.value
        # Mouse input + extended flags; disable quick edit, line/echo/processed
        # input, and VT conversion so arrows and Ctrl+C remain native records.
        mode = (self.original_mode | 0x10 | 0x80) & ~(0x40 | 0x01 | 0x02 | 0x04 | 0x200)
        if not self.kernel.SetConsoleMode(self.handle, mode):
            raise OSError("Cannot enable console mouse input")

    def decode(self, record):
        if record.kind == 1 and record.event.key.down:
            event = record.event.key
            key = WINDOWS_ARROWS.get(event.vk)
            if key is None and event.char != "\x00":
                key = normalize_key(event.char)
            if key:
                self.pending.extend([key] * min(64, max(1, event.repeat)))
        elif record.kind == 2 and record.event.mouse.flags == 0x04:
            delta = self.ctypes.c_short(record.event.mouse.buttons >> 16).value
            if delta:
                self.pending.extend(["wheel_up" if delta > 0 else "wheel_down"] *
                                    min(64, max(1, abs(delta) // 120)))

    def read(self):
        from ctypes import wintypes
        if not self.pending:
            count = wintypes.DWORD()
            if not self.kernel.GetNumberOfConsoleInputEvents(self.handle, self.ctypes.byref(count)):
                return None
            if count.value:
                records = (self.record_type * min(count.value, 128))()
                read = wintypes.DWORD()
                if self.kernel.ReadConsoleInputW(self.handle, records, len(records), self.ctypes.byref(read)):
                    for record in records[:read.value]:
                        self.decode(record)
        return self.pending.popleft() if self.pending else None

    def restore(self):
        self.kernel.SetConsoleMode(self.handle, self.original_mode)
