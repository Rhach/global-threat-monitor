"""Shared state, bounded aggregation and read-only layer rendering fixtures."""
import copy
import unittest
from unittest.mock import patch

from map_layers import LAYERS, intensity, layer_nodes
from test_monitor import monitor
from terminal_map import coastline_texture, border_texture


class MapLayerTests(unittest.TestCase):
    def app(self):
        app = monitor.CyberMonitor(initial_theme="ice", seed=12)
        app.simulation.automatic = app.incidents.automatic = False
        return app

    def test_volume_buckets_include_final_bytes_and_expire_on_simulation_clock(self):
        app = self.app()
        session = app.simulation.create(app.organization.connect("FRA-BKP", "SIN-STORE", "BACKUP"))
        app.add_session_route(session)
        app.update(30)
        activity = app.simulation.endpoint_activity
        self.assertTrue(session.complete)
        self.assertEqual(activity.last_bytes, {"FRA": 2010000, "SIN": 2010000})
        self.assertEqual(activity.recent_bytes, {"FRA": 60300000, "SIN": 60300000})
        self.assertEqual(sum(activity.recent_bytes.values()), 2 * app.simulation.total_bytes)
        app.update(60)
        self.assertEqual(activity.recent_bytes, {})
        self.assertEqual(len(activity.buckets), 60)
        self.assertEqual(activity.pending, {})

    def test_unknown_endpoint_is_excluded_and_fractional_advances_match(self):
        apps = [self.app(), self.app()]
        for app in apps:
            app.simulation.create(app.organization.connect("ATH-WS1", "EXT-UNK", "HTTPS"))
        apps[0].update(4)
        for _ in range(40):
            apps[1].update(.1)
        for app in apps:
            self.assertEqual(set(app.simulation.endpoint_activity.recent_bytes), {"ATH"})
        self.assertEqual(list(apps[0].simulation.endpoint_activity.buckets),
                         list(apps[1].simulation.endpoint_activity.buckets))

    def test_same_moment_traffic_incident_stale_health_and_density(self):
        app = self.app()
        incident = app.start_critical_incident()
        app.trigger_attack(app.organization.connect("FRA-BKP", "SIN-STORE", "BACKUP"))
        app.process_shell_command("outage COL-PER")
        app.update(6)
        app.map_layer = "traffic"
        nodes = layer_nodes(app)
        self.assertEqual(nodes["FRA"].symbol, "3")
        self.assertAlmostEqual(nodes["FRA"].value, 16.08)
        app.map_layer = "incidents"
        self.assertEqual(layer_nodes(app)["ATH"].symbol, "◆")
        self.assertEqual(layer_nodes(app)["FRA"].symbol, "•")
        app.map_layer = "health"
        self.assertEqual(layer_nodes(app)["PER"].symbol, "!")
        self.assertEqual(layer_nodes(app)["ATH"].symbol, "•")
        app.map_layer = "density"
        self.assertEqual(layer_nodes(app)["FRA"].symbol, "3")
        self.assertEqual(layer_nodes(app)["FRA"].value, 12060000)
        self.assertEqual(incident, app.critical_incident)
        self.assertEqual(app.simulation.now, 6)

    def test_containment_marker_has_no_route_activity_and_retains_density(self):
        app = self.app()
        incident = app.start_critical_incident()
        app.update(49)
        transfer = incident.sessions[-1]
        app.incidents.request_response("block", "session", transfer.identifier)
        app.update(2)
        for layer in ("traffic", "incidents", "density"):
            app.map_layer = layer
            self.assertEqual(layer_nodes(app)["ATH"].symbol, "✓")
            app.canvas.clear()
            app.draw_map(0, 0, 80, 20)
            self.assertFalse(any("◉" in row for row in app.canvas.grid))
        self.assertGreater(layer_nodes(app)["ATH"].value, 10000000)
        app.update(30)
        app.map_layer = "incidents"
        self.assertTrue(incident in app.incidents.history)
        self.assertEqual(layer_nodes(app)["ATH"].symbol, "✓")

    def test_layer_switch_paused_console_and_literal_input_preserve_camera(self):
        app = self.app()
        app.handle_key("r")
        app.handle_key("]")
        app.handle_key("h")
        app.paused = True
        views = {name: (v.bounds, v.zoom) for name, v in app.map_views.items()}
        now = app.simulation.now
        for layer in ("incidents", "health", "density", "traffic"):
            app.handle_key("w")
            self.assertEqual(app.map_layer, layer)
            self.assertEqual(app.view, "EUROPE")
            self.assertEqual({name: (v.bounds, v.zoom) for name, v in app.map_views.items()}, views)
        app.handle_key("c")
        app.handle_key("w")
        self.assertEqual(app.shell_input, "w")
        app.process_shell_command("layer density")
        self.assertEqual(app.map_layer, "density")
        app.process_shell_command("layer wrong")
        self.assertEqual(app.map_layer, "density")
        self.assertEqual(app.simulation.now, now)
        self.assertEqual({name: (v.bounds, v.zoom) for name, v in app.map_views.items()}, views)

    def test_sizes_labels_clipping_static_cache_and_render_does_not_mutate_state(self):
        app = self.app()
        app.start_critical_incident()
        app.update(49)
        before = copy.deepcopy(list(app.simulation.endpoint_activity.buckets))
        state = (app.simulation.now, app.simulation.total_bytes, len(app.critical_incident.timeline))
        for width, height in ((79, 24), (119, 40)):
            app.canvas = monitor.Canvas(width, height)
            for layer in LAYERS:
                app.map_layer = layer
                app.draw()
                screen = "\n".join("".join(row) for row in app.canvas.grid)
                self.assertIn("W layer", screen)
                self.assertIn("stale" if layer != "health" else "catchup", screen)
                left_w = int(width * .64)
                top_h = max(7, int((height - 11) * .61))
                texture = coastline_texture(left_w - 4, top_h - 4, app.map_views[app.view].bounds)
                self.assertIs(texture, coastline_texture(left_w - 4, top_h - 4, app.map_views[app.view].bounds))
                labels = []
                with patch.object(app, "text", wraps=app.text) as text:
                    app.draw_map(0, 8, left_w, top_h)
                for call in text.call_args_list:
                    x, y, size, value = call.args[:4]
                    if value[:3] in app.organization.cities and size <= 5:
                        cells = {(x + i, y) for i in range(size)}
                        self.assertFalse(any(cells & previous for previous in labels))
                        self.assertGreaterEqual(x, 2)
                        self.assertLessEqual(x + size, left_w - 2)
                        labels.append(cells)
        self.assertEqual(state, (app.simulation.now, app.simulation.total_bytes, len(app.critical_incident.timeline)))
        self.assertEqual(before, list(app.simulation.endpoint_activity.buckets))

    def test_dismissed_benign_remains_physical_normal_and_all_linked_endpoints_marked(self):
        app = self.app()
        incident = app.start_critical_incident("benign")
        app.update(7)
        app.incidents.dismiss("approved backup")
        transferred = app.simulation.total_bytes
        app.update(1)
        self.assertGreater(app.simulation.total_bytes, transferred)
        for layer in ("traffic", "incidents", "density"):
            app.map_layer = layer
            self.assertNotEqual(layer_nodes(app)["FRA"].symbol, "◆")
            app.canvas.clear()
            app.draw_map(0, 0, 90, 20)
            self.assertFalse(any("◉" in row for row in app.canvas.grid))
            self.assertNotIn(app.palette["critical_trail"],
                             [color for row in app.canvas.colors for color in row])
        second = self.app()
        multiasset = second.start_critical_incident()
        session = second.simulation.create(second.organization.connect("FRA-BKP", "SIN-STORE", "BACKUP"))
        session.incident_id = multiasset.identifier
        multiasset.sessions.append(session)
        second.map_layer = "incidents"
        for code in ("ATH", "FRA", "SIN"):
            self.assertEqual(layer_nodes(second)[code].symbol, "◆")

    def test_filters_leave_both_legends_and_geography_cache_visible(self):
        app = self.app()
        app.start_critical_incident()
        app.update(49)
        app.process_shell_command("filter service=DNS")
        app.canvas = monitor.Canvas(79, 24)
        coast_before = coastline_texture.cache_info().misses
        borders_before = border_texture.cache_info().misses
        for layer in LAYERS:
            app.map_layer = layer
            app.draw()
            screen = "\n".join("".join(row) for row in app.canvas.grid)
            self.assertIn("Filters:", screen)
            self.assertIn("! stale", screen)
            self.assertIn("x off", screen)
            if layer in ("traffic", "density"):
                self.assertIn("1<1 2<10 3>=10", screen)
                self.assertIn("modeled", screen)
            elif layer == "incidents":
                self.assertIn("Modeled; received evidence", screen)
        self.assertLessEqual(coastline_texture.cache_info().misses - coast_before, 1)
        self.assertLessEqual(border_texture.cache_info().misses - borders_before, 1)

    def test_completed_all_unknown_activity_retains_flag_without_fabricated_geography(self):
        app = self.app()
        session = app.simulation.create(app.organization.connect("REM-UNK", "EXT-UNK", "HTTPS"))
        app.add_session_route(session)
        app.update(12)
        activity = app.simulation.endpoint_activity
        self.assertTrue(session.complete)
        self.assertEqual(activity.recent_bytes, {})
        self.assertGreater(activity.recent_unknown_bytes, 0)
        self.assertEqual(activity.recent_unknown_bytes, 2 * app.simulation.total_bytes)
        self.assertEqual(len(activity.unknown_buckets), 12)
        app.canvas = monitor.Canvas(79, 24)
        app.map_layer = "density"
        app.draw()
        screen = "\n".join("".join(row) for row in app.canvas.grid)
        self.assertIn("1<1 2<10 3>=10MB/60s modeled ?geo unknown", screen)
        self.assertTrue(all(node.value == 0 for node in layer_nodes(app).values()))
        app.update(57)
        self.assertGreater(activity.recent_unknown_bytes, 0)
        app.draw()
        self.assertIn("?geo unknown", "\n".join("".join(row) for row in app.canvas.grid))
        app.update(1)
        self.assertEqual(activity.recent_unknown_bytes, 0)
        self.assertEqual(len(activity.unknown_buckets), 60)
        app.draw()
        self.assertNotIn("?geo", "\n".join("".join(row) for row in app.canvas.grid))

    def test_intensity_boundaries_are_quantitative(self):
        self.assertEqual([intensity(value, 1, 10) for value in (0, .5, 1, 9, 10)], ["•", "1", "2", "2", "3"])


if __name__ == "__main__":
    unittest.main()
