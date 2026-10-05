"""Heartbeat, bounded delivery, delayed evidence and recovery clock fixtures."""

from dataclasses import replace
import unittest
from unittest.mock import patch

from collector_model import CollectorSimulation
from test_monitor import monitor


class CollectorTests(unittest.TestCase):
    def simulation(self):
        delivered, lost = [], []
        model = CollectorSimulation({"COL-ATH": None, "COL-FRA": None}, delivered.append, lost.append)
        return model, delivered, lost

    def test_heartbeat_thresholds_and_large_direct_advance_never_rewind(self):
        model, _, _ = self.simulation()
        health = model.set_mode("COL-ATH", "outage", 0)
        self.assertEqual(health.state, "delayed")
        model.advance_to(5.999)
        self.assertEqual(health.state, "delayed")
        model.advance_to(6)
        self.assertEqual(health.state, "stale")
        model.advance_to(10)
        self.assertEqual(health.state, "offline")
        self.assertEqual((health.last_heartbeat, model.collectors["COL-FRA"].last_heartbeat), (0, 10))
        model.advance_to(200)
        self.assertGreater(model.next_boundary(), model.now)
        self.assertEqual(model.collectors["COL-FRA"].last_heartbeat, 200)
        with self.assertRaisesRegex(ValueError, "backwards"):
            model.set_mode("COL-ATH", "recovering", 20)

    def test_overflow_duplicate_queue_and_exact_rate_limited_recovery(self):
        model, delivered, lost = self.simulation()
        health = model.set_mode("COL-ATH", "outage", 0)
        for index in range(70):
            model.submit("COL-ATH", 0, "test", index, f"E-{index}")
        self.assertEqual((len(health.queue), health.dropped, len(lost)), (32, 38, 38))
        self.assertEqual(delivered, [])
        model.submit("COL-ATH", 0, "test", "duplicate", "E-0")
        self.assertEqual(health.submitted, 70)
        model.set_mode("COL-ATH", "recovering", 10)
        self.assertEqual(health.state, "recovering")
        model.advance_to(10.499)
        self.assertEqual(delivered, [])
        model.advance_to(11)
        self.assertEqual([e.received_at for e in delivered], [10.5, 11])
        model.advance_to(26)
        self.assertEqual([e.payload for e in delivered], list(range(32)))
        self.assertEqual([e.received_at for e in delivered], [10 + (index + 1) * 0.5 for index in range(32)])
        self.assertTrue(all(e.occurred_at == 0 for e in delivered))
        self.assertEqual((health.state, len(health.queue), health.processed), ("healthy", 0, 32))
        self.assertGreater(model.next_boundary(), model.now)
        model.advance_to(100)
        self.assertEqual(len(delivered), 32)
        self.assertEqual(model.metrics()["loss_percent"], 0)
        self.assertIsNone(model.metrics()["p95_ms"])
        self.assertEqual(health.dropped, 38)  # Lifetime loss survives window expiry.

    def test_p95_defined_window_count_bound_and_event_loss(self):
        model, _, _ = self.simulation()
        health = model.set_mode("COL-ATH", "delayed", 0, delay=3)
        for index in range(4):
            model.submit("COL-ATH", 0, "test", index)
        model.advance_to(4.5)
        self.assertEqual([lag for _, lag in health.samples], [3, 3.5, 4, 4.5])
        self.assertEqual(model.metrics()["p95_ms"], 4500)
        model.set_mode("COL-ATH", "recovering", 4.5)
        for index in range(300):
            model.submit("COL-ATH", 4.5, "test", index)
        self.assertEqual(len(health.samples), 256)
        model.advance_to(65)
        self.assertIsNone(model.metrics()["p95_ms"])

    def test_payload_load_uses_observed_collector_bytes_and_missing_outage_measurement(self):
        model, _, _ = self.simulation()
        model.advance_to(1)
        model.sample_payload({"COL-ATH": 2010000})
        health = model.collectors["COL-ATH"]
        self.assertEqual(health.observed_payload_rate, 16.08)
        self.assertGreater(health.cpu, 18)
        model.set_mode("COL-ATH", "outage", 1)
        model.advance_to(2)
        model.sample_payload({"COL-ATH": 4020000})
        self.assertIsNone(health.observed_payload_rate)
        model.set_mode("COL-ATH", "recovering", 2)
        model.advance_to(3)
        model.sample_payload({"COL-ATH": 6030000})
        self.assertEqual(health.observed_payload_rate, 16.08)  # No invented payload catchup.

    def test_fractional_recovery_keeps_partially_blind_payload_bucket_missing(self):
        model, delivered, _ = self.simulation()
        model.advance_to(0.1)
        health = model.set_mode("COL-ATH", "outage", 0.1)
        model.submit("COL-ATH", 0.1, "test", "DNS started")
        model.advance_to(0.3)
        model.submit("COL-ATH", 0.3, "test", "DNS completed")
        model.set_mode("COL-ATH", "recovering", 0.8)
        model.advance_to(1)
        model.sample_payload({"COL-ATH": 292})
        self.assertEqual(delivered, [])
        self.assertIsNone(health.observed_payload_rate)
        self.assertAlmostEqual(health.cpu, 18.3)  # Backlog work only; no invented payload work.
        model.advance_to(2)
        model.sample_payload({"COL-ATH": 584})
        self.assertEqual(health.observed_payload_rate, 0.002336)


