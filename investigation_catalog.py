"""Typed received-event facts and validated investigation filters; no prose parsing."""

from collections import deque
from dataclasses import dataclass, replace
import re
import shlex

from simulation_model import Session


def severity_name(value):
    return {"crit": "critical", "medium": "med"}.get(value.lower(), value.lower())


@dataclass(frozen=True)
class LogPayload:
    message: str
    status: str = "info"
    severity: str = "INFO"
    source_id: str = ""
    peer_id: str = ""
    service: str = ""
    incident_id: str = ""
    session_id: str = ""
    action_id: str = ""
    schedule_context: tuple = ()


@dataclass(frozen=True)
class EventRecord:
    identifier: str
    occurred_at: float
    received_at: float
    kind: str
    message: str
    severity: str = "info"
    collector_id: str = ""
    source_id: str = ""
    peer_id: str = ""
    service: str = ""
    incident_id: str = ""
    session_id: str = ""
    action_id: str = ""
    status: str = "info"
    lost_event_id: str = ""
    lost_occurred_at: float = None
    schedule_context: tuple = ()

    @classmethod
    def observation(cls, observation):
        return cls(observation.identifier, observation.timestamp, observation.received_at,
                   "observation", observation.message, severity_name(observation.severity),
                   observation.collector_id, observation.source_id, observation.peer_id,
                   observation.service, observation.incident_id, observation.session_id,
                   observation.action_id, "warn")

    @classmethod
    def telemetry(cls, event):
        payload = event.payload
        if event.kind == "incident":
            record = cls.observation(payload)
            return replace(record, received_at=event.received_at)
        return cls(event.identifier, event.occurred_at, event.received_at, "telemetry", payload.message,
                   severity_name(payload.severity), event.collector_id, payload.source_id,
                   payload.peer_id, payload.service, payload.incident_id, payload.session_id,
                   payload.action_id, payload.status, schedule_context=payload.schedule_context)

    @property
    def lag(self):
        return max(0.0, self.received_at - self.occurred_at) if self.received_at is not None else None


class EventCatalog:
    """Retain the last 120 received records, including system/loss notifications.

    Retention follows receipt insertion order; display follows occurrence time
    and identifier. Incident-owned evidence survives independently in its archive.
    """
    LIMIT = 120

    def __init__(self):
        self.records = deque(maxlen=self.LIMIT)
        self.sequence = 0

    def append(self, record):
        self.records.append(record)

    def system(self, now, message, severity="info", collector_id="", kind="system", **metadata):
        self.sequence += 1
        return EventRecord(f"SYS-{self.sequence:08d}", now, now, kind, message,
                           severity_name(severity), collector_id, **metadata)

    def find(self, identifier):
        return next((r for r in self.records if r.identifier == identifier), None)

    def ordered(self):
        return sorted(self.records, key=lambda r: (r.occurred_at, r.identifier))


