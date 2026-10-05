#!/usr/bin/env python3
"""Seeded offline family evidence, partial scopes, verified scopes and lookalikes."""

import importlib.util
from pathlib import Path


def main():
    spec = importlib.util.spec_from_file_location(
        "monitor_demo", Path(__file__).with_name("global-threat-monitor.py"))
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)

    def app_for(variant):
        app = monitor.CyberMonitor(initial_theme="ice", seed=12, initial_scenario=variant)
        app.simulation.automatic = app.incidents.automatic = False
        return app

    def print_evidence(incident):
        print("\n" + incident.summary())
        for evidence in incident.timeline:
            if evidence.stage != "SESSION FINISHED":
                print(f"t={evidence.timestamp:g} {evidence.identifier}: {evidence.message}")
        for session in incident.sessions:
            print(f"  {session.incident_id} {session.connection.source_id}>{session.connection.peer_id} "
                  f"credential={session.credential_id} / {session.summary()}")

    # Unchecked paths provide all three families' complete, retained evidence.
    for family, moment in (("exfiltration", 49), ("credential-misuse", 20), ("lateral-movement", 22)):
        app = app_for(family)
        incident = app.critical_incident
        app.update(moment)
        print_evidence(incident)
        assert len(incident.sessions) >= 3 and incident.confidence == "strong"
        if family == "credential-misuse":
            assert app.organization.city_for("REM-UNK") is None
            assert all(s.service == "HTTPS" and s.profile == "baseline" for s in incident.sessions)
        elif family == "lateral-movement":
            assert all(s.service == "SSH" and s.lifetime == 180 for s in incident.sessions)
            app.update(52)
            assert app.critical_incident is incident and len(app.attacks) == 3
            print("At74s: all three SSH sessions still active; archive waits for last natural completion at198s.")
        app.update(incident.LIFETIME - app.simulation.now)
        assert incident.complete and not app.attacks and incident.disposition == "unresolved"
        print("Retained: " + incident.summary())

    # Exfiltration: only the last actual upload remains, so session scope suffices.
    app = app_for("exfiltration")
    app.update(49)
    incident = app.critical_incident
    action = app.incidents.request_response("block", "session", incident.sessions[-1].identifier)
    app.update(2)
    assert action.outcome == "contained"
    print("\nEXFILTRATION: " + action.result)

    # Credential misuse: one source/peer is partial; identity policy spans assets.
    app = app_for("credential-misuse")
    app.update(2)
    incident = app.critical_incident
    action = app.incidents.request_response("block", "peer", "REM-UNK", "FRA-APP")
    app.update(2)
    assert action.outcome == "partial"
    print("\nCREDENTIAL MISUSE / narrow peer: " + action.result)
    app.update(4)
    action = app.incidents.request_response("revoke", "credential", "aster.admin")
    app.update(2)
    assert action.outcome == "contained"
    print("CREDENTIAL MISUSE / identity: " + action.result)
    assert [s.state for s in incident.sessions] == ["blocked", "revoked"]
    app.update(20)
    assert incident.complete and incident.disposition == "contained"

    # Lateral access: isolation at the first source cannot cover downstream assets.
    app = app_for("lateral-movement")
    app.update(2)
    incident = app.critical_incident
    action = app.incidents.request_response("isolate", "endpoint", "ATH-WS1")
    app.update(2)
    assert action.outcome == "partial"
    print("\nLATERAL MOVEMENT / first asset: " + action.result)
    app.update(18)
    assert [s.state for s in incident.sessions] == ["isolated", "active", "active"]
    print("Residual: " + incident.residual_risk)
    action = app.incidents.request_response("revoke", "credential", "aster.admin")
    app.update(2)
    assert action.outcome == "contained"
    print("LATERAL MOVEMENT / downstream identity: " + action.result)
    app.update(198 - app.simulation.now)
    assert incident.complete and incident.disposition == "contained"

    # Every family has an authorization path that contradicts its first alert.
    for variant, moment in (("benign", 7), ("credential-benign", 20), ("lateral-benign", 22)):
        app = app_for(variant)
        incident = app.critical_incident
        original = incident.timeline[0]
        app.update(moment)
        print("\nLOOKALIKE " + variant + ": " + incident.timeline[-1].message)
        assert incident.confidence == "low" and incident.assessment.startswith("authorized ")
        app.incidents.dismiss("reviewed matching owner authorization")
        app.update(incident.LIFETIME - app.simulation.now)
        assert original in incident.timeline and incident.disposition == "dismissed" and app.blocked == 0
        print("Retained original severity=" + incident.severity + "; " + incident.residual_risk)

    print("\nAll three families, all benign alternatives and scoped outcomes verified offline (seed12).")


if __name__ == "__main__":
    main()
