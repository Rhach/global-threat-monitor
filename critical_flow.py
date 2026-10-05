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
    action_id: str = ""
    result: str = ""

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
        self.timeline = deque(maxlen=64)  # Original evidence plus 8 response lifecycles.
        self.observation_count = 0
        self.sessions = []
        self.next_step = 1
        self.actions = []
        self.mark_route(route)

    def mark_route(self, route):
        self.route = route
        route.critical = route.flagged = True

    @property
    def contained(self):
        return any(a.status == "verified" and a.covers_incident for a in self.actions)

    @property
    def response_status(self):
        if not self.actions:
            return "no response applied"
        action = self.actions[-1]
        timestamp = (action.verified_at if action.verified_at is not None else
                     action.applied_at if action.applied_at is not None else action.requested_at)
        return f"{action.identifier} {action.status} t={timestamp:.2f} / {action.scope}={action.target}"

    @property
    def complete(self):
        return self.finished_at is not None

    @property
    def next_boundary(self):
        return (self.started_at + self.STAGES[self.next_step][0]
                if self.next_step < len(self.STAGES) else math.inf)

    def summary(self):
        orig = sum(s.orig_bytes for s in self.sessions)
        resp = sum(s.resp_bytes for s in self.sessions)
        return (f"{self.identifier} {self.stage} / disposition={self.disposition} / "
                f"ATH-WS1>EXT-DXB / sessions={len(self.sessions)} / "
                f"orig/resp_bytes={orig}/{resp} / {self.response_status}")

    def detail_lines(self):
        return tuple(textwrap.wrap(self.summary(), width=72)) + tuple(
            line for action in self.actions for line in action.detail_lines())

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


@dataclass
class ResponseAction:
    identifier: str
    incident_id: str
    kind: str
    scope: str
    target: str
    peer_id: str
    requested_at: float
    status: str = "requested"
    applied_at: float = None
    verified_at: float = None
    affected_sessions: tuple = ()
    result: str = "pending"
    covers_incident: bool = False

    APPLY_DELAY = 1.0
    VERIFY_DELAY = 1.0

    def matches(self, session):
        connection = session.connection
        if self.scope == "session":
            return session.identifier == self.target
        if self.scope == "endpoint":
            return self.target in (connection.source_id, connection.peer_id)
        if self.scope == "peer":
            return connection.source_id == self.target and connection.peer_id == self.peer_id
        return session.credential_id == self.target

    @property
    def next_boundary(self):
        if self.status == "requested":
            return self.requested_at + self.APPLY_DELAY
        if self.status == "applied":
            return self.applied_at + self.VERIFY_DELAY
        return math.inf

    def detail_lines(self):
        return tuple(textwrap.wrap(
            f"{self.identifier} {self.kind} {self.scope}={self.target}" +
            (f">{self.peer_id}" if self.peer_id else "") +
            f" / {self.status} / requested={self.requested_at:.2f} " +
            f"applied={self.applied_at} verified={self.verified_at} / {self.result}", width=72))


