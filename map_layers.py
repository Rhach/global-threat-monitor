"""Read-only map projections of shared sessions, incidents and collectors."""

from dataclasses import dataclass

LAYERS = ("traffic", "incidents", "health", "density")
TITLES = {"traffic": "TRAFFIC / 1s", "incidents": "INCIDENTS",
          "health": "SENSOR HEALTH", "density": "DENSITY / 60s"}
LEGENDS = {"traffic": "1<1 2<10 3>=10Mb/s/1s modeled",
           "incidents": "• normal ◆ suspect ✓ held ! stale x off",
           "health": "• healthy ~ lag ! stale x off r catchup",
           "density": "1<1 2<10 3>=10MB/60s modeled"}


def intensity(value, low, high):
    return "3" if value >= high else "2" if value >= low else "1" if value > 0 else "•"


@dataclass(frozen=True)
class MapNode:
    symbol: str
    color: str
    value: float
    active: bool
    priority: tuple


def layer_nodes(app):
    """No progression, aggregation or geography fabrication occurs during draw."""
    layer = app.map_layer
    simulation = app.simulation
    volumes = simulation.endpoint_activity.recent_bytes if layer == "density" else simulation.endpoint_activity.last_bytes
    suspects, contained = set(), set()
    incidents = list(app.incidents.history)
    if app.critical_incident is not None:
        incidents.append(app.critical_incident)
    # Assessment comes from correlated lifecycle facts; dismissed activity is ordinary.
    for incident in incidents:
        if incident.disposition == "dismissed":
            continue
        identifiers = {incident.source_id, incident.peer_id}
        identifiers.update(identifier for session in incident.sessions
                           for identifier in (session.connection.source_id, session.connection.peer_id))
        codes = {app.organization.assets[identifier].city_code for identifier in identifiers}
        codes.discard(None)
        (contained if incident.contained else suspects).update(codes)
    routes = [route for route in app.attacks if not route.complete]
    if layer == "traffic":
        suspects.update(city[3] for route in routes if route.flagged and not (route.session is not None and route.session.incident_id)
                        for city in (route.src_city, route.dst_city) if city is not None)
    route_codes = {city[3] for route in routes for city in (route.src_city, route.dst_city)
                   if city is not None}
    result = {}
    for code in app.organization.cities:
        health = app.collectors.collectors["COL-" + code]
        value = volumes.get(code, 0)
        if layer == "traffic":
            value = value * 8 / 1000000
        stale = health.state in ("stale", "offline")
        suspect = code in suspects
        held = code in contained and not suspect
        active = (bool(value) if layer in ("traffic", "density") else False) or (layer == "traffic" and code in route_codes)
        if layer == "health":
            symbol = {"healthy": "•", "delayed": "~", "stale": "!", "offline": "x", "recovering": "r"}[health.state]
            active = health.state != "healthy"
        elif layer == "density":
            symbol = "x" if health.state == "offline" else "!" if stale else "◆" if suspect else "✓" if held else intensity(value, 1000000, 10000000)
        else:
            symbol = "x" if health.state == "offline" else "!" if stale else "◆" if suspect else "✓" if held else (
                intensity(value, 1, 10) if layer == "traffic" else "•")
            active = active or suspect or held
        color = "warn" if (health.state != "healthy" if layer == "health" else stale or suspect) else "success" if held else "accent"
        if layer == "health":
            rank = {"healthy": 0, "delayed": 1, "recovering": 2, "stale": 3, "offline": 4}[health.state]
            priority = (rank, health.lag, len(health.queue))
        else:
            active = active or suspect or held or stale
            priority = (stale, suspect, held, active, value)
        result[code] = MapNode(symbol, color, value, active, priority)
    return result


class EndpointActivity:
    """At most 60 complete one-second buckets, plus one pending bucket.

    Count payload once per located endpoint (twice if both ends share a city).
    Unknown endpoints are excluded, never assigned the observing collector's city.
    Completed and stopped sessions contribute their final byte increments.
    """
    WINDOW = 60

    def __init__(self, organization):
        from collections import deque
        self.organization = organization
        self.buckets = deque(maxlen=self.WINDOW)
        self.unknown_buckets = deque(maxlen=self.WINDOW)
        self.pending_unknown_bytes = 0
        self.last_unknown_bytes = self.recent_unknown_bytes = 0
        self.pending = {}
        self.last_bytes = {}
        self.recent_bytes = {}

    def add(self, connection, transferred):
        for identifier in (connection.source_id, connection.peer_id):
            code = self.organization.assets[identifier].city_code
            if code is None:
                self.pending_unknown_bytes += transferred
            elif transferred:
                self.pending[code] = self.pending.get(code, 0) + transferred

    def sample(self, now):
        self.last_bytes = self.pending
        self.pending = {}
        self.buckets.append((now, self.last_bytes))
        self.last_unknown_bytes = self.pending_unknown_bytes
        self.pending_unknown_bytes = 0
        self.unknown_buckets.append(self.last_unknown_bytes)
        self.recent_unknown_bytes = sum(self.unknown_buckets)
        recent = {}
        for _, bucket in self.buckets:
            for code, count in bucket.items():
                recent[code] = recent.get(code, 0) + count
        self.recent_bytes = recent
