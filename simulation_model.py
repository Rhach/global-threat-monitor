"""Persistent fictional organization for the offline simulation (Python 3.9+).

Collectors describe observation coverage, not asset ownership or peer geography.
No networking, wall clock, terminal, or rendering behavior belongs in this model.
"""

from dataclasses import dataclass
from collections import deque
import math
import random
from typing import Dict, Optional, Tuple


def valid_advance(dt):
    """Invalid or backwards elapsed time never mutates the simulation."""
    return float(dt) if isinstance(dt, (int, float)) and math.isfinite(dt) and dt > 0 else 0.0


class Session:
    """An analytically integrated payload profile, independent of update cadence.

    Segments contain start/end ages and directional bytes per second. Rates are
    payload Mb/s over the previous one simulation second (zero before creation).
    Packet counts model payload-bearing datagrams/segments, not wire overhead.
    conn_state uses Zeek's vocabulary; this is not a Zeek log implementation.
    """

    RATE_WINDOW = 1.0
    PROFILES = {
        "DNS": ("udp", 53, "none", 0.2,
                ((0, 0.04, 1800, 0), (0.08, 0.16, 0, 2750))),
        "HTTPS": ("tcp", 443, "TLS", 12.0,
                  tuple(segment for t in (0, 4, 8) for segment in
                        ((t, t + 0.2, 6000, 0), (t + 0.3, t + 1.3, 0, 240000)))),
        "SSH": ("tcp", 22, "SSH", 180.0,
                ((0, 180, 24, 40),) + tuple(
                    (t, t + 0.5, 320, 1200) for t in range(2, 180, 10))),
        "BACKUP": ("tcp", 443, "TLS", 30.0, ((0, 30, 2000000, 10000),)),
    }

    def __init__(self, connection, started_at=0.0, orig_port=49152, profile=None):
        self.connection = connection
        self.identifier = connection.identifier
        self.service = connection.service
        if self.service not in self.PROFILES:
            raise ValueError("Unsupported simulated service: " + self.service)
        self.proto, self.resp_port, self.encryption, self.lifetime, self.segments = self.PROFILES[self.service]
        self.profile = profile or "baseline"
        self.incident_id = None
        self.severity = "info" if connection.expected else "med"
        self.credential_id = None
        self.response_action_id = None
        if profile is not None:
            if profile != "outbound_bulk" or self.service != "HTTPS":
                raise ValueError("Unsupported session profile: " + str(profile))
            # HTTPS remains the application service; TLS is encryption only.
            self.lifetime = 30.0
            self.segments = ((0, 30, 2000000, 10000),)
        self.orig_port = orig_port
        self.started_at = started_at
        self.now = started_at
        self.stopped_at = None
        self.state = "active"
        self.orig_bytes = self.resp_bytes = self.orig_pkts = self.resp_pkts = 0
        self.orig_rate = self.resp_rate = 0.0

    @property
    def duration(self):
        return max(0.0, min(self.now - self.started_at, self.lifetime,
                            self.stopped_at - self.started_at if self.stopped_at is not None else self.lifetime))

    @property
    def complete(self):
        return self.state != "active"

    @property
    def conn_state(self):
        if self.complete:
            return "SF" if self.state == "completed" else "RSTO"
        return "S1" if self.proto == "tcp" or self.resp_bytes else "S0"

    @property
    def rate(self):
        return self.orig_rate + self.resp_rate

    def totals_at(self, now):
        age = max(0.0, min(now - self.started_at, self.lifetime))
        if self.stopped_at is not None:
            age = min(age, self.stopped_at - self.started_at)
        values = [0.0, 0.0, 0.0, 0.0]
        for start, end, orig, resp in self.segments:
            seconds = max(0.0, min(age, end) - start)
            for direction, bps in enumerate((orig, resp)):
                values[direction] += seconds * bps
                # Packetize each burst's transmitted payload, including a
                # partial final segment. Epsilon avoids float-induced extras.
                payload = int(seconds * bps + 1e-7)
                values[direction + 2] += math.ceil(payload / (512 if self.proto == "udp" else 1200))
        return tuple(int(value + 1e-7) for value in values)

    def advance_to(self, now):
        if not math.isfinite(now) or now < self.now:
            return
        self.now = now
        if self.state == "active" and now + 1e-9 >= self.started_at + self.lifetime:
            self.state = "completed"
        self.orig_bytes, self.resp_bytes, self.orig_pkts, self.resp_pkts = self.totals_at(now)
        previous = self.totals_at(now - self.RATE_WINDOW)
        self.orig_rate = (self.orig_bytes - previous[0]) * 8 / 1000000 / self.RATE_WINDOW
        self.resp_rate = (self.resp_bytes - previous[1]) * 8 / 1000000 / self.RATE_WINDOW
        if self.complete:
            self.orig_rate = self.resp_rate = 0.0

    def stop(self, now, state, action_id):
        if self.complete:
            return False
        self.stopped_at = now
        self.state = state
        self.response_action_id = action_id
        self.advance_to(now)
        return True

    def summary(self):
        return (f"{self.identifier} {self.proto}/{self.service} encryption={self.encryption} "
                f"ports={self.orig_port}>{self.resp_port} {self.state}/{self.conn_state} "
                f"duration={self.duration:.2f}s orig/resp_bytes={self.orig_bytes}/{self.resp_bytes} "
                f"orig/resp_pkts={self.orig_pkts}/{self.resp_pkts} "
                f"orig/resp_Mb/s={self.orig_rate:.4f}/{self.resp_rate:.4f} (1s window)" +
                (f" / action={self.response_action_id}" if self.response_action_id else ""))

    def detail_lines(self):
        """Console facts stay readable at the minimum terminal width."""
        return (f"{self.identifier} {self.proto}/{self.service} encryption={self.encryption} "
                f"ports={self.orig_port}>{self.resp_port} {self.state}/{self.conn_state}",
                f"  duration={self.duration:.2f}s orig/resp_bytes={self.orig_bytes}/{self.resp_bytes}",
                f"  orig/resp_pkts={self.orig_pkts}/{self.resp_pkts} "
                f"Mb/s={self.orig_rate:.4f}/{self.resp_rate:.4f} (1s window)") + (
                    (f"  action={self.response_action_id or 'none'} credential={self.credential_id or 'none'}",)
                    if self.response_action_id or self.credential_id else ())


