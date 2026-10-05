"""Bounded keyboard investigation, independent of rendering and simulation time."""

from dataclasses import dataclass
import textwrap


@dataclass
class InspectionView:
    kind: str
    selected_id: str = ""
    selected: object = None
    incident_id: str = ""
    incident: object = None
    offset: int = 0


class Investigation:
    """IDs, not row positions, bind selection; at most five navigation frames.

    Active lists retain the selected completed record while its model archive
    retains it. Resolvers consult the existing bounded archives for later reuse.
    No receipt is manufactured and no simulation object is changed here.
    """

    MAX_DEPTH = 5

    def __init__(self):
        self.stack = []

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

    def open_list(self, app, kind, incident=None):
        view = InspectionView(kind, incident_id=incident.identifier if incident else "",
                              incident=incident)
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
            rows.sort(key=lambda s: (not bool(s.incident_id), -s.rate, s.identifier))
        else:
            rows = [app.critical_incident] if app.critical_incident else []
        # A completed selection stays available; unrelated completed rows belong
        # to the model's history, not this active inspection list.
        if view.selected is not None and not any(r.identifier == view.selected_id for r in rows):
            rows.append(view.selected)
        if not view.selected_id and rows:
            view.selected_id, view.selected = rows[0].identifier, rows[0]
        selected = next((r for r in rows if r.identifier == view.selected_id), None)
        if selected is not None:
            view.selected = selected
        return rows

    def move(self, app, direction):
        rows = self.rows(app)
        if rows:
            index = next((i for i, r in enumerate(rows) if r.identifier == self.current.selected_id), 0)
            selected = rows[(index + direction) % len(rows)]
            self.current.selected_id, self.current.selected = selected.identifier, selected

    def handle_key(self, app, key):
        view = self.current
        self.resolve(app, view)
        if key == "escape":
            self.stack.pop()
        elif key == "p":
            app.paused = not app.paused
        elif key in ("+", "=", "-"):
            # Keep the existing speed limits without importing the application.
            app.speed_multiplier = max(0.25, min(4.0, app.speed_multiplier + (-0.25 if key == "-" else 0.25)))
        elif view.kind in ("flows", "incidents"):
            if key in ("n", "m"):
                self.move(app, -1 if key == "n" else 1)
            elif key == "enter":
                self.rows(app)
                if view.selected is not None:
                    self.push(InspectionView("flow" if view.kind == "flows" else "incident",
                                             view.selected_id, view.selected))
        elif key in ("u", "d"):
            view.offset = max(0, view.offset + (-1 if key == "u" else 1) * max(1, app.canvas.height - 9))
        elif key == "e" and view.kind == "incident" and view.selected is not None:
            self.open_list(app, "flows", view.selected)
        elif key == "i" and view.kind == "flow" and view.selected is not None and view.selected.incident_id:
            incident = self.find_incident(app, view.selected.incident_id)
            if incident is not None:
                self.push(InspectionView("incident", incident.identifier, incident))
        return bool(self.stack)

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
        actions = list(incident.actions) if incident else []
        actions += [a for a in app.simulation.policies.values() if a not in actions]
        matching = [a for a in actions if a.matches(session) or session.identifier in a.affected_sessions]
        lines = [f"FLOW {session.identifier} / {'RETAINED FINAL SUMMARY' if session.complete else 'ACTIVE'}",
                 "Offline modeled session facts; originator out / responder in."]
        lines += self.asset_lines(app, connection.source_id, "Originator")
        lines += self.asset_lines(app, connection.peer_id, "Responder")
        lines += [f"Endpoints: {app.organization.assets[connection.source_id].address}:{session.orig_port} > "
                  f"{app.organization.assets[connection.peer_id].address}:{session.resp_port}",
                  f"Service={session.service} transport={session.proto} encryption={session.encryption}",
                  f"State={session.state}/{session.conn_state} duration={session.duration:.2f}s "
                  f"started={session.started_at:.2f}s stopped={session.stopped_at}",
                  f"Bytes out={session.orig_bytes:,} in={session.resp_bytes:,}; "
                  f"packets out={session.orig_pkts:,} in={session.resp_pkts:,}",
                  f"Rates out={session.orig_rate:.4f} in={session.resp_rate:.4f} Mb/s (trailing 1 simulation second)",
                  f"Baseline={'expected' if connection.expected else 'unfamiliar'}; purpose={connection.purpose}",
                  f"Credential={session.credential_id or 'none'}; policy stop={session.response_action_id or 'none'}",
                  f"Incident link: {session.incident_id or 'none'}" + (" (I opens incident)" if incident else ""),
                  "POLICY ACTIONS (modeled actuator lifecycle)"]
        lines += [line for a in matching for line in a.detail_lines()] or ["No matching requested/applied policy actions."]
        lines += [f"{a.identifier} affected session links: {', '.join(a.affected_sessions) or 'none'}; "
                  f"incident coverage={'verified' if a.covers_incident else 'unverified'}" for a in matching]
        lines += self.coverage_lines(app, {connection.collector_id})
        lines.append("LINKED RECEIVED EVIDENCE (occurrence order; seconds on simulation clock)")
        evidence = [e for e in incident.timeline if e.session_id == session.identifier] if incident else []
        lines += [line for e in evidence for line in e.detail_lines()] or ["No received observations linked to this flow."]
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
        for observation in incident.timeline:
            lines.extend(observation.detail_lines())
            if observation.action_id:
                lines.append(f"  Action link: {observation.action_id}; result={observation.result}")
        if not incident.timeline:
            lines.append("No received observations; pending or lost collector evidence is unavailable.")
        return lines

    def detail_lines(self, app, width):
        view = self.current
        self.resolve(app, view)
        if view.selected is None:
            return [f"{view.selected_id}: unavailable; record evicted from bounded model history.",
                    "Esc returns to the list; selection has not moved to another ID."]
        source = self.flow_lines(app, view.selected) if view.kind == "flow" else self.incident_lines(app, view.selected)
        return [wrapped for line in source for wrapped in textwrap.wrap(line, max(1, width),
                replace_whitespace=False, drop_whitespace=True) or [""]]

    def draw(self, app):
        width, height = app.canvas.width, app.canvas.height
        view = self.current
        app.text(1, 0, width - 2, "INVESTIGATION / " + ("PAUSED" if app.paused else "LIVE") +
                 f" / t={app.simulation.now:.2f}s / {app.speed_multiplier:g}x", "accent")
        px, py, pw, ph = app.panel(0, 2, width, height - 4, view.kind.upper())
        if view.kind in ("flows", "incidents"):
            rows = self.rows(app)
            capacity = max(1, ph - 2)
            index = next((i for i, r in enumerate(rows) if r.identifier == view.selected_id), 0)
            view.offset = min(view.offset, max(0, len(rows) - capacity))
            if index < view.offset:
                view.offset = index
            elif index >= view.offset + capacity:
                view.offset = index - capacity + 1
            app.text(px, py, pw, "ID / STATE / SITE:ASSET > PEER / SERVICE / Mb/s" if view.kind == "flows" else
                     "ID / STAGE / CONFIDENCE / DISPOSITION", "muted")
            for row, item in enumerate(rows[view.offset:view.offset + capacity]):
                selected = item.identifier == view.selected_id
                if view.kind == "flows":
                    value = f"{item.identifier} {item.state} {app.organization.context(item.connection)} {item.service} {item.rate:.2f}"
                else:
                    value = f"{item.identifier} {item.visible_stage} {item.confidence} {item.disposition}"
                app.text(px, py + row + 1, pw, ("> " if selected else "  ") + value,
                         "accent" if selected else "text")
            if not rows:
                app.text(px, py + 2, pw, "No active records. Esc returns; simulation can continue.", "muted")
            if view.selected_id and view.selected is None:
                app.text(px, py + ph - 2, pw, f"{view.selected_id}: unavailable; bounded history evicted record", "warn")
            app.text(px, py + ph - 1, pw, f"Selected ID: {view.selected_id or 'none'} / {len(rows)} rows; completed selection retained", "muted")
            controls = "N/M prev/next | Enter inspect | Esc back | P pause | +/- speed"
        else:
            lines = self.detail_lines(app, pw)
            view.offset = min(view.offset, max(0, len(lines) - ph))
            for i, line in enumerate(lines[view.offset:view.offset + ph]):
                app.text(px, py + i, pw, line, "warn" if "COVERAGE GAP" in line else "text")
            link = "E related flows" if view.kind == "incident" else "I linked incident"
            controls = f"U/D scroll | {link} | Esc back | P pause | +/- speed"
            app.text(1, height - 2, width - 2, f"Lines {view.offset + 1}-{min(len(lines), view.offset + ph)}/{len(lines)}; simulation continues unless paused", "muted")
        app.text(1, height - 1, width - 2, controls, "accent")
