"""Correlated offline observations, retained incidents and geographic follow."""

from collections import deque
from dataclasses import dataclass
import math
import random
import textwrap


@dataclass(frozen=True)
class Observation:
    identifier: str
    incident_id: str
    timestamp: float
    stage: str
    source_id: str
    peer_id: str
    collector_id: str
    session_id: str
    message: str

    def summary(self):
        session = " / " + self.session_id if self.session_id else ""
        return (f"t={self.timestamp:.2f} {self.identifier} {self.incident_id} "
                f"{self.source_id}>{self.peer_id}{session} / {self.stage}: {self.message}")

    def detail_lines(self):
        return (f"t={self.timestamp:.2f} {self.identifier} {self.incident_id} / {self.stage}",
                f"  {self.source_id}>{self.peer_id} / {self.collector_id} / {self.session_id or 'no session'}") + tuple(
                    textwrap.wrap(self.message, width=72, initial_indent="  ", subsequent_indent="  "))


class CriticalIncident:
    # Session starts are serial, so one reserved slot suffices for every stage.
    STAGES = ((0, "AUTH ANOMALY"), (2, "NEW PEER"),
              (16, "RECURRING EGRESS"), (30, "RECURRING EGRESS"),
              (44, "OUTBOUND TRANSFER"), (49, "UNUSUAL VOLUME"),
              (74, "UNRESOLVED"))
    LIFETIME = 74.0

    def __init__(self, route, number, started_at=0.0):
        self.route = route
        self.identifier = f"CT-{number:03d}"
        self.started_at = started_at
        self.age = 0.0
        self.following = True
        self.stage = "AUTH ANOMALY"
        self.disposition = "pending"
        self.finished_at = None
        self.timeline = deque(maxlen=32)
        self.observation_count = 0
        self.sessions = []
        self.next_step = 1
        self.mark_route(route)

    def mark_route(self, route):
        self.route = route
        route.critical = route.flagged = True

    @property
    def contained(self):
        return False  # Response consequences are a later implementation slice.

    @property
    def complete(self):
        return self.finished_at is not None

    @property
    def next_boundary(self):
        return self.started_at + self.STAGES[self.next_step][0]

    def summary(self):
        orig = sum(s.orig_bytes for s in self.sessions)
        resp = sum(s.resp_bytes for s in self.sessions)
        return (f"{self.identifier} {self.stage} / disposition={self.disposition} / "
                f"ATH-WS1>EXT-DXB / sessions={len(self.sessions)} / "
                f"orig/resp_bytes={orig}/{resp} / no response applied")

    def detail_lines(self):
        return tuple(textwrap.wrap(self.summary(), width=72))

    def position(self, progress=None):
        """The same geographic arc drives both camera and activity marker."""
        t = self.route.progress if progress is None else progress
        sx, sy = self.route.src_city[:2]
        dx, dy = self.route.dst_city[:2]
        bend = min(12.0, abs(dx - sx) * 0.12)
        return (sx + (dx - sx) * t,
                min(80.0, sy + (dy - sy) * t + 4 * bend * t * (1 - t)))

    def follow(self, viewport, dt):
        if not self.following or dt <= 0:
            return
        lon, lat = self.position()
        if 0 < self.route.progress < 1:
            lon, lat = self.position(min(1.0, self.route.progress + 0.025))
        blend = 1 - math.exp(-4 * dt)
        viewport.zoom += (6.0 - viewport.zoom) * blend
        viewport.longitude += (lon - viewport.longitude) * blend
        viewport.latitude += (lat - viewport.latitude) * blend
        viewport._clamp_center()


