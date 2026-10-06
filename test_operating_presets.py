"""Shared model pacing, captured compression and preset switches; no wall waits."""

from unittest.mock import patch
import unittest

from operating_presets import OperatingPresets
from test_monitor import monitor


class OperatingPresetTests(unittest.TestCase):
    def app(self, preset="operations", seed=12, utc="2026-01-01T00:00:00Z", automatic=True, speed=1):
        app = monitor.CyberMonitor(initial_theme="ice", seed=seed, initial_preset=preset,
                                   start_utc=utc, initial_speed=speed)
        app.incidents.automatic = automatic
        return app

    def snapshot(self, app):
        incidents = list(app.incidents.history) + ([app.critical_incident] if app.critical_incident else [])
        return (app.simulation.now, app.clock_base, app.preset, app.simulation.total_bytes,
                dict(app.simulation.collector_bytes), list(app.traffic_history), app.metrics,
                app.total_events, app.response_counts,
                [(i.identifier, i.variant, i.preset, i.timing_scale, i.started_at, i.finished_at,
                  i.disposition, list(i.timeline), [(s.identifier, s.started_at, s.lifetime, s.orig_bytes,
                  s.resp_bytes, s.state, s.timing_scale) for s in i.sessions],
                  [(a.identifier, a.requested_at, a.applied_at, a.verified_at, a.outcome, a.affected_sessions)
                   for a in i.actions]) for i in incidents])

    def test_operations_has_long_quiet_and_no_incident_without_actual_work(self):
        app = self.app(utc="2026-01-01T21:30:00Z")  # All sites quiet for the next two UTC hours.
        self.assertTrue(900 <= app.critical_cooldown <= 1200)
        with patch.object(app.incidents.pacing.rng, "random", return_value=0):
            app.update(7200)
        self.assertEqual((app.incident_count, app.simulation.total_bytes), (0, 0))
        self.assertIsNone(app.incidents.pacing.last_workload)
        self.assertGreater(app.incidents.next_start, app.simulation.now)

    def test_operations_opportunities_require_real_scheduled_sessions_and_chance(self):
        working = self.app()
        due = working.incidents.next_start
        with patch.object(working.incidents.pacing.rng, "random", return_value=0):
            working.update(due)
        self.assertEqual(working.incident_count, 1)
        self.assertAlmostEqual(working.critical_incident.started_at, due)
        activity = working.incidents.pacing.last_workload
        self.assertEqual(activity[2:], ("SIN-API", "morning"))
        self.assertLessEqual(due - activity[0], 60)
        quiet_chance = self.app()
        with patch.object(quiet_chance.incidents.pacing.rng, "random", return_value=1):
            quiet_chance.update(1800)
        self.assertGreater(quiet_chance.simulation.total_bytes, 0)
        self.assertEqual(quiet_chance.incident_count, 0)
        disabled = self.app()
        disabled.simulation.automatic = False
        with patch.object(disabled.incidents.pacing.rng, "random", return_value=0):
            disabled.update(1800)
        self.assertEqual(disabled.incident_count, 0)

    def test_showcase_bounded_family_rotation_benign_variety_and_no_overlap(self):
        for seed in (1, 12, 41):
            app = self.app("showcase", seed=seed)
            app.update(OperatingPresets.SHOWCASE_BOUND)
            history = list(app.incidents.history)
            self.assertGreaterEqual(len(history), 3)
            first = history[:3]
            self.assertEqual({i.family for i in first}, {"exfiltration", "credential-misuse", "lateral-movement"})
            self.assertEqual(sum(i.benign_alternative for i in first), 1)
            self.assertTrue(all(i.finished_at <= 90 and i.timing_scale == 0.1 for i in first))
            for before, after in zip(history, history[1:]):
                self.assertLessEqual(before.finished_at, after.started_at)
                self.assertTrue(all(s.complete for s in before.sessions))
            observations = [o.identifier for i in history for o in i.timeline]
            self.assertEqual(len(observations), len(set(observations)))
            self.assertLessEqual(len(app.incidents.pacing.bag), 3)
            self.assertLessEqual(len(app.simulation.sessions), app.simulation.MAX_ACTIVE)

    def test_compression_preserves_all_family_profile_integrals_and_actual_timings(self):
        for variant in monitor.IncidentSimulation.VARIANTS:
            apps = [self.app(preset, automatic=False) for preset in ("operations", "showcase")]
            for app in apps:
                app.simulation.automatic = False
                incident = app.start_critical_incident(variant)
                app.update(incident.LIFETIME)
                self.assertIsNone(app.critical_incident)
            normal, compact = (app.incidents.history[-1] for app in apps)
            self.assertEqual([(s.orig_bytes, s.resp_bytes, s.orig_pkts, s.resp_pkts) for s in normal.sessions],
                             [(s.orig_bytes, s.resp_bytes, s.orig_pkts, s.resp_pkts) for s in compact.sessions], variant)
            for full, short in zip(normal.sessions, compact.sessions):
                self.assertAlmostEqual(short.started_at, full.started_at * 0.1)
                self.assertAlmostEqual(short.lifetime, full.lifetime * 0.1)
            self.assertEqual([o.stage for o in normal.timeline], [o.stage for o in compact.timeline])
            for full, short in zip(normal.timeline, compact.timeline):
                self.assertAlmostEqual(short.timestamp, full.timestamp * 0.1)
            self.assertEqual(apps[0].simulation.total_bytes, apps[1].simulation.total_bytes)
            self.assertAlmostEqual(compact.finished_at, normal.finished_at * 0.1)
            self.assertTrue(all(s.complete for s in compact.sessions))

    def test_compressed_bulk_response_cutoff_actual_volume_buckets_and_idempotency(self):
        snapshots = []
        for mode, scale in (("operations", 1), ("showcase", 0.1)):
            app = self.app(mode, automatic=False)
            app.simulation.automatic = False
            incident = app.start_critical_incident()
            app.update(49 * scale)
            transfer = incident.sessions[-1]
            self.assertEqual(transfer.orig_bytes, 10000000)
            self.assertIn("10,000,000", incident.timeline[-1].message)
            action = app.incidents.request_response("block", "session", transfer.identifier)
            duplicate = app.incidents.request_response("block", "session", transfer.identifier)
            self.assertIs(duplicate, action)
            app.update(2 * scale)
            self.assertEqual((action.status, action.outcome, app.blocked), ("verified", "contained", 1))
            self.assertEqual(transfer.orig_bytes, 12000000)
            self.assertAlmostEqual(action.applied_at, 50 * scale)
            self.assertAlmostEqual(action.verified_at, 51 * scale)
            self.assertFalse(any(r.session is transfer for r in app.attacks))
            stopped = transfer.orig_bytes + transfer.resp_bytes
            app.update(30)
            self.assertEqual(transfer.orig_bytes + transfer.resp_bytes, stopped)
            self.assertAlmostEqual(sum(app.traffic_history) * 1000000 / 8, app.simulation.total_bytes, places=5)
            snapshots.append([(s.orig_bytes, s.resp_bytes) for s in incident.sessions])
        self.assertEqual(snapshots[0], snapshots[1])

    def test_delayed_apply_verify_and_benign_authorization_are_compressed(self):
        app = self.app("showcase", automatic=False)
        app.simulation.automatic = False
        incident = app.start_critical_incident("delayed")
        app.update(4.9)
        transfer = incident.sessions[-1]
        action = app.incidents.request_response("block", "session", transfer.identifier)
        self.assertEqual((action.apply_delay, action.verify_delay), (0.5, 0.3))
        app.update(0.8)
        self.assertAlmostEqual(action.applied_at, 5.4)
        self.assertAlmostEqual(action.verified_at, 5.7)
        self.assertEqual(transfer.orig_bytes, 20000000)
        benign = self.app("showcase", automatic=False)
        benign.simulation.automatic = False
        case = benign.start_critical_incident("benign")
        benign.update(0.7)
        self.assertEqual(case.assessment, "authorized transfer")
        self.assertEqual(case.sessions[0].schedule_context["job_id"], "JOB-FRA-SIN-001")
        self.assertTrue(any(o.stage == "AUTHORIZATION MATCH" and o.timestamp == 0.7 for o in case.timeline))
        benign.update(2.5)
        self.assertEqual(case.sessions[0].orig_bytes + case.sessions[0].resp_bytes, 60300000)

    def test_late_access_response_retains_prior_access_and_final_pending_action(self):
        app = self.app("showcase", automatic=False)
        app.simulation.automatic = False
        incident = app.start_critical_incident("credential-misuse")
        app.update(2.99)
        action = app.incidents.request_response("revoke", "credential", "aster.admin")
        app.update(0.01)  # All access completes at final stage, action still pending.
        self.assertIs(app.critical_incident, incident)
        self.assertTrue(all(s.complete for s in incident.sessions))
        totals = [(s.orig_bytes, s.resp_bytes) for s in incident.sessions]
        app.update(0.19)
        self.assertEqual(action.status, "verified")
        self.assertEqual(action.outcome, "partial")
        self.assertFalse(action.covers_incident)
        self.assertIn("completed access", action.result)
        self.assertEqual([(s.orig_bytes, s.resp_bytes) for s in incident.sessions], totals)
        self.assertIsNone(app.critical_incident)

    def test_switch_preserves_active_incident_sessions_pending_action_and_ordinary_sessions(self):
        app = self.app(automatic=False)
        incident = app.start_critical_incident()
        app.update(49)
        ordinary = next(s for s in app.simulation.sessions if not s.incident_id)
        ordinary_facts = (ordinary.started_at, ordinary.lifetime, ordinary.timing_scale, ordinary.segments)
        action = app.incidents.request_response("block", "session", incident.sessions[-1].identifier)
        evidence = list(incident.timeline)
        timing = (incident.STAGES, incident.planned_sessions, incident.LIFETIME)
        app.process_shell_command("preset showcase")
        self.assertEqual(app.preset, "showcase")
        self.assertIs(app.critical_incident, incident)
        self.assertEqual((incident.preset, incident.timing_scale), ("operations", 1))
        self.assertEqual((incident.STAGES, incident.planned_sessions, incident.LIFETIME), timing)
        self.assertEqual(list(incident.timeline), evidence)
        self.assertEqual((ordinary.started_at, ordinary.lifetime, ordinary.timing_scale, ordinary.segments), ordinary_facts)
        self.assertEqual((action.apply_delay, action.verify_delay), (1, 1))
        app.update(2)
        self.assertEqual((action.applied_at, action.verified_at, app.blocked), (50, 51, 1))
        app.update(23)
        self.assertIs(app.incidents.history[-1], incident)
        next_case = app.start_critical_incident("lateral-movement")
        self.assertEqual((next_case.preset, next_case.LIFETIME), ("showcase", 19.8))
        app.process_shell_command("preset operations")
        self.assertEqual(next_case.timing_scale, 0.1)
        app.update(19.8)
        self.assertIsNone(app.critical_incident)
        self.assertTrue(all(s.complete for s in next_case.sessions))
        self.assertEqual(app.incident_count, 2)

    def test_runtime_showcase_entry_restarts_finite_family_cycle_and_same_preset_is_noop(self):
        app = self.app("showcase")
        app.update(12)
        app.process_shell_command("preset operations")
        app.process_shell_command("preset showcase")
        current = app.critical_incident
        if current:
            app.update(current.LIFETIME - current.age)
        begin = len(app.incidents.history)
        app.update(90)
        cases = list(app.incidents.history)[begin:begin + 3]
        self.assertEqual({i.family for i in cases}, {"exfiltration", "credential-misuse", "lateral-movement"})
        facts = (app.incidents.next_start, list(app.incidents.pacing.bag),
                 app.incidents.pacing.pending_variant, app.total_events)
        app.process_shell_command("preset showcase")
        self.assertEqual((app.incidents.next_start, list(app.incidents.pacing.bag),
                          app.incidents.pacing.pending_variant, app.total_events), facts)

    def test_seeded_showcase_and_actions_are_invariant_to_fps_rendering_and_host_clock(self):
        with patch.object(monitor.time, "time", return_value=1000):
            a = self.app("showcase")
        with patch.object(monitor.time, "time", return_value=2000):
            b = self.app("showcase")
        a.update(90)
        for _ in range(1350):
            b.update(1 / 15)
            b.draw()
        self.assertEqual(self.snapshot(a), self.snapshot(b))
        apps = [self.app("showcase", automatic=False) for _ in range(2)]
        for app in apps:
            app.simulation.automatic = False
            app.start_critical_incident()
        apps[0].update(4.9)
        for _ in range(294):
            apps[1].update(1 / 60)
        for app in apps:
            transfer = app.critical_incident.sessions[-1]
            app.incidents.request_response("block", "session", transfer.identifier)
        apps[0].update(2.5)
        for _ in range(150):
            apps[1].update(1 / 60)
        self.assertEqual(self.snapshot(apps[0]), self.snapshot(apps[1]))

    def test_showcase_pause_speed_and_capacity_defer_without_consuming_candidate(self):
        paused = self.app("showcase", speed=4)
        paused.paused = True
        paused.update(90)
        self.assertEqual((paused.simulation.now, paused.incident_count), (0, 0))
        paused.paused = False
        paused.update(22.5)
        normal = self.app("showcase")
        normal.update(90)
        self.assertEqual(self.snapshot(paused), self.snapshot(normal))
        full = self.app("showcase")
        full.simulation.automatic = False
        for _ in range(full.simulation.MAX_ACTIVE):
            session = full.simulation.create(full.organization.connect("ATH-ADM", "FRA-APP", "SSH"), reserved=True)
            full.add_session_route(session)
        full.update(11)
        pending = full.incidents.pacing.pending_variant
        bag = list(full.incidents.pacing.bag)
        self.assertIsNotNone(pending)
        self.assertEqual(full.incident_count, 0)
        full.update(2)
        self.assertEqual((full.incidents.pacing.pending_variant, full.incidents.pacing.bag), (pending, bag))
        full.update(178)
        self.assertGreater(full.incident_count, 0)
        self.assertEqual(full.incidents.history[0].variant if full.incidents.history else full.critical_incident.variant, pending)

    def test_preset_controls_display_and_validation_at_minimum_size_with_incident_filters(self):
        app = self.app("showcase", automatic=False)
        app.start_critical_incident()
        app.update(4.9)
        app.investigation.filters.apply(app, "site=SITE-ATH")
        app.canvas = monitor.Canvas(79, 24)
        app.paused = True
        app.draw()
        frame = "\n".join("".join(row) for row in app.canvas.grid)
        for text in ("SHOWCASE", "P1 CT-001", "UNUSUAL VOLUME", "Sev critical", "Conf strong", "Resp", "Filters:", "Y/Z/Enter", "UTC"):
            self.assertIn(text, frame)
        app.process_shell_command("preset operations")
        self.assertIn("retains showcase x0.1 timing", "\n".join(app.shell_history))
        app.process_shell_command("preset wrong")
        self.assertEqual(app.preset, "operations")
        self.assertIn("Use preset", app.shell_history[-1])
        with self.assertRaises(ValueError):
            self.app("wrong")


if __name__ == "__main__":
    unittest.main()
