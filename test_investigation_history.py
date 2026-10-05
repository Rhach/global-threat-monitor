"""Historical outcomes, typed filtering, receipt chronology and real retention gates."""

import re
import unittest

from test_monitor import monitor
from investigation_catalog import EventRecord


class HistoryTests(unittest.TestCase):
    def app(self):
        app = monitor.CyberMonitor(initial_theme="ice", seed=12)
        app.simulation.automatic = app.incidents.automatic = False
        app.canvas = monitor.Canvas(79, 24)
        return app

    def text(self, app):
        return "\n".join(app.investigation.detail_lines(app, 75))

    def test_all_four_historical_outcomes_keep_causal_records_after_routes_end(self):
        app = self.app()
        retained = []
        for variant in ("exfiltration", "benign", "partial", "exfiltration"):
            incident = app.start_critical_incident(variant)
            if variant == "benign":
                app.update(7)
                app.incidents.dismiss("approved JOB-FRA-SIN-001")
            else:
                app.update(49)
                if len(retained) in (0, 2):
                    session = incident.sessions[-2 if variant == "partial" else -1]
                    app.incidents.request_response("block", "session", session.identifier)
            app.update(incident.started_at + incident.LIFETIME - app.simulation.now)
            retained.append(incident)
        self.assertFalse(app.attacks)
        self.assertEqual([i.disposition for i in retained], ["contained", "dismissed", "partially contained", "unresolved"])
        for incident in retained:
            app.process_shell_command("filter incident=" + incident.identifier)
            app.process_shell_command("archive " + incident.identifier)
            text = self.text(app)
            self.assertIn(incident.disposition, text)
            self.assertIn(incident.source_id, text)
            self.assertIn(incident.peer_id, text)
            for session in incident.sessions:
                self.assertIn(session.identifier, text)
                self.assertTrue(session.complete)
                self.assertIn(str(session.orig_bytes), text)
            for observation in incident.timeline:
                self.assertIn(observation.identifier, text)
            for action in incident.actions:
                self.assertIn(action.identifier, text)
                self.assertIn(action.outcome, text)
            app.handle_key("escape")
            app.handle_key("escape")

    def test_combined_filters_match_typed_incident_session_and_received_event(self):
        app = self.app()
        incident = app.start_critical_incident()
        app.update(49)
        app.investigation.filters.apply(app, "site=ATH location=Dubai severity=CRIT service=https incident=ct-001")
        self.assertEqual(app.investigation.filters.values,
                         {"site": "SITE-ATH", "location": "DXB", "severity": "critical", "service": "HTTPS", "incident": "CT-001"})
        self.assertTrue(app.investigation.filters.matches(app, incident))
        self.assertTrue(app.investigation.filters.matches(app, incident.sessions[-1]))
        records = app.investigation.matching_events(app)
        self.assertTrue(records)
        self.assertTrue(all(r.incident_id == incident.identifier and r.service == "HTTPS" and r.severity == "critical" for r in records))
        self.assertNotIn(incident.timeline[0].identifier, [r.identifier for r in records])  # Auth has no network service.
        app.handle_key("v")
        app.handle_key("enter")
        text = self.text(app)
        self.assertIn(f"Timeline matches={len(app.investigation.filtered_evidence(app, incident.timeline))}/{len(incident.timeline)}", text)
        app.handle_key("x")
        self.assertEqual(app.investigation.filters.values, {})
        self.assertIn(incident.timeline[0].identifier, self.text(app))

    def test_filters_are_validated_atomically_and_unknown_location_is_real_metadata(self):
        app = self.app()
        app.investigation.filters.apply(app, 'site=REM location="unknown geography" severity=INFO service=HTTPS')
        before = app.investigation.filters.values.copy()
        for expression in ("site=FRA service=TLS", "severity=urgent", "incident=1", "site=nowhere", "location=Atlantis",
                           "source=ATH-WS1", "site=ATH site=FRA", "site=", "severity=critical junk", 'location="bad'):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                app.investigation.filters.apply(app, expression)
            self.assertEqual(app.investigation.filters.values, before)
        connection = app.organization.connect("REM-UNK", "FRA-APP", "HTTPS")
        app.trigger_attack(connection)
        record = app.event_catalog.records[-1]
        self.assertTrue(app.investigation.filters.matches(app, record))
        self.assertEqual(record.source_id, "REM-UNK")
        self.assertEqual(record.service, "HTTPS")
        app.investigation.filters.apply(app, 'location="New York" severity=medium')
        self.assertEqual(app.investigation.filters.values, {"location": "NYC", "severity": "med"})
        app.investigation.filters.apply(app, "")
        self.assertEqual(app.investigation.filters.values, {})

    def test_unscoped_system_text_is_never_parsed_into_filter_facts(self):
        app = self.app()
        app.log("ATH-WS1 CT-001 HTTPS critical Frankfurt")
        record = app.event_catalog.records[-1]
        self.assertEqual((record.source_id, record.service, record.incident_id), ("", "", ""))
        app.investigation.filters.apply(app, "site=ATH incident=CT-001 service=HTTPS")
        self.assertFalse(app.investigation.filters.matches(app, record))
        app.process_shell_command("outage COL-ATH")
        notice = app.event_catalog.records[-1]
        app.investigation.filters.apply(app, "site=ATH location=Athens")
        self.assertTrue(app.investigation.filters.matches(app, notice))
        self.assertEqual(notice.kind, "operator")
        self.assertEqual(notice.collector_id, "COL-ATH")
        self.assertEqual(notice.source_id, "")

    def test_empty_results_coverage_gap_and_hidden_selection_are_distinct(self):
        app = self.app()
        original = app.start_critical_incident()
        app.update(49)
        app.handle_key("v")
        selected = app.investigation.current.selected_id
        app.process_shell_command("outage COL-ATH")
        app.investigation.filters.apply(app, "site=EXT service=DNS")
        self.assertEqual(app.investigation.rows(app), [])
        app.draw()
        screen = "\n".join("".join(r) for r in app.canvas.grid)
        for value in ("No matching retained records", "excluded by filters", "Matches: 0", "COVERAGE GAP COL-ATH"):
            self.assertIn(value, screen)
        self.assertNotIn("evicted", screen)
        app.handle_key("enter")
        self.assertEqual(app.investigation.current.kind, "incidents")
        app.handle_key("x")
        self.assertEqual(app.investigation.current.selected_id, selected)
        self.assertIn(original, app.investigation.rows(app))
        app.investigation.filters.apply(app, "site=EXT location=DXB")
        self.assertIn("COVERAGE GAP COL-ATH", app.investigation.filters.coverage(app))

    def test_new_receipts_reorder_events_without_stealing_selection_or_filter(self):
        app = self.app()
        app.process_shell_command("outage COL-ATH")
        original = app.start_critical_incident()
        app.update(49)
        app.investigation.filters.apply(app, "incident=CT-001 severity=critical")
        app.handle_key("o")
        self.assertEqual(app.investigation.current.selected_id, "")
        app.process_shell_command("recover COL-ATH")
        app.update(0.5)
        self.assertEqual(len(app.investigation.rows(app)), 1)
        self.assertEqual(app.investigation.current.selected_id, "")  # Explicit N/M is needed after an initially empty list.
        app.handle_key("m")
        selected = app.investigation.current.selected_id
        filters = app.investigation.filters.values.copy()
        app.update(5)
        records = app.investigation.rows(app)
        self.assertEqual(app.investigation.current.selected_id, selected)
        self.assertEqual(app.investigation.filters.values, filters)
        self.assertEqual([(r.occurred_at, r.identifier) for r in records], sorted((r.occurred_at, r.identifier) for r in records))
        self.assertTrue(all(r.received_at > r.occurred_at for r in records))
        self.assertEqual(records[0].received_at, 49.5)
        app.handle_key("enter")
        self.assertIn("Occurred=0.00s received=49.50s lag=49.50s", self.text(app))
        app.handle_key("i")
        self.assertEqual(app.investigation.current.selected_id, original.identifier)
        self.assertIn("received=49.50 lag=49.50s", self.text(app))

    def test_metadata_survives_buffering_even_after_incident_archive_eviction(self):
        app = self.app()
        app.process_shell_command("outage COL-FRA")
        original = app.start_critical_incident("benign")
        app.update(32)
        for _ in range(64):
            app.start_critical_incident("benign")
            app.update(32)
        self.assertIsNone(app.incidents.find_incident(original.identifier))
        app.process_shell_command("recover COL-FRA")
        app.update(3)
        app.investigation.filters.apply(app, "incident=CT-001 service=BACKUP site=FRA")
        records = app.investigation.matching_events(app)
        self.assertTrue(records)
        self.assertTrue(all(r.service == "BACKUP" and r.incident_id == original.identifier for r in records))
        self.assertTrue(any(r.kind == "observation" for r in records))
        self.assertTrue(all(r.received_at >= 2080 for r in records))
        app.handle_key("o")
        app.handle_key("enter")
        self.assertIn("Linked incident unavailable", self.text(app))

    def test_real_64_to_65_incident_retention_evicts_selection_and_keeps_session_priority(self):
        app = self.app()
        original = None
        for _ in range(64):
            incident = app.start_critical_incident("benign")
            app.update(32)
            original = original or incident
        self.assertEqual(len(app.incidents.history), 64)
        self.assertIs(app.incidents.find_incident(original.identifier), original)
        app.process_shell_command("archive CT-001")
        self.assertIn("RETAINED FINAL SUMMARY", self.text(app))
        app.start_critical_incident("benign")
        app.update(32)
        self.assertEqual(len(app.incidents.history), 64)
        self.assertEqual(app.incidents.history[0].identifier, "CT-002")
        self.assertIn("CT-001: unavailable; record evicted", self.text(app))
        app.handle_key("escape")
        self.assertEqual(app.investigation.current.selected_id, "CT-001")
        self.assertNotIn("CT-001", [i.identifier for i in app.investigation.rows(app)])
        first_session = original.sessions[0]
        self.assertIs(app.investigation.find_session(app, first_session.identifier), first_session)
        app.investigation.filters.apply(app, "severity=critical service=BACKUP incident=CT-001")
        self.assertTrue(app.investigation.filters.matches(app, first_session))
        self.assertEqual(first_session.severity, "critical")

    def test_real_session_and_event_retention_boundaries_evict_without_stale_details(self):
        app = self.app()
        app.trigger_attack(app.organization.connect("ATH-WS1", "FRA-DNS", "DNS"))
        app.handle_key("e")
        original_id = app.investigation.current.selected_id
        app.handle_key("enter")
        app.update(0.2)
        for _ in range(120):
            app.trigger_attack(app.organization.connect("ATH-WS1", "FRA-DNS", "DNS"))
            app.update(0.2)
        self.assertEqual(len(app.simulation.history), 120)
        self.assertIn(original_id + ": unavailable; record evicted", self.text(app))
        app.handle_key("escape")
        app.handle_key("escape")
        app.handle_key("o")
        event_id = app.investigation.current.selected_id
        app.handle_key("enter")
        for index in range(120):
            app.log("Local notice " + str(index))
        self.assertEqual(len(app.event_catalog.records), 120)
        self.assertIn(event_id + ": unavailable; record evicted", self.text(app))
        app.handle_key("escape")
        self.assertEqual(app.investigation.current.selected_id, event_id)
        self.assertNotIn(event_id, [r.identifier for r in app.investigation.rows(app)])

    def test_editor_console_counts_no_result_and_minimum_dimensions(self):
        app = self.app()
        app.start_critical_incident()
        app.update(49)
        app.handle_key("v")
        app.handle_key("/")
        for key in "site=ATH severity=critical service=HTTPS incident=CT-001":
            self.assertTrue(app.handle_key(key))
        app.handle_key("enter")
        self.assertFalse(app.investigation.editing)
        app.draw()
        screen = "\n".join("".join(r) for r in app.canvas.grid)
        self.assertIn("Filters: site=SITE-ATH", screen)
        self.assertIn("incident=CT-001", screen)
        self.assertIn("Matches: 1", screen)
        before = app.investigation.filters.values.copy()
        app.handle_key("/")
        self.assertTrue(app.handle_key("q"))
        app.handle_key("enter")
        self.assertTrue(app.investigation.editing)
        self.assertEqual(app.investigation.filters.values, before)
        app.draw()
        self.assertIn("Invalid:", "\n".join("".join(r) for r in app.canvas.grid))
        app.handle_key("escape")
        app.process_shell_command("filter incident=CT-999")
        app.process_shell_command("events")
        self.assertIn("No received events match", "\n".join(app.shell_history))
        self.assertIn("Matches: 0 received events", "\n".join(app.shell_history))
        app.process_shell_command("filter clear")
        app.process_shell_command("filter site=ATH severity=critical service=HTTPS")
        app.process_shell_command("events 1")
        self.assertIn("Incident link=CT-001", "\n".join(app.shell_history))
        for width, height in ((79, 24), (119, 35), (79, 24)):
            app.canvas = monitor.Canvas(width, height)
            app.draw()
            self.assertTrue(all(len(row) == width for row in app.canvas.grid))
        app.handle_key("x")
        self.assertEqual(app.investigation.filters.values, {})

    def test_loss_record_metadata_is_a_notice_and_not_fabricated_received_evidence(self):
        app = self.app()
        app.process_shell_command("outage COL-ATH")
        for _ in range(3):
            app.start_critical_incident()
            app.update(74)
        notices = [r for r in app.event_catalog.records if r.kind == "loss"]
        self.assertTrue(notices)
        self.assertTrue(all(r.lost_event_id and r.lost_occurred_at is not None and r.collector_id == "COL-ATH" for r in notices))
        self.assertFalse(any(r.kind == "observation" for r in app.event_catalog.records))
        app.investigation.filters.apply(app, "site=ATH severity=high service=HTTPS")
        self.assertTrue(app.investigation.matching_events(app))
        record = next(r for r in app.investigation.matching_events(app) if r.lost_event_id)
        self.assertIn("original evidence unavailable", "\n".join(app.investigation.event_lines(app, record)))

    def test_filter_editor_archive_and_event_ansi_frames_erase_without_stale_cells(self):
        app = self.app()
        app.start_critical_incident()
        app.update(49)
        screen = [[" "] * 79 for _ in range(24)]
        tokens = re.compile(r"\033\[([0-9;]*)([Hm])|([^\033]+)")
        row = col = 0
        keys = ["v", "/"] + list("site=ATH severity=critical service=HTTPS incident=CT-001")
        keys += ["q", "enter", "backspace", "enter", "enter", "d", "e", "enter", "i", "d",
                 "escape", "x", "escape", "o", "enter", "d", "escape", "escape"]
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
            self.assertEqual(screen, app.canvas.grid, f"Stale inspection frame after {key}")
        self.assertEqual(app.active_mode, "dashboard")
        self.assertEqual(app.investigation.filters.values, {})

    def test_stream_shows_typed_asset_context_and_flow_filtered_zero_is_honest(self):
        app = self.app()
        incident = app.start_critical_incident()
        app.update(49)
        app.investigation.filters.apply(app, "incident=CT-001 severity=critical service=HTTPS")
        app.draw_events(0, 0, 79, 12)
        screen = "\n".join("".join(r) for r in app.canvas.grid)
        self.assertIn("ATH:ws>EXT:peer", screen)
        app.handle_key("e")
        app.handle_key("enter")
        app.investigation.filters.apply(app, "service=DNS")
        text = self.text(app)
        self.assertIn("No evidence matches filters; retained received evidence exists", text)
        self.assertNotIn("No received observations linked to this flow", text)
        self.assertEqual(app.investigation.current.selected_id, incident.sessions[-1].identifier)

    def test_replaced_policy_keeps_the_retained_ordinary_flows_causal_stop(self):
        app = self.app()
        app.start_critical_incident()
        app.update(49)
        ordinary = app.trigger_attack(app.organization.connect("ATH-WS1", "FRA-APP", "HTTPS")).session
        first = app.incidents.request_response("isolate", "endpoint", "ATH-WS1")
        app.update(25)
        self.assertEqual((ordinary.state, ordinary.response_action_id), ("isolated", first.identifier))
        app.start_critical_incident()
        second = app.incidents.request_response("isolate", "endpoint", "ATH-WS1")
        app.update(2)
        text = "\n".join(app.investigation.flow_lines(app, ordinary))
        self.assertIn("CAUSAL STOP: " + first.identifier, text)
        self.assertIn("applied=50.0", text)
        self.assertIn("CURRENT PERSISTENT POLICY: " + second.identifier, text)
        self.assertIn("applied=75.0", text)
        self.assertEqual(ordinary.response_action_id, first.identifier)
        self.assertIn(ordinary.identifier, first.affected_sessions)
        self.assertNotIn(ordinary.identifier, second.affected_sessions)

    def test_event_to_flow_incident_other_related_flow_path_is_fully_navigable(self):
        app = self.app()
        incident = app.start_critical_incident()
        app.update(49)
        app.investigation.filters.apply(app, "incident=CT-001 service=HTTPS severity=critical")
        app.handle_key("o")
        app.handle_key("enter")
        record = app.investigation.current.selected
        self.assertTrue(record.session_id)
        app.handle_key("e")
        self.assertEqual(app.investigation.current.selected_id, record.session_id)
        app.handle_key("i")
        app.handle_key("e")
        self.assertEqual(app.investigation.current.kind, "flows")
        # Choose a session different from the already open event-linked one.
        if app.investigation.current.selected_id == record.session_id:
            app.handle_key("m")
        other_id = app.investigation.current.selected_id
        self.assertNotEqual(other_id, record.session_id)
        app.handle_key("enter")
        self.assertEqual(app.investigation.current.kind, "flow")
        self.assertEqual(app.investigation.current.selected_id, other_id)
        self.assertEqual(len(app.investigation.stack), 6)
        app.handle_key("escape")
        self.assertEqual(app.investigation.current.selected_id, other_id)
        app.handle_key("escape")
        self.assertEqual(app.investigation.current.selected_id, incident.identifier)


if __name__ == "__main__":
    unittest.main()
