"""Persistent organization, baseline assessment and dashboard integration fixtures."""

import ipaddress
import random
import unittest
from unittest.mock import patch

from simulation_model import Organization
from test_monitor import monitor


class OrganizationTests(unittest.TestCase):
    def make_model(self, seed=12):
        return Organization(monitor.CITIES, seed=seed)

    def test_catalog_roles_identity_and_example_addresses(self):
        model = self.make_model()
        self.assertEqual(len(model.collectors), 128)
        self.assertEqual({collector.city for collector in model.collectors.values()},
                         set(monitor.CITIES))
        self.assertTrue({"office", "data-center", "cloud", "remote-user"}.issubset(
            {site.role for site in model.sites.values()}))
        ranges = [ipaddress.ip_network(network) for network in
                  ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")]
        for asset in model.assets.values():
            self.assertTrue(any(ipaddress.ip_address(asset.address) in block for block in ranges))
            self.assertIn(asset.site_id, model.sites)
            self.assertTrue(asset.role and asset.owner and asset.criticality)
            if asset.collector_id is not None:
                self.assertIn(asset.collector_id, model.collectors)

    def test_expected_peer_is_assessed_by_relationship_and_service(self):
        model = self.make_model()
        expected = model.connect("ATH-WS1", "FRA-APP", "HTTPS")
        unexpected_service = model.connect("ATH-WS1", "FRA-APP", "SSH")
        new_peer = model.connect("ATH-WS1", "EXT-UNK", "HTTPS")
        self.assertTrue(expected.expected)
        self.assertFalse(unexpected_service.expected)
        self.assertFalse(new_peer.expected)
        self.assertEqual(expected.collector_id, new_peer.collector_id)
        self.assertEqual(model.context(expected), "ATH:ws>FRA:app")
        self.assertNotEqual(expected.identifier, new_peer.identifier)
        self.assertIn("review baseline", model.describe(new_peer))
        self.assertNotIn("malicious", model.describe(new_peer))

    def test_unknown_geography_is_independent_of_observing_collector(self):
        model = self.make_model()
        remote = model.connect("REM-UNK", "FRA-APP", "HTTPS")
        self.assertTrue(remote.expected)
        self.assertIsNone(model.city_for(remote.source_id))
        self.assertEqual(model.collectors[remote.collector_id].city[3], "FRA")
        self.assertIn("geography unknown", model.describe(remote))
        self.assertIsNone(model.city_for("EXT-UNK"))
        self.assertEqual(model.city_for("ATH-WS1"), monitor.CITIES[38])

    def test_seeded_selection_favors_expected_peers_and_retains_bounded_catalog(self):
        a, b = self.make_model(), self.make_model()
        catalog = (dict(a.sites), dict(a.assets), dict(a.collectors))
        connections = [a.choose_connection() for _ in range(1000)]
        self.assertEqual(connections, [b.choose_connection() for _ in range(1000)])
        self.assertGreater(sum(connection.expected for connection in connections), 850)
        self.assertTrue(any(not connection.expected for connection in connections))
        self.assertEqual(catalog, (a.sites, a.assets, a.collectors))
        self.assertFalse(hasattr(a, "connection_history"))

    def test_random_source_can_be_injected(self):
        model = Organization(monitor.CITIES, rng=random.Random(19))
        connection = model.choose_connection(unexpected=False)
        self.assertTrue(connection.expected)
        self.assertFalse(model.choose_connection(unexpected=True).expected)


class OrganizationDashboardTests(unittest.TestCase):
    def make_app(self):
        return monitor.CyberMonitor(initial_theme="ice", seed=12)

    def test_manual_background_and_events_share_catalog_connection(self):
        app = self.make_app()
        connection = app.organization.connect("ATH-WS1", "FRA-APP", "HTTPS")
        with patch.object(app.organization, "choose_connection", return_value=connection):
            manual = app.trigger_attack()
            app.update(0.1)  # Background spawn follows the same selection path.
        self.assertEqual([route.connection for route in app.attacks], [connection, connection])
        app.generate_threat_log()
        self.assertIn("ATH:ws>FRA:app expected", app.threat_logs[-1][3])
        self.assertIn("ATH-WS1@SITE-ATH", app.threat_logs[-1][3])
        self.assertIn("FRA-APP@SITE-FRA", app.threat_logs[-1][3])
        self.assertEqual(app.threat_logs[-1][2], "ATH")
        self.assertIs(manual.src_city, app.organization.city_for("ATH-WS1"))

    def test_unknown_peer_renders_without_fabricated_map_destination(self):
        app = self.make_app()
        connection = app.organization.connect("ATH-WS1", "EXT-UNK", "HTTPS")
        route = app.trigger_attack(connection)
        self.assertIsNone(route.dst_city)
        self.assertTrue(route.flagged)
        self.assertEqual(app.threat_logs[-1][1], "MED")
        for size in ((79, 24), (119, 40), (159, 48)):
            app.canvas = monitor.Canvas(*size)
            app.draw()
            frame = "\n".join("".join(row) for row in app.canvas.grid)
            self.assertIn("ATH:ws>EXT:peer?", frame)
            self.assertIn("geo unknown", frame)
            self.assertIn("NEW", frame)

    def test_unfamiliar_observation_does_not_claim_automatic_containment(self):
        app = self.make_app()
        connection = app.organization.connect("ATH-WS1", "EXT-UNK", "HTTPS")
        route = app.trigger_attack(connection)
        blocked = app.blocked
        app.attack_cooldown = app.event_cooldown = 100
        app.update(route.duration + 0.5)
        self.assertEqual(app.blocked, blocked)
        self.assertNotIn(route, app.attacks)
        self.assertIn("assessment pending", app.threat_logs[-1][3])

    def test_redraw_and_map_navigation_preserve_asset_and_collector_identity(self):
        app = self.make_app()
        catalog = app.organization
        assets, collectors = list(catalog.assets.values()), list(catalog.collectors.values())
        connection = catalog.connect("ATH-WS1", "FRA-APP", "HTTPS")
        route = app.trigger_attack(connection)
        app.paused = True
        for key in ("r", "]", "right", "b", "0", "r"):
            app.handle_key(key)
            app.draw()
        self.assertIs(app.organization, catalog)
        self.assertTrue(all(a is b for a, b in zip(assets, catalog.assets.values())))
        self.assertTrue(all(a is b for a, b in zip(collectors, catalog.collectors.values())))
        self.assertIs(route.connection, connection)

    def test_console_demonstration_reports_expected_and_unknown_peer(self):
        app = self.make_app()
        app.process_shell_command("baseline")
        app.process_shell_command("unfamiliar")
        self.assertTrue(app.attacks[-2].connection.expected)
        self.assertFalse(app.attacks[-1].connection.expected)
        app.process_shell_command("flows")
        history = "\n".join(app.shell_history)
        self.assertIn("expected", history)
        self.assertIn("geography unknown", history)
        self.assertIn(app.attacks[-1].connection.identifier, history)
        app.process_shell_command("org")
        self.assertIn("collector location does not locate a remote peer", "\n".join(app.shell_history))


if __name__ == "__main__":
    unittest.main()