class InvestigationFilters:
    KEYS = ("site", "location", "severity", "service", "incident")

    def __init__(self):
        self.values = {}

    def expression(self):
        return " ".join(f"{key}={value}" for key, value in self.values.items())

    def label(self):
        return self.expression() or "none"

    def apply(self, app, expression):
        """Replace atomically; invalid input leaves the previous filter intact."""
        proposed = {}
        try:
            tokens = shlex.split(expression)
        except ValueError:
            raise ValueError("Invalid quoted value")
        for token in tokens:
            if token.count("=") != 1:
                raise ValueError("Use site=ATH location=DXB severity=critical service=HTTPS incident=CT-001")
            key, value = token.split("=", 1)
            key = key.lower()
            if key not in self.KEYS or not value or key in proposed:
                raise ValueError("Unknown, empty or duplicate filter; keys: site location severity service incident")
            if key == "site":
                site = next((s for s in app.organization.sites.values()
                             if value.lower() in (s.identifier.lower(), s.code.lower(), s.name.lower())), None)
                if site is None:
                    raise ValueError("Unknown site; use org (for example ATH, FRA, SIN, REM, EXT)")
                value = site.identifier
            elif key == "location":
                if value.lower() in ("unknown", "unknown geography"):
                    value = "unknown"
                else:
                    city = next((c for c in app.organization.cities.values()
                                 if value.lower() in (c[2].lower(), c[3].lower())), None)
                    if city is None:
                        raise ValueError("Unknown location; use city code/name or unknown")
                    value = city[3]
            elif key == "severity":
                value = severity_name(value)
                if value not in ("info", "low", "med", "high", "critical"):
                    raise ValueError("Severity: info low med high critical (CRIT/medium accepted)")
            elif key == "service":
                value = value.upper()
                if value not in Session.PROFILES:
                    raise ValueError("Service: DNS HTTPS SSH BACKUP")
            elif key == "incident":
                value = value.upper()
                if not re.fullmatch(r"CT-\d{3,}", value):
                    raise ValueError("Incident: stable CT-ID, for example CT-001")
            proposed[key] = value
        self.values = {key: proposed[key] for key in self.KEYS if key in proposed}

    @staticmethod
    def asset_ids(record):
        identifiers = {i for i in (getattr(record, "source_id", ""), getattr(record, "peer_id", "")) if i}
        if hasattr(record, "connection"):
            identifiers.update((record.connection.source_id, record.connection.peer_id))
        if hasattr(record, "sessions"):
            identifiers.update(i for s in record.sessions for i in (s.connection.source_id, s.connection.peer_id))
        return identifiers

    def matches(self, app, record):
        assets = [app.organization.assets[i] for i in self.asset_ids(record) if i in app.organization.assets]
        sites = {a.site_id for a in assets}
        locations = {a.city_code or "unknown" for a in assets}
        collector_id = getattr(record, "collector_id", "")
        if not assets and collector_id in app.organization.collectors:
            code = app.organization.collectors[collector_id].city[3]
            locations.add(code)
            sites.update(s.identifier for s in app.organization.sites.values() if s.city_code == code)
        if hasattr(record, "sessions"):
            severity = record.severity
            services = {s.service for s in record.sessions} | {record.route.connection.service}
            incident_id = record.identifier
        elif hasattr(record, "connection"):
            severity = record.severity
            services = {record.service}
            incident_id = record.incident_id or ""
        else:
            severity = getattr(record, "severity", "info")
            services = {getattr(record, "service", "")}
            incident_id = getattr(record, "incident_id", "")
        facts = {"site": sites, "location": locations, "severity": {severity_name(severity)},
                 "service": services, "incident": {incident_id}}
        return all(value in facts[key] for key, value in self.values.items())

    def coverage(self, app):
        spatial = InvestigationFilters()
        spatial.values = {k: v for k, v in self.values.items() if k in ("site", "location")}
        if not spatial.values:
            identifiers = set(app.collectors.collectors)
        else:
            identifiers = {a.collector_id for a in app.organization.assets.values()
                           if spatial.matches(app, EventRecord("", 0, 0, "", "", source_id=a.identifier)) and a.collector_id}
            incidents = list(app.incidents.history) + ([app.critical_incident] if app.critical_incident else [])
            records = list(app.event_catalog.records) + list(app.simulation.sessions) + list(app.simulation.history)
            records += [s for incident in incidents for s in incident.sessions]
            records += incidents
            for record in records:
                if not spatial.matches(app, record):
                    continue
                identifier = (record.connection.collector_id if hasattr(record, "connection") else
                              getattr(record, "collector_id", ""))
                if identifier:
                    identifiers.add(identifier)
                if hasattr(record, "sessions"):
                    identifiers.add(app.organization.assets[record.source_id].collector_id)
                    identifiers.update(s.connection.collector_id for s in record.sessions)
            # Collector-only operator notices can locate a scope without assets.
            for identifier, collector in app.organization.collectors.items():
                if spatial.matches(app, EventRecord("", 0, 0, "", "", collector_id=identifier)):
                    identifiers.add(identifier)
        unknown_scope = not identifiers
        if unknown_scope:
            identifiers = set(app.collectors.collectors)
        degraded = ", ".join(f"{i}:{app.collectors.collectors[i].state}" for i in sorted(identifiers)
                             if app.collectors.collectors[i].state != "healthy")
        if unknown_scope:
            return "Scope visibility unknown; global " + ("COVERAGE GAP " + degraded if degraded else
                    "collectors healthy (does not establish scope visibility)")
        return "COVERAGE GAP " + degraded if degraded else ""