class SessionSimulation:
    """Bounded sessions, seeded scheduling and exact one-second traffic buckets.

    Advance through spawn, completion and sampling boundaries, including every
    boundary crossed by a large dt. Callbacks run at their simulation timestamp.
    Traffic includes completed sessions' final bytes; there is no hidden aggregate.
    """

    MAX_ACTIVE = 12
    HISTORY_LIMIT = 120

    def __init__(self, organization, seed=None):
        self.organization = organization
        self.rng = random.Random(seed)
        self.now = 0.0
        self._advance_total = 0.0
        self._time_correction = 0.0
        self.sessions = []
        self.reserved_slots = 0
        self.history = deque(maxlen=self.HISTORY_LIMIT)
        self.traffic_history = deque([0.0], maxlen=120)
        self.total_bytes = 0
        from map_layers import EndpointActivity
        self.endpoint_activity = EndpointActivity(organization)
        self.collector_bytes = {identifier: 0 for identifier in organization.collectors}
        self.last_sample_bytes = 0
        self.sample_time = 1.0
        self.next_spawn = 0.0
        self.automatic = True
        self.throughput = 0.0
        # Persistent scope is bounded by the finite asset/peer/credential catalog.
        # Session-only responses need no retained policy: flow IDs never recur.
        self.policies = {}

    def create(self, connection=None, profile=None, reserved=False, credential_id=None):
        if len(self.sessions) >= self.MAX_ACTIVE - (0 if reserved else self.reserved_slots):
            return None
        connection = connection or self.organization.choose_connection()
        session = Session(connection, self.now, self.rng.randint(49152, 65535), profile)
        session.credential_id = credential_id
        policy = next((action for action in self.policies.values() if action.matches(session)), None)
        if policy:
            session.stop(self.now, "denied", policy.identifier)
            self.history.append(session)
        else:
            self.sessions.append(session)
        return session

    def apply_response(self, action, on_completed=None):
        """Called at the effective boundary after all bytes reach that instant."""
        if action.scope != "session":
            self.policies[(action.kind, action.scope, action.target, action.peer_id)] = action
        affected = []
        state = {"block": "blocked", "isolate": "isolated", "revoke": "revoked"}[action.kind]
        for session in list(self.sessions):
            if action.matches(session) and session.stop(self.now, state, action.identifier):
                self.sessions.remove(session)
                self.history.append(session)
                affected.append(session.identifier)
                if on_completed:
                    on_completed(session)
        return tuple(affected)

    def advance(self, dt, on_created=None, on_completed=None, on_sample=None,
                next_boundary=None, on_boundary=None):
        # Compensated summation avoids accumulating rounding at every frame.
        delta = valid_advance(dt) - self._time_correction
        advanced = self._advance_total + delta
        if not math.isfinite(advanced):
            return
        self._time_correction = (advanced - self._advance_total) - delta
        self._advance_total = advanced
        target = round(advanced, 12)
        if target <= self.now:
            return
        if self.automatic and self.next_spawn < self.now:
            self.next_spawn = self.now  # Resuming background work never rewinds.
        while self.now < target:
            boundary = min(target, self.sample_time,
                           next_boundary() if next_boundary else target,
                           self.next_spawn if self.automatic else target,
                           min((s.started_at + s.lifetime for s in self.sessions), default=target))
            self.now = boundary
            for session in list(self.sessions):
                before = session.orig_bytes + session.resp_bytes
                session.advance_to(boundary)
                transferred = session.orig_bytes + session.resp_bytes - before
                self.total_bytes += transferred
                self.endpoint_activity.add(session.connection, transferred)
                self.collector_bytes[session.connection.collector_id] += transferred
                if session.complete:
                    self.sessions.remove(session)
                    self.history.append(session)
                    if on_completed:
                        on_completed(session)
            if on_boundary:
                on_boundary()
            if boundary + 1e-9 >= self.sample_time:
                self.endpoint_activity.sample(self.now)
                self.throughput = (self.total_bytes - self.last_sample_bytes) * 8 / 1000000
                self.last_sample_bytes = self.total_bytes
                self.traffic_history.append(self.throughput)
                self.sample_time += 1.0
                if on_sample:
                    on_sample()
            if self.automatic and boundary + 1e-9 >= self.next_spawn:
                if len(self.sessions) < 5:
                    session = self.create()
                    if session is not None and on_created:
                        on_created(session)
                self.next_spawn = round(self.next_spawn + self.rng.uniform(0.7, 1.6), 12)


