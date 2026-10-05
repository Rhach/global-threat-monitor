"""Bounded keyboard investigation, independent of rendering and simulation time."""

from dataclasses import dataclass
import textwrap
from investigation_catalog import EventRecord, InvestigationFilters


@dataclass
class InspectionView:
    kind: str
    selected_id: str = ""
    selected: object = None
    incident_id: str = ""
    incident: object = None
    offset: int = 0
    archive: bool = False
    initialized: bool = False


class Investigation:
    """IDs, not row positions, bind selection; at most six navigation frames.

    Active lists retain the selected completed record while its model archive
    retains it. Resolvers consult the existing bounded archives for later reuse.
    No receipt is manufactured and no simulation object is changed here.
    """

    MAX_DEPTH = 6

    def __init__(self):
        self.stack = []
        self.filters = InvestigationFilters()
        self.editing = False
        self.filter_input = ""
        self.filter_error = ""

    @property
    def current(self):
        return self.stack[-1] if self.stack else None

    def push(self, view):
        # Returning to an existing link collapses the cycle and preserves its
        # scroll/selection. Flow -> incident -> related list -> flow is usable.
        for index, previous in enumerate(self.stack):
            if (previous.kind, previous.selected_id, previous.incident_id) == (view.kind, view.selected_id, view.incident_id):
                del self.stack[index + 1:]
                return True
        if len(self.stack) < self.MAX_DEPTH:
            self.stack.append(view)
            return True
        return False

    def open_list(self, app, kind, incident=None, archive=False):
        view = InspectionView(kind, incident_id=incident.identifier if incident else "",
                              incident=incident, archive=archive)
        if self.push(view):
            self.rows(app)

    def find_incident(self, app, identifier):
        return app.incidents.find_incident(identifier)

    def find_session(self, app, identifier):
        sessions = list(app.simulation.sessions) + list(app.simulation.history)
        incidents = list(app.incidents.history) + ([app.critical_incident] if app.critical_incident else [])
        sessions += [s for incident in incidents for s in incident.sessions]
        return next((s for s in sessions if s.identifier == identifier), None)

    def resolve(self, app, view):
        if view.selected_id:
            view.selected = (self.find_session(app, view.selected_id) if view.kind in ("flows", "flow") else
                             app.event_catalog.find(view.selected_id) if view.kind in ("events", "event") else
                             self.find_incident(app, view.selected_id))
        if view.incident_id:
            view.incident = self.find_incident(app, view.incident_id)

    def rows(self, app):
        view = self.current
        self.resolve(app, view)
        if view.kind == "flows":
            if view.incident_id:
                rows = list(view.incident.sessions) if view.incident is not None else []
            else:
                rows = list(app.simulation.sessions)
                if view.archive:
                    rows += list(app.simulation.history)
                    incidents = list(app.incidents.history) + ([app.critical_incident] if app.critical_incident else [])
                    rows += [s for incident in incidents for s in incident.sessions]
                    rows = list({s.identifier: s for s in rows}.values())
            rows.sort(key=(lambda s: (s.started_at, s.identifier)) if view.archive else
                      (lambda s: (not bool(s.incident_id), -s.rate, s.identifier)))
        elif view.kind == "events":
            rows = app.event_catalog.ordered()
        else:
            rows = (list(app.incidents.history) if view.archive else []) + ([app.critical_incident] if app.critical_incident else [])
        # A completed selection stays available; unrelated completed rows belong
        # to the model's history, not this active inspection list.
        if view.selected is not None and not any(r.identifier == view.selected_id for r in rows):
            rows.append(view.selected)
        rows = [r for r in rows if self.filters.matches(app, r)]
        if not view.initialized:
            if rows:
                view.selected_id, view.selected = rows[0].identifier, rows[0]
            view.initialized = True
        selected = next((r for r in rows if r.identifier == view.selected_id), None)
        if selected is not None:
            view.selected = selected
        return rows

    def move(self, app, direction):
        rows = self.rows(app)
        if rows:
            index = next((i for i, r in enumerate(rows) if r.identifier == self.current.selected_id),
                         -1 if direction > 0 else 0)
            selected = rows[(index + direction) % len(rows)]
            self.current.selected_id, self.current.selected = selected.identifier, selected

    def handle_key(self, app, key):
        if self.editing:
            if key == "escape":
                self.editing = False
            elif key == "enter":
                try:
                    self.filters.apply(app, self.filter_input)
                    self.editing = False
                    self.filter_error = ""
                except ValueError as error:
                    self.filter_error = str(error)
            elif key == "backspace":
                self.filter_input = self.filter_input[:-1]
            elif len(key) == 1 and key.isprintable() and len(self.filter_input) < 160:
                self.filter_input += key
            return True
        view = self.current
        self.resolve(app, view)
        if key == "escape":
            self.stack.pop()
        elif key == "/":
            self.editing = True
            self.filter_input = self.filters.expression()
            self.filter_error = ""
        elif key == "x":
            self.filters.values = {}
        elif key == "p":
            app.paused = not app.paused
        elif key in ("+", "=", "-"):
            # Keep the existing speed limits without importing the application.
            app.speed_multiplier = max(0.25, min(4.0, app.speed_multiplier + (-0.25 if key == "-" else 0.25)))
        elif view.kind in ("flows", "incidents", "events"):
            if key in ("n", "m"):
                self.move(app, -1 if key == "n" else 1)
            elif key == "enter":
                rows = self.rows(app)
                if any(r.identifier == view.selected_id for r in rows):
                    self.push(InspectionView({"flows": "flow", "incidents": "incident", "events": "event"}[view.kind],
                                             view.selected_id, view.selected))
            elif key == "v" and view.kind != "events":
                view.archive = not view.archive
                view.offset = 0
        elif key in ("u", "d"):
            view.offset = max(0, view.offset + (-1 if key == "u" else 1) * max(1, app.canvas.height - 9))
        elif key == "e" and view.kind == "incident" and view.selected is not None:
            self.open_list(app, "flows", view.selected)
        elif key == "e" and view.kind == "event" and view.selected is not None and view.selected.session_id:
            session = self.find_session(app, view.selected.session_id)
            if session is not None:
                self.push(InspectionView("flow", session.identifier, session))
        elif key == "i" and view.kind in ("flow", "event") and view.selected is not None and view.selected.incident_id:
            incident = self.find_incident(app, view.selected.incident_id)
            if incident is not None:
                self.push(InspectionView("incident", incident.identifier, incident))
        return bool(self.stack)

    def matching_events(self, app):
        return [r for r in app.event_catalog.ordered() if self.filters.matches(app, r)]

    def filtered_evidence(self, app, evidence):
        return [e for e in evidence if self.filters.matches(app, EventRecord.observation(e))]

    @staticmethod
    def asset_lines(app, identifier, label):
        asset = app.organization.assets[identifier]
        site = app.organization.sites[asset.site_id]
        geography = asset.city_code or "unknown geography"
        return [f"{label}: {asset.identifier} ({asset.name}) / {asset.role}",
                f"  Site: {site.identifier} ({site.name}) / {geography}; address={asset.address}"]

    @staticmethod
    def coverage_lines(app, identifiers):
        lines = []
        for identifier in sorted(identifiers):
            health = app.collectors.collectors[identifier]
            lines.append("Collector: " + health.summary())
            if health.state != "healthy":
                lines.append(f"COVERAGE GAP {identifier}:{health.state}; traffic and policy facts are modeled; "
                             "fresh collector evidence unavailable. Only received observations appear below.")
            if health.dropped:
                lines.append(f"Coverage incomplete: {identifier} dropped {health.dropped} observations (collector total).")
        return lines

    def flow_lines(self, app, session):
        connection = session.connection
        incident = self.find_incident(app, session.incident_id) if session.incident_id else None
        retained = list(app.incidents.history) + ([app.critical_incident] if app.critical_incident else [])
        causal = [a for record in retained for a in record.actions
                  if a.identifier == session.response_action_id or session.identifier in a.affected_sessions]
        current = list(app.simulation.policies.values())
        actions = list({a.identifier: a for a in causal + (list(incident.actions) if incident else []) + current}.values())
        matching = [a for a in actions if a.matches(session) or session.identifier in a.affected_sessions]
        lines = [f"FLOW {session.identifier} / {'RETAINED FINAL SUMMARY' if session.complete else 'ACTIVE'}",
                 "Offline modeled session facts; originator out / responder in."]
        lines += self.asset_lines(app, connection.source_id, "Originator")
        lines += self.asset_lines(app, connection.peer_id, "Responder")
        lines += [f"Endpoints: {app.organization.assets[connection.source_id].address}:{session.orig_port} > "
                  f"{app.organization.assets[connection.peer_id].address}:{session.resp_port}",
                  f"Service={session.service} transport={session.proto} encryption={session.encryption}",
                  f"State={session.state}/{session.conn_state} severity={session.severity} duration={session.duration:.2f}s "
                  f"started={session.started_at:.2f}s stopped={session.stopped_at}",
                  f"Bytes out={session.orig_bytes:,} in={session.resp_bytes:,}; "
                  f"packets out={session.orig_pkts:,} in={session.resp_pkts:,}",
                  f"Rates out={session.orig_rate:.4f} in={session.resp_rate:.4f} Mb/s (trailing 1 simulation second)",
                  f"Baseline={'expected' if connection.expected else 'unfamiliar'}; purpose={connection.purpose}",
                  f"Credential={session.credential_id or 'none'}; policy stop={session.response_action_id or 'none'}",
                  f"Incident link: {session.incident_id or 'none'}" + (" (I opens incident)" if incident else ""),
                  "POLICY ACTIONS (modeled actuator lifecycle)"]
        if session.response_action_id and not any(a.identifier == session.response_action_id for a in matching):
            lines.append(f"Causal stop {session.response_action_id}: action details unavailable in bounded retention.")
        for action in matching:
            role = ("CAUSAL STOP" if action.identifier == session.response_action_id else
                    "CURRENT PERSISTENT POLICY" if action in current else "RELATED INCIDENT ACTION")
            lines.append(f"{role}: {action.identifier}")
            lines.extend(action.detail_lines())
        if not matching:
            lines.append("No matching requested/applied policy actions.")
        lines += [f"{a.identifier} affected session links: {', '.join(a.affected_sessions) or 'none'}; "
                  f"incident coverage={'verified' if a.covers_incident else 'unverified'}" for a in matching]
        lines += self.coverage_lines(app, {connection.collector_id})
        lines.append("LINKED RECEIVED EVIDENCE (occurrence order; seconds on simulation clock)")
        evidence = [e for e in incident.timeline if e.session_id == session.identifier] if incident else []
        total = len(evidence)
        evidence = self.filtered_evidence(app, evidence)
        lines.append(f"Evidence matches={len(evidence)}/{total}; filters={self.filters.label()}")
        lines += [line for e in evidence for line in e.detail_lines()] or [
            "No evidence matches filters; retained received evidence exists. X clears filters." if total else
            "No received observations linked to this flow."]
        return lines

    def incident_lines(self, app, incident):
        lines = [f"INCIDENT {incident.identifier} / {'RETAINED FINAL SUMMARY' if incident.complete else 'ACTIVE'}",
                 f"Started={incident.started_at:.2f}s age={incident.age:.2f}s finished={incident.finished_at}"]
        lines += self.asset_lines(app, incident.source_id, "Source")
        lines += self.asset_lines(app, incident.peer_id, "Peer")
        lines += list(incident.detail_lines())
        lines += [f"{a.identifier} affected session links: {', '.join(a.affected_sessions) or 'none'}; "
                  f"incident coverage={'verified' if a.covers_incident else 'unverified'}" for a in incident.actions]
        lines += self.coverage_lines(app, {app.organization.assets[incident.source_id].collector_id} |
                                     {s.connection.collector_id for s in incident.sessions})
        lines.append("RELATED MODELED SESSIONS (E opens linked flow list)")
        lines += [s.summary() for s in incident.sessions] or ["No modeled sessions yet."]
        lines.append("RECEIVED TIMELINE: chronological occurrence / receipt (simulation seconds)")
        lines.append("Observation IDs link sessions and actions; response records are actuator model results.")
        evidence = self.filtered_evidence(app, incident.timeline)
        lines.append(f"Timeline matches={len(evidence)}/{len(incident.timeline)}; filters={self.filters.label()}")
        for observation in evidence:
            lines.extend(observation.detail_lines())
            if observation.action_id:
                lines.append(f"  Action link: {observation.action_id}; result={observation.result}")
        if not incident.timeline:
            lines.append("No received observations; pending or lost collector evidence is unavailable.")
        elif not evidence:
            lines.append("No timeline matches these filters; retained evidence exists. X clears filters.")
        return lines

    def event_lines(self, app, record):
        receipt = f"{record.received_at:.2f}s lag={record.lag:.2f}s" if record.received_at is not None else "unknown"
        lines = [f"EVENT {record.identifier} / {record.kind} / severity={record.severity}",
                 f"Occurred={record.occurred_at:.2f}s received={receipt} (simulation clock)",
                 f"Service={record.service or 'not specified'} collector={record.collector_id or 'system/operator'}",
                 f"Incident link={record.incident_id or 'none'} (I opens if retained)",
                 f"Session link={record.session_id or 'none'} (E opens if retained)",
                 f"Action link={record.action_id or 'none'}"]
        for identifier, label in ((record.source_id, "Source"), (record.peer_id, "Peer")):
            if identifier:
                lines += self.asset_lines(app, identifier, label)
        if not record.source_id and not record.peer_id:
            lines.append("Asset/service scope unspecified; this notice does not imply asset observations.")
        if record.lost_event_id:
            lines.append(f"Lost event={record.lost_event_id} occurred={record.lost_occurred_at:.2f}s; "
                         "loss notice received, original evidence unavailable.")
        if record.incident_id and self.find_incident(app, record.incident_id) is None:
            lines.append("Linked incident unavailable; evicted from bounded incident archive.")
        if record.session_id and self.find_session(app, record.session_id) is None:
            lines.append("Linked session unavailable; evicted from bounded model history.")
        lines += self.coverage_lines(app, {record.collector_id}) if record.collector_id else []
        lines.append(record.message)
        return lines

    def detail_lines(self, app, width):
        view = self.current
        self.resolve(app, view)
        if view.selected is None:
            return [f"{view.selected_id}: unavailable; record evicted from bounded model history.",
                    "Esc returns to the list; selection has not moved to another ID."]
        source = ({"flow": self.flow_lines, "incident": self.incident_lines, "event": self.event_lines}[view.kind])(app, view.selected)
        return [wrapped for line in source for wrapped in textwrap.wrap(line, max(1, width),
                replace_whitespace=False, drop_whitespace=True) or [""]]

    def draw_filter_editor(self, app):
        width, height = app.canvas.width, app.canvas.height
        px, py, pw, ph = app.panel(0, 2, width, height - 4, "INVESTIGATION FILTERS")
        content = ["Enter replaces all filters atomically. Empty input clears.",
                   "Keys: site location severity service incident (combine with spaces)",
                   "Examples: site=ATH severity=critical service=HTTPS incident=CT-001",
                   'location=Athens or location="New York" or location=unknown',
                   "Site/location match either endpoint; all dimensions combine with AND.",
                   "Applied: " + self.filters.label(), "Edit: " + self.filter_input + "▏"]
        if self.filter_error:
            content.append("Invalid: " + self.filter_error)
        lines = [part for line in content for part in textwrap.wrap(line, pw) or [""]]
        for i, line in enumerate(lines[:ph]):
            app.text(px, py + i, pw, line, "warn" if line.startswith("Invalid:") else "text")
        app.text(1, 0, width - 2, "FILTER EDITOR / simulation " + ("PAUSED" if app.paused else "LIVE"), "accent")
        app.text(1, height - 1, width - 2, "Enter apply | Backspace edit | Esc cancel | Ctrl+C quit", "accent")

    def draw(self, app):
        if self.editing:
            self.draw_filter_editor(app)
            return
        width, height = app.canvas.width, app.canvas.height
        view = self.current
        app.text(1, 0, width - 2, "INVESTIGATION / " + ("PAUSED" if app.paused else "LIVE") +
                 f" / t={app.simulation.now:.2f}s / {app.speed_multiplier:g}x", "accent")
        filter_lines = textwrap.wrap("Filters: " + self.filters.label(), width - 2)
        for i, line in enumerate(filter_lines):
            app.text(1, 1 + i, width - 2, line, "muted")
        top = 2 + len(filter_lines)
        title = view.kind.upper() + (" / RETAINED + ACTIVE" if view.archive else "")
        px, py, pw, ph = app.panel(0, top, width, height - top - 2, title)
        if view.kind in ("flows", "incidents", "events"):
            rows = self.rows(app)
            capacity = max(1, ph - 3)
            index = next((i for i, r in enumerate(rows) if r.identifier == view.selected_id), 0)
            view.offset = min(view.offset, max(0, len(rows) - capacity))
            if index < view.offset:
                view.offset = index
            elif index >= view.offset + capacity:
                view.offset = index - capacity + 1
            app.text(px, py, pw, {"flows": "ID / STATE / SITE:ASSET > PEER / SERVICE / Mb/s",
                     "incidents": "ID / STAGE / CONFIDENCE / DISPOSITION",
                     "events": "ID / OCCURRED / RECEIVED / LAG / LEVEL / SERVICE"}[view.kind], "muted")
            for row, item in enumerate(rows[view.offset:view.offset + capacity]):
                selected = item.identifier == view.selected_id
                if view.kind == "flows":
                    value = f"{item.identifier} {item.state} {app.organization.context(item.connection)} {item.service} {item.rate:.2f}"
                elif view.kind == "incidents":
                    value = f"{item.identifier} {item.visible_stage} {item.confidence} {item.disposition}"
                else:
                    receipt = f"{item.received_at:.2f} {item.lag:.2f}" if item.received_at is not None else "unknown"
                    value = f"{item.identifier} {item.occurred_at:.2f} {receipt} {item.severity} {item.service or '-'}"
                app.text(px, py + row + 1, pw, ("> " if selected else "  ") + value,
                         "accent" if selected else "text")
            if not rows:
                app.text(px, py + 2, pw, "No matching retained records; this does not establish collector coverage.", "muted")
            state = ("unavailable; bounded history evicted record" if view.selected_id and view.selected is None else
                     "excluded by filters; N/M selects a match" if view.selected_id and
                     not any(r.identifier == view.selected_id for r in rows) else "")
            app.text(px, py + ph - 2, pw, f"Selected ID: {view.selected_id or 'none'}" + (" / " + state if state else ""),
                     "warn" if state else "muted")
            coverage = self.filters.coverage(app)
            app.text(px, py + ph - 1, pw, f"Matches: {len(rows)} | " + (coverage or "Relevant collectors healthy; absence is not evidence of safety"),
                     "warn" if coverage else "muted")
            app.text(1, height - 2, width - 2, "V active/archive | / filters | X clear | P pause | +/- speed", "muted")
            controls = "N/M prev/next | Enter inspect | Esc back | Q quit"
        else:
            lines = self.detail_lines(app, pw)
            view.offset = min(view.offset, max(0, len(lines) - ph))
            for i, line in enumerate(lines[view.offset:view.offset + ph]):
                app.text(px, py + i, pw, line, "warn" if "COVERAGE GAP" in line else "text")
            link = "E related flows" if view.kind == "incident" else "I incident / E flow" if view.kind == "event" else "I linked incident"
            controls = f"U/D scroll | {link} | Esc back | / filters | X clear | P pause"
            app.text(1, height - 2, width - 2, f"Lines {view.offset + 1}-{min(len(lines), view.offset + ph)}/{len(lines)}; simulation continues unless paused", "muted")
        app.text(1, height - 1, width - 2, controls, "accent")
