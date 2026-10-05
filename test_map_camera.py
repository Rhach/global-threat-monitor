"""Camera policy uses wall time without changing correlated simulation facts."""
import unittest
from unittest.mock import patch

from map_layers import LAYERS
from test_monitor import monitor


class MapCameraTests(unittest.TestCase):
    def app(self, **kwargs):
        with patch.object(monitor.time, "monotonic", return_value=0):
            app = monitor.CyberMonitor(initial_theme="ice", seed=12, **kwargs)
        app.simulation.automatic = app.incidents.automatic = False
        return app

    def start(self, app, variant="exfiltration"):
        with patch.object(monitor.time, "monotonic", return_value=0):
            return app.start_critical_incident(variant)

    def camera(self, app):
        return (app.view, {name: (v.bounds, v.zoom) for name, v in app.map_views.items()})

    def facts(self, app, incident):
        return (app.simulation.now, app.simulation.total_bytes, incident.age,
                incident.disposition, incident.visible_stage, tuple(incident.timeline),
                tuple((s.identifier, s.orig_bytes, s.resp_bytes, s.state) for s in incident.sessions),
                tuple((a.identifier, a.status, a.applied_at) for a in incident.actions))

    def test_disabled_preference_prevents_arrival_follow_but_explicit_follow_works(self):
        app = self.app(initial_auto_follow=False)
        before = self.camera(app)
        incident = self.start(app)
        self.assertFalse(incident.following)
        self.assertEqual(app.camera_state, "MANUAL")
        app.update_map(now=.2)
        self.assertEqual(before, self.camera(app))
        with patch.object(monitor.time, "monotonic", return_value=.2):
            app.handle_key("enter")
        facts = self.facts(app, incident)
        app.update_map(now=.4)
        self.assertTrue(incident.following)
        self.assertFalse(app.auto_follow)
        self.assertNotEqual(before, self.camera(app))
        self.assertEqual(facts, self.facts(app, incident))

    def test_pin_resists_manual_and_scheduled_incident_arrivals_and_idle(self):
        for scheduled in (False, True):
            app = self.app()
            with patch.object(monitor.time, "monotonic", return_value=0):
                app.handle_key("r")
                app.handle_key("]")
                app.handle_key("h")
                app.handle_key("z")
            before = self.camera(app)
            if scheduled:
                app.incidents.automatic = True
                app.critical_cooldown = 1
                with patch.object(monitor.time, "monotonic", return_value=1):
                    app.update(1)
                incident = app.critical_incident
            else:
                incident = self.start(app, "benign")
            self.assertEqual(app.camera_state, "PINNED")
            self.assertFalse(incident.following)
            facts = self.facts(app, incident)
            for now in (2, 12, 100):
                app.update_map(now=now)
            self.assertEqual(before, self.camera(app))
            self.assertEqual(facts, self.facts(app, incident))

    def test_manual_interruption_unpin_and_preference_do_not_resume_current_follow(self):
        app = self.app()
        incident = self.start(app)
        facts = self.facts(app, incident)
        with patch.object(monitor.time, "monotonic", return_value=0):
            app.handle_key("right")
            self.assertFalse(incident.following)
            app.handle_key("y")
            self.assertFalse(app.auto_follow)
            app.handle_key("y")
            self.assertTrue(app.auto_follow)
            self.assertFalse(incident.following)
            app.handle_key("z")
            app.handle_key("enter")
            self.assertEqual(app.camera_state, "PINNED")
            app.handle_key("z")
            self.assertEqual(app.camera_state, "MANUAL")
            app.handle_key("enter")
            self.assertEqual(app.camera_state, "FOLLOW")
        self.assertEqual(facts, self.facts(app, incident))

    def test_pin_allows_explicit_adjustment_and_preserves_stored_regions(self):
        app = self.app(initial_pinned=True)
        with patch.object(monitor.time, "monotonic", return_value=0):
            app.handle_key("r")
            app.handle_key("]")
            app.handle_key("right")
            european = app.map_views["EUROPE"].bounds
            app.handle_key("r")
            app.handle_key("]")
            asian = app.map_views["ASIA"].bounds
            for _ in range(len(monitor.VIEWS) - 1):
                app.handle_key("r")
            self.assertEqual(app.view, "EUROPE")
            self.assertEqual(app.map_views["EUROPE"].bounds, european)
            self.assertEqual(app.map_views["ASIA"].bounds, asian)
            app.handle_key("0")
        self.assertTrue(app.camera_pinned)
        self.assertEqual(app.map_views["EUROPE"].bounds, monitor.VIEWS["EUROPE"])

    def test_pause_freezes_follow_pin_freezes_idle_manual_pause_still_eases(self):
        app = self.app()
        self.start(app)
        app.paused = True
        before = self.camera(app)
        app.update_map(now=1)
        self.assertEqual(before, self.camera(app))
        with patch.object(monitor.time, "monotonic", return_value=1):
            app.handle_key("]")
            app.handle_key("z")
        pinned = self.camera(app)
        app.update_map(now=30)
        self.assertEqual(pinned, self.camera(app))
        with patch.object(monitor.time, "monotonic", return_value=30):
            app.handle_key("z")
        app.update_map(now=39.9)
        self.assertEqual(pinned, self.camera(app))
        app.update_map(now=40.2)
        self.assertLess(app.map_views[app.view].zoom, pinned[1][app.view][1])
        self.assertEqual(app.simulation.now, 0)

    def test_console_detail_drill_navigation_keeps_exact_pinned_view(self):
        app = self.app(initial_pinned=True)
        self.start(app)
        with patch.object(monitor.time, "monotonic", return_value=0):
            app.handle_key("]")
            app.handle_key("right")
        before = self.camera(app)
        for key in ("c", "i", "g"):
            app.handle_key(key)
            if key == "i":
                app.handle_key("enter")
            app.update_map(now=20)
            self.assertEqual(before, self.camera(app))
            app.handle_key("escape")
            if app.active_mode == "inspection":
                app.handle_key("escape")
            self.assertEqual(app.active_mode, "dashboard")
            app.update_map(now=21)
            self.assertEqual(before, self.camera(app))
        app.process_shell_command("enhance")
        self.assertEqual(before, self.camera(app))
        self.assertTrue(app.camera_pinned)

    def test_stage_changes_follow_new_route_without_resetting_model(self):
        app = self.app()
        incident = self.start(app)
        route_ids = []
        for stage_time in (2, 16, 30, 44, 49):
            with patch.object(monitor.time, "monotonic", return_value=0):
                app.update(stage_time - app.simulation.now)
            route_ids.append(incident.route.connection.identifier)
            snapshot = self.facts(app, incident)
            for tick in range(1, 6):
                app.update_map(now=stage_time + tick / 10)
            self.assertEqual(snapshot, self.facts(app, incident))
            self.assertIs(app.critical_incident, incident)
            self.assertTrue(incident.following)
        self.assertGreater(len(set(route_ids)), 1)
        self.assertEqual(incident.age, 49)

    def test_wall_time_easing_independent_of_speed_and_frame_rate(self):
        apps = [self.app(initial_speed=speed) for speed in (.25, 4)]
        for app in apps:
            self.start(app)
        snapshots = [self.facts(app, app.critical_incident) for app in apps]
        for app, fps in zip(apps, (15, 60)):
            for tick in range(1, fps * 3 + 1):
                app.update_map(now=tick / fps)
        for app, snapshot in zip(apps, snapshots):
            self.assertEqual(snapshot, self.facts(app, app.critical_incident))
        a, b = (app.map_views[app.view] for app in apps)
        self.assertAlmostEqual(a.zoom, b.zoom, places=3)
        self.assertAlmostEqual(a.longitude, b.longitude, places=3)
        self.assertAlmostEqual(a.latitude, b.latitude, places=3)

    def test_camera_console_and_minimum_header_coexist_with_layers_filters(self):
        app = self.app()
        self.start(app)
        app.process_shell_command("camera auto off")
        self.assertFalse(app.auto_follow)
        app.process_shell_command("camera pin")
        app.process_shell_command("filter service=DNS")
        for width, height in ((79, 24), (119, 40)):
            app.canvas = monitor.Canvas(width, height)
            for layer in LAYERS:
                app.map_layer = layer
                app.draw()
                row = "".join(app.canvas.grid[0])
                for text in ("PINNED", "A:off", "Y/Z/Enter", "UTC"):
                    self.assertIn(text, row)
                screen = "\n".join("".join(row) for row in app.canvas.grid)
                self.assertIn("Filters:", screen)
                self.assertIn("! stale", screen)
        app.process_shell_command("camera follow")
        self.assertIn("Map pinned", "\n".join(app.shell_history))
        app.process_shell_command("camera unpin")
        app.process_shell_command("camera follow")
        self.assertEqual(app.camera_state, "FOLLOW")
        app.handle_key("c")
        for key in ("y", "z"):
            app.handle_key(key)
        self.assertEqual(app.shell_input, "yz")
        self.assertFalse(app.auto_follow)
        self.assertFalse(app.camera_pinned)


if __name__ == "__main__":
    unittest.main()