@dataclass(frozen=True)
class Site:
    identifier: str
    name: str
    code: str
    role: str
    owner: str
    criticality: str
    city_code: Optional[str]
    utc_offset_minutes: int = 0


@dataclass(frozen=True)
class Asset:
    identifier: str
    name: str
    short_name: str
    site_id: str
    role: str
    owner: str
    criticality: str
    address: str
    city_code: Optional[str]
    collector_id: Optional[str]


@dataclass(frozen=True)
class Collector:
    identifier: str
    city: Tuple[float, float, str, str]


@dataclass(frozen=True)
class ExpectedConnection:
    source_id: str
    peer_id: str
    service: str
    purpose: str


@dataclass(frozen=True)
class Connection:
    identifier: str
    source_id: str
    peer_id: str
    service: str
    expected: bool
    purpose: str
    collector_id: str


class Organization:
    """Bounded catalog plus connection selection shared by UI and background work.

    Only connection IDs grow; completed records are retained by callers, not here.
    An injected random.Random-compatible object permits deterministic fixtures.
    """

    def __init__(self, cities, seed=None, rng=None):
        self.rng = rng if rng is not None else random.Random(seed)
        self.cities = {city[3]: city for city in cities}
        self.collectors: Dict[str, Collector] = {
            "COL-" + code: Collector("COL-" + code, city)
            for code, city in self.cities.items()
        }
        self.sites = {
            site.identifier: site for site in (
                Site("SITE-ATH", "Aster Athens office", "ATH", "office",
                     "Workplace IT", "medium", "ATH", 120),
                Site("SITE-FRA", "Aster Frankfurt data center", "FRA", "data-center",
                     "Platform team", "high", "FRA", 60),
                Site("SITE-SIN", "Aster Singapore cloud region", "SIN", "cloud",
                     "Cloud team", "high", "SIN", 480),
                Site("SITE-REMOTE", "Aster remote users", "REM", "remote-user",
                     "Workplace IT", "medium", None),
                Site("SITE-EXTERNAL", "External peers", "EXT", "external",
                     "External / unmanaged", "unknown", None),
            )
        }
        definitions = (
            ("ATH-WS1", "Athens workstation", "ws", "SITE-ATH", "workstation",
             "Workplace IT", "medium", "192.0.2.10", "ATH", "COL-ATH"),
            ("ATH-ADM", "Athens administrator", "adm", "SITE-ATH", "admin-endpoint",
             "Platform team", "high", "192.0.2.11", "ATH", "COL-ATH"),
            ("FRA-APP", "Frankfurt application", "app", "SITE-FRA", "application-server",
             "Platform team", "high", "198.51.100.20", "FRA", "COL-FRA"),
            ("FRA-DNS", "Frankfurt resolver", "dns", "SITE-FRA", "dns-resolver",
             "Platform team", "high", "198.51.100.53", "FRA", "COL-FRA"),
            ("FRA-BKP", "Frankfurt backup", "bkp", "SITE-FRA", "backup-server",
             "Platform team", "high", "198.51.100.30", "FRA", "COL-FRA"),
            ("SIN-API", "Singapore API", "api", "SITE-SIN", "cloud-service",
             "Cloud team", "high", "203.0.113.20", "SIN", "COL-SIN"),
            ("SIN-STORE", "Singapore object store", "store", "SITE-SIN", "backup-store",
             "Cloud team", "high", "203.0.113.30", "SIN", "COL-SIN"),
            ("REM-LON", "London remote laptop", "lon", "SITE-REMOTE", "remote-user",
             "Workplace IT", "medium", "192.0.2.40", "LON", "COL-FRA"),
            ("REM-UNK", "Roaming remote laptop", "roam", "SITE-REMOTE", "remote-user",
             "Workplace IT", "medium", "192.0.2.41", None, "COL-FRA"),
            ("EXT-UNK", "Unfamiliar peer", "peer", "SITE-EXTERNAL", "external-peer",
             "External / unmanaged", "unknown", "203.0.113.200", None, None),
            ("EXT-DXB", "Unfamiliar Dubai peer", "peer", "SITE-EXTERNAL", "external-peer",
             "External / unmanaged", "unknown", "203.0.113.201", "DXB", None),
        )
        self.assets = {values[0]: Asset(*values) for values in definitions}
        self.expected_connections = (
            ExpectedConnection("ATH-WS1", "FRA-APP", "HTTPS", "office application"),
            ExpectedConnection("ATH-WS1", "FRA-DNS", "DNS", "name resolution"),
            ExpectedConnection("ATH-ADM", "FRA-APP", "SSH", "platform administration"),
            ExpectedConnection("FRA-APP", "SIN-API", "HTTPS", "regional API"),
            ExpectedConnection("FRA-APP", "FRA-DNS", "DNS", "name resolution"),
            ExpectedConnection("FRA-BKP", "SIN-STORE", "BACKUP", "backup replication"),
            ExpectedConnection("REM-LON", "FRA-APP", "HTTPS", "remote application"),
            ExpectedConnection("REM-UNK", "FRA-APP", "HTTPS", "remote application"),
        )
        self._connection_number = 0
        self.credentials = {"aster.ws1": "ATH-WS1", "aster.admin": "ATH-ADM",
                            "aster.backup": "FRA-BKP"}

    def city_for(self, asset_id):
        """None is deliberately preserved for unknown geography."""
        return self.cities.get(self.assets[asset_id].city_code)

    def asset_label(self, asset_id):
        asset = self.assets[asset_id]
        site = self.sites[asset.site_id]
        return site.code + ":" + asset.short_name + ("?" if asset.city_code is None else "")

    def context(self, connection):
        return self.asset_label(connection.source_id) + ">" + self.asset_label(connection.peer_id)

    def describe(self, connection):
        source, peer = self.assets[connection.source_id], self.assets[connection.peer_id]
        geography = " / geography unknown" if source.city_code is None or peer.city_code is None else ""
        baseline = "expected" if connection.expected else "unfamiliar; review baseline"
        return (f"{self.context(connection)} {baseline}{geography} / {connection.service} / "
                f"{source.identifier}@{source.site_id} > {peer.identifier}@{peer.site_id} / "
                f"{source.address} > {peer.address} / {connection.collector_id} / "
                f"{connection.identifier} / {connection.purpose}")

    def connect(self, source_id, peer_id, service):
        """Assess against configured relationships; geography never sets assessment."""
        source = self.assets[source_id]
        self.assets[peer_id]  # Reject absent peers without manufacturing an asset.
        if source.collector_id is None:
            raise ValueError("A modeled connection needs an observing collector")
        relationship = next((entry for entry in self.expected_connections
                             if (entry.source_id, entry.peer_id, entry.service) ==
                             (source_id, peer_id, service)), None)
        self._connection_number += 1
        return Connection(f"FLOW-{self._connection_number:05d}", source_id, peer_id,
                          service, relationship is not None,
                          relationship.purpose if relationship else "outside configured peer/service baseline",
                          source.collector_id)

    def choose_connection(self, unexpected=None):
        """Favor the baseline (90%); unfamiliar does not assert malicious intent."""
        if unexpected is None:
            unexpected = self.rng.random() < 0.10
        if unexpected:
            peer_id = self.rng.choice(("EXT-UNK", "EXT-DXB"))
            return self.connect("ATH-WS1", peer_id, "HTTPS")
        entry = self.rng.choice(self.expected_connections)
        return self.connect(entry.source_id, entry.peer_id, entry.service)
