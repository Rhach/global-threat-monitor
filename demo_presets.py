#!/usr/bin/env python3
"""Compare two presets at the same modeled UTC start/seed, without real waits."""

import importlib.util
from pathlib import Path

from workload_schedules import utc_text


def main():
    spec = importlib.util.spec_from_file_location(
        "monitor_demo", Path(__file__).with_name("global-threat-monitor.py"))
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)

    def application(preset):
        return monitor.CyberMonitor(initial_theme="ice", seed=12, initial_preset=preset,
                                   start_utc="2026-01-01T00:00:00Z")

    for preset in ("operations", "showcase"):
        app = application(preset)
        app.update(90)
        print(f"\n{preset.upper()} / seed12 / UTC {utc_text(app.clock_base + app.simulation.now)}")
        print("  " + app.schedules.compact_context())
        print("  " + app.incidents.pacing.summary(app.simulation.now, app.incidents.next_start))
        print(f"  Incidents={app.incident_count}; payload={app.simulation.total_bytes:,}B; "
              f"events={app.total_events}; current={app.critical_incident.identifier if app.critical_incident else 'none'}")
        for incident in app.incidents.history:
            print(f"  {incident.identifier} {incident.variant} [{incident.started_at:.2f},{incident.finished_at:.2f}] "
                  f"scale={incident.timing_scale:g}; sessions={len(incident.sessions)}; "
                  f"payload={sum(s.orig_bytes + s.resp_bytes for s in incident.sessions):,}B; "
                  f"assessment={incident.assessment}")
        if preset == "operations":
            assert app.incident_count == 0
        else:
            first = list(app.incidents.history)[:3]
            assert {i.family for i in first} == {"exfiltration", "credential-misuse", "lateral-movement"}
            assert sum(i.benign_alternative for i in first) == 1
            assert all(i.finished_at <= 90 and all(s.complete for s in i.sessions) for i in first)

    print("\nEquivalent scoped containment; automatic work off for this controlled comparison:")
    payloads = []
    for preset in ("operations", "showcase"):
        app = application(preset)
        app.simulation.automatic = app.incidents.automatic = False
        incident = app.start_critical_incident()
        scale = incident.timing_scale
        app.update(49 * scale)
        transfer = incident.sessions[-1]
        assert transfer.orig_bytes == 10000000
        action = app.incidents.request_response("block", "session", transfer.identifier)
        app.update(2 * scale)
        assert action.outcome == "contained" and transfer.orig_bytes == 12000000
        assert app.blocked == 1
        payloads.append((transfer.orig_bytes, transfer.resp_bytes))
        print(f"  {preset}: upload start={transfer.started_at:g}s, request={action.requested_at:g}s, "
              f"apply={action.applied_at:g}s, verify={action.verified_at:g}s; "
              f"orig/resp={transfer.orig_bytes:,}/{transfer.resp_bytes:,}B; "
              f"outcome={action.outcome}; live route={any(r.session is transfer for r in app.attacks)}")
        before = tuple(incident.timeline)
        app.process_shell_command("preset " + ("showcase" if preset == "operations" else "operations"))
        assert tuple(incident.timeline) == before and incident.preset == preset
        app.update(incident.LIFETIME - incident.age)
        assert incident.complete and app.blocked == 1
        print(f"    Switch to {app.preset}: retained {incident.preset} timing; "
              f"archive finish={incident.finished_at:g}s; one action applied")
    assert payloads[0] == payloads[1]


if __name__ == "__main__":
    main()
