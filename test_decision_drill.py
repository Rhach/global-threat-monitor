"""Decision, actual collateral, clock isolation and minimum-terminal fixtures."""

import unittest
from unittest.mock import patch

from test_monitor import monitor


class DecisionDrillTests(unittest.TestCase):
    def app(self, case="exfiltration", **options):
        app = monitor.CyberMonitor(initial_theme="ice", seed=99, **options)
        app.start_drill(case)
        return app

    def choose(self, app, key):
        app.handle_key(key)
        self.assertIsNotNone(app.drill.preview)
        app.handle_key("enter")

    def review(self, app):
        app.handle_key("h")
        return "\n".join(app.drill.debrief)

    def test_scoped_block_shared_lifecycle_and_preserved_legitimate_bytes(self):
        app = self.app()
        drill = app.drill
        bulk = drill.target()
        evidence = list(drill.incident.timeline)
        app.handle_key("b")
        self.assertIn("ATH-WS1>EXT-DXB", "\n".join(drill.preview_lines()))
        self.assertFalse(drill.incident.actions)
        app.handle_key("enter")
        action = drill.incident.actions[0]
        app.update(1)
        self.assertEqual((action.status, bulk.orig_bytes, bulk.rate), ("applied", 12000000, 0))
        app.update(1)
        self.assertEqual((action.requested_at, action.applied_at, action.verified_at), (49, 50, 51))
        self.assertTrue(drill.incident.contained)
        self.assertEqual((drill.legitimate.state, drill.legitimate.orig_bytes, drill.legitimate.resp_bytes),
                         ("active", 1200, 240000))
        self.assertTrue(all(o in drill.incident.timeline for o in evidence))
        text = self.review(app)
        self.assertIn("Scoped containment verified", text)
        self.assertIn("Disrupted legitimate IDs: none", text)
        self.assertIn("content unknown", text)
        self.assertEqual(app.simulation.now, 0)
        app.handle_key("enter")
        self.assertEqual((app.drill, app.active_mode), (None, "dashboard"))

    def test_session_scope_is_an_available_consequential_action(self):
        app = self.app()
        self.choose(app, "k")
        app.update(2)
        self.assertEqual(app.drill.incident.actions[0].scope, "session")
        self.assertTrue(app.drill.incident.contained)
        self.assertFalse(app.drill.legitimate.complete)

    def test_broad_local_isolation_exposes_and_stops_legitimate_service(self):
        app = self.app()
        drill = app.drill
        app.handle_key("l")
        preview = "\n".join(drill.preview_lines())
        self.assertIn("LOCAL endpoint", preview)
        self.assertIn("ATH-WS1>FRA-APP HTTPS legitimate service", preview)
        self.assertFalse(drill.incident.actions)
        app.handle_key("enter")
        app.update(2)
        self.assertTrue(drill.incident.contained)
        self.assertEqual((drill.legitimate.state, drill.legitimate.orig_bytes, drill.legitimate.resp_bytes),
                         ("isolated", 1200, 168000))
        action = drill.incident.actions[0]
        self.assertIn(drill.legitimate.identifier, action.affected_sessions)
        text = self.review(app)
        self.assertIn("Contained with service disruption", text)
        self.assertIn("policy=" + action.identifier, text)

    def test_benign_wait_reveals_authorization_and_dismiss_preserves_backup(self):
        app = self.app("benign")
        drill = app.drill
        self.assertFalse(drill.incident.assessment.startswith("authorized"))
        self.choose(app, "w")
        self.assertEqual(drill.world.simulation.now, 7)
        self.assertEqual(drill.incident.assessment, "authorized transfer")
        self.assertTrue(any(o.stage == "AUTHORIZATION MATCH" for o in drill.incident.timeline))
        self.choose(app, "j")
        backup = drill.incident.sessions[0]
        before = backup.orig_bytes
        app.update(2)
        self.assertGreater(backup.orig_bytes, before)
        self.assertFalse(backup.complete)
        self.assertFalse(drill.incident.actions)
        text = self.review(app)
        self.assertIn("False-positive dismissed", text)
        self.assertIn("JOB-FRA-SIN-001", text)
        self.assertIn("Disrupted legitimate IDs: none", text)

    def test_incorrect_dismissal_keeps_upload_live_and_uncertainty_visible(self):
        app = self.app()
        drill = app.drill
        self.choose(app, "j")
        app.update(2)
        self.assertEqual(drill.target().orig_bytes, 14000000)
        self.assertFalse(drill.incident.actions)
        text = self.review(app)
        self.assertIn("Incorrect dismissal", text)
        self.assertIn("active related sessions", text)

    def test_waiting_observes_more_bytes_and_timeout_does_not_recover(self):
        app = self.app()
        drill = app.drill
        self.choose(app, "w")
        self.assertEqual(drill.target().orig_bytes, 20000000)
        self.assertIn("Waited for evidence; no containment applied", self.review(app))
        app.handle_key("enter")
        app.start_drill()
        drill = app.drill
        app.update(999)
        self.assertEqual(drill.world.simulation.now, drill.deadline)
        text = "\n".join(drill.debrief)
        self.assertIn("Timed out: Unresolved", text)
        self.assertIn("historical suspected data removal unresolved", text)
        self.assertFalse(drill.incident.contained)
        self.assertEqual(drill.incident.sessions[-1].orig_bytes, 60000000)
        app.update(999)
        self.assertEqual(drill.world.simulation.now, drill.deadline)
        app.handle_key("escape")
        self.assertEqual(app.active_mode, "dashboard")

    def test_partial_case_has_real_second_upload_and_distinct_residual(self):
        app = self.app("partial")
        drill = app.drill
        self.assertEqual(drill.target().connection.source_id, "ATH-WS1")
        self.choose(app, "b")
        app.update(2)
        remaining = drill.incident.sessions[-1]
        self.assertEqual((remaining.connection.source_id, remaining.orig_bytes, remaining.state),
                         ("ATH-ADM", 10000000, "active"))
        self.assertFalse(drill.incident.contained)
        self.assertEqual(drill.incident.disposition, "partially contained")
        text = self.review(app)
        self.assertIn("Partial containment", text)
        self.assertIn(remaining.identifier, text)

    def test_partial_target_navigation_can_contain_the_second_endpoint(self):
        app = self.app("partial")
        self.choose(app, "b")
        app.update(2)
        app.handle_key("t")
        self.assertEqual(app.drill.target().connection.source_id, "ATH-ADM")
        self.choose(app, "b")
        app.update(2)
        self.assertTrue(app.drill.incident.contained)
        self.assertIn("Scoped containment verified", self.review(app))

    def test_finish_pending_is_not_a_verified_success(self):
        app = self.app()
        self.choose(app, "b")
        text = self.review(app)
        self.assertIn("Response pending; containment unverified", text)
        self.assertIn("applied=None verified=None", text)

    def test_dismiss_after_containment_does_not_claim_active_risk(self):
        app = self.app()
        self.choose(app, "b")
        app.update(2)
        self.choose(app, "j")
        text = self.review(app)
        self.assertIn("Dismissed after verified containment", text)
        self.assertIn("no residual modeled incident network activity", text)
        self.assertNotIn("Incorrect dismissal", text)

    def test_inspection_and_ordinary_keys_apply_no_response(self):
        app = self.app()
        drill = app.drill
        for key in "xxxxxxxxxxxxxxxtnmyza":
            app.handle_key(key)
        self.assertFalse(drill.incident.actions)
        app.handle_key("i")
        app.handle_key("enter")
        lines = drill.world.investigation.detail_lines(drill.world, 72)
        self.assertTrue(any(drill.incident.identifier in line for line in lines))
        self.assertTrue(any("10,000,000" in line for line in lines))
        app.handle_key("d")
        app.update(1)
        self.assertEqual(drill.world.simulation.now, 50)
        self.assertFalse(drill.incident.actions)
        app.handle_key("escape")
        app.handle_key("escape")
        self.assertEqual(drill.world.active_mode, "dashboard")
        app.handle_key("b")
        app.handle_key("escape")
        self.assertIsNone(drill.preview)
        self.assertFalse(drill.incident.actions)

    def test_pause_speed_and_wait_are_exercise_local(self):
        app = self.app(initial_speed=2, initial_pinned=True)
        drill = app.drill
        app.handle_key("p")
        app.update(50)
        self.choose(app, "w")
        self.assertEqual((drill.world.simulation.now, drill.waits), (49, 0))
        app.handle_key("i")
        app.handle_key("+")
        app.handle_key("p")
        app.update(2)
        self.assertEqual(drill.world.simulation.now, 53.5)
        app.handle_key("escape")
        app.handle_key("escape")
        self.assertEqual((app.speed_multiplier, app.paused, app.camera_pinned, app.simulation.now),
                         (2, False, True, 0))

    def test_cancel_preserves_entire_original_world_and_camera_timer_age(self):
        with patch.object(monitor.time, "monotonic", return_value=10):
            app = monitor.CyberMonitor(initial_theme="ice", initial_sound=True, seed=4,
                                       initial_auto_follow=False, initial_pinned=True)
            app.simulation.automatic = app.incidents.automatic = False
            incident = app.start_critical_incident()
            app.update(3)
            app.handle_key("]")
            app.handle_key("right")
            app.paused = True
            before = (app.simulation, app.organization, app.incidents, app.collectors, app.attacks,
                      app.investigation, app.event_catalog, app.threat_logs, app.clock_base)
            facts = (app.simulation.now, app.simulation.total_bytes, list(incident.timeline),
                     incident.following, app.camera_incident_id)
            cameras = {key: view.bounds for key, view in app.map_views.items()}
            timers = app.last_auto_zoom, app.last_map_interaction
            app.start_drill()
        with patch.object(monitor.time, "monotonic", return_value=40):
            app.handle_key("p")
            self.choose(app, "l")
            app.update(2)
            app.handle_key("escape")
        self.assertEqual((app.simulation, app.organization, app.incidents, app.collectors, app.attacks,
                          app.investigation, app.event_catalog, app.threat_logs, app.clock_base), before)
        self.assertEqual((app.simulation.now, app.simulation.total_bytes, list(incident.timeline),
                          incident.following, app.camera_incident_id), facts)
        self.assertEqual({key: view.bounds for key, view in app.map_views.items()}, cameras)
        self.assertEqual((app.last_auto_zoom, app.last_map_interaction), (timers[0] + 30, timers[1] + 30))
        self.assertTrue(app.paused)
        self.assertFalse(monitor.audio.muted)
        self.assertTrue(app.camera_pinned)
        self.assertFalse(app.auto_follow)

    def test_seed_and_frame_cadence_reproduce_full_debrief(self):
        texts = []
        for fps in (15, 60):
            app = self.app()
            self.choose(app, "b")
            for _ in range(fps * 2):
                app.update(1 / fps)
            texts.append(self.review(app))
        self.assertEqual(texts[0], texts[1])

    def test_minimum_terminal_keeps_actions_scope_confirmation_and_debrief_accessible(self):
        for case in ("exfiltration", "benign", "partial"):
            app = self.app(case)
            app.canvas = monitor.Canvas(79, 24)
            app.draw()
            text = "\n".join("".join(row) for row in app.canvas.grid)
            for control in ("I inspect", "B peer", "L local", "J dismiss", "W wait", "H finish"):
                self.assertIn(control, text)
            app.handle_key("l")
            app.draw()
            text = "\n".join("".join(row) for row in app.canvas.grid)
            self.assertIn("PREVIEW: isolate endpoint=", text)
            self.assertIn("Enter CONFIRM scope", text)
            self.assertIn("including legitimate", text)
            app.handle_key("escape")
            self.review(app)
            app.draw()
            before = [row[:] for row in app.canvas.grid]
            app.handle_key("d")
            app.draw()
            self.assertNotEqual(before, app.canvas.grid)
            self.assertIn("Esc restore dashboard", "".join(app.canvas.grid[-1]))

    def test_authorized_without_dismissal_needs_no_containment(self):
        for waiting in (False, True):
            app = self.app("benign")
            if waiting:
                self.choose(app, "w")
            else:
                app.update(5)
            text = self.review(app)
            self.assertIn("Authorized transfer", text)
            self.assertNotIn("Unresolved", text)
            self.assertFalse(app.drill.incident.actions)

    def test_policy_against_approved_backup_is_false_positive_disruption(self):
        app = self.app("benign")
        self.choose(app, "w")
        self.choose(app, "l")
        app.update(2)
        backup = app.drill.incident.sessions[0]
        self.assertEqual((backup.state, backup.orig_bytes), ("isolated", 12000000))
        text = self.review(app)
        self.assertIn("False-positive response; authorized service disrupted", text)
        self.assertIn("Disrupted legitimate IDs: " + backup.identifier, text)

    def test_filter_editor_q_is_literal_and_quit_closes_exercise(self):
        app = self.app()
        drill = app.drill
        app.handle_key("i")
        app.handle_key("/")
        self.assertTrue(app.handle_key("q"))
        self.assertEqual(drill.world.investigation.filter_input, "q")
        self.assertFalse(app.handle_key("quit"))
        self.assertIsNone(app.drill)
        self.assertEqual(app.active_mode, "dashboard")


if __name__ == "__main__":
    unittest.main()
