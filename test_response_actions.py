"""Consequential scoped response, exact clocks, idempotency and policy fixtures."""

import unittest
from unittest.mock import patch

from test_monitor import monitor


class ResponseTests(unittest.TestCase):
    def app(self):
        with patch.object(monitor.time, "monotonic", return_value=0):
            app = monitor.CyberMonitor(initial_theme="ice", seed=12)
            app.start_critical_incident()
        app.simulation.automatic = app.incidents.automatic = False
        return app

    def test_bulk_block_exact_bytes_rates_buckets_map_and_preserved_evidence(self):
        app = self.app()
        app.update(49)
        incident, transfer = app.critical_incident, app.critical_incident.sessions[-1]
        original_evidence = list(incident.timeline)
        backup = app.simulation.create(app.organization.connect("FRA-BKP", "SIN-STORE", "BACKUP"))
        app.add_session_route(backup)
        legitimate = app.simulation.create(app.organization.connect("ATH-WS1", "FRA-APP", "HTTPS"))
        app.add_session_route(legitimate)
        action = app.incidents.request_response("block", "session", transfer.identifier)
        self.assertEqual(action.status, "requested")
        self.assertEqual(transfer.orig_bytes, 10000000)
        app.update(0.5)
        self.assertEqual(transfer.orig_bytes, 11000000)
        app.update(0.5)
        self.assertEqual((action.requested_at, action.applied_at, action.verified_at), (49, 50, None))
        self.assertEqual((transfer.orig_bytes, transfer.resp_bytes), (12000000, 60000))
        self.assertEqual((transfer.orig_rate, transfer.resp_rate, transfer.duration), (0, 0, 6))
        self.assertEqual(transfer.response_action_id, action.identifier)
        self.assertIn(transfer, app.simulation.history)
        self.assertNotIn(transfer, app.simulation.sessions)
        self.assertFalse(any(r.session is transfer for r in app.attacks))
        self.assertFalse(backup.complete)
        self.assertFalse(legitimate.complete)
        self.assertGreater(app.metrics["NET"], 32)  # final bulk + legitimate backup bucket
        app.update(1)
        self.assertEqual((action.status, action.verified_at), ("verified", 51))
        self.assertTrue(incident.contained)
        self.assertAlmostEqual(app.metrics["NET"], 16.08 + 0.576)
        app.canvas = monitor.Canvas(159, 48)
        app.draw_map(0, 8, 100, 25)
        colors = [color for row in app.canvas.colors for color in row]
        self.assertNotIn(app.palette["critical_trail"], colors)
        self.assertFalse(any(char == "◉" for row in app.canvas.grid for char in row))
        app.update(30)
        self.assertEqual((transfer.orig_bytes, transfer.resp_bytes), (12000000, 60000))
        self.assertTrue(all(e in incident.timeline for e in original_evidence))
        self.assertEqual(incident.disposition, "contained")
        self.assertEqual(round(sum(app.traffic_history) * 1000000 / 8), app.simulation.total_bytes)
        phases = [(e.stage, e.timestamp) for e in incident.timeline if e.action_id == action.identifier]
        self.assertEqual(phases, [("RESPONSE REQUESTED", 49), ("RESPONSE APPLIED", 50),
                                  ("RESPONSE VERIFIED", 51)])

    def test_repeated_commands_retry_and_render_increment_only_once(self):
        app = self.app()
        app.update(49)
        flow = app.critical_incident.sessions[-1].identifier
        for _ in range(3):
            app.process_shell_command("block session " + flow)
        action = app.critical_incident.actions[0]
        self.assertEqual(len(app.critical_incident.actions), 1)
        app.process_shell_command("retry " + action.identifier)
        app.update(2)
        for width, height in ((79, 24), (99, 35), (159, 48)):
            app.canvas = monitor.Canvas(width, height)
            for _ in range(5):
                app.draw()
                app.process_shell_command("retry " + action.identifier)
                app.process_shell_command("block session " + flow)
        self.assertEqual((app.blocked, app.response_counts), (1, {"block": 1, "isolate": 0, "revoke": 0}))
        self.assertEqual(len(app.critical_incident.actions), 1)
        self.assertEqual(len([e for e in app.critical_incident.timeline if e.action_id]), 3)
        app.process_shell_command("actions")
        text = "\n".join(app.shell_history)
        self.assertIn("requested=49.00 applied=50.0 verified=51.0", " ".join(text.split()))

    def test_peer_policy_preserves_legitimate_sessions_and_denies_future_peer(self):
        app = self.app()
        app.update(2)
        first = app.critical_incident.sessions[-1]
        normal = app.simulation.create(app.organization.connect("ATH-WS1", "FRA-APP", "HTTPS"))
        action = app.incidents.request_response("block", "peer", "ATH-WS1", "EXT-DXB")
        app.update(2)
        self.assertTrue(app.critical_incident.contained)
        self.assertEqual(first.state, "blocked")
        self.assertFalse(normal.complete)
        denied = app.simulation.create(app.organization.connect("ATH-WS1", "EXT-DXB", "HTTPS"))
        self.assertEqual((denied.state, denied.orig_bytes, denied.rate), ("denied", 0, 0))
        self.assertEqual(denied.response_action_id, action.identifier)
        self.assertIsNone(app.add_session_route(denied))
        app.update(70)
        self.assertEqual(len(app.incidents.history[-1].sessions), 1)  # future scenario stages cancelled
        self.assertEqual(len(app.attacks), 0)
        app.start_critical_incident()
        app.update(49)
        self.assertTrue(all(s.state == "denied" and s.orig_bytes == 0 for s in app.critical_incident.sessions))
        self.assertFalse(app.attacks)

    def test_endpoint_isolation_stops_benign_incoming_and_outgoing_only_local_target(self):
        app = self.app()
        app.update(49)
        sessions = [app.simulation.create(app.organization.connect(*endpoints, "HTTPS"))
                    for endpoints in (("ATH-WS1", "FRA-APP"), ("FRA-APP", "ATH-WS1"),
                                      ("REM-LON", "FRA-APP"))]
        action = app.incidents.request_response("isolate", "endpoint", "ATH-WS1")
        app.update(2)
        self.assertEqual([s.state for s in sessions], ["isolated", "isolated", "active"])
        self.assertEqual(len(action.affected_sessions), 3)
        self.assertEqual(app.response_counts["isolate"], 1)
        app.simulation.automatic = True
        app.update(500)
        self.assertLessEqual(len(app.attacks), app.simulation.MAX_ACTIVE)
        self.assertEqual({r.session.identifier for r in app.attacks},
                         {s.identifier for s in app.simulation.sessions})
        self.assertTrue(all("ATH-WS1" not in (s.connection.source_id, s.connection.peer_id)
                            for s in app.simulation.sessions))

    def test_credential_revocation_uses_explicit_credential_scope(self):
        app = self.app()
        app.update(49)
        same = app.simulation.create(app.organization.connect("ATH-WS1", "FRA-APP", "HTTPS"),
                                     credential_id="aster.ws1")
        other = app.simulation.create(app.organization.connect("ATH-WS1", "FRA-APP", "HTTPS"))
        action = app.incidents.request_response("revoke", "credential", "aster.ws1")
        app.update(2)
        self.assertEqual((same.state, other.state), ("revoked", "active"))
        future = app.simulation.create(app.organization.connect("ATH-WS1", "FRA-APP", "HTTPS"),
                                       credential_id="aster.ws1")
        self.assertEqual((future.state, future.response_action_id), ("denied", action.identifier))
        self.assertEqual(app.response_counts["revoke"], 1)
        app.update(23)
        app.start_critical_incident()
        repeated = app.critical_incident
        self.assertEqual(repeated.stage, "AUTH REJECTED")
        self.assertIn("credential remains revoked", repeated.timeline[0].message)
        app.update(49)
        self.assertTrue(all(s.state == "denied" and s.orig_bytes == 0 for s in repeated.sessions))
        self.assertFalse(any(e.stage == "UNUSUAL VOLUME" for e in repeated.timeline))
        self.assertEqual(repeated.stage, "TRANSFER STOPPED")

    def test_early_session_block_verifies_scope_but_later_recurrence_continues(self):
        app = self.app()
        app.update(2)
        first = app.critical_incident.sessions[-1]
        action = app.incidents.request_response("block", "session", first.identifier)
        app.update(2)
        self.assertEqual(action.status, "verified")
        self.assertFalse(app.critical_incident.contained)
        self.assertIn("future sessions remain outside", action.result)
        app.update(45)
        self.assertEqual(len(app.critical_incident.sessions), 4)
        self.assertEqual(app.critical_incident.sessions[-1].orig_bytes, 10000000)
        app.update(25)
        self.assertEqual(app.incidents.history[-1].disposition, "unresolved")

    def test_cancelled_request_has_no_effect_and_remote_invalid_targets_rejected(self):
        app = self.app()
        for command in ("isolate endpoint EXT-DXB", "block peer ATH-WS1 MISSING",
                        "revoke credential missing", "block session FLOW-99999"):
            app.process_shell_command(command)
            self.assertIn("Response error:", app.shell_history[-1])
        self.assertEqual(app.critical_incident.actions, [])
        action = app.incidents.request_response("isolate", "endpoint", "ATH-WS1")
        app.incidents.cancel_response(action.identifier)
        app.update(74)
        self.assertEqual((action.status, app.blocked, len(app.simulation.policies)), ("cancelled", 0, 0))
        self.assertEqual(app.incidents.history[-1].sessions[-1].orig_bytes, 60000000)

    def test_response_matches_large_advance_and_fps_partitions(self):
        apps = [self.app() for _ in range(3)]
        for app in apps:
            app.simulation.automatic = True
            app.update(49)
            app.incidents.request_response("block", "session", app.critical_incident.sessions[-1].identifier)
        apps[0].update(40)
        for fps, app in zip((15, 60), apps[1:]):
            for _ in range(40 * fps):
                app.update(1 / fps)
        def snapshot(app):
            incident = app.incidents.history[-1]
            return (app.simulation.total_bytes, list(app.traffic_history), list(incident.timeline),
                    incident.actions, app.response_counts, app.metrics,
                    [(s.identifier, s.orig_bytes, s.resp_bytes, s.state) for s in incident.sessions])
        self.assertEqual(snapshot(apps[0]), snapshot(apps[1]))
        self.assertEqual(snapshot(apps[0]), snapshot(apps[2]))

    def test_last_moment_request_consumes_final_boundary_then_finishes(self):
        for requested in (73.5, 73.999):
            app = self.app()
            app.update(requested)
            action = app.incidents.request_response("block", "session", app.critical_incident.sessions[-1].identifier)
            app.update(10)
            self.assertIsNone(app.critical_incident)
            self.assertEqual((action.applied_at, action.verified_at), (requested + 1, requested + 2))
            self.assertEqual(app.incidents.history[-1].finished_at, requested + 2)
            self.assertEqual(app.incidents.history[-1].sessions[-1].orig_bytes, 60000000)
            self.assertEqual(app.incidents.history[-1].disposition, "unresolved")
            self.assertIn("late/no matching", action.result)

    def test_action_limit_preserves_original_evidence_and_policy_state_is_bounded(self):
        app = self.app()
        app.update(49)
        original = list(app.critical_incident.timeline)
        for session in app.critical_incident.sessions:
            for kind in ("block", "revoke"):
                app.incidents.request_response(kind, "session", session.identifier)
        with self.assertRaisesRegex(ValueError, "limit"):
            app.incidents.request_response("isolate", "endpoint", "ATH-WS1")
        app.update(25)
        incident = app.incidents.history[-1]
        self.assertEqual(len(incident.actions), 8)
        self.assertTrue(all(observation in incident.timeline for observation in original))
        self.assertLessEqual(len(incident.timeline), 64)
        self.assertEqual(app.simulation.policies, {})

    def test_pause_speed_and_cancel_future_stage_policy_retain_clock(self):
        app = self.app()
        app.update(2)
        action = app.incidents.request_response("isolate", "endpoint", "ATH-WS1")
        app.paused = True
        app.update(100)
        self.assertEqual(action.status, "requested")
        app.paused = False
        app.speed_multiplier = 4
        app.update(0.5)
        self.assertEqual((action.applied_at, action.verified_at), (3, 4))
        app.update(18)
        incident = app.incidents.history[-1]
        self.assertEqual(len(incident.sessions), 1)
        self.assertEqual(incident.disposition, "contained")


if __name__ == "__main__":
    unittest.main()
