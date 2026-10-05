"""Service profiles, deterministic scheduling, telemetry and dashboard fixtures."""

import random
import unittest

from simulation_model import Session, SessionSimulation, Organization
from test_monitor import monitor


class SessionTests(unittest.TestCase):
    def session(self, service):
        organization = Organization(monitor.CITIES, seed=12)
        endpoints = {"DNS": ("ATH-WS1", "FRA-DNS"),
                     "HTTPS": ("ATH-WS1", "FRA-APP"),
                     "SSH": ("ATH-ADM", "FRA-APP"),
                     "BACKUP": ("FRA-BKP", "SIN-STORE")}
        return Session(organization.connect(*endpoints[service], service))

    def test_dns_request_precedes_response_and_completes(self):
        session = self.session("DNS")
        session.advance_to(0.04)
        self.assertEqual((session.orig_bytes, session.resp_bytes), (72, 0))
        self.assertEqual(session.conn_state, "S0")
        session.advance_to(0.2)
        self.assertEqual((session.orig_bytes, session.resp_bytes), (72, 220))
        self.assertEqual((session.orig_pkts, session.resp_pkts), (1, 1))
        self.assertEqual((session.proto, session.resp_port, session.encryption), ("udp", 53, "none"))
        self.assertTrue(session.complete)
        self.assertEqual(session.conn_state, "SF")
        self.assertEqual(session.rate, 0)
        session.advance_to(100)
        self.assertEqual((session.duration, session.orig_bytes, session.resp_bytes), (0.2, 72, 220))

    def test_https_is_encrypted_tcp_and_bursty_response_heavy(self):
        session = self.session("HTTPS")
        self.assertEqual((session.proto, session.service, session.encryption, session.resp_port),
                         ("tcp", "HTTPS", "TLS", 443))
        session.advance_to(1.3)
        self.assertGreater(session.resp_rate, session.orig_rate)
        self.assertEqual((session.orig_bytes, session.resp_bytes), (1200, 240000))
        session.advance_to(3)
        self.assertEqual(session.rate, 0)
        self.assertFalse(session.complete)
        session.advance_to(5.3)
        self.assertEqual(session.resp_bytes, 480000)
        self.assertGreater(session.rate, 0)

    def test_ssh_persists_with_low_volume_and_stable_fields(self):
        session = self.session("SSH")
        identity = (session.identifier, session.orig_port, session.resp_port)
        session.advance_to(30)
        self.assertFalse(session.complete)
        self.assertEqual(session.conn_state, "S1")
        self.assertLess(session.orig_bytes + session.resp_bytes, 10000)
        self.assertGreater(session.orig_pkts + session.resp_pkts, 0)
        session.advance_to(150)
        self.assertEqual(identity, (session.identifier, session.orig_port, session.resp_port))
        self.assertEqual((session.proto, session.encryption), ("tcp", "SSH"))
        self.assertFalse(session.complete)

    def test_bulk_totals_are_integral_of_directional_activity(self):
        session = self.session("BACKUP")
        session.advance_to(10)
        self.assertEqual((session.orig_bytes, session.resp_bytes), (20000000, 100000))
        self.assertEqual((session.orig_rate, session.resp_rate), (16.0, 0.08))
        session.advance_to(30)
        self.assertEqual((session.orig_bytes, session.resp_bytes), (60000000, 300000))
        self.assertTrue(session.complete)
        self.assertEqual(session.rate, 0)
        self.assertEqual((session.orig_pkts, session.resp_pkts), (50000, 250))
        session.advance_to(300)
        self.assertEqual(session.orig_bytes, 60000000)

    def test_payload_and_packets_are_independent_of_dt_partition(self):
        for service in Session.PROFILES:
            sessions = [self.session(service) for _ in range(3)]
            duration = sessions[0].lifetime
            sessions[0].advance_to(duration)
            for fps, session in zip((15, 60), sessions[1:]):
                for tick in range(1, round(duration * fps) + 1):
                    session.advance_to(tick / fps)
            self.assertEqual([s.totals_at(duration) for s in sessions],
                             [sessions[0].totals_at(duration)] * 3)
            self.assertTrue(all(s.complete for s in sessions))

    def test_unsupported_service_has_clear_error(self):
        organization = Organization(monitor.CITIES)
        with self.assertRaisesRegex(ValueError, "Unsupported simulated service"):
            Session(organization.connect("ATH-WS1", "FRA-APP", "SMTP"))


