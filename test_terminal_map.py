"""Map integration regressions for v4. Run with python -m unittest -v."""

import re
import unittest
from unittest.mock import patch

from test_monitor import monitor
from terminal_map import MapViewport, border_texture, clip_line, coastline_texture


class TerminalMapTests(unittest.TestCase):
    def test_offscreen_endpoints_can_cross_visible_panel(self):
        self.assertEqual(clip_line(-20, 3, 30, 3, 10, 6), (0, 3, 9, 3))
        self.assertEqual(clip_line(2, -20, 2, 30, 10, 6), (2, 0, 2, 5))
        self.assertIsNone(clip_line(-20, -3, 30, -3, 10, 6))

    def test_real_coastlines_resize_and_cache(self):
        rows = coastline_texture(80, 22, monitor.VIEWS["WORLD"])
        self.assertIs(rows, coastline_texture(80, 22, monitor.VIEWS["WORLD"]))
        self.assertTrue(any(any(0x2801 <= ord(c) <= 0x28ff for c in row) for row in rows))
        for view in monitor.VIEWS.values():
            for width, height in ((1, 1), (46, 3), (80, 22)):
                rows = coastline_texture(width, height, view)
                self.assertEqual(len(rows), height)
                self.assertTrue(all(len(row) == width for row in rows))

    def test_zoom_pan_limits_and_reset(self):
        for bounds in monitor.VIEWS.values():
            viewport = MapViewport(bounds)
            viewport.zoom_by(100)
            self.assertEqual(viewport.zoom, 8)
            for dx, dy in ((-1, -1), (1, 1)):
                for _ in range(100):
                    viewport.pan(dx, dy)
                west, east, south, north = viewport.bounds
                self.assertGreaterEqual(west, -180)
                self.assertLessEqual(east, 180)
                self.assertGreaterEqual(south, -85)
                self.assertLessEqual(north, 85)
            viewport.zoom_by(0.001)
            self.assertEqual(viewport.zoom, 1)
            viewport.reset()
            self.assertEqual(viewport.bounds, bounds)

    def test_borders_render_and_cache_at_regional_and_world_scales(self):
        for bounds in monitor.VIEWS.values():
            rows = border_texture(80, 22, bounds)
            self.assertTrue(any(char != " " for row in rows for char in row))
            self.assertIs(rows, border_texture(80, 22, bounds))
            self.assertEqual(len(rows), 22)
            self.assertTrue(all(len(row) == 80 for row in rows))