class CollectorDashboardTests(unittest.TestCase):
    def app(self, speed=1):
        with patch.object(monitor.time, "monotonic", return_value=0):
            app = monitor.CyberMonitor(initial_theme="ice", initial_speed=speed, seed=12)
        app.simulation.automatic = app.incidents.automatic = False
        return app

    def outage(self, app, identifier="COL-ATH"):
        app.process_shell_command("outage " + identifier)

    def test_offline_before_start_hides_stage_evidence_confidence_feed_but_traffic_continues(self):
        app = self.app()
        self.outage(app)
        before_events = app.total_events
        incident = app.start_critical_incident()
        app.update(49)
        self.assertEqual((incident.confidence, incident.assessment, incident.visible_stage),
                         ("unobserved", "awaiting evidence", "EVIDENCE PENDING"))
        self.assertFalse(incident.timeline)
        self.assertIn("no delivered evidence", incident.residual_risk)
        self.assertEqual(app.total_events, before_events)
        self.assertEqual(incident.sessions[-1].orig_bytes, 10000000)
        self.assertEqual(app.metrics["NET"], 16.08)
        health = app.collectors.collectors["COL-ATH"]
        self.assertEqual((health.state, app.sensors_online), ("offline", 127))
        self.assertIsNone(health.observed_payload_rate)
        app.canvas = monitor.Canvas(79, 24)
        app.draw()
        banner = "".join(app.canvas.grid[1])
        self.assertIn("EVIDENCE PENDING", banner)
        self.assertIn("COVERAGE GAP", banner)
        self.assertNotIn("UNUSUAL VOLUME", banner)
        app.canvas = monitor.Canvas(159, 48)
        app.draw_map(0, 8, 100, 25)
        cx, cy = monitor.project(*app.organization.cities["ATH"][:2], 96, 21, app.map_views["WORLD"].bounds)
        self.assertEqual(app.canvas.grid[10 + round(cy)][2 + round(cx)], "x")
        app.process_shell_command("flows")
        self.assertIn("fresh observations unavailable", "\n".join(app.shell_history))

    def test_ordinary_start_completion_and_denial_logs_use_collector_receipts(self):
        app = self.app()
        self.outage(app)
        initial = app.total_events
        route = app.trigger_attack(app.organization.connect("ATH-WS1", "FRA-DNS", "DNS"))
        app.update(1)
        self.assertTrue(route.session.complete)
        self.assertEqual(app.total_events, initial)
        health = app.collectors.collectors["COL-ATH"]
        self.assertEqual(len(health.queue), 2)
        app.process_shell_command("recover COL-ATH")
        app.update(1)
        received = [row[3] for row in app.threat_logs if "FLOW-00001" in row[3]]
        self.assertEqual(len(received), 2)
        self.assertTrue(any("occurred=0.00 received=1.50" in line for line in received))
        self.assertTrue(any("occurred=0.20 received=2.00" in line for line in received))
        self.assertEqual(health.state, "healthy")

    def test_recovery_routes_archived_incident_while_new_incident_active(self):
        app = self.app()
        self.outage(app)
        original = app.start_critical_incident()
        app.update(74)
        self.assertIsNone(app.critical_incident)
        self.assertEqual((original.confidence, len(original.timeline)), ("unobserved", 0))
        current = app.start_critical_incident()
        app.process_shell_command("recover COL-ATH")
        app.update(0.5)
        self.assertEqual(len(original.timeline), 1)
        self.assertEqual(len(current.timeline), 0)
        self.assertEqual(original.timeline[0].received_at, 74.5)
        self.assertEqual(current.confidence, "unobserved")
        app.update(6)
        self.assertEqual(original.confidence, "strong")
        self.assertEqual(original.disposition, "unresolved")
        self.assertTrue(all(e.incident_id == original.identifier for e in original.timeline))
        self.assertTrue(all(e.incident_id == current.identifier for e in current.timeline))
        self.assertEqual([e.timestamp for e in original.timeline], sorted(e.timestamp for e in original.timeline))

    def test_old_cross_collector_assessment_cannot_reverse_newer_evidence(self):
        app = self.app()
        incident = app.start_critical_incident("partial")
        original = incident.timeline[0]
        self.outage(app)
        app.update(46)
        self.assertEqual(incident.confidence, "limited")  # Both Athens assets use the interrupted collector.
        newest = replace(original, identifier=incident.identifier + "-OBS-90", timestamp=46,
                         confidence="strong", assessment="suspected exfiltration", confidence_reason="new independent volume evidence",
                         assessment_update=True, collector_id="COL-FRA", source_id="FRA-APP", stage="UNUSUAL VOLUME")
        app.submit_observation(newest)
        self.assertEqual(incident.confidence, "strong")
        app.process_shell_command("recover COL-ATH")
        app.update(10)
        # The real volume observation at49 may supersede the synthetic independent observation;
        # old queued peer/recurrence evidence cannot reduce support after its receipt.
        self.assertEqual(incident.confidence, "strong")
        self.assertGreaterEqual(incident._assessment_time[0], 46)
        self.assertEqual(incident.timeline[0], original)

    def test_delayed_ingestion_has_live_heartbeats_and_exact_receipt_times(self):
        app = self.app()
        app.process_shell_command("delay COL-ATH 3")
        incident = app.start_critical_incident()
        app.update(2)
        health = app.collectors.collectors["COL-ATH"]
        self.assertEqual((health.state, health.last_heartbeat), ("delayed", 2))
        self.assertEqual(incident.confidence, "unobserved")
        app.update(1)
        self.assertEqual((incident.timeline[0].timestamp, incident.timeline[0].received_at), (0, 3))
        self.assertEqual((incident.confidence, incident.visible_stage), ("limited", "AUTH ANOMALY"))
        app.update(2)
        self.assertEqual((incident.timeline[-1].timestamp, incident.timeline[-1].received_at), (2, 5))
        self.assertEqual(incident.confidence, "supported")
        app.process_shell_command("collectors COL-ATH")
        self.assertIn("heartbeat=4.00", "\n".join(app.shell_history))
        before = app.collectors.collectors["COL-ATH"].mode
        for command in ("outage MISSING", "delay COL-ATH nan", "delay COL-ATH 0"):
            app.process_shell_command(command)
        self.assertEqual(app.collectors.collectors["COL-ATH"].mode, before)

    def test_session_action_receipts_identify_alternate_target_and_compact_service_survives(self):
        app = self.app()
        incident = app.start_critical_incident("partial")
        app.update(49)
        alternate = incident.sessions[-1]
        action = app.incidents.request_response("block", "session", alternate.identifier)
        for width, height in ((79, 24), (119, 40)):
            app.canvas = monitor.Canvas(width, height)
            app.draw_flows(0, 0, 28, 8)
            text = "\n".join("".join(row) for row in app.canvas.grid)
            self.assertIn("HTTPS R ATH:adm>EXT:peer", text)
        app.update(2)
        phases = [e for e in incident.timeline if e.action_id == action.identifier]
        self.assertEqual(len(phases), 3)
        self.assertTrue(all((e.source_id, e.peer_id, e.collector_id, e.session_id) ==
                            ("ATH-ADM", "EXT-DXB", "COL-ATH", alternate.identifier) for e in phases))

    def test_dedup_and_unknown_evicted_incident_are_explicit_without_wrong_attachment(self):
        app = self.app()
        incident = app.start_critical_incident()
        original = incident.timeline[0]
        count = app.total_events
        app.submit_observation(original)
        self.assertEqual(app.total_events, count)
        orphan = replace(original, identifier="CT-999-OBS-01", incident_id="CT-999", received_at=None)
        app.submit_observation(orphan)
        self.assertEqual(len(incident.timeline), 1)
        self.assertIn("Unknown/evicted incident CT-999", app.threat_logs[-1][3])
        self.assertEqual(len(app.incidents.delivery_errors), 1)

    def test_response_effects_are_exact_despite_delayed_verification_evidence(self):
        app = self.app()
        incident = app.start_critical_incident()
        app.update(49)
        self.outage(app)
        action = app.incidents.request_response("block", "session", incident.sessions[-1].identifier)
        timeline = list(incident.timeline)
        app.update(2)
        self.assertEqual((action.applied_at, action.verified_at, app.blocked), (50, 51, 1))
        self.assertEqual(incident.sessions[-1].orig_bytes, 12000000)
        self.assertEqual(list(incident.timeline), timeline)
        self.assertEqual(incident.visible_stage, "UNUSUAL VOLUME")
        app.process_shell_command("recover COL-ATH")
        app.update(3)
        phases = [e for e in incident.timeline if e.action_id == action.identifier]
        self.assertEqual([e.timestamp for e in phases], [49, 50, 51])
        self.assertTrue(all(e.received_at > e.timestamp for e in phases))
        self.assertEqual(app.blocked, 1)
        self.assertEqual(incident.visible_stage, "CONTAINMENT VERIFIED")

    def test_overflow_loss_is_explicit_and_history_memory_stays_bounded(self):
        app = self.app()
        self.outage(app)
        connection = app.organization.connect("ATH-WS1", "FRA-APP", "HTTPS")
        for _ in range(400):
            app.log_connection(connection)
        health = app.collectors.collectors["COL-ATH"]
        self.assertEqual((len(health.queue), health.dropped), (32, 368))
        self.assertIn("Telemetry lost", app.threat_logs[-1][3])
        self.assertEqual(app.collectors.metrics()["loss_percent"], 92)
        self.assertLessEqual(len(health.seen), 256)
        self.assertLessEqual(len(app.threat_logs), 80)
        app.process_shell_command("recover COL-ATH")
        app.update(16)
        self.assertEqual((health.processed, health.state), (32, "healthy"))
        self.assertEqual(health.dropped, 368)
        self.assertEqual(app.collectors.metrics()["p95_ms"], 15500)
        app.update(61)
        self.assertEqual(app.collectors.metrics()["loss_percent"], 0)
        self.assertIsNone(app.collectors.metrics()["p95_ms"])

    def test_outage_recovery_pause_speed_and_fps_partitions(self):
        apps = [self.app() for _ in range(3)]
        for app in apps:
            app.simulation.automatic = True
            app.start_critical_incident("partial")
            self.outage(app)
            app.update(49)
            app.process_shell_command("recover COL-ATH")
        apps[0].update(40)
        for fps, app in zip((15, 60), apps[1:]):
            for _ in range(40 * fps):
                app.update(1 / fps)
        def snapshot(app):
            return (app.simulation.now, app.simulation.total_bytes, app.metrics, app.total_events,
                    list(app.traffic_history), [row[1:] for row in app.threat_logs],
                    [(i.identifier, i.confidence, i.visible_stage, list(i.timeline)) for i in app.incidents.history],
                    [(c.identifier, c.state, c.last_heartbeat, c.dropped, c.processed, list(c.samples))
                     for c in app.collectors.collectors.values()])
        self.assertEqual(snapshot(apps[0]), snapshot(apps[1]))
        self.assertEqual(snapshot(apps[0]), snapshot(apps[2]))
        app = self.app(4)
        self.outage(app)
        app.paused = True
        app.update(100)
        self.assertEqual(app.collectors.now, 0)
        app.paused = False
        app.update(2.5)
        self.assertEqual(app.collectors.collectors["COL-ATH"].state, "offline")
        self.assertEqual(app.collectors.now, 10)


if __name__ == "__main__":
    unittest.main()
