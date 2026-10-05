"""Finite scenario connection plans for the shared offline incident lifecycle.

The plan is also the source for response coverage checks. SSH connections model
authenticated network access, never commands, process execution or payloads.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PlannedSession:
    offset: float
    source_id: str
    peer_id: str
    service: str
    credential_id: str
    profile: str = None

    @property
    def scope(self):
        return self.source_id, self.peer_id, self.credential_id


FAMILIES = ("exfiltration", "credential-misuse", "lateral-movement")
NEW_VARIANTS = ("credential-misuse", "credential-benign", "lateral-movement", "lateral-benign")


def family_for(variant):
    if variant.startswith("credential-"):
        return "credential-misuse"
    if variant.startswith("lateral-"):
        return "lateral-movement"
    return "exfiltration"


def connection_plan(variant):
    if variant in ("credential-misuse", "credential-benign"):
        return (PlannedSession(2, "REM-UNK", "FRA-APP", "HTTPS", "aster.admin"),
                PlannedSession(8, "ATH-WS1", "SIN-API", "HTTPS", "aster.admin"),
                PlannedSession(16, "REM-UNK", "SIN-API", "HTTPS", "aster.admin"))
    if variant in ("lateral-movement", "lateral-benign"):
        return (PlannedSession(2, "ATH-ADM" if variant == "lateral-benign" else "ATH-WS1",
                               "FRA-APP", "SSH", "aster.admin" if variant == "lateral-benign" else "aster.ws1"),
                PlannedSession(10, "FRA-APP", "SIN-API", "SSH", "aster.admin"),
                PlannedSession(18, "SIN-API", "FRA-BKP", "SSH", "aster.admin"))
    if variant == "benign":
        return (PlannedSession(2, "FRA-BKP", "SIN-STORE", "BACKUP", "aster.backup"),)
    plan = tuple(PlannedSession(offset, "ATH-WS1", "EXT-DXB", "HTTPS", "aster.ws1",
                                "outbound_bulk" if offset == 44 else None)
                 for offset in (2, 16, 30, 44))
    if variant == "partial":
        plan += (PlannedSession(46, "ATH-ADM", "EXT-DXB", "HTTPS", "aster.admin", "outbound_bulk"),)
    return plan


def family_stages(variant):
    if variant in ("credential-misuse", "credential-benign"):
        return ((0, "IDENTITY ALERT"), (2, "UNEXPECTED IDENTITY"), (8, "IDENTITY REUSE"),
                (16, "REPEATED ACCESS"), (20, "AUTHORIZATION MATCH" if variant.endswith("benign")
                 else "CREDENTIAL CORRELATION"), (30, "ASSESSMENT COMPLETE"))
    if variant in ("lateral-movement", "lateral-benign"):
        return ((0, "SSH ACCESS ALERT"), (2, "FIRST SSH HOP"), (10, "SECOND SSH HOP"),
                (18, "THIRD SSH HOP"), (22, "AUTHORIZATION MATCH" if variant.endswith("benign")
                 else "HOP CORRELATION"), (198, "ASSESSMENT COMPLETE"))
    return None


def reserved_slots(variant):
    return 3 if family_for(variant) == "lateral-movement" else 2 if (
        family_for(variant) == "credential-misuse" or variant == "partial") else 1
