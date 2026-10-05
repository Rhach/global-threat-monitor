"""Persistent fictional organization for the offline simulation (Python 3.9+).

Collectors describe observation coverage, not asset ownership or peer geography.
No networking, wall clock, terminal, or rendering behavior belongs in this model.
"""

from dataclasses import dataclass
import random
from typing import Dict, Optional, Tuple


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