class IncidentSimulation:
    """Scenario events share SessionSimulation's exact event-boundary clock.

    Callbacks supply terminal routes and logs; all evidence comes from modeled
    authentication and session metadata, with no encrypted payload visibility.
    """

    HISTORY_LIMIT = 64

    def __init__(self, simulation, make_route, emit, seed=None):
        self.simulation = simulation
        self.make_route = make_route
        self.emit = emit
        self.rng = random.Random(seed)
        self.active = None
        self.history = deque(maxlen=self.HISTORY_LIMIT)
        self.count = 0
        self.next_start = self.rng.uniform(30, 90)
        self.automatic = True

    def next_boundary(self):
        if self.active:
            return self.active.next_boundary
        return max(self.simulation.now, self.next_start) if self.automatic else math.inf

    def observe(self, stage, message, session=None):
        incident = self.active
        incident.observation_count += 1
        observation = Observation(f"{incident.identifier}-OBS-{incident.observation_count:02d}",
                                  incident.identifier, self.simulation.now, stage,
                                  "ATH-WS1", "EXT-DXB", "COL-ATH",
                                  session.identifier if session else "", message)
        incident.timeline.append(observation)
        self.emit(observation)

    def start(self):
        if self.active:
            return self.active
        if len(self.simulation.sessions) >= self.simulation.MAX_ACTIVE:
            return None
        self.simulation.reserved_slots = 1
        self.count += 1
        # Allocate the first flow ID now; no session/bytes exist until NEW PEER.
        connection = self.simulation.organization.connect("ATH-WS1", "EXT-DXB", "HTTPS")
        route = self.make_route(connection, None)
        self.active = CriticalIncident(route, self.count, self.simulation.now)
        self.observe("AUTH ANOMALY", "5 failed logins then success for user aster.ws1; "
                     "configured baseline 0-1 failures per login; credential misuse suspected")
        return self.active

    def start_session(self, bulk=False):
        incident = self.active
        connection = (incident.route.connection if not incident.sessions else
                      self.simulation.organization.connect("ATH-WS1", "EXT-DXB", "HTTPS"))
        session = self.simulation.create(connection, profile="outbound_bulk" if bulk else None,
                                         reserved=True)
        if session is None:
            raise RuntimeError("Scenario reservation invariant violated")
        session.incident_id = incident.identifier
        incident.sessions.append(session)
        incident.mark_route(self.make_route(connection, session))
        return session

    def completed_session(self, session):
        if self.active and session.incident_id == self.active.identifier:
            self.observe("SESSION FINISHED", f"normal transport completion; "
                         f"orig/resp_bytes={session.orig_bytes}/{session.resp_bytes}; "
                         "assessment pending, no containment", session)

    def process_boundary(self):
        now = self.simulation.now
        if self.active is None:
            if self.automatic and now + 1e-9 >= self.next_start:
                if self.start() is None:
                    self.next_start = now + 1.0  # Retry without half-created evidence.
            return
        incident = self.active
        incident.age = now - incident.started_at
        if now + 1e-9 < incident.next_boundary:
            return
        offset, incident.stage = incident.STAGES[incident.next_step]
        incident.next_step += 1
        if offset == 2:
            session = self.start_session()
            self.observe(incident.stage, "first scenario contact with 203.0.113.201; "
                         "outside ATH-WS1 baseline (FRA-APP HTTPS / FRA-DNS DNS)", session)
        elif offset in (16, 30):
            session = self.start_session()
            self.observe(incident.stage, f"HTTPS connection {len(incident.sessions)} to same peer; "
                         "14s start intervals; recurrence observed, intent unconfirmed", session)
        elif offset == 44:
            session = self.start_session(bulk=True)
            self.observe(incident.stage, "HTTPS/TLS outbound upload started to same unfamiliar peer; "
                         "payload unavailable; suspected data removal (TA0010)", session)
        elif offset == 49:
            session = incident.sessions[-1]
            self.observe(incident.stage, f"{session.orig_bytes:,} originator bytes in 5s; "
                         "expected HTTPS 3,600 originator bytes per 12s session; "
                         "unusual outbound volume, content unknown", session)
        else:
            incident.disposition = "unresolved"
            incident.finished_at = now
            self.observe(incident.stage, "transfer ended naturally; suspected exfiltration remains "
                         "unresolved; no response applied", incident.sessions[-1])
            self.history.append(incident)
            self.active = None
            self.simulation.reserved_slots = 0
            self.next_start = now + self.rng.uniform(30, 90)
