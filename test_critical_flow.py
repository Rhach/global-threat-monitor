"""Priority incident timing, camera, rendering and manual override regressions."""

import re
import unittest
from unittest.mock import patch

from test_monitor import monitor


class CriticalFlowTests(unittest.TestCase):
    def make_app(self, speed=1):
        with patch.object(monitor.time, "monotonic", return_value=0):
            return monitor.CyberMonitor(initial_theme="ice", initial_speed=speed)

    def start(self, app):
        with patch.object(monitor.time, "monotonic", return_value=0), \
                patch.object(monitor.random, "choice", return_value=("New York", "London")):
            app.start_critical_incident()
        return app.critical_incident

    def test_schedule_is_30_to_90_seconds_and_independent_of_speed(self):
        for speed in (0.25, 4):
            app = self.make_app(speed)
            self.assertTrue(30 <= app.critical_cooldown <= 90)
            app.critical_cooldown = 30
            app.update_critical_incident(29)
            self.assertIsNone(app.critical_incident)
            app.update_critical_incident(1)
            self.assertIsNotNone(app.critical_incident)
            self.assertTrue(30 <= app.critical_cooldown <= 90)

    def test_stages_containment_count_once_and_route_cleanup(self):
        app = self.make_app()
        incident = self.start(app)
        blocked = app.blocked
        self.assertEqual(incident.stage, "SIGNAL ACQUIRED")
        self.assertEqual(app.threat_logs[-1][1], "CRIT")
        app.update_critical_incident(2)
        self.assertEqual(incident.stage, "TRACING FLOW")
        app.update_critical_incident(12)
        self.assertEqual(incident.stage, "QUARANTINING")
        self.assertEqual(incident.route.progress, 1)
        app.update_critical_incident(3)
        self.assertTrue(incident.contained)
        self.assertEqual(app.blocked, blocked + 1)
        app.update_critical_incident(1)
        self.assertEqual(app.blocked, blocked + 1)
        app.update_critical_incident(3)
        self.assertIsNone(app.critical_incident)
        self.assertNotIn(incident.route, app.attacks)
        self.assertTrue(incident.route.complete)
        app.draw()

    def test_critical_route_is_not_accelerated_by_normal_flow_updates(self):
        app = self.make_app(speed=4)
        incident = self.start(app)
        with patch.object(monitor.time, "monotonic", return_value=0):
            app.update(3)
        self.assertEqual(incident.age, 3)
        self.assertAlmostEqual(incident.route.progress, 1 / 12)

    def test_camera_follows_the_rendered_geographic_packet(self):
        app = self.make_app()
        incident = self.start(app)
        viewport = app.map_views["WORLD"]
        for tick in range(1, 140):
            now = tick / 10
            with patch.object(monitor.time, "monotonic", return_value=now):
                app.update(0.1)
        self.assertGreater(viewport.zoom, 5)
        lon, lat = incident.position()
        west, east, south, north = viewport.bounds
        self.assertTrue(west < lon < east and south < lat < north)
        self.assertAlmostEqual(lon, incident.route.dst_city[0], delta=1)

    def test_pause_and_hidden_modes_freeze_incident_and_camera(self):
        app = self.make_app()
        incident = self.start(app)
        app.paused = True
        cooldown = app.critical_cooldown
        bounds = app.map_views["WORLD"].bounds
        with patch.object(monitor.time, "monotonic", return_value=20):
            app.update(20)
        self.assertEqual(incident.age, 0)
        self.assertEqual(app.critical_cooldown, cooldown)
        self.assertEqual(app.map_views["WORLD"].bounds, bounds)
        app.paused = False
        for mode in ("shell", "breach"):
            app.active_mode = mode
            app.update_critical_incident(20)
            app.update_map(now=30)
        self.assertEqual(incident.age, 0)
        self.assertEqual(app.critical_cooldown, cooldown)

    def test_manual_map_input_stops_follow_without_canceling_threat(self):
        for key in ("wheel_up", "left", "r", "0", "b"):
            app = self.make_app()
            incident = self.start(app)
            app.handle_key(key)
            self.assertFalse(incident.following, key)
            self.assertIs(app.critical_incident, incident)
            app.update_critical_incident(3)
            self.assertEqual(incident.stage, "TRACING FLOW")

    def test_no_duplicate_incidents_and_bounded_flow_list(self):
        app = self.make_app()
        for _ in range(20):
            app.trigger_attack()
        incident = self.start(app)
        app.start_critical_incident()
        self.assertIs(app.critical_incident, incident)
        self.assertEqual(app.incident_count, 1)
        self.assertEqual(len(app.attacks), 12)

    def test_preview_key_starts_incident_and_console_keeps_literal_f(self):
        app = self.make_app()
        app.handle_key("f")
        self.assertIsNotNone(app.critical_incident)
        app.handle_key("c")
        app.handle_key("f")
        self.assertEqual(app.shell_input, "f")
        self.assertEqual(app.incident_count, 1)

    def test_critical_rendering_and_incremental_output_across_sizes(self):
        app = self.make_app()
        incident = self.start(app)
        tokens = re.compile(r"\033\[([0-9;]*)([Hm])|([^\033]+)")
        for width, height in ((79, 24), (99, 35), (159, 48)):
            app.canvas = monitor.Canvas(width, height)
            screen = [[" "] * width for _ in range(height)]
            row = col = 0
            for age in (0, 2, 9, 14, 17, 20):
                # Rendering has no simulation side effects.
                incident.age = age
                incident.route.progress = min(1, max(0, (age - 2) / 12))
                incident.follow(app.map_views[app.view], 0.25)
                app.draw()
                self.assertIn("P1 CT-001", "".join(app.canvas.grid[1]))
                self.assertIn(app.palette["critical_ok" if incident.contained else "critical"],
                              app.canvas.colors[1])
                for match in tokens.finditer(app.canvas.render_diff()):
                    params, command, text = match.groups()
                    if command == "H":
                        row, col = (int(n) - 1 for n in params.split(";"))
                    elif text:
                        for char in text:
                            self.assertTrue(0 <= row < height and 0 <= col < width)
                            screen[row][col] = char
                            col += 1
                self.assertEqual(screen, app.canvas.grid)


if __name__ == "__main__":
    unittest.main()
