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
    severity: str = "critical"
    confidence: str = "limited"
    confidence_reason: str = ""
    assessment: str = "suspected credential misuse"
    disposition: str = "pending"
    response_status: str = "none"
    assessment_update: bool = False
    received_at: float = None

    def summary(self):
        session = " / " + self.session_id if self.session_id else ""
        receipt = (f" received={self.received_at:.2f} lag={max(0, self.received_at - self.timestamp):.2f}s"
                   if self.received_at is not None else " receipt=pending")
        return (f"t={self.timestamp:.2f}{receipt} {self.identifier} {self.incident_id} "
                f"{self.source_id}>{self.peer_id}{session} / {self.stage}: {self.message} / "
                f"severity={self.severity} confidence={self.confidence} "
                f"assessment={self.assessment} disposition={self.disposition} response={self.response_status}")

    def detail_lines(self):
        receipt = (f"received={self.received_at:.2f} lag={max(0, self.received_at - self.timestamp):.2f}s"
                   if self.received_at is not None else "receipt=pending")
        return (f"t={self.timestamp:.2f} {self.identifier} {self.incident_id} / {self.stage}", receipt,
                f"  {self.source_id}>{self.peer_id} / {self.collector_id} / {self.session_id or 'no session'}") + tuple(
                        textwrap.wrap(f"severity={self.severity} confidence={self.confidence} "
                                      f"assessment={self.assessment} disposition={self.disposition} "
                                      f"response={self.response_status}; reason: {self.confidence_reason}", width=72)) + tuple(
                    textwrap.wrap(self.message, width=72, initial_indent="  ", subsequent_indent="  "))


