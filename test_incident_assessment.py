"""Evidence-dependent assessment and real delayed/partial/benign outcomes."""

import unittest
from unittest.mock import patch

from test_monitor import monitor


class AssessmentTests(unittest.TestCase):
    def app(self, variant="exfiltration", seed=12):
        with patch.object(monitor.time, "monotonic", return_value=0):
            app = monitor.CyberMonitor(initial_theme="ice", seed=seed)
            app.simulation.automatic = app.incidents.automatic = False
            app.start_critical_incident(variant)
        return app

    def test_benign_approval_weakens_confidence_dismissal_preserves_alert_and_transfer(self):
        app = self.app("benign")
        incident = app.critical_incident
        original = incident.timeline[0]
        self.assertEqual((incident.severity, incident.confidence, incident.disposition),
                         ("critical", "limited", "pending"))
        self.assertIn("queued job request", original.message)
        self.assertIn("no bytes measured yet", original.message)
        self.assertFalse(app.simulation.sessions)
        app.update(7)
        session = incident.sessions[0]
        self.assertEqual((session.service, session.orig_bytes), ("BACKUP", 10000000))
        self.assertEqual((incident.confidence, incident.assessment), ("low", "authorized transfer"))
        self.assertIn("owner approval matches JOB", incident.confidence_reason)
        self.assertIn("authorization contradicts", incident.timeline[-1].message)
        app.process_shell_command("dismiss approved JOB-FRA-SIN-001")
        app.process_shell_command("dismiss duplicate decision")
        self.assertEqual(len([e for e in incident.timeline if e.stage == "OPERATOR DISMISSED"]), 1)
        self.assertEqual((incident.disposition, app.blocked, incident.severity), ("dismissed", 0, "critical"))
        self.assertIn("authorized legitimate transfer continues", incident.residual_risk)
        app.update(10)
        self.assertEqual(session.orig_bytes, 30000000)
        self.assertFalse(session.complete)
        app.update(15)
        self.assertIsNone(app.critical_incident)
        self.assertEqual((session.orig_bytes, session.state), (60000000, "completed"))
        self.assertEqual(incident.disposition, "dismissed")
        self.assertIn(original, incident.timeline)
        self.assertEqual((original.confidence, original.assessment, original.severity),
                         ("limited", "suspected exfiltration", "critical"))

    def test_incorrect_dismissal_leaves_actual_activity_and_historical_risk(self):
        app = self.app()
        app.update(2)
        incident = app.incidents.dismiss("looks normal without checking evidence")
        app.update(47)
        transfer = incident.sessions[-1]
        self.assertEqual((incident.disposition, transfer.orig_bytes, incident.confidence),
                         ("dismissed", 10000000, "strong"))
        self.assertIn(transfer.identifier, incident.residual_risk)
        self.assertFalse(incident.contained)
        app.update(25)
        self.assertEqual(transfer.orig_bytes, 60000000)
        self.assertEqual(incident.disposition, "dismissed")
        self.assertIn("historical suspected data removal unresolved", incident.residual_risk)
        self.assertEqual(app.blocked, 0)

    def test_delayed_response_has_real_bytes_until_application_and_verification_window(self):
        app = self.app("delayed")
        app.update(49)
        incident, session = app.critical_incident, app.critical_incident.sessions[-1]
        action = app.incidents.request_response("block", "session", session.identifier)
        self.assertEqual((action.apply_delay, action.verify_delay), (5, 3))
        self.assertFalse(incident.contained)
        app.update(4)
        self.assertEqual((action.status, session.orig_bytes), ("requested", 18000000))
        app.paused = True
        app.update(100)
        self.assertEqual((app.simulation.now, action.status), (53, "requested"))
        app.paused = False
        app.speed_multiplier = 4
        app.update(0.25)
        self.assertEqual((action.applied_at, session.orig_bytes, session.rate), (54, 20000000, 0))
        self.assertFalse(incident.contained)
        app.update(0.5)
        self.assertEqual(action.status, "applied")
        app.update(0.25)
        self.assertEqual((action.verified_at, action.outcome, incident.disposition), (57, "contained", "contained"))
        self.assertTrue(incident.contained)
        self.assertEqual(incident.severity, "critical")

    def test_partial_action_verifies_scope_but_residual_asset_remains_active(self):
        app = self.app("partial")
        app.update(49)
        incident = app.critical_incident
        primary, alternate = incident.sessions[-2:]
        self.assertEqual((primary.connection.source_id, alternate.connection.source_id), ("ATH-WS1", "ATH-ADM"))
        self.assertEqual((primary.orig_bytes, alternate.orig_bytes), (10000000, 6000000))
        action = app.incidents.request_response("block", "peer", "ATH-WS1", "EXT-DXB")
        app.update(2)
        self.assertEqual((action.status, action.outcome, incident.disposition),
                         ("verified", "partial", "partially contained"))
        self.assertFalse(incident.contained)
        self.assertEqual((primary.orig_bytes, primary.rate, alternate.orig_bytes), (12000000, 0, 10000000))
        self.assertGreater(alternate.rate, 0)
        self.assertIn(alternate.identifier, action.result)
        self.assertIn(alternate.identifier, incident.residual_risk)
        self.assertTrue(any(r.session is alternate for r in app.attacks))
        app.canvas = monitor.Canvas(159, 48)
        app.draw_map(0, 8, 100, 25)
        self.assertTrue(any(char == "◉" for row in app.canvas.grid for char in row))
        app.update(25)
        self.assertEqual(alternate.orig_bytes, 60000000)
        self.assertEqual((incident.disposition, incident.severity), ("partially contained", "critical"))
        self.assertEqual(incident.timeline[-1].disposition, "partially contained")

    def test_partial_with_second_scoped_response_reaches_verified_containment(self):
        app = self.app("partial")
        app.update(49)
        incident = app.critical_incident
        primary, alternate = incident.sessions[-2:]
        first = app.incidents.request_response("block", "session", primary.identifier)
        app.update(2)
        self.assertEqual(first.outcome, "partial")
        second = app.incidents.request_response("revoke", "session", alternate.identifier)
        app.update(2)
        self.assertEqual((second.status, second.outcome), ("verified", "contained"))
        self.assertTrue(incident.contained)
        self.assertEqual(incident.disposition, "contained")
        self.assertEqual((primary.orig_bytes, alternate.orig_bytes), (12000000, 12000000))
        self.assertEqual(first.outcome, "partial")  # Historical verification is preserved.
        self.assertEqual(app.blocked, 2)
        app.update(23)
        self.assertEqual(incident.disposition, "contained")
        self.assertEqual(incident.severity, "critical")

    def test_stopping_alternate_keeps_primary_active_and_highlighted(self):
        app = self.app("partial")
        app.update(49)
        incident = app.critical_incident
        primary, alternate = incident.sessions[-2:]
        action = app.incidents.request_response("block", "session", alternate.identifier)
        app.update(2)
        self.assertEqual(action.outcome, "partial")
        self.assertEqual((primary.state, alternate.state), ("active", "blocked"))
        self.assertIs(incident.route.session, primary)
        self.assertGreater(incident.route.rate, 0)

    def test_benign_response_cannot_suppress_later_contradictory_approval(self):
        app = self.app("benign")
        app.update(2)
        incident = app.critical_incident
        session = incident.sessions[0]
        app.incidents.request_response("block", "session", session.identifier)
        app.update(2)
        self.assertTrue(incident.contained)
        self.assertEqual(session.orig_bytes, 2000000)
        app.update(3)
        self.assertEqual((incident.confidence, incident.assessment), ("low", "authorized transfer"))
        self.assertEqual(session.state, "blocked")
        self.assertEqual(incident.severity, "critical")
        self.assertIn("AUTHORIZATION MATCH", [e.stage for e in incident.timeline])

    def test_primary_isolation_before_alternate_stage_cannot_cancel_unprotected_asset(self):
        app = self.app("partial")
        app.update(2)
        action = app.incidents.request_response("isolate", "endpoint", "ATH-WS1")
        app.update(2)
        self.assertEqual(action.outcome, "partial")
        self.assertIn("ATH-ADM", action.result)
        self.assertFalse(app.critical_incident.contained)
        app.update(45)
        alternate = app.critical_incident.sessions[-1]
        self.assertEqual((alternate.connection.source_id, alternate.orig_bytes, alternate.state),
                         ("ATH-ADM", 6000000, "active"))
        self.assertEqual(app.critical_incident.stage, "UNUSUAL VOLUME")
        self.assertTrue(all(s.orig_bytes == 0 for s in app.critical_incident.sessions[1:-1]))

    def test_partial_reservation_failure_is_atomic_and_two_uploads_fit_at_capacity(self):
        with patch.object(monitor.time, "monotonic", return_value=0):
            app = monitor.CyberMonitor(initial_theme="ice", seed=12)
        app.simulation.automatic = app.incidents.automatic = False
        for _ in range(11):
            app.simulation.create(app.organization.connect("ATH-ADM", "FRA-APP", "SSH"))
        connection_number = app.organization._connection_number
        self.assertIsNone(app.start_critical_incident("partial"))
        self.assertEqual((app.incident_count, app.simulation.reserved_slots), (0, 0))
        self.assertEqual(app.organization._connection_number, connection_number)
        app.simulation.sessions.pop()
        app.start_critical_incident("partial")
        self.assertEqual(app.simulation.reserved_slots, 2)
        app.update(49)
        self.assertEqual(len(app.simulation.sessions), 12)
        self.assertEqual(len([s for s in app.critical_incident.sessions if not s.complete]), 2)

    def test_confidence_changes_only_on_delivered_observation_with_reason(self):
        app = self.app()
        incident, pending = app.critical_incident, []
        original = incident.timeline[0]
        deliver = app.incidents.deliver_observation
        with patch.object(app.incidents, "deliver_observation", side_effect=pending.append):
            app.update(2)
            app.incidents.observe("NEUTRAL SNAPSHOT", "neutral completion/status evidence")
        self.assertEqual((incident.confidence, len(incident.timeline)), ("limited", 1))
        deliver(pending[0])
        self.assertEqual(incident.confidence, "supported")
        self.assertTrue(pending[0].assessment_update)
        self.assertFalse(pending[1].assessment_update)
        deliver(pending[1])
        self.assertEqual(incident.confidence, "supported")
        self.assertIn("new peer outside", incident.confidence_reason)
        app.update(47)
        self.assertEqual(incident.confidence, "strong")
        self.assertIn("outbound bytes", incident.confidence_reason)
        self.assertEqual(original.confidence, "limited")
        self.assertEqual(original.severity, "critical")
        self.assertTrue(all(e.confidence_reason for e in incident.timeline))
        self.assertTrue(all(e.severity == "critical" for e in incident.timeline))
        with self.assertRaises(AttributeError):
            incident.severity = "low"

    def test_dashboard_separate_facts_and_timeline_console_at_minimum_width(self):
        app = self.app("benign")
        app.update(7)
        app.incidents.dismiss("approved schedule")
        for width, height in ((79, 24), (119, 40)):
            app.canvas = monitor.Canvas(width, height)
            app.draw()
            facts = "".join(app.canvas.grid[2])
            for text in ("Sev critical", "Conf low", "Disp dismissed", "Resp none"):
                self.assertIn(text, facts)
            self.assertIn("authorized transfer", "\n".join("".join(row) for row in app.canvas.grid))
        app.process_shell_command("timeline 3")
        self.assertIn("owner approval", "\n".join(app.shell_history))
        self.assertIn("confidence=low", "\n".join(app.shell_history))

    def test_late_policy_cannot_hide_naturally_completed_uncontained_alternate_transfer(self):
        app = self.app("partial")
        app.update(49)
        incident = app.critical_incident
        app.incidents.request_response("block", "session", incident.sessions[-2].identifier)
        app.update(26.5)
        late = app.incidents.request_response("block", "peer", "ATH-WS1", "EXT-DXB")
        app.update(5)
        self.assertFalse(incident.contained)
        self.assertEqual(incident.disposition, "partially contained")
        self.assertIn("uncontained completed transfers", late.result)
        self.assertEqual(incident.sessions[-1].orig_bytes, 60000000)

    def test_variants_match_large_advance_and_fps_partitions_with_same_actions(self):
        for variant in ("benign", "delayed", "partial", "exfiltration"):
            apps = [self.app(variant) for _ in range(3)]
            request_time = 7 if variant == "benign" else 49
            for app in apps:
                app.simulation.automatic = True
                app.update(request_time)
                if variant == "benign":
                    app.incidents.dismiss("approved job")
                else:
                    app.incidents.request_response("block", "session", app.critical_incident.sessions[-2 if variant == "partial" else -1].identifier)
            apps[0].update(40)
            for fps, app in zip((15, 60), apps[1:]):
                for _ in range(40 * fps):
                    app.update(1 / fps)
            def snapshot(app):
                incident = app.incidents.history[-1]
                return (app.simulation.total_bytes, list(app.traffic_history), list(incident.timeline),
                        incident.actions, incident.confidence, incident.confidence_reason,
                        incident.assessment, incident.disposition, incident.severity, app.response_counts)
            self.assertEqual(snapshot(apps[0]), snapshot(apps[1]), variant)
            self.assertEqual(snapshot(apps[0]), snapshot(apps[2]), variant)

    def test_seeded_manual_and_automatic_variant_selection_repeats(self):
        selections = []
        for _ in range(2):
            app = self.app("seeded", seed=12)
            variants = []
            for _ in range(24):
                variants.append(app.critical_incident.variant)
                app.update(app.critical_incident.LIFETIME)
                app.start_critical_incident("seeded")
            selections.append(variants)
        self.assertEqual(selections[0], selections[1])
        self.assertEqual(set(selections[0]), set(app.incidents.VARIANTS))
        a = self.app("seeded", seed=12)
        with patch.object(monitor.time, "monotonic", return_value=0):
            b = monitor.CyberMonitor(initial_theme="ice", seed=12)
        b.simulation.automatic = False
        b.critical_cooldown = 0
        b.incidents.process_boundary()
        self.assertEqual(a.critical_incident.variant, b.critical_incident.variant)
        self.assertEqual(list(a.critical_incident.timeline), list(b.critical_incident.timeline))


if __name__ == "__main__":
    unittest.main()
