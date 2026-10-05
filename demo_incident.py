#!/usr/bin/env python3
"""Replay correlated auth/peer/transfer evidence without terminal, sleeps or network."""

import importlib.util
from pathlib import Path


def main():
    spec = importlib.util.spec_from_file_location(
        "monitor_demo", Path(__file__).with_name("global-threat-monitor.py"))
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)
    app = monitor.CyberMonitor(initial_theme="ice", seed=12)
    app.simulation.automatic = app.incidents.automatic = False
    app.handle_key("f")  # Same entrypoint and scenario as the automatic scheduler.
    incident = app.critical_incident
    print("Offline suspected exfiltration; TLS payload unavailable; no response applied")
    for timestamp in (0, 2, 14, 16, 28, 30, 42, 44, 49, 74):
        app.update(timestamp - app.simulation.now)
        print(f"\nt={app.simulation.now:.0f}s " + incident.summary())
        for observation in incident.timeline:
            if observation.timestamp == timestamp:
                print("  " + observation.summary())
        if app.critical_incident and app.critical_incident.route.session:
            print("  " + app.critical_incident.route.session.summary())
    total = round(sum(app.traffic_history) * 1000000 / 8)
    print(f"\nBucket integral={total:,}B; session payload total={app.simulation.total_bytes:,}B")
    print(f"Retained {len(incident.timeline)} original observations, {len(incident.sessions)} sessions; "
          f"contained={app.blocked}; final disposition={incident.disposition}")
    assert total == app.simulation.total_bytes == 62470800
    assert incident.disposition == "unresolved" and app.blocked == 0


if __name__ == "__main__":
    main()
