#!/usr/bin/env python3
"""Pin Athens across a distant incident, then follow with unchanged lifecycle."""
import importlib.util
from pathlib import Path
from unittest.mock import patch


def main():
    spec = importlib.util.spec_from_file_location(
        "monitor_demo", Path(__file__).with_name("global-threat-monitor.py"))
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)
    with patch.object(monitor.time, "monotonic", return_value=0):
        app = monitor.CyberMonitor(initial_theme="ice", seed=12)
        app.simulation.automatic = app.incidents.automatic = False
        app.view = "EUROPE"
        viewport = app.map_views[app.view]
        viewport.zoom = 6
        viewport.longitude, viewport.latitude = app.organization.cities["ATH"][:2]
        app.handle_key("z")
        pinned = viewport.bounds
        incident = app.start_critical_incident("benign")
        app.update(7)
    print("Athens pinned: " + app.camera_summary())
    print("Incident elsewhere: " + incident.summary())
    app.update_map(now=60)
    assert viewport.bounds == pinned and not incident.following
    print("After60s wall-clock camera update: Athens still pinned; simulation remains7s.")

    def facts():
        return (app.simulation.now, incident.age, incident.disposition,
                tuple(incident.timeline), tuple((s.identifier, s.orig_bytes, s.resp_bytes)
                                               for s in incident.sessions), len(incident.actions))

    before = facts()
    with patch.object(monitor.time, "monotonic", return_value=60):
        app.handle_key("z")
        assert app.camera_state == "MANUAL" and viewport.bounds == pinned
        app.handle_key("enter")
    for tick in range(1, 21):
        app.update_map(now=60 + tick / 10)
    assert before == facts() and viewport.bounds != pinned
    print("Unpinned, explicitly followed: " + app.camera_summary())
    print(f"Center now {viewport.longitude:.2f},{viewport.latitude:.2f}; "
          "same incident7s, evidence, bytes, disposition and actions.")
    print("Moving markers represent aggregate session activity, not packet transit or incident progress.")
    app.paused = True
    stopped = viewport.bounds
    app.update_map(now=80)
    assert viewport.bounds == stopped
    print("Pause freezes follow. Unpinned manual idle easing uses wall time; pin freezes all automatic motion.")


if __name__ == "__main__":
    main()
