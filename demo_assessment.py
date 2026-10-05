#!/usr/bin/env python3
"""Compare evidence/outcomes without terminal, sleeps, network or dependencies."""

import importlib.util
from pathlib import Path


def main():
    spec = importlib.util.spec_from_file_location(
        "monitor_demo", Path(__file__).with_name("global-threat-monitor.py"))
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)
    for variant in ("benign", "exfiltration", "delayed", "partial"):
        app = monitor.CyberMonitor(initial_theme="ice", seed=12)
        app.simulation.automatic = app.incidents.automatic = False
        app.process_shell_command("scenario " + variant)
        incident = app.critical_incident
        original = incident.timeline[0]
        print(f"\n{variant.upper()} / seed=12 / original severity={original.severity}, confidence={original.confidence}")
        if variant == "benign":
            app.update(7)
            print("Delivered evidence: " + incident.timeline[-1].message)
            app.process_shell_command("dismiss approved JOB-FRA-SIN-001")
            before = incident.sessions[0].orig_bytes
            app.update(2)
            assert incident.sessions[0].orig_bytes > before and app.blocked == 0
        else:
            app.update(49)
            transfer = incident.sessions[-2 if variant == "partial" else -1]
            app.process_shell_command("block session " + transfer.identifier)
            action = incident.actions[-1]
            print(f"Requested t={action.requested_at:g}; apply delay={action.apply_delay:g}s; verify={action.verify_delay:g}s")
            app.update(action.apply_delay)
            print(f"Applied t={action.applied_at:g}; stopped bytes={transfer.orig_bytes:,}; live rate={transfer.rate:g}")
            assert not incident.contained
            app.update(action.verify_delay)
            print(f"Verified t={action.verified_at:g}; outcome={action.outcome}; {action.result}")
            if variant == "partial":
                alternate = incident.sessions[-1]
                assert alternate.orig_bytes > 0 and alternate.rate > 0 and not incident.contained
                print(f"Residual {alternate.identifier}@{alternate.connection.source_id}: {alternate.orig_bytes:,}B, {alternate.rate:.2f}Mb/s")
            else:
                assert incident.contained
        print(f"Assessment={incident.assessment}; confidence={incident.confidence}; reason={incident.confidence_reason}")
        print(f"Disposition={incident.disposition}; severity={incident.severity}; response={incident.response_phase}")
        app.update(incident.started_at + incident.LIFETIME - app.simulation.now)
        assert incident.complete and original in incident.timeline and incident.severity == "critical"
        assert incident.disposition == ("dismissed" if variant == "benign" else
                                        "partially contained" if variant == "partial" else "contained")
        print("Retained outcome: " + incident.disposition + "; " + incident.residual_risk)


if __name__ == "__main__":
    main()