class IncidentSimulation:
    """Scenario events share SessionSimulation's exact event-boundary clock.

    Callbacks supply terminal routes and logs; all evidence comes from modeled
    authentication and session metadata, with no encrypted payload visibility.
    """

    HISTORY_LIMIT = 64
    ACTION_LIMIT = 8

    def __init__(self, simulation, make_route, emit, seed=None,
                 on_completed=None, on_applied=None):
        self.simulation = simulation
        self.make_route = make_route
        self.emit = emit
        self.rng = random.Random(seed)
        self.active = None
        self.history = deque(maxlen=self.HISTORY_LIMIT)
        self.count = 0
        self.next_start = self.rng.uniform(30, 90)
        self.automatic = True
        self.on_completed = on_completed
        self.on_applied = on_applied

    def next_boundary(self):
        if self.active:
            action_boundary = min((a.next_boundary for a in self.active.actions), default=math.inf)
            return min(self.active.next_boundary, action_boundary)
        return max(self.simulation.now, self.next_start) if self.automatic else math.inf

    def observe(self, stage, message, session=None, action=None, result=""):
        incident = self.active
        incident.observation_count += 1
        source_id = action.target if action and action.scope in ("endpoint", "peer") else "ATH-WS1"
        peer_id = (action.peer_id if action.scope == "peer" else
                   "EXT-DXB" if action.scope == "session" else "") if action else "EXT-DXB"
        collector_id = self.simulation.organization.assets[source_id].collector_id
        observation = Observation(f"{incident.identifier}-OBS-{incident.observation_count:02d}",
                                  incident.identifier, self.simulation.now, stage,
                                  source_id, peer_id, collector_id,
                                  session.identifier if session else "", message,
                                  action.identifier if action else "", result)
        incident.timeline.append(observation)
        self.emit(observation)

    def request_response(self, kind, scope, target, peer_id="", action_id=None):
        """Explicit scopes; retries by ID or identical request return the same action."""
        incident = self.active
        if incident is None:
            raise ValueError("No active incident; start scenario first")
        if action_id:
            existing = next((a for a in incident.actions if a.identifier == action_id), None)
            if existing is None:
                raise ValueError("Unknown action ID for active incident")
            return existing
        allowed = {"block": ("session", "peer"), "isolate": ("endpoint",),
                   "revoke": ("session", "credential")}
        if scope not in allowed.get(kind, ()):
            raise ValueError("Use block session/peer, isolate endpoint, or revoke session/credential")
        if peer_id and scope != "peer":
            raise ValueError("Only peer scope accepts a peer asset ID")
        if scope == "session":
            if not any(s.identifier == target for s in incident.sessions):
                raise ValueError("Session target must belong to this incident")
        elif scope in ("endpoint", "peer"):
            asset = self.simulation.organization.assets.get(target)
            if asset is None or asset.site_id == "SITE-EXTERNAL":
                raise ValueError("Target must be an identified local organization asset")
            if scope == "peer" and peer_id not in self.simulation.organization.assets:
                raise ValueError("Unknown peer asset ID")
        elif target != "aster.ws1":
            raise ValueError("Known modeled credential: aster.ws1 (ATH-WS1)")
        key = (kind, scope, target, peer_id)
        existing = next((a for a in incident.actions if
                         (a.kind, a.scope, a.target, a.peer_id) == key), None)
        if existing:
            return existing
        if len(incident.actions) >= self.ACTION_LIMIT:
            raise ValueError("Incident response limit reached (8 actions)")
        covers = ((scope == "endpoint" and target == "ATH-WS1") or
                  (scope == "peer" and (target, peer_id) == ("ATH-WS1", "EXT-DXB")) or
                  (scope == "credential" and target == "aster.ws1"))
        action = ResponseAction(f"{incident.identifier}-ACT-{len(incident.actions) + 1:02d}",
                                incident.identifier, kind, scope, target, peer_id,
                                self.simulation.now, covers_incident=covers)
        incident.actions.append(action)
        self.observe("RESPONSE REQUESTED", f"{action.identifier} {kind}: {scope}={target}" +
                     (f">{peer_id}" if peer_id else "") +
                     "; pending application in 1 simulation second", action=action, result="pending")
        return action

    def cancel_response(self, action_id):
        action = self.request_response("", "", "", action_id=action_id)
        if action.status == "requested":
            action.status, action.result = "cancelled", "cancelled before application"
            self.observe("RESPONSE CANCELLED", action.identifier + " " + action.result,
                         action=action, result=action.result)
        return action

    def process_responses(self):
        incident, now = self.active, self.simulation.now
        for action in incident.actions:
            if now + 1e-9 < action.next_boundary:
                continue
            if action.status == "requested":
                action.applied_at, action.status = now, "applied"
                action.affected_sessions = self.simulation.apply_response(action, self.on_completed)
                action.result = f"stopped {len(action.affected_sessions)} active sessions; " + (
                    "persistent policy applied" if action.scope != "session" else
                    "no future policy" if action.affected_sessions else "late/no matching active transfer")
                if self.on_applied:
                    self.on_applied(action)
                self.observe("RESPONSE APPLIED", action.identifier + " " + action.result,
                             action=action, result=action.result)
            elif action.status == "applied":
                matches = [s for s in self.simulation.sessions if action.matches(s)]
                action.verified_at = now
                action.status = "verified" if not matches else "verification failed"
                if action.scope == "session" and not matches:
                    # A stopped final upload can finish this scenario; an earlier
                    # single connection leaves later planned recurrence possible.
                    target_session = next(s for s in incident.sessions if s.identifier == action.target)
                    future_network = any(offset in (2, 16, 30, 44)
                                         for offset, _ in incident.STAGES[incident.next_step:])
                    action.covers_incident = (target_session.profile == "outbound_bulk" and
                                             target_session.identifier in action.affected_sessions and
                                             not future_network and not any(
                                                 s.incident_id == incident.identifier
                                                 for s in self.simulation.sessions))
                action.result = ("scope verified: no matching active sessions; " +
                                 ("no residual or planned incident network activity" if action.covers_incident else
                                  "late/no matching active transfer; no action-caused containment"
                                  if action.scope == "session" and not action.affected_sessions else
                                  "other/future sessions remain outside this scope")) if not matches else "matching sessions remain"
                self.observe("RESPONSE VERIFIED", action.identifier + " " + action.result,
                             action=action, result=action.result)
                if incident.contained:
                    incident.stage, incident.disposition = "CONTAINMENT VERIFIED", "contained"

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
        revoked = next((a for a in self.simulation.policies.values()
                        if a.scope == "credential" and a.target == "aster.ws1"), None)
        if revoked:
            self.active.stage = "AUTH REJECTED"
            self.observe("AUTH REJECTED", f"login for user aster.ws1 rejected by "
                         f"{revoked.identifier}; credential remains revoked; no successful use")
        else:
            self.observe("AUTH ANOMALY", "5 failed logins then success for user aster.ws1; "
                         "configured baseline 0-1 failures per login; credential misuse suspected")
        return self.active

    def start_session(self, bulk=False):
        incident = self.active
        connection = (incident.route.connection if not incident.sessions else
                      self.simulation.organization.connect("ATH-WS1", "EXT-DXB", "HTTPS"))
        session = self.simulation.create(connection, profile="outbound_bulk" if bulk else None,
                                         reserved=True, credential_id="aster.ws1")
        if session is None:
            raise RuntimeError("Scenario reservation invariant violated")
        session.incident_id = incident.identifier
        incident.sessions.append(session)
        incident.mark_route(self.make_route(connection, session))
        if session.complete:
            incident.stage = "POLICY DENIED"
            self.observe("POLICY DENIED", f"{session.response_action_id} prevented new session; "
                         "zero transferred bytes", session)
        return session

    def completed_session(self, session):
        if self.active and session.incident_id == self.active.identifier:
            self.observe("SESSION FINISHED", f"{session.state} transport; "
                         f"orig/resp_bytes={session.orig_bytes}/{session.resp_bytes}; "
                         f"action={session.response_action_id or 'none'}; assessment pending", session)

    def process_boundary(self):
        now = self.simulation.now
        if self.active is None:
            if self.automatic and now + 1e-9 >= self.next_start:
                if self.start() is None:
                    self.next_start = now + 1.0  # Retry without half-created evidence.
            return
        incident = self.active
        incident.age = now - incident.started_at
        self.process_responses()
        if incident.next_step >= len(incident.STAGES):
            self.finish_if_ready()
            return
        if now + 1e-9 < incident.next_boundary:
            return
        offset, stage = incident.STAGES[incident.next_step]
        if not incident.contained:
            incident.stage = stage
        incident.next_step += 1
        if incident.contained and offset != 74:
            return  # Verified broad policy cancels remaining scenario network stages.
        if offset == 2:
            session = self.start_session()
            if session.complete:
                return
            self.observe(incident.stage, "first scenario contact with 203.0.113.201; "
                         "outside ATH-WS1 baseline (FRA-APP HTTPS / FRA-DNS DNS)", session)
        elif offset in (16, 30):
            session = self.start_session()
            if session.complete:
                return
            self.observe(incident.stage, f"HTTPS connection {len(incident.sessions)} to same peer; "
                         "14s start intervals; recurrence observed, intent unconfirmed", session)
        elif offset == 44:
            session = self.start_session(bulk=True)
            if session.complete:
                return
            self.observe(incident.stage, "HTTPS/TLS outbound upload started to same unfamiliar peer; "
                         "payload unavailable; suspected data removal (TA0010)", session)
        elif offset == 49:
            session = incident.sessions[-1]
            if session.complete:
                incident.stage = "TRANSFER STOPPED"
                self.observe(incident.stage, f"{session.state}; orig/resp_bytes="
                             f"{session.orig_bytes}/{session.resp_bytes}; "
                             f"action={session.response_action_id}; no live transfer", session)
                return
            self.observe(incident.stage, f"{session.orig_bytes:,} originator bytes since upload start; "
                         "expected HTTPS 3,600 originator bytes per 12s session; "
                         f"content unknown; session {session.state}", session)
        else:
            self.finish_if_ready()

    def finish_if_ready(self):
        incident = self.active
        if any(a.status in ("requested", "applied") for a in incident.actions):
            return  # Final scenario boundary consumed; only response boundaries remain.
        incident.disposition = "contained" if incident.contained else "unresolved"
        incident.finished_at = self.simulation.now
        self.observe(incident.stage, "scenario ended; " + incident.disposition + "; " +
                     incident.response_status, incident.sessions[-1] if incident.sessions else None)
        self.history.append(incident)
        self.active = None
        self.simulation.reserved_slots = 0
        self.next_start = self.simulation.now + self.rng.uniform(30, 90)
