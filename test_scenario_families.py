"""Actual family traffic, scope coverage, contradictory evidence and replay."""

import unittest
from unittest.mock import patch

from test_monitor import monitor
from map_layers import layer_nodes


class ScenarioFamilyTests(unittest.TestCase):
    def app(self, variant=None, seed=12, **kwargs):
        with patch.object(monitor.time, "monotonic", return_value=0):
            app = monitor.CyberMonitor(initial_theme="ice", seed=seed, initial_scenario=variant, **kwargs)
        app.simulation.automatic = app.incidents.automatic = False
        return app

    def snapshot(self, app):
        incidents = list(app.incidents.history) + ([app.critical_incident] if app.critical_incident else [])
        return (app.simulation.now, app.simulation.total_bytes, list(app.traffic_history), app.metrics,
                app.response_counts, app.total_events, list(app.event_catalog.records),
                [(i.identifier, i.family, i.variant, i.disposition, i.confidence, i.assessment,
                  list(i.timeline), i.actions, [(s.identifier, s.connection, s.credential_id,
                                               s.orig_bytes, s.resp_bytes, s.state) for s in i.sessions])
                 for i in incidents])

    def test_three_families_have_distinct_patterns_linked_receipts_and_retained_details(self):
        patterns = []
        for variant, moment, lifetime, count in (("exfiltration", 49, 74, 4),
                                                ("credential-misuse", 20, 30, 3),
                                                ("lateral-movement", 22, 198, 3)):
            app = self.app(variant)
            incident = app.critical_incident
            app.update(moment)
            self.assertEqual(incident.family, variant)
            self.assertEqual(len(incident.sessions), count)
            self.assertEqual(incident.confidence, "strong")
            actual = [(s.connection.source_id, s.connection.peer_id, s.service, s.profile) for s in incident.sessions]
            patterns.append(actual)
            linked = [e for e in incident.timeline if e.session_id and e.stage != "SESSION FINISHED"]
            self.assertGreaterEqual(len(linked), 3)
            self.assertTrue(all(s.incident_id == incident.identifier for s in incident.sessions))
            self.assertTrue(all(e.incident_id == incident.identifier and e.received_at == e.timestamp for e in linked))
            self.assertEqual({e.session_id for e in linked}, {s.identifier for s in incident.sessions})
            self.assertTrue(all(e.identifier in {r.identifier for r in app.event_catalog.records} for e in linked))
            app.update(lifetime - moment)
            self.assertTrue(incident.complete)
            self.assertFalse(app.attacks)
            self.assertFalse(app.simulation.sessions)
            self.assertEqual(incident.finished_at, lifetime)
            self.assertEqual(incident.disposition, "unresolved")
            detail = "\n".join(app.investigation.incident_lines(app, incident))
            self.assertIn("family=" + variant, detail)
            self.assertIn("Planned network scope", detail)
            self.assertIn("RETAINED FINAL SUMMARY", detail)
            for session in incident.sessions:
                self.assertIs(app.investigation.find_session(app, session.identifier), session)
                self.assertIn(session.identifier, detail)
        self.assertEqual(len({tuple(p) for p in patterns}), 3)
        self.assertEqual([p[2] for p in patterns[1]], ["HTTPS"] * 3)
        self.assertEqual([p[2] for p in patterns[2]], ["SSH"] * 3)

    def test_credential_revoke_follows_identity_across_assets_but_spares_other_identity(self):
        app = self.app("credential-misuse")
        app.update(8)
        incident = app.critical_incident
        affected = list(incident.sessions)
        # Same asset and application, different credentials; no invented owner restriction.
        normal = app.simulation.create(app.organization.connect("ATH-WS1", "FRA-APP", "HTTPS"),
                                       credential_id="aster.ws1")
        matching = app.simulation.create(app.organization.connect("ATH-ADM", "FRA-APP", "SSH"),
                                         credential_id="aster.admin")
        action = app.incidents.request_response("revoke", "credential", "aster.admin")
        original = list(incident.timeline)
        app.update(2)
        self.assertEqual((action.applied_at, action.verified_at, action.outcome), (9, 10, "contained"))
        self.assertTrue(incident.contained)
        self.assertTrue(all(s.state == "revoked" and s.rate == 0 for s in affected + [matching]))
        self.assertEqual(normal.state, "active")
        self.assertEqual(len(action.affected_sessions), 3)
        totals = [(s.orig_bytes, s.resp_bytes) for s in affected]
        denied = app.simulation.create(app.organization.connect("REM-UNK", "SIN-API", "HTTPS"),
                                       credential_id="aster.admin")
        self.assertEqual((denied.state, denied.orig_bytes, denied.response_action_id), ("denied", 0, action.identifier))
        self.assertIn("prior authentications retained", action.result)
        app.update(20)
        self.assertEqual([(s.orig_bytes, s.resp_bytes) for s in affected], totals)
        self.assertEqual(len(incident.sessions), 2)  # covered future stages cancelled
        self.assertTrue(all(e in incident.timeline for e in original))
        self.assertEqual(incident.disposition, "contained")

    def test_credential_session_and_peer_scope_leave_other_assets_and_plans(self):
        for scope in ("session", "peer", "endpoint"):
            app = self.app("credential-misuse")
            app.update(2)
            incident, first = app.critical_incident, app.critical_incident.sessions[0]
            action = app.incidents.request_response("block" if scope != "endpoint" else "isolate", scope,
                                                   first.identifier if scope == "session" else "REM-UNK",
                                                   "FRA-APP" if scope == "peer" else "")
            app.update(2)
            self.assertEqual(action.outcome, "partial")
            self.assertFalse(incident.contained)
            self.assertIn("ATH-WS1>SIN-API credential=aster.admin", action.result)
            app.update(16)
            second, third = incident.sessions[1:]
            self.assertEqual(second.connection.source_id, "ATH-WS1")
            self.assertGreater(second.orig_bytes, 0)
            self.assertEqual(third.state, "denied" if scope == "endpoint" else "active")
            self.assertEqual(incident.disposition, "partially contained")

    def test_lateral_isolating_first_source_does_not_protect_later_hops(self):
        app = self.app("lateral-movement")
        app.update(2)
        incident = app.critical_incident
        first = app.incidents.request_response("isolate", "endpoint", "ATH-WS1")
        app.update(2)
        self.assertEqual(first.outcome, "partial")
        self.assertIn("FRA-APP>SIN-API credential=aster.admin", first.result)
        self.assertIn("SIN-API>FRA-BKP credential=aster.admin", first.result)
        app.update(18)
        self.assertEqual([s.state for s in incident.sessions], ["isolated", "active", "active"])
        self.assertEqual([s.service for s in incident.sessions], ["SSH"] * 3)
        self.assertEqual([s.started_at for s in incident.sessions], [2, 10, 18])
        self.assertTrue(all(s.rate > 0 for s in incident.sessions[1:]))
        app.map_layer = "incidents"
        nodes = layer_nodes(app)
        self.assertTrue(all(nodes[code].symbol == "◆" for code in ("ATH", "FRA", "SIN")))
        second = app.incidents.request_response("revoke", "credential", "aster.admin")
        app.update(2)
        self.assertEqual(second.outcome, "contained")
        self.assertEqual([s.state for s in incident.sessions], ["isolated", "revoked", "revoked"])
        self.assertEqual((first.outcome, app.response_counts), ("partial", {"block": 0, "isolate": 1, "revoke": 1}))
        self.assertFalse(app.attacks)
        app.update(198 - app.simulation.now)
        self.assertEqual(incident.disposition, "contained")
        self.assertEqual(incident.actions, [first, second])

    def test_lateral_middle_asset_isolation_covers_two_hops_not_third(self):
        app = self.app("lateral-movement")
        app.update(10)
        incident = app.critical_incident
        action = app.incidents.request_response("isolate", "endpoint", "FRA-APP")
        app.update(2)
        self.assertEqual(action.outcome, "partial")
        self.assertEqual(len(action.affected_sessions), 2)
        self.assertEqual(app.incidents.unprotected_future(incident), [("SIN-API", "FRA-BKP", "aster.admin")])
        app.update(10)
        self.assertEqual(incident.sessions[-1].state, "active")
        self.assertIn(incident.sessions[-1].identifier, incident.residual_risk)

    def test_lateral_session_peer_and_single_credential_response_only_match_actual_scope(self):
        for kind, scope, target, peer, expected in (
                ("block", "session", None, "", ["blocked", "active", "active"]),
                ("block", "peer", "FRA-APP", "SIN-API", ["active", "blocked", "active"]),
                ("revoke", "credential", "aster.admin", "", ["active", "revoked", "revoked"])):
            app = self.app("lateral-movement")
            app.update(22)
            incident = app.critical_incident
            target = target or incident.sessions[0].identifier
            action = app.incidents.request_response(kind, scope, target, peer)
            app.update(2)
            self.assertEqual([s.state for s in incident.sessions], expected)
            self.assertEqual((action.status, action.outcome, incident.contained), ("verified", "partial", False))
            for s in incident.sessions:
                if not s.complete:
                    self.assertIn(s.identifier, action.result)

    def test_benign_alternative_for_every_family_matches_actual_authorization_and_keeps_evidence(self):
        for variant, moment, assessment, record in (
                ("benign", 7, "authorized transfer", "JOB-FRA-SIN-001"),
                ("credential-benign", 20, "authorized credential use", "DELEGATION-001"),
                ("lateral-benign", 22, "authorized administration", "MAINT-001")):
            app = self.app(variant)
            incident = app.critical_incident
            original = incident.timeline[0]
            app.update(moment)
            self.assertEqual((incident.confidence, incident.assessment), ("low", assessment))
            self.assertIn(record, incident.confidence_reason)
            self.assertIn("authorization contradicts", incident.timeline[-1].message)
            app.incidents.dismiss("approved " + record)
            before = app.simulation.total_bytes
            app.update(1)
            self.assertGreater(app.simulation.total_bytes, before)
            self.assertEqual((app.blocked, incident.severity), (0, "critical"))
            app.update(incident.LIFETIME - app.simulation.now)
            self.assertEqual(incident.disposition, "dismissed")
            self.assertIn(original, incident.timeline)
            self.assertTrue(all(s.state == "completed" for s in incident.sessions))
            self.assertIn("authorized", incident.residual_risk)

    def test_early_response_preserves_new_benign_confirmation_and_actual_collateral(self):
        for variant, moment in (("credential-benign", 20), ("lateral-benign", 22)):
            app = self.app(variant)
            app.update(2)
            incident = app.critical_incident
            action = app.incidents.request_response("revoke", "credential", "aster.admin")
            app.update(2)
            self.assertTrue(incident.contained)
            self.assertEqual(action.outcome, "contained")
            app.update(moment - app.simulation.now)
            self.assertEqual(incident.confidence, "low")
            self.assertEqual([s.state for s in incident.sessions], ["revoked", "denied", "denied"])
            self.assertIn("AUTHORIZATION MATCH", [e.stage for e in incident.timeline])
            self.assertEqual(incident.severity, "critical")

    def test_benign_approval_requires_exact_actual_service_and_scopes(self):
        for variant, moment in (("credential-benign", 20), ("lateral-benign", 22)):
            app = self.app(variant)
            incident = app.critical_incident
            incident.authorization["services"] = ("DNS",) * 3
            app.update(moment)
            self.assertEqual(incident.confidence, "supported")
            self.assertTrue(incident.assessment.startswith("suspected "))
            self.assertEqual(incident.timeline[-1].stage, "APPROVAL MISMATCH")

    def test_existing_revocation_denies_reused_identity_without_claiming_success(self):
        app = self.app("credential-misuse")
        app.update(2)
        app.incidents.request_response("revoke", "credential", "aster.admin")
        app.update(28)
        incident = app.start_critical_incident("credential-misuse")
        self.assertEqual(incident.stage, "AUTH REJECTED")
        app.update(20)
        self.assertEqual([s.state for s in incident.sessions], ["denied"] * 3)
        self.assertTrue(all(s.orig_bytes == 0 and s.resp_bytes == 0 for s in incident.sessions))
        self.assertEqual(incident.confidence, "limited")
        self.assertEqual(incident.timeline[-1].stage, "ACCESS PREVENTED")
        self.assertFalse(any("accepts credential" in e.message for e in incident.timeline))

    def test_unrelated_credential_action_never_claims_generic_family_containment(self):
        for variant in ("credential-misuse", "lateral-movement"):
            app = self.app(variant)
            app.update(2)
            incident = app.critical_incident
            action = app.incidents.request_response("revoke", "credential", "aster.backup")
            app.update(2)
            self.assertEqual((action.status, action.outcome, action.affected_sessions), ("verified", "no incident effect", ()))
            self.assertFalse(incident.contained)
            self.assertEqual(incident.sessions[0].state, "active")

    def test_late_policy_does_not_erase_naturally_finished_access_or_hop(self):
        for variant, moment, kind, scope, target in (
                ("credential-misuse", 20, "revoke", "credential", "aster.admin"),
                ("lateral-movement", 183, "isolate", "endpoint", "SIN-API")):
            app = self.app(variant)
            app.update(moment)
            incident = app.critical_incident
            finished = [s for s in incident.sessions if s.state == "completed"]
            self.assertTrue(finished)
            action = app.incidents.request_response(kind, scope, target)
            app.update(2)
            self.assertEqual((action.outcome, incident.contained), ("partial", False))
            self.assertIn("uncontained completed access sessions", action.result)
            self.assertTrue(all(s.identifier in action.result for s in finished))

    def test_long_ssh_lifetime_completion_routes_and_last_boundary_action(self):
        app = self.app("lateral-movement")
        app.update(74)
        incident = app.critical_incident
        self.assertFalse(incident.complete)
        self.assertEqual(len(app.attacks), 3)
        app.draw()
        app.update(108)
        self.assertEqual([s.state for s in incident.sessions], ["completed", "active", "active"])
        self.assertTrue(any(e.stage == "SESSION FINISHED" and e.timestamp == 182 for e in incident.timeline))
        app.update(15.5)
        action = app.incidents.request_response("block", "session", incident.sessions[-1].identifier)
        app.update(10)
        self.assertEqual((action.applied_at, action.verified_at, incident.finished_at), (198.5, 199.5, 199.5))
        self.assertFalse(incident.contained)
        self.assertFalse(app.attacks)
        completions = [e.timestamp for e in incident.timeline if e.stage == "SESSION FINISHED"]
        self.assertEqual(completions, [182, 190, 198])

    def test_unknown_geography_has_no_fabricated_route_and_banner_camera_work_at_minimum_size(self):
        app = self.app("credential-misuse")
        incident = app.critical_incident
        self.assertIsNone(incident.route.src_city)
        self.assertEqual(incident.position(), app.organization.cities["FRA"][:2])
        for moment in (0, 3, 9, 17, 30):
            app.update(moment - app.simulation.now)
            for width, height in ((79, 24), (119, 40)):
                app.canvas = monitor.Canvas(width, height)
                app.draw()
                screen = "\n".join("".join(row) for row in app.canvas.grid)
                if moment < 30:
                    self.assertIn("credential-misuse", "".join(app.canvas.grid[1]))
                if moment in (0, 3, 17):
                    self.assertNotIn("◉", screen)
                app.update_map(now=moment + 0.5)
            self.assertIsNone(app.organization.city_for("REM-UNK"))

    def test_reservation_is_atomic_and_three_concurrent_ssh_hops_fit_capacity(self):
        app = self.app()
        for _ in range(10):
            app.simulation.create(app.organization.connect("ATH-ADM", "FRA-APP", "SSH"))
        number = app.organization._connection_number
        self.assertIsNone(app.start_critical_incident("lateral-movement"))
        self.assertEqual((app.incident_count, app.simulation.reserved_slots, app.organization._connection_number), (0, 0, number))
        app.simulation.sessions.pop()
        incident = app.start_critical_incident("lateral-movement")
        self.assertEqual(app.simulation.reserved_slots, 3)
        app.update(22)
        self.assertEqual((len(app.simulation.sessions), len(incident.sessions)), (12, 3))

    def test_seeded_scheduler_and_manual_path_replay_for_every_new_family(self):
        for variant in monitor.IncidentSimulation.VARIANTS:
            a, b = self.app(), self.app()
            a.start_critical_incident(variant)
            b.incidents.automatic = True
            b.critical_cooldown = 0
            with patch.object(b.incidents.variant_rng, "choice", return_value=variant):
                b.incidents.process_boundary()
            b.incidents.automatic = False
            for app in (a, b):
                app.update(app.critical_incident.LIFETIME)
            self.assertEqual(self.snapshot(a), self.snapshot(b), variant)

    def test_large_advance_equals_render_partitions_with_actions_pause_and_speed(self):
        for variant in ("credential-misuse", "lateral-movement", "credential-benign", "lateral-benign"):
            apps = [self.app(variant) for _ in range(3)]
            for app in apps:
                app.simulation.automatic = True
                app.update(2)
                incident = app.critical_incident
                app.incidents.request_response("block", "session", incident.sessions[0].identifier)
                app.paused = True
                before = self.snapshot(app)
                app.update(100)
                self.assertEqual(before, self.snapshot(app))
                app.paused = False
            apps[0].update(204)
            for fps, app in zip((15, 60), apps[1:]):
                app.speed_multiplier = 4
                for _ in range(204 * fps // 4):
                    app.update(1 / fps)
            self.assertEqual(self.snapshot(apps[0]), self.snapshot(apps[1]), variant)
            self.assertEqual(self.snapshot(apps[0]), self.snapshot(apps[2]), variant)
            incident = apps[0].incidents.history[-1]
            self.assertEqual(len({e.identifier for e in incident.timeline}), len(incident.timeline))
            self.assertEqual(len(incident.actions), 1)
            self.assertEqual(apps[0].blocked, 1)

    def test_console_select_preview_and_shortcuts_keep_default_exfiltration(self):
        for variant in ("credential-misuse", "lateral-movement", "credential-benign", "lateral-benign"):
            app = self.app()
            app.process_shell_command("scenario " + variant)
            incident = app.critical_incident
            app.process_shell_command("response")
            output = "\n".join(app.shell_history)
            self.assertIn("Family: " + incident.family, output)
            for plan in incident.planned_sessions:
                self.assertIn(f"block peer {plan.source_id} {plan.peer_id}", output)
                self.assertIn("revoke credential " + plan.credential_id, output)
            app.handle_key("f")
            app.process_shell_command("scenario exfiltration")
            self.assertIs(app.critical_incident, incident)
            self.assertEqual(app.incident_count, 1)
        app = self.app()
        app.handle_key("f")
        self.assertEqual(app.critical_incident.variant, "exfiltration")


if __name__ == "__main__":
    unittest.main()
