#!/usr/bin/env python3
"""Four reproducible service profiles and byte reconciliation; no sleeps/network."""

import importlib.util
from pathlib import Path

from simulation_model import Organization, SessionSimulation


def main():
    spec = importlib.util.spec_from_file_location(
        "monitor_demo", Path(__file__).with_name("global-threat-monitor.py"))
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)
    simulation = SessionSimulation(Organization(monitor.CITIES, seed=12), seed=12)
    simulation.automatic = False
    sessions = [simulation.create(simulation.organization.connect(source, peer, service))
                for source, peer, service in (("ATH-WS1", "FRA-DNS", "DNS"),
                                              ("ATH-WS1", "FRA-APP", "HTTPS"),
                                              ("ATH-ADM", "FRA-APP", "SSH"),
                                              ("FRA-BKP", "SIN-STORE", "BACKUP"))]
    print("Offline payload simulation; no hidden background aggregate")
    for timestamp in (0.04, 0.2, 1, 3, 10, 12, 30, 31):
        simulation.advance(timestamp - simulation.now)
        print(f"\nt={simulation.now:.2f}s total={simulation.total_bytes:,} bytes "
              f"previous complete 1s bucket={simulation.throughput:.6f} Mb/s")
        for session in sessions:
            print("  " + session.summary())
    history_bytes = round(sum(simulation.traffic_history) * 1000000 / 8)
    print(f"\n31s bucket integral={history_bytes:,} bytes; modeled total="
          f"{simulation.total_bytes:,} bytes; match={history_bytes == simulation.total_bytes}")
    backup = sessions[-1]
    print(f"Backup completed: {backup.orig_bytes:,} originator + "
          f"{backup.resp_bytes:,} responder bytes; rate={backup.rate:.2f} Mb/s")
    print(f"SSH still active: {not sessions[2].complete}; completed summaries retained="
          f"{len(simulation.history)} (maximum 120)")


if __name__ == "__main__":
    main()
