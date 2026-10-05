#!/usr/bin/env python3
"""Fixed-clock coverage gaps, archived catchup and explicit overflow; offline."""

import importlib.util
from pathlib import Path


def main():
    spec = importlib.util.spec_from_file_location(
        "monitor_demo", Path(__file__).with_name("global-threat-monitor.py"))
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)

    def application():
        app = monitor.CyberMonitor(initial_theme="ice", seed=12)
        app.simulation.automatic = app.incidents.automatic = False
        return app

    app = application()
    app.process_shell_command("outage COL-ATH")
    original = app.start_critical_incident()
    app.trigger_attack(app.organization.connect("FRA-BKP", "SIN-STORE", "BACKUP"))
    for timestamp in (0, 6, 10, 49, 74):
        app.update(timestamp - app.simulation.now)
        health = app.collectors.collectors["COL-ATH"]
        print(f"\nt={app.simulation.now:g}s / healthy={app.sensors_online}/128 / " + health.summary())
        print(f"  visible stage={original.visible_stage}; confidence={original.confidence}; "
              f"timeline={len(original.timeline)}; actual incident originator bytes="
              f"{sum(s.orig_bytes for s in original.sessions):,}")
    assert original.complete and not original.timeline and original.confidence == "unobserved"
    current = app.start_critical_incident()
    app.process_shell_command("recover COL-ATH")
    app.update(0.5)
    assert len(original.timeline) == 1 and not current.timeline
    print("\nFirst receipt updates the original archived incident: " + original.timeline[0].summary())
    app.update(8.5)
    assert len(original.timeline) == 11 and original.confidence == "strong"
    assert all(e.incident_id == original.identifier and e.received_at > e.timestamp for e in original.timeline)
    assert app.sensors_online == 128
    print("\nRecovered original chronology (occurrence / receipt):")
    for observation in original.timeline:
        print(f"  {observation.identifier}: {observation.timestamp:.2f}s / "
              f"{observation.received_at:.2f}s / {observation.stage}")
    print(f"  {current.identifier} keeps its own {len(current.timeline)} observations")
    print(f"  Ingestion p95 over60s: {app.collectors.metrics()['p95_ms']:.1f}ms; "
          "these are event delays, not packet transit measurements")

    overflow = application()
    overflow.process_shell_command("outage COL-ATH")
    for _ in range(3):
        overflow.start_critical_incident()
        overflow.update(74)
    health = overflow.collectors.collectors["COL-ATH"]
    assert len(health.queue) == 32 and health.dropped == 13
    print("\nThree real unchecked scenarios during outage: " + health.summary())
    overflow.process_shell_command("recover COL-ATH")
    overflow.update(16)
    assert not health.queue and health.processed == 32 and health.dropped == 13
    print("Recovery delivered32 records in16s; dropped13 remain explicitly lost.")


if __name__ == "__main__":
    main()
