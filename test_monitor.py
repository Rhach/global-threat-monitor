"""Regression checks for terminal rendering and simulation timing."""

import contextlib
import importlib.util
import io
from pathlib import Path
import random
import re
import subprocess
import sys
import time
import unittest


spec = importlib.util.spec_from_file_location(
    "monitor", Path(__file__).with_name("global-threat-monitor.py")
)
monitor = importlib.util.module_from_spec(spec)
with contextlib.redirect_stdout(io.StringIO()):
    spec.loader.exec_module(monitor)


class RenderingTests(unittest.TestCase):
    def test_unchanged_frame_emits_nothing(self):
        canvas = monitor.Canvas(80, 24)
        canvas.write_str(2, 1, "Sensor online", "\033[32m")
        self.assertTrue(canvas.render_diff())
        self.assertEqual(canvas.render_diff(), "")

    def test_sparse_update_and_erasure(self):
        canvas = monitor.Canvas(160, 48)
        canvas.write_str(4, 3, "ALERT", "\033[31m")
        full = canvas.render_diff()
        canvas.clear()
        canvas.write_str(4, 3, "OK", "\033[32m")
        delta = canvas.render_diff()
        self.assertIn("\033[4;5H", delta)
        self.assertIn("OK", delta)
        self.assertIn("   ", delta)
        self.assertLess(len(delta), len(full) // 20)
        self.assertEqual(canvas.render_diff(), "")

    def test_color_only_change_is_rendered(self):
        canvas = monitor.Canvas(10, 2)
        canvas.write_str(0, 0, "OK", "\033[32m")
        canvas.render_diff()
        canvas.write_str(0, 0, "OK", "\033[31m")
        self.assertIn("\033[31m", canvas.render_diff())

    def test_incremental_output_reconstructs_full_screen(self):
        """Replay actual dashboard output through a minimal ANSI cell emulator."""
        random.seed(19)
        app = monitor.CyberMonitor(initial_theme="ice")
        app.canvas = monitor.Canvas(99, 35)
        screen = [[" "] * 99 for _ in range(35)]
        tokens = re.compile(r"\033\[([0-9;]*)([Hm])|([^\033]+)")
        row = col = 0
        for frame in range(180):
            if frame in (30, 60, 90, 120):
                app.handle_key("r")
            if frame == 130:
                app.handle_key("c")
            if frame == 140:
                app.handle_key("escape")
            app.update(1 / 30)
            app.draw()
            for match in tokens.finditer(app.canvas.render_diff()):
                params, command, text = match.groups()
                if command == "H":
                    row, col = (int(n) - 1 for n in params.split(";"))
                elif text:
                    for char in text:
                        self.assertLess(col, 99)
                        screen[row][col] = char
                        col += 1
            self.assertEqual(screen, app.canvas.grid, f"Incorrect terminal frame {frame}")

    def test_draw_has_no_simulation_side_effects(self):
        random.seed(7)
        app = monitor.CyberMonitor(initial_theme="ice")
        app.canvas = monitor.Canvas(159, 48)
        app.update()
        app.paused = True
        metrics = app.metrics.copy()
        app.draw()
        grid = [row[:] for row in app.canvas.grid]
        colors = [row[:] for row in app.canvas.colors]
        app.draw()
        self.assertEqual(app.metrics, metrics)
        self.assertEqual(app.canvas.grid, grid)
        self.assertEqual(app.canvas.colors, colors)

    def test_supported_sizes_and_themes_keep_borders_intact(self):
        for theme in monitor.THEMES:
            app = monitor.CyberMonitor(initial_theme=theme)
            for width, height in ((79, 24), (99, 35), (159, 48), (239, 65)):
                with self.subTest(theme=theme, size=(width, height)):
                    app.canvas = monitor.Canvas(width, height)
                    app.trigger_attack()
                    app.draw()
                    self.assertEqual(len(app.canvas.grid), height)
                    self.assertTrue(all(len(row) == width for row in app.canvas.grid))
                    self.assertNotIn("\n", "".join(app.canvas.grid[-1]))
                    # Panels keep their right edge even with long endpoint labels.
                    for view in monitor.VIEWS:
                        app.view = view
                        app.draw()
                    for y in range(8, height - 2):
                        self.assertIn(app.canvas.grid[y][-1], "│╮╯ ")


class TimingTests(unittest.TestCase):
    def test_route_motion_uses_elapsed_time(self):
        palette = monitor.THEMES["ice"]
        a = monitor.AttackVector(monitor.CITIES[0], monitor.CITIES[1], palette)
        b = monitor.AttackVector(monitor.CITIES[0], monitor.CITIES[1], palette)
        for _ in range(30):
            a.update(1 / 30)
        for _ in range(60):
            b.update(1 / 60)
        self.assertAlmostEqual(a.progress, b.progress)

    def test_speed_scales_motion(self):
        app = monitor.CyberMonitor(initial_theme="ice", initial_speed=2.0)
        app.trigger_attack(app.organization.connect("ATH-WS1", "FRA-APP", "HTTPS"))
        attack = app.attacks[0]
        app.update(0.1)
        self.assertAlmostEqual(attack.progress, 0.2 / attack.MARKER_PERIOD)
        self.assertAlmostEqual(attack.session.duration, 0.2)
        self.assertEqual(attack.session.orig_bytes, 1200)

    def test_histories_and_manual_routes_are_bounded(self):
        app = monitor.CyberMonitor(initial_theme="ice")
        for _ in range(500):
            app.trigger_attack()
            app.generate_threat_log()
        self.assertLessEqual(len(app.threat_logs), 80)
        self.assertLessEqual(len(app.attacks), 12)

    def test_pause_freezes_simulation(self):
        app = monitor.CyberMonitor(initial_theme="ice")
        app.trigger_attack()
        app.paused = True
        progress = app.attacks[0].progress
        elapsed = app.elapsed
        app.update(1)
        self.assertEqual(app.attacks[0].progress, progress)
        self.assertEqual(app.elapsed, elapsed)

    def test_nonfinite_speed_falls_back_to_default(self):
        for value in ("nan", "inf", "-inf", None):
            self.assertEqual(monitor.clamp_speed(value), 1.0)

    def test_shell_accepts_q_in_a_command_and_escape_returns(self):
        app = monitor.CyberMonitor(initial_theme="ice")
        app.handle_key("c")
        for key in "query":
            self.assertTrue(app.handle_key(key))
        self.assertEqual(app.shell_input, "query")
        app.handle_key("escape")
        self.assertEqual(app.active_mode, "dashboard")
        self.assertFalse(app.handle_key("q"))

    def test_drill_completion_and_timeout_return_to_dashboard(self):
        app = monitor.CyberMonitor(initial_theme="ice")
        app.handle_key("g")
        for _ in range(15):
            app.handle_key("x")
        self.assertEqual(app.active_mode, "dashboard")
        app.handle_key("g")
        app.update(11)
        self.assertEqual(app.active_mode, "dashboard")
        self.assertEqual(app.breach_time_left, 0)


@unittest.skipIf(monitor.WINDOWS, "PTY integration requires a POSIX terminal")
class TerminalIntegrationTests(unittest.TestCase):
    def test_interaction_resize_and_terminal_restoration(self):
        import fcntl
        import os
        import pty
        import select
        import struct
        import termios

        master, slave = pty.openpty()
        original = termios.tcgetattr(slave)
        capture = bytearray()

        def resize(width, height):
            fcntl.ioctl(slave, termios.TIOCSWINSZ,
                        struct.pack("HHHH", height, width, 0, 0))

        def collect(seconds):
            deadline = time.monotonic() + seconds
            data = bytearray()
            while time.monotonic() < deadline:
                ready = select.select([master], [], [],
                                      max(0, deadline - time.monotonic()))[0]
                if ready:
                    data.extend(os.read(master, 65536))
            capture.extend(data)
            return bytes(data)

        resize(160, 48)
        env = os.environ.copy()
        env.pop("COLUMNS", None)
        env.pop("LINES", None)
        child = subprocess.Popen(
            [sys.executable, str(Path(monitor.__file__)), "--theme", "ice", "--fps", "30"],
            stdin=slave, stdout=slave, stderr=slave, env=env)
        try:
            collect(0.5)
            os.write(master, b"p")
            collect(0.15)
            self.assertEqual(collect(0.2), b"", "Paused terminal emitted data")
            os.write(master, b"pcstatus\rquery\r")
            collect(0.2)
            self.assertIsNone(child.poll(), "Console q unexpectedly quit the app")
            os.write(master, b"\x1br")
            collect(0.1)
            resize(40, 10)
            small = collect(0.2)
            self.assertIn(b"Resize to at least", small, "Resize warning absent")
            self.assertEqual(small.count(b"\033[2J"), 1, "Small terminal repeatedly cleared")
            resize(80, 24)
            collect(0.2)
            os.write(master, b"e\rd")
            inspection = collect(0.2)
            self.assertIn(b"INVESTIGATION", inspection)
            resize(100, 35)
            larger_detail = collect(0.2)
            self.assertEqual(larger_detail.count(b"\033[2J"), 1)
            self.assertIn(b"INVESTIGATION", larger_detail)
            resize(80, 24)
            smaller_detail = collect(0.2)
            self.assertEqual(smaller_detail.count(b"\033[2J"), 1)
            self.assertIn(b"INVESTIGATION", smaller_detail)
            os.write(master, b"\x1b")
            collect(0.1)
            os.write(master, b"\x1b")
            collect(0.1)
            os.write(master, b"g")
            collect(0.1)
            os.write(master, b"xxxxxxxxxxxxxxx")
            collect(0.1)
            os.write(master, b"q")
            collect(0.1)
            child.wait(timeout=2)
            self.assertEqual(child.returncode, 0)
            self.assertNotIn(b"Traceback", capture)
            self.assertIn(b"\033[?25h\033[?1049l", capture)
            restored = termios.tcgetattr(slave)
            # macOS sets PENDIN when switching back to canonical mode. It is
            # kernel-managed pending-input state, not a changed keyboard mode.
            restored[3] &= ~getattr(termios, "PENDIN", 0)
            original[3] &= ~getattr(termios, "PENDIN", 0)
            self.assertEqual(restored, original)
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=2)
            os.close(master)
            os.close(slave)


if __name__ == "__main__":
    unittest.main()
