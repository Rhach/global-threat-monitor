#!/usr/bin/env python3
"""Replay fixed UTC phase windows; real sessions and counters, no waits/network."""

import argparse
from collections import Counter
import importlib.util
from pathlib import Path

from workload_schedules import utc_text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", action="store_true",
                        help="Replay one uninterrupted 24h UTC day (bounded state, no waits or rendering).")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location(
        "monitor_demo", Path(__file__).with_name("global-threat-monitor.py"))
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)

    def application(utc):
        app = monitor.CyberMonitor(initial_theme="ice", seed=12, start_utc=utc)
        app.incidents.automatic = False
        return app

    def show(label, app):
        flows = list(app.simulation.history) + app.simulation.sessions
        print(f"\n{label}: UTC {utc_text(app.clock_base + app.simulation.now)}")
        for line in app.schedules.context_lines()[1:]:
            print("  " + line)
        print("  Actual sessions by site/service:", dict(Counter(
            (s.schedule_context.get("site_id"), s.service) for s in flows)))
        print(f"  Payload={app.simulation.total_bytes:,}B; last 1s={app.metrics['NET']:.4f}Mb/s; "
              f"received/system events={app.total_events}; last 1s EPS={app.last_eps}")

    if args.day:
        day = application("2026-01-01T00:00:00Z")
        for hour in (0, 1, 2, 6, 7, 8, 9, 10, 16, 17, 18, 19, 21, 24):
            day.update(hour * 3600 - day.simulation.now)
            show(f"Continuous day / UTC hour {hour}", day)
        backups = [job for job in day.schedules.jobs if job.kind == "backup"]
        maintenance = [job for job in day.schedules.jobs if job.kind == "maintenance"]
        assert len(backups) == 2 and all(job.total_bytes == 60300000 for job in backups)
        assert len(maintenance) == 3 and all(job.finished_at is not None for job in maintenance)
        assert len(day.schedules.jobs) <= 64 and len(day.simulation.history) <= 120
        print("\nCompleted jobs in the same uninterrupted world:")
        for job in day.schedules.jobs:
            print("  " + job.summary(day.clock_base))
        return

    print("Independent fixed UTC phase windows; use --day for one continuous 24h world.")
    quiet = application("2026-01-01T21:30:00Z")
    quiet.update(61)
    show("Overnight quiet", quiet)
    assert quiet.simulation.total_bytes == 0

    morning = application("2026-01-01T00:00:00Z")
    morning.update(61)
    show("Singapore morning; Europe quiet", morning)
    authenticated = [s for s in list(morning.simulation.history) + morning.simulation.sessions if s.auth_result]
    assert authenticated and all(s.credential_id == "aster.cloud" for s in authenticated)
    print(f"  {len(authenticated)} actual authenticated HTTPS sessions; "
          + morning.collectors.collectors["COL-SIN"].summary())

    europe = application("2026-01-01T07:00:00Z")
    europe.update(61)
    show("Frankfurt morning; Athens/Singapore work", europe)

    backup = application("2026-01-01T00:59:59Z")
    backup.update(2)
    show("Frankfurt daily backup starts", backup)
    job = next(j for j in backup.schedules.jobs if j.kind == "backup")
    session = next(s for s in backup.simulation.sessions if s.identifier == job.session_id)
    assert (session.orig_bytes, session.resp_bytes) == (2000000, 10000)
    assert backup.collectors.collectors["COL-FRA"].observed_payload_rate == 16.08
    print("  " + job.summary(backup.clock_base))
    print("  " + backup.collectors.collectors["COL-FRA"].summary())
    backup.update(29)
    assert job.total_bytes == 60300000 and session.complete
    print("  Completed: " + job.summary(backup.clock_base))
    print("  Retained context:", session.schedule_context)

    backup.update(10)
    health = backup.collectors.collectors["COL-ATH"]
    assert health.state == "offline" and health.planned_maintenance
    print("\nAthens planned maintenance: " + health.summary())
    backup.update(260)
    assert health.mode == "healthy" and health.planned_maintenance is None
    print("  Window ends; scheduled owner recovers its own outage: " + health.summary())

    unexpected = application("2026-01-01T00:59:59Z")
    unexpected.process_shell_command("outage COL-ATH")
    unexpected.update(301)
    health = unexpected.collectors.collectors["COL-ATH"]
    assert health.mode == "outage" and health.control_owner == "operator"
    print("\nIndependent operator outage survives planned window: " + health.summary())

    midnight = application("2026-01-01T15:59:59Z")
    midnight.update(2)
    show("Singapore crosses local midnight", midnight)
    tomorrow = application("2026-01-02T00:59:59Z")
    tomorrow.update(31)
    next_job = next(j for j in tomorrow.schedules.jobs if j.kind == "backup")
    assert next_job.identifier != job.identifier and next_job.total_bytes == 60300000
    print("  Next day has a distinct job: " + next_job.summary(tomorrow.clock_base))


if __name__ == "__main__":
    main()