class CriticalIncident:
    # The partial variant reserves two slots for concurrent related uploads.
    STAGES = ((0, "AUTH ANOMALY"), (2, "NEW PEER"),
              (16, "RECURRING EGRESS"), (30, "RECURRING EGRESS"),
              (44, "OUTBOUND TRANSFER"), (49, "UNUSUAL VOLUME"),
              (74, "UNRESOLVED"))
    LIFETIME = 74.0

    def __init__(self, route, number, started_at=0.0, variant="exfiltration"):
        self.route = route
        self.identifier = f"CT-{number:03d}"
        self.started_at = started_at
        self.variant = variant
        self.source_id, self.peer_id = route.connection.source_id, route.connection.peer_id
        self.credential_id = "aster.backup" if variant == "benign" else "aster.ws1"
        self._severity = "critical"  # Historical priority is never rewritten by outcome.
        self.confidence = "limited"
        self.confidence_reason = "authentication failures exceed the configured baseline; intent unconfirmed"
        self.confidence_reasons = deque([self.confidence_reason], maxlen=8)
        self.assessment = "suspected credential misuse"
        self.visible_stage = "EVIDENCE PENDING"
        self._assessment_time = (-math.inf, -1)
        self._visible_stage_time = (-math.inf, -1)
        self.delivered_ids = deque(maxlen=128)
        self._delivered_ids = set()
        self.dismissal_reason = ""
        self.partial_observed = False
        if variant == "benign":
            self.STAGES = ((0, "TRANSFER ALERT"), (2, "OUTBOUND TRANSFER"),
                           (7, "AUTHORIZATION MATCH"), (32, "ASSESSMENT COMPLETE"))
            self.confidence_reason = "queued request declares bulk transfer; ownership/approval not yet reconciled"
            self.confidence_reasons = deque([self.confidence_reason], maxlen=8)
            self.assessment = "suspected exfiltration"
        elif variant == "partial":
            self.STAGES = self.STAGES[:-2] + ((46, "RELATED ENDPOINT"),
                                             (49, "UNUSUAL VOLUME"), (76, "UNRESOLVED"))
        self.LIFETIME = self.STAGES[-1][0]
        self.age = 0.0
        self.following = True
        self.stage = self.STAGES[0][1]
        self.disposition = "pending"
        self.finished_at = None
        self.timeline = deque(maxlen=64)  # Original evidence plus 8 response lifecycles.
        self.observation_count = 0
        self.sessions = []
        self.next_step = 1
        self.actions = []
        self.routes = []  # At most the auth anchor plus five modeled sessions.
        self.scheduled_job = ({"job_id": "JOB-FRA-SIN-001", "approved_by": "Platform team",
                               "source_id": "FRA-BKP", "peer_id": "SIN-STORE", "service": "BACKUP",
                               "purpose": "scheduled replication"} if variant == "benign" else None)
        self.mark_route(route)

    def mark_route(self, route):
        self.route = route
        if route not in self.routes:
            self.routes.append(route)
        route.critical = route.flagged = True

    @property
    def contained(self):
        return any(a.status == "verified" and a.covers_incident for a in self.actions)

    @property
    def severity(self):
        return self._severity

    @property
    def response_phase(self):
        return self.actions[-1].status if self.actions else "none"

    @property
    def residual_risk(self):
        active = [s for s in self.sessions if not s.complete]
        if self.confidence == "unobserved":
            return "no delivered evidence; modeled activity is not an available incident assessment"
        if self.assessment == "authorized transfer":
            return "authorized legitimate transfer" + (" continues" if active else " completed")
        if self.contained:
            return "no residual modeled incident network activity; payload content remains unknown"
        if active:
            return "active related sessions: " + ", ".join(s.identifier for s in active)
        return "suspected data removal unresolved; future activity may remain" if not self.complete else "historical suspected data removal unresolved"

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
        return (f"{self.identifier} {self.visible_stage} / variant={self.variant} severity={self.severity} "
                f"confidence={self.confidence} assessment={self.assessment} disposition={self.disposition} / "
                f"{self.source_id}>{self.peer_id} / sessions={len(self.sessions)} / "
                f"orig/resp_bytes={orig}/{resp} / {self.response_status}")

    def detail_lines(self):
        return tuple(textwrap.wrap(self.summary(), width=72)) + tuple(
            textwrap.wrap("Confidence reason: " + self.confidence_reason, width=72)) + tuple(
            textwrap.wrap("Residual risk: " + self.residual_risk, width=72)) + tuple(
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
    apply_delay: float = 1.0
    verify_delay: float = 1.0
    outcome: str = "pending"

    APPLY_DELAY = 1.0
    VERIFY_DELAY = 1.0

    def matches(self, session):
        connection = session.connection
        return self.matches_scope(connection.source_id, connection.peer_id,
                                  session.credential_id, session.identifier)

    def matches_scope(self, source_id, peer_id, credential_id, session_id=""):
        if self.scope == "session":
            return session_id == self.target
        if self.scope == "endpoint":
            return self.target in (source_id, peer_id)
        if self.scope == "peer":
            return source_id == self.target and peer_id == self.peer_id
        return credential_id == self.target

    @property
    def next_boundary(self):
        if self.status == "requested":
            return self.requested_at + self.apply_delay
        if self.status == "applied":
            return self.applied_at + self.verify_delay
        return math.inf

    def detail_lines(self):
        return tuple(textwrap.wrap(
            f"{self.identifier} {self.kind} {self.scope}={self.target}" +
            (f">{self.peer_id}" if self.peer_id else "") +
            f" / {self.status} / requested={self.requested_at:.2f} " +
            f"applied={self.applied_at} verified={self.verified_at} / outcome={self.outcome} / {self.result}", width=72))


class IncidentSimulation:
    """Scenario events share SessionSimulation's exact event-boundary clock.

    Callbacks supply terminal routes and logs; all evidence comes from modeled
    authentication and session metadata, with no encrypted payload visibility.
    """

    HISTORY_LIMIT = 64
    ACTION_LIMIT = 8
    VARIANTS = ("exfiltration", "benign", "delayed", "partial")

    def __init__(self, simulation, make_route, emit, seed=None,
                 on_completed=None, on_applied=None, submit_observation=None):
        self.simulation = simulation
        self.make_route = make_route
        self.emit = emit
        self.rng = random.Random(seed)
        self.variant_rng = random.Random(seed)
        self.active = None
        self.history = deque(maxlen=self.HISTORY_LIMIT)
        self.count = 0
        self.next_start = self.rng.uniform(30, 90)
        self.automatic = True
        self.on_completed = on_completed
        self.on_applied = on_applied
        self._next_assessment = None
        self.submit_observation = submit_observation
        self.delivery_errors = deque(maxlen=64)

    def next_boundary(self):
        if self.active:
            action_boundary = min((a.next_boundary for a in self.active.actions), default=math.inf)
            return min(self.active.next_boundary, action_boundary)
        return max(self.simulation.now, self.next_start) if self.automatic else math.inf

    def observe(self, stage, message, session=None, action=None, result=""):
        incident = self.active
        if session is None and action and action.scope == "session":
            session = next((candidate for candidate in incident.sessions
                            if candidate.identifier == action.target), None)
        incident.observation_count += 1
        source_id = (session.connection.source_id if session else action.target
                     if action and action.scope in ("endpoint", "peer") else
                     self.simulation.organization.credentials[action.target]
                     if action and action.scope == "credential" else incident.source_id)
        peer_id = (action.peer_id if action.scope == "peer" else
                   (session.connection.peer_id if session else incident.peer_id)
                   if action.scope == "session" else "") if action else (
                       session.connection.peer_id if session else incident.peer_id)
        collector_id = self.simulation.organization.assets[source_id].collector_id
        assessment_update = self._next_assessment is not None
        confidence, assessment, reason = self._next_assessment or (
            incident.confidence, incident.assessment, incident.confidence_reason)
        self._next_assessment = None
        observation = Observation(f"{incident.identifier}-OBS-{incident.observation_count:02d}",
                                  incident.identifier, self.simulation.now, stage,
                                  source_id, peer_id, collector_id,
                                  session.identifier if session else "", message,
                                  action.identifier if action else "", result, incident.severity,
                                  confidence, reason, assessment,
                                  incident.disposition, incident.response_phase, assessment_update)
        if self.submit_observation:
            self.submit_observation(observation)
        else:
            self.deliver_observation(observation)

    def find_incident(self, identifier):
        if self.active and self.active.identifier == identifier:
            return self.active
        return next((incident for incident in self.history if incident.identifier == identifier), None)

    def deliver_observation(self, observation):
        """Evidence receipt hook: visible confidence changes only on delivery.

        Collectors can later defer this call without revealing a stage's proposed
        assessment. Occurrence IDs/times are assigned before delivery.
        """
        incident = self.find_incident(observation.incident_id)
        if incident is None:
            self.delivery_errors.append(f"Unknown/evicted incident {observation.incident_id}; "
                                        f"unattached evidence {observation.identifier}")
            return False
        if observation.identifier in incident._delivered_ids:
            return False
        if len(incident.delivered_ids) == incident.delivered_ids.maxlen:
            incident._delivered_ids.remove(incident.delivered_ids.popleft())
        incident.delivered_ids.append(observation.identifier)
        incident._delivered_ids.add(observation.identifier)
        order = (observation.timestamp, int(observation.identifier.rsplit("-", 1)[1]))
        # Neutral phase/completion snapshots must not roll an assessment back
        # when older observations are eventually delivered after newer evidence.
        if observation.assessment_update and order >= incident._assessment_time:
            incident._assessment_time = order
            incident.confidence, incident.assessment = observation.confidence, observation.assessment
            incident.confidence_reason = observation.confidence_reason
            if observation.confidence_reason not in incident.confidence_reasons:
                incident.confidence_reasons.append(observation.confidence_reason)
        if (observation.stage not in ("SESSION FINISHED", "RESPONSE REQUESTED", "RESPONSE APPLIED",
                                     "RESPONSE CANCELLED", "OPERATOR DISMISSED", "RESPONSE VERIFIED") or
                observation.stage == "RESPONSE VERIFIED" and observation.disposition == "contained") and order >= incident._visible_stage_time:
            incident._visible_stage_time = order
            incident.visible_stage = ("CONTAINMENT VERIFIED" if observation.stage == "RESPONSE VERIFIED"
                                      else observation.stage)
        ordered = sorted(list(incident.timeline) + [observation], key=lambda item: (
            item.timestamp, int(item.identifier.rsplit("-", 1)[1])))
        incident.timeline.clear()
        incident.timeline.extend(ordered)
        self.emit(observation)
        return True

    def assess(self, confidence, assessment, reason):
        self._next_assessment = (confidence, assessment, reason)

    def dismiss(self, reason="operator dismissal"):
        incident = self.active
        if incident is None:
            raise ValueError("No active incident to dismiss")
        if incident.disposition == "dismissed":
            return incident
        incident.disposition, incident.dismissal_reason = "dismissed", reason[:200]
        self.observe("OPERATOR DISMISSED", incident.dismissal_reason + "; " + incident.residual_risk +
                     "; original alert severity/evidence retained; no network policy applied")
        return incident

    def unprotected_future(self, incident):
        remaining = []
        for offset, _ in incident.STAGES[incident.next_step:]:
            if offset in (2, 16, 30, 44):
                target = (incident.source_id, incident.peer_id, incident.credential_id)
            elif offset == 46 and incident.variant == "partial":
                target = ("ATH-ADM", incident.peer_id, "aster.admin")
            else:
                continue
            if not any(a.matches_scope(*target) for a in self.simulation.policies.values()):
                remaining.append(target)
        return remaining

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
        elif target not in self.simulation.organization.credentials:
            raise ValueError("Unknown modeled credential; known: " +
                             ", ".join(self.simulation.organization.credentials))
        key = (kind, scope, target, peer_id)
        existing = next((a for a in incident.actions if
                         (a.kind, a.scope, a.target, a.peer_id) == key), None)
        if existing:
            return existing
        if len(incident.actions) >= self.ACTION_LIMIT:
            raise ValueError("Incident response limit reached (8 actions)")
        action = ResponseAction(f"{incident.identifier}-ACT-{len(incident.actions) + 1:02d}",
                                incident.identifier, kind, scope, target, peer_id,
                                self.simulation.now,
                                apply_delay=5.0 if incident.variant == "delayed" else 1.0,
                                verify_delay=3.0 if incident.variant == "delayed" else 1.0)
        incident.actions.append(action)
        self.observe("RESPONSE REQUESTED", f"{action.identifier} {kind}: {scope}={target}" +
                     (f">{peer_id}" if peer_id else "") +
                     f"; pending application in {action.apply_delay:g} simulation seconds; "
                     f"verification window {action.verify_delay:g}s", action=action, result="pending")
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
                active_route = next((route for route in reversed(incident.routes)
                                     if route.session is not None and not route.session.complete), None)
                if active_route:
                    incident.mark_route(active_route)
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
                residual = [s for s in incident.sessions if not s.complete]
                future = self.unprotected_future(incident)
                escaped = [s for s in incident.sessions
                           if s.profile == "outbound_bulk" and s.state == "completed" and s.orig_bytes]
                related_effect = any(s.identifier in action.affected_sessions for s in incident.sessions)
                protected = action.scope != "session" and any(
                    action.matches_scope(source, peer, credential) for source, peer, credential in
                    ((incident.source_id, incident.peer_id, incident.credential_id),
                     ("ATH-ADM", incident.peer_id, "aster.admin"))[:2 if incident.variant == "partial" else 1])
                action.covers_incident = (not matches and not residual and not future and not escaped and
                                         (related_effect or protected))
                if matches:
                    action.outcome, action.result = "failed", "matching sessions remain"
                elif action.covers_incident:
                    action.outcome = "contained"
                    action.result = "scope verified: no matching active sessions; no residual or planned incident network activity"
                elif related_effect or protected:
                    action.outcome = "partial"
                    action.result = ("scope verified; other/future sessions remain outside this scope; " +
                                     ("residual active: " + ", ".join(s.identifier for s in residual) if residual else
                                      "uncontained completed transfers: " + ", ".join(s.identifier for s in escaped) if escaped else
                                      "unprotected planned endpoints: " + ", ".join(t[0] for t in future)))
                    incident.partial_observed = True
                    if incident.disposition != "dismissed":
                        incident.disposition = "partially contained"
                else:
                    action.outcome = "no incident effect"
                    action.result = "scope verified; late/no matching active transfer; no action-caused containment"
                if incident.contained:
                    incident.stage = "CONTAINMENT VERIFIED"
                    if incident.disposition != "dismissed":
                        incident.disposition = "contained"
                self.observe("RESPONSE VERIFIED", action.identifier + " " + action.result,
                             action=action, result=action.result)

    def start(self, variant="exfiltration"):
        if self.active:
            return self.active
        if variant == "seeded":
            variant = self.variant_rng.choice(self.VARIANTS)
        if variant not in self.VARIANTS:
            raise ValueError("Scenario variants: " + ", ".join(self.VARIANTS) + ", seeded")
        reservation = 2 if variant == "partial" else 1
        if len(self.simulation.sessions) > self.simulation.MAX_ACTIVE - reservation:
            return None
        self.simulation.reserved_slots = reservation
        self.count += 1
        # Allocate the first flow ID now; no session/bytes exist until NEW PEER.
        source, peer, service = (("FRA-BKP", "SIN-STORE", "BACKUP") if variant == "benign" else
                                 ("ATH-WS1", "EXT-DXB", "HTTPS"))
        connection = self.simulation.organization.connect(source, peer, service)
        route = self.make_route(connection, None)
        self.active = CriticalIncident(route, self.count, self.simulation.now, variant)
        initial_confidence, initial_assessment, initial_reason = (
            self.active.confidence, self.active.assessment, self.active.confidence_reason)
        self.active.confidence, self.active.assessment = "unobserved", "awaiting evidence"
        self.active.confidence_reason = "no collector evidence delivered"
        self.active.confidence_reasons.clear()
        self.assess(initial_confidence, initial_assessment, initial_reason)
        revoked = next((a for a in self.simulation.policies.values()
                        if a.scope == "credential" and a.target == self.active.credential_id), None)
        if variant == "benign":
            self.observe("TRANSFER ALERT", "queued job request declares a bulk transfer from FRA-BKP to SIN-STORE; "
                         "generic data-removal alert before execution; ownership/authorization not yet reconciled; "
                         "no bytes measured yet; TLS payload unknown")
        elif revoked:
            self.active.stage = "AUTH REJECTED"
            self.observe("AUTH REJECTED", f"login for user aster.ws1 rejected by "
                         f"{revoked.identifier}; credential remains revoked; no successful use")
        else:
            self.observe("AUTH ANOMALY", "5 failed logins then success for user aster.ws1; "
                         "configured baseline 0-1 failures per login; credential misuse suspected")
        return self.active

    def start_session(self, bulk=False, secondary=False):
        incident = self.active
        connection = (incident.route.connection if not incident.sessions else
                      self.simulation.organization.connect("ATH-ADM" if secondary else incident.source_id,
                                                           incident.peer_id, "BACKUP" if incident.variant == "benign" else "HTTPS"))
        session = self.simulation.create(connection, profile="outbound_bulk" if bulk else None,
                                         reserved=True, credential_id="aster.admin" if secondary else incident.credential_id)
        if session is None:
            raise RuntimeError("Scenario reservation invariant violated")
        session.incident_id = incident.identifier
        if incident.variant == "benign":
            session.schedule_context = dict(incident.scheduled_job)
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
                         f"action={session.response_action_id or 'none'}; assessment={self.active.assessment}", session)

    def process_boundary(self):
        now = self.simulation.now
        if self.active is None:
            if self.automatic and now + 1e-9 >= self.next_start:
                if self.start("seeded") is None:
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
        if incident.contained and offset != incident.LIFETIME and incident.variant != "benign":
            return  # Verified broad policy cancels remaining scenario network stages.
        if incident.variant == "benign":
            if offset == 2:
                session = self.start_session()
                if not session.complete:
                    self.observe(incident.stage, "30s BACKUP/TLS upload; modeled job identity awaiting owner confirmation; "
                                 "content unknown", session)
            elif offset == 7:
                session = incident.sessions[0]
                job = session.schedule_context
                match = (job["source_id"], job["peer_id"], job["service"]) == (
                    session.connection.source_id, session.connection.peer_id, session.service)
                if match:
                    self.assess("low", "authorized transfer", "owner approval matches JOB-FRA-SIN-001, expected peer/service and replication profile")
                    self.observe("AUTHORIZATION MATCH", f"{job['approved_by']} confirms {job['job_id']}: approved scheduled replication "
                                 f"{session.connection.source_id}>{session.connection.peer_id}; actual service {session.service}; "
                                 "authorization contradicts data-removal hypothesis; TLS content remains unknown", session)
            else:
                self.finish_if_ready()
            return
        if offset == 2:
            session = self.start_session()
            if session.complete:
                return
            self.assess("supported", "suspected exfiltration", "new peer outside ATH-WS1 expected HTTPS/DNS relationships follows authentication anomaly")
            self.observe(incident.stage, "first scenario contact with 203.0.113.201; "
                         "outside ATH-WS1 baseline (FRA-APP HTTPS / FRA-DNS DNS)", session)
        elif offset in (16, 30):
            session = self.start_session()
            if session.complete:
                return
            self.assess("supported", "suspected exfiltration", "recurring HTTPS sessions to the same unfamiliar peer at 14s intervals; intent unconfirmed")
            self.observe(incident.stage, f"HTTPS connection {len(incident.sessions)} to same peer; "
                         "14s start intervals; recurrence observed, intent unconfirmed", session)
        elif offset == 44:
            session = self.start_session(bulk=True)
            if session.complete:
                return
            self.observe(incident.stage, "HTTPS/TLS outbound upload started to same unfamiliar peer; "
                         "payload unavailable; suspected data removal (TA0010)", session)
        elif offset == 46:
            session = self.start_session(bulk=True, secondary=True)
            if not session.complete:
                self.assess("supported", "suspected exfiltration", "related ATH-ADM upload uses same unfamiliar peer; a second local endpoint remains in scope")
                self.observe(incident.stage, "ATH-ADM starts related HTTPS/TLS upload to same peer using aster.admin; "
                             "separate actual transfer and credential; content unknown", session)
        elif offset == 49:
            bulk_sessions = [s for s in incident.sessions if s.profile == "outbound_bulk"]
            session = next((s for s in bulk_sessions if not s.complete), bulk_sessions[0])
            if session.complete:
                incident.stage = "TRANSFER STOPPED"
                self.observe(incident.stage, f"{session.state}; orig/resp_bytes="
                             f"{session.orig_bytes}/{session.resp_bytes}; "
                             f"action={session.response_action_id}; no live transfer", session)
                return
            self.assess("strong", "suspected exfiltration", f"{session.connection.source_id} outbound bytes greatly exceed reference interactive HTTPS volume; encrypted content unknown")
            self.observe(incident.stage, f"{session.orig_bytes:,} originator bytes since upload start; "
                         "reference interactive HTTPS profile: 3,600 originator bytes per 12s session; "
                         f"content unknown; session {session.state}", session)
        else:
            self.finish_if_ready()

    def finish_if_ready(self):
        incident = self.active
        if any(a.status in ("requested", "applied") for a in incident.actions):
            return  # Final scenario boundary consumed; only response boundaries remain.
        if incident.disposition != "dismissed":
            incident.disposition = ("contained" if incident.contained else
                                    "partially contained" if incident.partial_observed else "unresolved")
        incident.finished_at = self.simulation.now
        self.observe(incident.stage, "scenario ended; " + incident.disposition + "; " +
                     incident.response_status, incident.sessions[-1] if incident.sessions else None)
        self.history.append(incident)
        self.active = None
        self.simulation.reserved_slots = 0
        self.next_start = self.simulation.now + self.rng.uniform(30, 90)
