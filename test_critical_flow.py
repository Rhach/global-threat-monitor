"""Correlated scenario clock/evidence plus map and incremental output regressions."""

import re
import unittest
from unittest.mock import patch

from test_monitor import monitor


class CriticalFlowTests(unittest.TestCase):
    def make_app(self, speed=1):
        with patch.object(monitor.time, "monotonic", return_value=0):
            app = monitor.CyberMonitor(initial_theme="ice", initial_speed=speed, seed=12)
        app.simulation.automatic = False
        app.incidents.automatic = False
        return app

    def start(self, app):
        with patch.object(monitor.time, "monotonic", return_value=0):
            return app.start_critical_incident()

    def snapshot(self, app):
        incidents = list(app.incidents.history) + ([app.critical_incident] if app.critical_incident else [])
        return (app.simulation.now, app.simulation.total_bytes, list(app.traffic_history),
                app.metrics, app.total_events, [row[1:] for row in app.threat_logs],
                [(i.identifier, i.started_at, i.finished_at, i.stage, i.disposition,
                  list(i.timeline), [(s.identifier, s.started_at, s.orig_port,
                                     s.orig_bytes, s.resp_bytes, s.state) for s in i.sessions])
                 for i in incidents])

    def test_correlated_evidence_actual_sessions_and_unresolved_cleanup(self):
        app = self.make_app()
        incident = self.start(app)
        self.assertEqual(incident.stage, "AUTH ANOMALY")
        self.assertEqual(len(app.simulation.sessions), 0)
        self.assertIn("5 failed logins", incident.timeline[0].message)
        app.update(2)
        first = incident.sessions[0]
        self.assertEqual(incident.stage, "NEW PEER")
        self.assertIs(incident.route.session, first)
        self.assertFalse(first.connection.expected)
        app.update(28)
        self.assertEqual(incident.stage, "RECURRING EGRESS")
        self.assertEqual([s.started_at for s in incident.sessions], [2, 16, 30])
        app.update(14)
        transfer = incident.sessions[-1]
        self.assertEqual((transfer.service, transfer.encryption, transfer.proto), ("HTTPS", "TLS", "tcp"))
        app.update(5)
        self.assertEqual(incident.stage, "UNUSUAL VOLUME")
        evidence = incident.timeline[-1]
        self.assertEqual(evidence.session_id, transfer.identifier)
        self.assertEqual(transfer.orig_bytes, 10000000)
        self.assertIn("3,600", evidence.message)
        self.assertIn("content unknown", evidence.message)
        for session in incident.sessions:
            self.assertEqual(session.incident_id, incident.identifier)
            self.assertEqual((session.connection.source_id, session.connection.peer_id),
                             ("ATH-WS1", "EXT-DXB"))
        app.update(25)
        self.assertIsNone(app.critical_incident)
        self.assertIs(app.incidents.history[-1], incident)
        self.assertEqual(incident.disposition, "unresolved")
        self.assertFalse(incident.contained)
        self.assertEqual((app.blocked, app.rule_hits), (0, [0, 0, 0, 0]))
        self.assertEqual(len(app.attacks), 0)
        self.assertEqual(len(app.simulation.sessions), 0)
        self.assertEqual(len(app.simulation.history), 4)
        self.assertEqual(transfer.orig_bytes, 60000000)
        self.assertEqual([e.timestamp for e in incident.timeline],
                         [0, 2, 14, 16, 28, 30, 42, 44, 49, 74, 74])
        self.assertEqual(len({e.identifier for e in incident.timeline}), 11)
        self.assertTrue(all(e.incident_id == incident.identifier and e.source_id == "ATH-WS1"
                            and e.peer_id == "EXT-DXB" and e.collector_id == "COL-ATH"
                            for e in incident.timeline))
        self.assertEqual({e.session_id for e in incident.timeline if e.session_id},
                         {s.identifier for s in incident.sessions})
        retained = list(incident.timeline)
        app.update(200)
        self.assertEqual(list(incident.timeline), retained)
        self.assertAlmostEqual(sum(app.traffic_history) * 1000000 / 8, 0)  # aged out buckets
        app.draw()

    def test_full_large_advance_matches_15_60_fps_with_background_and_scheduler(self):
        apps = [self.make_app() for _ in range(3)]
        for app in apps:
            app.simulation.automatic = app.incidents.automatic = True
            app.critical_cooldown = 30
        apps[0].update(240)
        for fps, app in zip((15, 60), apps[1:]):
            for _ in range(240 * fps):
                app.update(1 / fps)
        self.assertGreater(apps[0].incident_count, 1)
        self.assertEqual(self.snapshot(apps[0]), self.snapshot(apps[1]))
        self.assertEqual(self.snapshot(apps[0]), self.snapshot(apps[2]))

    def test_manual_and_scheduled_start_share_scenario_without_duplicates(self):
        a, b = self.make_app(), self.make_app()
        for app in (a, b):
            app.update(30)
        a.handle_key("f")
        b.incidents.automatic = True
        b.critical_cooldown = 0
        # Process the current boundary, exactly as advance does before moving.
        # Pin the scheduled variant while comparing the shared exfiltration path.
        with patch.object(b.incidents.variant_rng, "choice", return_value="exfiltration"):
            b.incidents.process_boundary()
        self.assertEqual(self.snapshot(a), self.snapshot(b))
        a.handle_key("f")
        a.process_shell_command("scenario")
        self.assertEqual(a.incident_count, 1)
        a.handle_key("c")
        a.handle_key("f")
        self.assertEqual(a.shell_input, "f")
        a.update(74)
        b.update(74)
        self.assertEqual(self.snapshot(a), self.snapshot(b))

    def test_pause_speed_console_and_drill_share_simulation_clock(self):
        a, b = self.make_app(), self.make_app(4)
        for app in (a, b):
            self.start(app)
        a.update(49)
        b.active_mode = "shell"
        b.update(49 / 4)
        self.assertEqual(self.snapshot(a), self.snapshot(b))
        before = self.snapshot(a)
        a.paused = True
        a.update(100)
        self.assertEqual(before, self.snapshot(a))
        a.paused = False
        a.active_mode = "breach"
        a.update(2)
        self.assertEqual(a.critical_incident.age, 51)
        for speed in (0.25, 4):
            app = self.make_app(speed)
            app.incidents.automatic = True
            self.assertTrue(30 <= app.critical_cooldown <= 90)
            app.critical_cooldown = 30
            app.update(29 / speed)
            self.assertIsNone(app.critical_incident)
            app.update(1 / speed)
            self.assertIsNotNone(app.critical_incident)
            self.assertEqual(app.critical_incident.started_at, 30)

    def test_no_activity_marker_at_auth_or_between_sessions(self):
        app = self.make_app()
        self.start(app)
        app.canvas = monitor.Canvas(159, 48)
        for elapsed in (0, 2.7, 2.3, 9):
            app.update(elapsed)
            app.canvas.clear()
            app.draw_map(0, 8, 100, 25)
            colors = [color for row in app.canvas.colors for color in row]
            markers = [char for row in app.canvas.grid for char in row if char == "◉"]
            if app.simulation.now == 2.7:
                self.assertTrue(markers)
            else:
                self.assertFalse(markers)
                self.assertFalse(app.palette["critical_trail"] in colors)

    def test_camera_follows_same_geographic_arc_using_real_time(self):
        app = self.make_app()
        incident = self.start(app)
        with patch.object(monitor.time, "monotonic", return_value=0):
            app.update(44)
        for tick in range(1, 50):
            with patch.object(monitor.time, "monotonic", return_value=tick / 10):
                app.update(0.01)
        viewport = app.map_views["WORLD"]
        self.assertGreater(viewport.zoom, 5)
        lon, lat = incident.position()
        west, east, south, north = viewport.bounds
        self.assertTrue(west < lon < east and south < lat < north)
        self.assertEqual(incident.position(0), incident.route.src_city[:2])
        self.assertEqual(incident.position(1), incident.route.dst_city[:2])
        before = (incident.age, app.simulation.total_bytes)
        app.update_map(now=10)
        self.assertEqual(before, (incident.age, app.simulation.total_bytes))

    def test_pause_and_hidden_modes_stop_incident_camera_follow(self):
        app = self.make_app()
        self.start(app)
        bounds = app.map_views["WORLD"].bounds
        app.paused = True
        app.update_map(now=20)
        self.assertEqual(app.map_views["WORLD"].bounds, bounds)
        app.paused = False
        for mode in ("shell", "breach"):
            app.active_mode = mode
            app.update_map(now=30)
            self.assertEqual(app.map_views["WORLD"].bounds, bounds)

    def test_manual_map_input_stops_follow_without_canceling_incident(self):
        for key in ("wheel_up", "left", "r", "0", "b"):
            app = self.make_app()
            incident = self.start(app)
            app.handle_key(key)
            self.assertFalse(incident.following, key)
            self.assertIs(app.critical_incident, incident)
            app.update(3)
            self.assertEqual(incident.stage, "NEW PEER")

    def test_reserved_capacity_and_full_trigger_failure_are_atomic(self):
        app = self.make_app()
        for _ in range(20):
            app.trigger_attack(app.organization.connect("ATH-ADM", "FRA-APP", "SSH"))
        incident = self.start(app)
        for _ in range(20):
            app.trigger_attack()
        app.update(49)
        self.assertIs(app.critical_incident, incident)
        self.assertEqual(len(app.simulation.sessions), 12)
        self.assertEqual(len(app.attacks), 12)
        full = self.make_app()
        for _ in range(12):
            full.simulation.create()
        connection_number = full.organization._connection_number
        self.assertIsNone(self.start(full))
        self.assertEqual(full.incident_count, 0)
        self.assertEqual(full.organization._connection_number, connection_number)
        self.assertEqual(full.simulation.reserved_slots, 0)

    def test_bounded_retained_summaries_console_and_scheduler_resume(self):
        app = self.make_app()
        for _ in range(70):
            self.start(app)
            app.update(74)
        self.assertEqual(len(app.incidents.history), 64)
        self.assertEqual(len(app.simulation.history), 120)
        self.assertTrue(all(len(i.timeline) == 11 and len(i.sessions) == 4 for i in app.incidents.history))
        app.process_shell_command("incident")
        app.process_shell_command("timeline")
        text = "\n".join(app.shell_history)
        self.assertIn("CT-070", text)
        self.assertIn("unresolved", text)
        self.assertIn("CT-070-OBS-01", text)
        self.assertIn("FLOW-", text)
        app.process_shell_command("incidents")
        self.assertEqual(len(app.shell_history), 100)
        app.process_shell_command("timeline 1")
        lines = list(app.shell_history)[-5:]
        self.assertTrue(all(len(line) <= 75 for line in lines))
        self.assertIn("5 failed logins", "\n".join(lines))
        app.process_shell_command("timeline 0")
        self.assertIn("Use timeline N", app.shell_history[-1])
        app.update(200)  # Disabled schedule is now in the past.
        app.incidents.automatic = True
        now = app.simulation.now
        app.update(0.5)
        self.assertEqual(app.critical_incident.started_at, now)
        self.assertEqual(app.simulation.now, now + 0.5)

    def test_critical_rendering_and_incremental_output_across_sizes(self):
        tokens = re.compile(r"\033\[([0-9;]*)([Hm])|([^\033]+)")
        for width, height in ((79, 24), (99, 35), (159, 48)):
            app = self.make_app()
            incident = self.start(app)
            app.canvas = monitor.Canvas(width, height)
            screen = [[" "] * width for _ in range(height)]
            row = col = 0
            previous = 0
            for age in (0, 2, 9, 14, 16, 30, 44, 49, 73, 74):
                app.update(age - previous)
                previous = age
                incident.follow(app.map_views[app.view], 0.25)
                app.draw()
                header = "".join(app.canvas.grid[1])
                if age < 74:
                    self.assertIn("P1 CT-001", header)
                    self.assertIn(incident.stage, header)
                    self.assertIn(app.palette["critical"], app.canvas.colors[1])
                else:
                    self.assertNotIn("P1 CT-001", header)
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