class DashboardMapTests(unittest.TestCase):
    def make_app(self, **kwargs):
        return monitor.CyberMonitor(initial_theme="ice", **kwargs)

    def test_controls_when_paused_and_region_reset(self):
        app = self.make_app()
        app.paused = True
        app.handle_key("]")
        app.handle_key("h")
        viewport = app.map_views["WORLD"]
        self.assertGreater(viewport.zoom, 1)
        self.assertLess(viewport.longitude, 0)
        self.assertEqual(app.speed_multiplier, 1)
        app.handle_key("0")
        self.assertEqual(viewport.bounds, monitor.VIEWS["WORLD"])
        app.handle_key("r")
        self.assertEqual(app.view, "EUROPE")
        self.assertEqual(app.map_views[app.view].bounds, monitor.VIEWS["EUROPE"])
        self.assertTrue(app.coastlines_available)

    def test_mouse_wheel_and_arrows_control_the_map(self):
        app = self.make_app()
        viewport = app.map_views["WORLD"]
        self.assertTrue(app.handle_key("wheel_up"))
        self.assertGreater(viewport.zoom, 1)
        original_zoom = viewport.zoom
        original_lon, original_lat = viewport.longitude, viewport.latitude
        app.handle_key("left")
        app.handle_key("up")
        self.assertLess(viewport.longitude, original_lon)
        self.assertGreater(viewport.latitude, original_lat)
        app.handle_key("right")
        app.handle_key("down")
        self.assertAlmostEqual(viewport.longitude, original_lon)
        self.assertAlmostEqual(viewport.latitude, original_lat)
        app.handle_key("wheel_down")
        self.assertLess(viewport.zoom, original_zoom)

    def test_idle_zoom_waits_ten_seconds_then_gradually_returns(self):
        with patch.object(monitor.time, "monotonic", return_value=0):
            app = self.make_app()
            app.handle_key("wheel_up")
            app.handle_key("wheel_up")
            app.handle_key("left")
        viewport = app.map_views["WORLD"]
        zoom = viewport.zoom
        app.update_map(now=9.9)
        app.update_map(now=10)
        self.assertEqual(viewport.zoom, zoom)
        app.update_map(now=10.2)
        self.assertTrue(1 < viewport.zoom < zoom)
        for tick in range(103, 240):
            app.update_map(now=tick / 10)
        self.assertEqual(viewport.zoom, 1)
        self.assertEqual(viewport.bounds, monitor.VIEWS["WORLD"])

    def test_map_interaction_restarts_timer_but_other_controls_do_not(self):
        with patch.object(monitor.time, "monotonic", return_value=0):
            app = self.make_app()
            app.handle_key("wheel_up")
        with patch.object(monitor.time, "monotonic", return_value=9):
            app.handle_key("right")
            app.handle_key("p")
            app.handle_key("a")
        viewport = app.map_views["WORLD"]
        zoom = viewport.zoom
        app.update_map(now=18.9)
        self.assertEqual(viewport.zoom, zoom)
        with patch.object(monitor.time, "monotonic", return_value=19.2):
            app.update(0.1)
        self.assertLess(viewport.zoom, zoom)
        self.assertEqual(app.elapsed, 0)  # Paused simulation; camera still moves.

    def test_idle_zoom_is_frame_rate_independent(self):
        with patch.object(monitor.time, "monotonic", return_value=0):
            apps = [self.make_app(initial_speed=speed) for speed in (0.25, 4)]
            for app in apps:
                app.handle_key("]")
                app.handle_key("]")
        for app, fps in zip(apps, (15, 60)):
            for tick in range(1, fps * 14 + 1):
                app.update_map(now=tick / fps)
        self.assertAlmostEqual(apps[0].map_views["WORLD"].zoom,
                               apps[1].map_views["WORLD"].zoom, delta=0.04)

    def test_hidden_map_and_scroll_do_not_affect_console_or_drill(self):
        with patch.object(monitor.time, "monotonic", return_value=0):
            app = self.make_app()
            app.handle_key("wheel_up")
        zoom = app.map_views["WORLD"].zoom
        app.handle_key("c")
        app.handle_key("up")
        app.handle_key("wheel_down")
        app.update_map(now=20)
        self.assertEqual(app.shell_input, "")
        self.assertEqual(app.map_views["WORLD"].zoom, zoom)
        app.handle_key("escape")
        app.handle_key("g")
        app.handle_key("wheel_up")
        self.assertIsNone(app.drill.preview)
        self.assertFalse(app.drill.incident.actions)
        app.update_map(now=20)
        self.assertEqual(app.map_views["WORLD"].zoom, zoom)

    def test_missing_coastlines_leave_sensors_and_borders_usable(self):
        with patch.object(monitor, "load_coastlines", side_effect=FileNotFoundError("coastlines")):
            app = self.make_app()
            self.assertFalse(app.coastlines_available)
            self.assertTrue(app.borders_visible)
            self.assertIn("Coastlines unavailable", app.threat_logs[-1][3])
            app.draw()

    def test_missing_border_data_leaves_detailed_coastlines_usable(self):
        with patch.object(monitor, "load_borders", side_effect=FileNotFoundError("borders")):
            app = self.make_app()
            self.assertTrue(app.coastlines_available)
            self.assertFalse(app.borders_visible)
            self.assertIn("Country borders unavailable", app.threat_logs[-1][3])
            app.draw()

    def test_border_toggle_while_paused(self):
        app = self.make_app()
        app.paused = True
        self.assertTrue(app.borders_visible)
        app.handle_key("b")
        self.assertFalse(app.borders_visible)
        app.handle_key("b")
        self.assertTrue(app.borders_visible)

    def test_border_and_coastline_dots_share_cells_without_erasure(self):
        app = self.make_app()
        coast = (chr(0x2801) + " " * 44,) * 9
        borders = (chr(0x2808) + " " * 44,) * 9
        with patch.object(monitor, "CITIES", []), \
                patch.object(monitor, "coastline_texture", return_value=coast), \
                patch.object(monitor, "border_texture", return_value=borders):
            app.draw_map(7, 5, 49, 13)
            self.assertEqual(app.canvas.grid[7][9], chr(0x2809))
            app.borders_visible = False
            app.draw_map(7, 5, 49, 13)
            self.assertEqual(app.canvas.grid[7][9], chr(0x2801))
            self.assertEqual(app.canvas.colors[7][9], app.palette["map_land"])

    def test_city_catalog_has_unique_codes_and_valid_world_coordinates(self):
        self.assertEqual(len(monitor.CITIES), 128)
        self.assertEqual(len({city[3] for city in monitor.CITIES}), 128)
        self.assertEqual(len({city[2] for city in monitor.CITIES}), 128)
        west, east, south, north = monitor.VIEWS["WORLD"]
        for lon, lat, name, code in monitor.CITIES:
            self.assertTrue(west <= lon <= east and south <= lat <= north, name)
            self.assertEqual(len(code), 3)

    def test_city_codes_only_appear_for_active_trace_endpoints(self):
        app = self.make_app()
        app.canvas = monitor.Canvas(159, 48)
        codes = {city[3] for city in monitor.CITIES}

        def labels():
            app.canvas.clear()
            with patch.object(app, "text", wraps=app.text) as text:
                app.draw_map(0, 0, 155, 28)
            return {call.args[3] for call in text.call_args_list
                    if call.args[2] == 3 and call.args[3] in codes}

        self.assertEqual(labels(), set())
        self.assertTrue(any("•" in row for row in app.canvas.grid))
        cities = {city[2]: city for city in monitor.CITIES}
        route = monitor.AttackVector(cities["Cape Town"], cities["Perth"], app.palette)
        app.attacks = [route]
        self.assertEqual(labels(), {"CPT", "PER"})
        route.complete = True
        self.assertEqual(labels(), set())

    def test_flagged_sensor_wins_when_cities_share_a_terminal_cell(self):
        app = self.make_app()
        groups = {}
        for city in monitor.CITIES:
            nx, ny = monitor.project(*city[:2], 46, 8, monitor.VIEWS["WORLD"])
            groups.setdefault((round(nx), round(ny)), []).append(city)
        (nx, ny), cities = next((point, cities) for point, cities in groups.items() if len(cities) > 1)
        destination = cities[0]
        source = next(city for city in monitor.CITIES if city not in cities)
        route = monitor.AttackVector(source, destination, app.palette)
        route.flagged = True
        app.attacks = [route]
        app.draw_map(0, 0, 50, 12)
        self.assertEqual(app.canvas.grid[ny + 2][nx + 2], "◆")
        self.assertEqual(app.canvas.colors[ny + 2][nx + 2], app.palette["warn"])

    def test_shell_map_keys_remain_literal_input(self):
        app = self.make_app()
        app.handle_key("c")
        for key in "mb[]hjkl0":
            app.handle_key(key)
        self.assertEqual(app.shell_input, "mb[]hjkl0")
        self.assertTrue(app.coastlines_available)
        self.assertTrue(app.borders_visible)
        self.assertEqual(app.map_views["WORLD"].zoom, 1)

    def test_map_writes_stay_inside_panel_at_all_zoom_levels(self):
        app = self.make_app()
        app.trigger_attack()
        original_write = app.canvas.write_str
        original_char = app.canvas.write_char

        def check(x, y, text):
            self.assertGreaterEqual(x, 7)
            self.assertLessEqual(x + len(text), 56)
            self.assertGreaterEqual(y, 5)
            self.assertLess(y, 18)

        def write(x, y, text, color=None):
            check(x, y, text)
            original_write(x, y, text, color)

        def char(x, y, value, color=None):
            check(x, y, value)
            original_char(x, y, value, color)

        with patch.object(app.canvas, "write_str", side_effect=write), \
                patch.object(app.canvas, "write_char", side_effect=char):
            for view in monitor.VIEWS:
                app.view = view
                for key in ("]", "h", "j", "]", "k", "l", "]", "]", "]", "0"):
                    app.handle_key(key)
                    app.draw_map(7, 5, 49, 13)

    def test_map_controls_incremental_output_has_no_stale_cells(self):
        app = self.make_app()
        app.canvas = monitor.Canvas(99, 35)
        app.trigger_attack()
        screen = [[" "] * 99 for _ in range(35)]
        tokens = re.compile(r"\033\[([0-9;]*)([Hm])|([^\033]+)")
        row = col = 0
        for key in (None, "wheel_up", "left", "b", "down", "r", "]", "b", "up", "0", "r"):
            if key is not None:
                app.handle_key(key)
            app.update(0.1)
            app.draw()
            for match in tokens.finditer(app.canvas.render_diff()):
                params, command, text = match.groups()
                if command == "H":
                    row, col = (int(n) - 1 for n in params.split(";"))
                elif text:
                    for char in text:
                        screen[row][col] = char
                        col += 1
            self.assertEqual(screen, app.canvas.grid)


if __name__ == "__main__":
    unittest.main()
