#!/usr/bin/env python3
"""Offline fixed-clock response demonstration; no sleeps, packets or terminal."""

import importlib.util
from pathlib import Path


def main():
    spec = importlib.util.spec_from_file_location(
        "monitor_demo", Path(__file__).with_name("global-threat-monitor.py"))
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)
    app = monitor.CyberMonitor(initial_theme="ice", seed=12)
    app.simulation.automatic = app.incidents.automatic = False
    app.start_critical_incident()
    app.update(49)
    incident, transfer = app.critical_incident, app.critical_incident.sessions[-1]
    app.process_shell_command("sessions")  # Includes legitimate backup on other assets.
    app.process_shell_command("response")
    print("\n".join(app.shell_history))
    print("\nBefore response: " + transfer.summary())
    app.process_shell_command("block session " + transfer.identifier)
    action = incident.actions[-1]
    for elapsed in (0, 1, 1, 1):
        app.update(elapsed)
        print(f"\nt={app.simulation.now:.0f}s: {incident.response_status}")
        print("  " + transfer.summary())
        print(f"  live routes={len(app.attacks)}; payload previous bucket={app.metrics['NET']:.4f} Mb/s")
    assert (action.requested_at, action.applied_at, action.verified_at) == (49, 50, 51)
    assert transfer.orig_bytes == 12000000 and transfer.rate == 0
    assert app.blocked == 1 and incident.contained
    assert any(s.service == "BACKUP" and not s.complete for s in app.simulation.sessions)
    print("\nResponse timeline:")
    for observation in incident.timeline:
        if observation.action_id:
            print("  " + observation.summary())
    app.update(28)
    print("\nRetained: " + incident.summary())
    app.update(1)
    integral = round(sum(app.traffic_history) * 1000000 / 8)
    assert integral == app.simulation.total_bytes
    print(f"Bucket integral={integral:,}B = total payload bytes; original evidence retained")


if __name__ == "__main__":
    main()
