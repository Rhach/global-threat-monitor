"""UTC/local calendar fixtures; advance phase windows without wall-clock waits."""

from collections import Counter
import math
import unittest
from unittest.mock import patch

from test_monitor import monitor
from workload_schedules import DAY, SEEDED_START_UTC, parse_start_utc, utc_text


class WorkloadScheduleTests(unittest.TestCase):
    def app(self, utc="2026-01-01T00:00:00Z", seed=12, speed=1):
        app = monitor.CyberMonitor(initial_theme="ice", seed=seed, start_utc=utc,
                                   initial_speed=speed)
        app.incidents.automatic = False
        return app

    def sessions(self, app):
        return list(app.simulation.history) + app.simulation.sessions

    def backup(self, app, site="SITE-FRA"):
        return next(s for s in self.sessions(app) if s.service == "BACKUP" and
                    s.schedule_context.get("site_id") == site)

    def test_explicit_utc_parser_and_seeded_default_are_host_independent(self):
        for value in (SEEDED_START_UTC, str(SEEDED_START_UTC), "2026-01-01T00:00:00Z",
                      "2026-01-01T00:00:00+00:00"):
            self.assertEqual(parse_start_utc(value), SEEDED_START_UTC)
        for value in (True, None, -1, math.inf, math.nan, "bad", "2026-01-01T00:00:00",
                      "2026-01-01T00:00:00+02:00", "1e100"):
            with self.assertRaises(ValueError):
                parse_start_utc(value)
        with patch.object(monitor.time, "time", return_value=1234567890):
            seeded = monitor.CyberMonitor(initial_theme="ice", seed=3)
            host = monitor.CyberMonitor(initial_theme="ice")
        self.assertEqual(seeded.clock_base, SEEDED_START_UTC)
        self.assertEqual(host.clock_base, 1234567890)
        self.assertEqual(seeded.schedules.epoch, seeded.clock_base)

    def test_overnight_is_quiet_and_singapore_morning_has_real_auth_sessions(self):
        quiet = self.app("2026-01-01T21:30:00Z")
        morning = self.app()
        quiet.update(61)
        morning.update(61)
        self.assertEqual((quiet.simulation.total_bytes, len(self.sessions(quiet))), (0, 0))
        self.assertTrue(all(quiet.schedules.phase(site) == "quiet" for site in quiet.schedules.sites.values()))
        flows = self.sessions(morning)
        self.assertTrue(flows)
        self.assertTrue(all(s.schedule_context["site_id"] == "SITE-SIN" for s in flows))
        self.assertEqual({s.service for s in flows}, {"DNS", "HTTPS"})
        auth = [s for s in flows if s.auth_result]
        self.assertTrue(auth)
        self.assertTrue(all(s.auth_result == "accepted" and s.credential_id == "aster.cloud" and
                            s.connection.source_id == "SIN-API" for s in auth))
        self.assertGreater(morning.simulation.total_bytes, 0)
        self.assertGreater(morning.total_events, quiet.total_events)
        health = morning.collectors.collectors["COL-SIN"]
        self.assertGreater(health.processed, 0)
        self.assertGreater(health.cpu, quiet.collectors.collectors["COL-SIN"].cpu)
        self.assertTrue(all(s.connection.expected for s in flows))
        record = next(r for r in morning.event_catalog.records if "modeled auth accepted" in r.message)
        self.assertIn(("phase", "morning"), record.schedule_context)
        session = next(s for s in flows if s.identifier == record.session_id)
        self.assertEqual(dict(record.schedule_context), session.schedule_context)

    def test_each_site_has_its_own_phase_cadence_and_service_selection(self):
        app = self.app("2026-01-01T07:00:00Z")
        app.update(61)
        counts = Counter(s.schedule_context["site_id"] for s in self.sessions(app))
        self.assertGreater(counts["SITE-FRA"], 3 * counts["SITE-ATH"])
        self.assertGreater(counts["SITE-FRA"], 3 * counts["SITE-SIN"])
        for session in self.sessions(app):
            phase = session.schedule_context["phase"]
            self.assertEqual(phase, "morning" if session.schedule_context["site_id"] == "SITE-FRA" else "work")
            if phase == "morning":
                self.assertIn(session.service, ("DNS", "HTTPS"))
        self.assertTrue(any(s.service == "SSH" for s in self.sessions(app)))
        self.assertTrue(all(s.service != "BACKUP" for s in self.sessions(app)))
        self.assertEqual(utc_text(app.clock_base + app.simulation.now), "2026-01-01T07:01:01Z")
        self.assertIn("FRA 2026-01-01 08:01:01", "\n".join(app.schedules.context_lines()))

    def test_backup_job_actual_bytes_rates_ingestion_owner_and_retained_context(self):
        app = self.app("2026-01-01T00:59:59Z")
        app.update(2)
        transfer = self.backup(app)
        job = next(j for j in app.schedules.jobs if j.kind == "backup")
        self.assertEqual((transfer.started_at, transfer.orig_bytes, transfer.resp_bytes), (1, 2000000, 10000))
        self.assertEqual(app.collectors.collectors["COL-FRA"].observed_payload_rate, 16.08)
        self.assertGreaterEqual(app.metrics["NET"], 16.08)
        self.assertGreater(app.collectors.collectors["COL-FRA"].cpu, 18)
        self.assertEqual(job.total_bytes, 2010000)
        self.assertEqual((job.owner, job.source_id, job.peer_id, job.collector_id),
                         ("Platform team", "FRA-BKP", "SIN-STORE", "COL-FRA"))
        self.assertTrue(transfer.connection.expected)
        self.assertEqual(transfer.schedule_context["job_id"], job.identifier)
        app.update(29)
        self.assertEqual((transfer.state, job.status, job.finished_at, job.total_bytes),
                         ("completed", "completed", 31, 60300000))
        self.assertEqual(app.simulation.collector_bytes["COL-FRA"], 60300000)
        self.assertIn("JOB-BACKUP-FRA-2026-01-01", "\n".join(app.investigation.flow_lines(app, transfer)))
        records = [r for r in app.event_catalog.records if r.session_id == transfer.identifier]
        self.assertEqual(len(records), 2)
        self.assertTrue(all(dict(r.schedule_context)["job_id"] == job.identifier for r in records))
        total = transfer.orig_bytes + transfer.resp_bytes
        app.update(31)
        self.assertEqual(transfer.orig_bytes + transfer.resp_bytes, total)
        self.assertEqual(len([s for s in self.sessions(app) if s.service == "BACKUP"]), 1)

    def test_singapore_backup_is_expected_and_does_not_broaden_ssh_baseline(self):
        app = self.app("2026-01-01T17:59:59Z")
        app.update(2)
        transfer = self.backup(app, "SITE-SIN")
        self.assertEqual((transfer.connection.source_id, transfer.connection.peer_id), ("SIN-STORE", "FRA-BKP"))
        self.assertTrue(transfer.connection.expected)
        self.assertEqual(transfer.schedule_context["approved_by"], "Cloud team")
        self.assertFalse(app.organization.connect("SIN-API", "FRA-BKP", "SSH").expected)

    def test_maintenance_explains_gap_and_cleans_up_even_when_future_work_disabled(self):
        app = self.app("2026-01-01T00:59:59Z")
        app.update(1)
        health = app.collectors.collectors["COL-ATH"]
        job = next(j for j in app.schedules.jobs if j.kind == "maintenance")
        self.assertEqual((health.mode, health.control_owner), ("outage", job.identifier))
        app.trigger_attack(app.organization.connect("ATH-WS1", "FRA-APP", "HTTPS"))
        app.update(11)
        self.assertEqual(health.state, "offline")
        self.assertIsNone(health.observed_payload_rate)
        self.assertTrue(health.queue)
        self.assertIn("planned maintenance=", health.summary())
        app.simulation.automatic = False
        app.update(289)
        self.assertEqual((job.finished_at, job.status), (301, "recovery started"))
        self.assertIsNone(health.planned_maintenance)
        self.assertEqual(health.control_owner, "baseline")
        self.assertEqual(health.mode, "recovering")
        app.update(2)
        self.assertFalse(health.queue)
        self.assertEqual(health.state, "healthy")
        self.assertTrue(any(r.session_id and r.received_at > r.occurred_at for r in app.event_catalog.records))

    def test_maintenance_never_overwrites_or_heals_operator_controls(self):
        for command in ("outage", "delay"):
            for before in (True, False):
                with self.subTest(command=command, before=before):
                    app = self.app("2026-01-01T00:59:59Z")
                    if before:
                        app.process_shell_command(command + " COL-ATH")
                    app.update(1)
                    health = app.collectors.collectors["COL-ATH"]
                    self.assertIsNotNone(health.planned_maintenance)
                    if not before:
                        app.process_shell_command(command + " COL-ATH")
                    app.update(300)
                    self.assertEqual(health.mode, "outage" if command == "outage" else "delayed")
                    self.assertEqual(health.control_owner, "operator")
                    self.assertIsNone(health.planned_maintenance)
                    job = next(j for j in app.schedules.jobs if j.kind == "maintenance")
                    self.assertEqual(job.status, "operator control retained")

    def test_completed_operator_recovery_allows_future_maintenance(self):
        app = self.app("2026-01-01T00:59:59Z")
        app.process_shell_command("outage COL-ATH")
        app.process_shell_command("recover COL-ATH")
        health = app.collectors.collectors["COL-ATH"]
        self.assertEqual(health.mode, "healthy")
        app.update(1)
        job = next(j for j in app.schedules.jobs if j.kind == "maintenance")
        self.assertEqual((health.mode, health.control_owner), ("outage", job.identifier))
        app.update(300)
        self.assertEqual((health.mode, health.control_owner), ("healthy", "baseline"))

    def test_pause_speed_and_disabled_schedules_use_the_single_clock(self):
        app = self.app("2026-01-01T00:59:59Z", speed=4)
        app.paused = True
        app.update(400)
        self.assertEqual((app.simulation.now, len(app.schedules.jobs)), (0, 0))
        app.paused = False
        app.update(0.5)
        self.assertEqual(app.simulation.now, 2)
        self.assertEqual(self.backup(app).orig_bytes, 2000000)
        other = self.app("2026-01-01T00:59:59Z")
        other.process_shell_command("schedules off")
        other.update(301)
        self.assertEqual((len(other.schedules.jobs), len(self.sessions(other)), other.simulation.total_bytes), (0, 0, 0))
        other.process_shell_command("schedules on")
        other.update(1)
        self.assertTrue(self.sessions(other))  # Work resumes without replaying expired backup.
        self.assertFalse(any(s.service == "BACKUP" for s in self.sessions(other)))

    def test_capacity_retries_and_missed_job_deadline_are_bounded(self):
        for lifetime, expected in ((12, "completed"), (600, "missed: capacity unavailable")):
            app = self.app("2026-01-01T00:59:59Z")
            for _ in range(app.simulation.MAX_ACTIVE):
                session = app.simulation.create(app.organization.connect("ATH-WS1", "FRA-APP", "HTTPS"), reserved=True)
                session.lifetime = lifetime
                app.add_session_route(session)
            app.update(301)
            job = next(j for j in app.schedules.jobs if j.kind == "backup")
            self.assertEqual(job.status, expected)
            self.assertFalse(app.schedules.pending_backups)
            if lifetime == 12:
                self.assertEqual((job.started_at, job.finished_at, job.total_bytes), (12, 42, 60300000))
            else:
                self.assertEqual(job.total_bytes, 0)
                self.assertFalse(job.session_id)
            self.assertLessEqual(len(app.simulation.sessions), app.simulation.MAX_ACTIVE)

    def test_midnight_and_next_day_job_identity_do_not_reissue_same_day(self):
        app = self.app("2026-01-01T15:59:59Z")  # Singapore crosses local midnight.
        app.update(2)
        self.assertIn("SIN 2026-01-02 00:00:01", "\n".join(app.schedules.context_lines()))
        self.assertFalse(app.schedules.jobs)
        # Calendar fixture injects successive day windows into the same scheduler;
        # session integration is exercised independently above, no 24h render loop.
        app = self.app("2026-01-01T01:00:00Z")
        for day in range(80):
            now = day * DAY
            app.simulation.now = now
            app.collectors.now = now
            app.collectors.next_heartbeat = now + 2
            for health in app.collectors.collectors.values():
                health.now = now
            app.schedules.process_boundary()
            app.schedules.process_boundary()
            maintenance = next(j for j in app.schedules.jobs if j.kind == "maintenance" and j.due_at == now)
            self.assertEqual(app.collectors.collectors["COL-ATH"].control_owner, maintenance.identifier)
            self.assertEqual(app.collectors.collectors["COL-ATH"].mode, "outage")
            jobs = [j for j in app.schedules.jobs if j.kind == "backup" and j.due_at == now]
            self.assertEqual(len(jobs), 1)
            session = app.schedules.running_backups[jobs[0].identifier][1]
            session.advance_to(now + 30)
            app.simulation.sessions.clear()
            app.attacks.clear()
            app.simulation.now = now + 300
            app.collectors.now = now + 300
            app.collectors.next_heartbeat = now + 302
            app.schedules.finish_jobs()
            self.assertEqual(app.collectors.collectors["COL-ATH"].mode, "healthy")
            self.assertEqual(maintenance.status, "recovery started")
        self.assertEqual(len(app.schedules.jobs), app.schedules.HISTORY_LIMIT)
        self.assertEqual(len(app.schedules.last_job_day), 2)
        self.assertFalse(app.schedules.running_backups)
        self.assertFalse(app.schedules.maintenance)
        self.assertEqual(app.schedules.jobs[-1].local_day, "2026-03-21")

    def test_partitions_redraws_and_history_keep_seeded_schedule_results(self):
        apps = [self.app("2026-01-01T00:59:59Z") for _ in range(2)]
        apps[0].update(45)
        for _ in range(450):
            apps[1].update(0.1)
            apps[1].draw()
        def facts(app):
            return (app.simulation.now, app.simulation.total_bytes, list(app.traffic_history),
                    app.total_events, list(app.event_catalog.records),
                    [j.summary(app.clock_base) for j in app.schedules.jobs],
                    [s.summary() for s in self.sessions(app)], app.metrics)
        self.assertEqual(facts(apps[0]), facts(apps[1]))

    def test_context_controls_and_minimum_header_preserve_existing_legends(self):
        app = self.app()
        app.canvas = monitor.Canvas(79, 24)
        app.update(1)
        app.draw()
        row = "".join(app.canvas.grid[0])
        for text in ("MANUAL", "A:on", "Y/Z/Enter", "2026-01-01T00:00:01", "UTC"):
            self.assertIn(text, row)
        self.assertIn("SIN:morning", "".join(app.canvas.grid[1]))
        app.process_shell_command("schedules")
        self.assertIn("fixed site offsets", "\n".join(app.shell_history))
        app.process_shell_command("jobs")
        self.assertIn("No daily jobs", app.shell_history[-1])
        app.start_critical_incident()
        app.investigation.filters.apply(app, "site=SITE-ATH")
        app.draw()
        frame = "\n".join("".join(row) for row in app.canvas.grid)
        for text in ("Sev critical", "Conf", "Resp", "Filters:", "W", "2026-01-01"):
            self.assertIn(text, frame)


if __name__ == "__main__":
    unittest.main()
