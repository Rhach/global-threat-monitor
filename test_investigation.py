"""Deterministic ID selection, evidence, navigation and ANSI inspection fixtures."""

import re
import unittest

from test_monitor import monitor
from terminal_input import InputDecoder


class InvestigationTests(unittest.TestCase):
    def app(self):
        app = monitor.CyberMonitor(initial_theme="ice", seed=12)
        app.simulation.automatic = app.incidents.automatic = False
        app.canvas = monitor.Canvas(79, 24)  # 80-column terminal reserves final column.
        return app

    def detail_text(self, app):
        return "\n".join(app.investigation.detail_lines(app, 75))

    def test_selection_is_id_across_sort_reorder_and_completion(self):
        app = self.app()
        app.trigger_attack(app.organization.connect("ATH-WS1", "FRA-APP", "HTTPS"))
        app.trigger_attack(app.organization.connect("FRA-BKP", "SIN-STORE", "BACKUP"))
        app.handle_key("e")
        first = app.investigation.current.selected_id
        self.assertEqual(app.investigation.rows(app)[0].identifier, first)
        app.update(1)
        self.assertNotEqual(app.investigation.rows(app)[0].identifier, first)
        self.assertEqual(app.investigation.current.selected_id, first)
        app.handle_key("enter")
        app.update(12)
        text = self.detail_text(app)
        self.assertIn("RETAINED FINAL SUMMARY", text)
        self.assertIn("State=completed/SF", text)
        self.assertIn("duration=12.00s", text)
        self.assertIn("Bytes out=3,600 in=720,000", text)
        app.handle_key("escape")
        self.assertIn(first, [s.identifier for s in app.investigation.rows(app)])
        self.assertEqual(app.investigation.current.selected_id, first)
        app.handle_key("m")
        self.assertNotEqual(app.investigation.current.selected_id, first)

    def test_flow_fields_policy_evidence_and_simulation_continuation(self):
        app = self.app()
        incident = app.start_critical_incident()
        app.update(49)
        flow = incident.sessions[-1]
        app.handle_key("e")
        app.handle_key("enter")
        self.assertEqual(app.investigation.current.selected_id, flow.identifier)
        app.update(1)
        self.assertEqual(flow.orig_bytes, 12000000)
        action = app.incidents.request_response("block", "session", flow.identifier)
        app.update(2)
        text = self.detail_text(app)
        for value in (flow.identifier, "SITE-ATH", "SITE-EXTERNAL", "192.0.2.10:",
                      "> 203.0.113.201:443", "Service=HTTPS transport=tcp encryption=TLS",
                      "State=blocked/RSTO", "duration=7.00s", "Rates out=0.0000 in=0.0000",
                      action.identifier, "verified", "CT-001", "received=44.00", "OUTBOUND TRANSFER"):
            self.assertIn(value, text)
        app.handle_key("p")
        now = app.simulation.now
        app.update(5)
        self.assertEqual(app.simulation.now, now)
        app.handle_key("+")
        self.assertEqual(app.speed_multiplier, 1.25)
        app.handle_key("p")
        app.update(1)
        self.assertEqual(app.simulation.now, now + 1.25)

    def test_nested_links_open_and_back_restores_selection_and_scroll(self):
        app = self.app()
        incident = app.start_critical_incident()
        app.update(49)
        app.handle_key("e")
        app.handle_key("enter")
        original_flow = app.investigation.current.selected_id
        app.handle_key("d")
        original_scroll = app.investigation.current.offset
        app.handle_key("i")
        self.assertEqual(app.investigation.current.kind, "incident")
        app.handle_key("d")
        incident_scroll = app.investigation.current.offset
        app.handle_key("e")
        self.assertEqual(len(app.investigation.rows(app)), len(incident.sessions))
        app.handle_key("m")
        other_flow = app.investigation.current.selected_id
        self.assertNotEqual(other_flow, original_flow)
        app.handle_key("enter")
        self.assertEqual(app.investigation.current.kind, "flow")
        self.assertEqual(app.investigation.current.selected_id, other_flow)
        app.handle_key("escape")
        self.assertEqual(app.investigation.current.selected_id, other_flow)
        app.handle_key("escape")
        self.assertEqual(app.investigation.current.offset, incident_scroll)
        app.handle_key("escape")
        self.assertEqual(app.investigation.current.selected_id, original_flow)
        self.assertEqual(app.investigation.current.offset, original_scroll)
        self.assertLessEqual(len(app.investigation.stack), app.investigation.MAX_DEPTH)

    def test_link_cycle_collapses_to_existing_detail(self):
        app = self.app()
        app.start_critical_incident()
        app.update(49)
        for key in ("e", "enter", "i", "e", "enter"):
            app.handle_key(key)
        self.assertEqual(app.investigation.current.kind, "flow")
        self.assertEqual(len(app.investigation.stack), 2)

    def test_back_preserves_regional_map_viewport_and_input_context(self):
        app = self.app()
        app.start_critical_incident()
        app.handle_key("r")
        app.handle_key("]")
        app.handle_key("right")
        view = app.view
        bounds = app.map_views[view].bounds
        app.handle_key("i")
        app.handle_key("enter")
        for key in ("right", "h", "]", "wheel_up", "r", "c", "g"):
            app.handle_key(key)
        app.update(49)
        self.assertEqual(app.view, view)
        self.assertEqual(app.map_views[view].bounds, bounds)
        app.handle_key("escape")
        app.handle_key("escape")
        self.assertEqual(app.active_mode, "dashboard")
        self.assertEqual(app.map_views[view].bounds, bounds)
        app.handle_key("left")
        self.assertNotEqual(app.map_views[view].bounds, bounds)
        app.handle_key("c")
        for key in "eimnud":
            app.handle_key(key)
        self.assertEqual(app.shell_input, "eimnud")

    def test_incident_completion_stays_selected_across_next_incident(self):
        app = self.app()
        original = app.start_critical_incident()
        app.handle_key("i")
        app.handle_key("enter")
        app.update(74)
        new = app.start_critical_incident()
        self.assertIn("RETAINED FINAL SUMMARY", self.detail_text(app))
        self.assertIn("unresolved", self.detail_text(app))
        app.handle_key("escape")
        self.assertEqual([i.identifier for i in app.investigation.rows(app)], [new.identifier, original.identifier])
        self.assertEqual(app.investigation.current.selected_id, original.identifier)

    def test_gap_delivered_only_timeline_and_delayed_receipt_chronology(self):
        app = self.app()
        app.process_shell_command("outage COL-ATH")
        incident = app.start_critical_incident()
        app.handle_key("i")
        app.handle_key("enter")
        app.update(49)
        text = self.detail_text(app)
        self.assertIn("COVERAGE GAP", text)
        self.assertIn("modeled", text)
        self.assertIn("No received observations", text)
        self.assertNotIn("CT-001-OBS-01", text)
        self.assertIn("FLOW-00004", text)
        app.process_shell_command("recover COL-ATH")
        app.update(5)
        text = self.detail_text(app)
        observations = list(incident.timeline)
        self.assertTrue(observations)
        self.assertTrue(all(e.received_at > e.timestamp for e in observations))
        self.assertEqual([e.timestamp for e in observations], sorted(e.timestamp for e in observations))
        positions = [text.index(e.identifier) for e in observations]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("received=49.50 lag=49.50s", text)
        self.assertIn("occurrence / receipt", text)

    def test_evicted_record_is_explicitly_unavailable_and_never_retargets(self):
        app = self.app()
        app.trigger_attack(app.organization.connect("ATH-WS1", "FRA-APP", "HTTPS"))
        app.handle_key("e")
        selected_id = app.investigation.current.selected_id
        app.handle_key("enter")
        app.update(12)
        app.simulation.history.clear()  # Model retention boundary.
        self.assertIn("unavailable; record evicted", self.detail_text(app))
        app.handle_key("escape")
        app.trigger_attack(app.organization.connect("FRA-BKP", "SIN-STORE", "BACKUP"))
        app.draw()
        self.assertEqual(app.investigation.current.selected_id, selected_id)
        app.handle_key("enter")
        self.assertEqual(app.investigation.current.kind, "flows")

    def test_scroll_exposes_long_timeline_at_minimum_and_resize(self):
        app = self.app()
        incident = app.start_critical_incident()
        app.update(74)
        # The active selection was not opened before completion; start another
        # incident to exercise minimum list rendering, then retain on completion.
        app.start_critical_incident()
        app.handle_key("i")
        app.handle_key("enter")
        app.update(74)
        app.draw()
        first = [row[:] for row in app.canvas.grid]
        for _ in range(100):
            app.handle_key("d")
        app.draw()
        final = "\n".join("".join(row) for row in app.canvas.grid)
        self.assertIn("scenario ended", final)
        self.assertNotEqual(app.canvas.grid, first)
        self.assertLess(app.investigation.current.offset, len(app.investigation.detail_lines(app, 75)))
        app.canvas = monitor.Canvas(159, 48)
        app.draw()
        app.canvas = monitor.Canvas(79, 24)
        app.draw()
        self.assertTrue(all(len(row) == 79 for row in app.canvas.grid))
        self.assertTrue(all(row[-1] in "│╮╯ " for row in app.canvas.grid[3:22]))
        app.handle_key("u")
        app.draw()
        self.assertLess(app.investigation.current.offset, 100 * 15)

    def test_ansi_replay_clears_details_after_navigation_and_fragmented_input(self):
        app = self.app()
        app.start_critical_incident()
        app.update(49)
        screen = [[" "] * 79 for _ in range(24)]
        tokens = re.compile(r"\033\[([0-9;]*)([Hm])|([^\033]+)")
        row = col = 0
        decoder = InputDecoder()
        decoder.feed("E\rI\x1b[", now=0)
        keys = []
        while (key := decoder.read(now=0)) is not None:
            keys.append(key)
        decoder.feed("Ad\x1b", now=0.01)
        while (key := decoder.read(now=0.01)) is not None:
            keys.append(key)
        keys.append(decoder.read(now=0.1))
        keys += ["escape", "escape"]
        for key in [None] + keys:
            if key:
                self.assertTrue(app.handle_key(key))
            app.draw()
            for match in tokens.finditer(app.canvas.render_diff()):
                params, command, text = match.groups()
                if command == "H":
                    row, col = (int(n) - 1 for n in params.split(";"))
                elif text:
                    for char in text:
                        self.assertLess(col, 79)
                        screen[row][col] = char
                        col += 1
            self.assertEqual(screen, app.canvas.grid)
        self.assertEqual(app.active_mode, "dashboard")


if __name__ == "__main__":
    unittest.main()