class SessionClockTests(unittest.TestCase):
    def simulation(self, seed=12):
        return SessionSimulation(Organization(monitor.CITIES, seed=seed), seed=seed)

    def snapshot(self, simulation):
        return (simulation.total_bytes, list(simulation.traffic_history),
                [(s.identifier, s.connection, s.started_at, s.orig_port, s.duration,
                  s.orig_bytes, s.resp_bytes, s.orig_pkts, s.resp_pkts, s.state)
                 for s in list(simulation.history) + simulation.sessions])

    def test_seeded_scheduler_replays_large_advance_and_15_60_fps(self):
        simulations = [self.simulation() for _ in range(3)]
        simulations[0].advance(60)
        for fps, simulation in zip((15, 60), simulations[1:]):
            random.seed(fps)  # Global random must not select modeled traffic.
            for _ in range(60 * fps):
                simulation.advance(1 / fps)
        self.assertEqual(self.snapshot(simulations[0]), self.snapshot(simulations[1]))
        self.assertEqual(self.snapshot(simulations[0]), self.snapshot(simulations[2]))

    def test_aggregate_history_reconciles_all_bytes_including_completed_dns(self):
        simulation = self.simulation()
        simulation.automatic = False
        dns = simulation.create(simulation.organization.connect("ATH-WS1", "FRA-DNS", "DNS"))
        backup = simulation.create(simulation.organization.connect("FRA-BKP", "SIN-STORE", "BACKUP"))
        simulation.advance(1)
        self.assertTrue(dns.complete)
        self.assertEqual(simulation.total_bytes, 2010292)
        self.assertAlmostEqual(simulation.throughput, backup.rate + 292 * 8 / 1000000)
        simulation.advance(29)
        self.assertTrue(backup.complete)
        self.assertEqual(simulation.total_bytes, 60300292)
        self.assertAlmostEqual(sum(simulation.traffic_history) * 1000000 / 8,
                               simulation.total_bytes)
        simulation.advance(1)
        self.assertEqual(simulation.throughput, 0)
        self.assertEqual(simulation.total_bytes, 60300292)

    def test_clock_ignores_nonfinite_negative_and_zero_advances(self):
        simulation = self.simulation()
        for dt in (float("nan"), float("inf"), -1, 0):
            simulation.advance(dt)
        self.assertEqual(simulation.now, 0)
        self.assertEqual(simulation.sessions, [])

    def test_live_sessions_and_retained_history_are_bounded(self):
        simulation = self.simulation()
        simulation.advance(10000)
        self.assertLessEqual(len(simulation.sessions), 12)
        self.assertEqual(len(simulation.history), 120)
        self.assertEqual(len(simulation.traffic_history), 120)


class SessionDashboardTests(unittest.TestCase):
    def app(self, speed=1):
        app = monitor.CyberMonitor(initial_theme="ice", initial_speed=speed, seed=12)
        app.critical_cooldown = 100000
        app.simulation.automatic = False
        return app

    def test_pause_speed_and_marker_period_do_not_fabricate_bytes(self):
        a, b = self.app(), self.app(2)
        for app in (a, b):
            app.trigger_attack(app.organization.connect("FRA-BKP", "SIN-STORE", "BACKUP"))
        b.attacks[0].MARKER_PERIOD = 0.7
        a.update(10)
        b.update(5)
        self.assertEqual(a.simulation.total_bytes, b.simulation.total_bytes)
        self.assertEqual(list(a.traffic_history), list(b.traffic_history))
        self.assertNotEqual(a.attacks[0].progress, b.attacks[0].progress)
        a.paused = True
        before = (a.elapsed, a.simulation.total_bytes, a.attacks[0].progress, list(a.traffic_history))
        a.update(10)
        self.assertEqual(before, (a.elapsed, a.simulation.total_bytes, a.attacks[0].progress,
                                  list(a.traffic_history)))

    def test_dashboard_seed_partition_replays_observations_and_traffic(self):
        apps = [self.app() for _ in range(3)]
        for app in apps:
            app.simulation.automatic = True
        apps[0].update(20)
        for fps, app in zip((15, 60), apps[1:]):
            for _ in range(20 * fps):
                app.update(1 / fps)
        expected = (apps[0].metrics, apps[0].total_events, list(apps[0].traffic_history),
                    [line[1:] for line in apps[0].threat_logs])
        for app in apps[1:]:
            self.assertEqual(expected, (app.metrics, app.total_events, list(app.traffic_history),
                                        [line[1:] for line in app.threat_logs]))

    def test_demo_console_and_retained_completion_expose_session_facts(self):
        app = self.app()
        app.process_shell_command("sessions")
        self.assertEqual([r.kind for r in app.attacks], ["DNS", "HTTPS", "SSH", "BACKUP"])
        app.update(30)
        app.process_shell_command("flows")
        app.process_shell_command("flow-history")
        text = "\n".join(app.shell_history)
        for fact in ("udp/DNS", "tcp/HTTPS encryption=TLS", "tcp/SSH", "tcp/BACKUP",
                     "60000000/300000", "completed/SF", "orig/resp_pkts", "1s window"):
            self.assertIn(fact, text)
        self.assertEqual([r.kind for r in app.attacks], ["SSH"])
        self.assertEqual(app.blocked, 0)

    def test_idle_web_session_keeps_context_but_stops_map_activity(self):
        app = self.app()
        app.canvas = monitor.Canvas(159, 48)
        app.map_views["WORLD"] = monitor.MapViewport((0, 35, 30, 60))
        route = app.trigger_attack(app.organization.connect("ATH-WS1", "FRA-APP", "HTTPS"))
        app.update(0.7)
        app.draw_map(0, 8, 100, 25)
        self.assertGreater(route.rate, 0)
        self.assertTrue(any(app.palette["packet"] in row for row in app.canvas.colors))
        app.update(2.3)
        app.canvas.clear()
        app.draw_map(0, 8, 100, 25)
        self.assertFalse(route.complete)
        self.assertEqual(route.rate, 0)
        self.assertIn(route, app.attacks)
        self.assertFalse(any(app.palette["packet"] in row for row in app.canvas.colors))
        frame = "\n".join("".join(row) for row in app.canvas.grid)
        self.assertIn("ATH", frame)
        self.assertIn("FRA", frame)


if __name__ == "__main__":
    unittest.main()
