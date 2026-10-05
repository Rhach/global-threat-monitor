#!/usr/bin/env python3
"""Fixed-clock keyboard inspection of transfer, response, gap and back navigation."""

import importlib.util
from pathlib import Path


def application():
    spec = importlib.util.spec_from_file_location(
        "monitor_demo", Path(__file__).with_name("global-threat-monitor.py"))
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)
    app = monitor.CyberMonitor(initial_theme="ice", seed=12)
    app.simulation.automatic = app.incidents.automatic = False
    app.canvas = monitor.Canvas(79, 24)
    return app


def main():
    app = application()
    incident = app.start_critical_incident()
    app.update(49)
    app.handle_key("r")
    app.handle_key("]")
    app.handle_key("right")
    before = app.view, app.map_views[app.view].bounds
    for key in ("e", "enter"):
        app.handle_key(key)
    transfer = app.investigation.current.selected
    assert transfer is incident.sessions[-1]
    print("E, Enter selects the incident's transfer by stable ID:")
    print("\n".join(app.investigation.detail_lines(app, 75)))
    app.update(1)
    assert transfer.orig_bytes == 12000000
    print(f"\nInspection stays LIVE: t={app.simulation.now:.2f}s, out={transfer.orig_bytes:,}B")
    # Existing response API applies the same scoped command as the console:
    # block session FLOW-00004. No additional investigation action shortcuts.
    action = app.incidents.request_response("block", "session", transfer.identifier)
    app.update(2)
    assert transfer.state == "blocked" and action.status == "verified"
    print("\nResponse lifecycle and retained stopped transfer:")
    for line in app.investigation.detail_lines(app, 75):
        print(line)
    app.handle_key("i")
    app.handle_key("d")
    app.draw()
    print("\nI opens the incident; D scrolls its chronological received timeline at 80x24:")
    print("\n".join("".join(row) for row in app.canvas.grid))
    for key in ("escape", "escape", "escape"):
        app.handle_key(key)
    assert app.active_mode == "dashboard"
    assert before == (app.view, app.map_views[app.view].bounds)
    print("\nEsc x3 restores the exact EUROPE map viewport:", before)

    gap = application()
    gap.process_shell_command("outage COL-ATH")
    original = gap.start_critical_incident()
    gap.update(49)
    gap.handle_key("i")
    gap.handle_key("enter")
    assert not original.timeline
    assert "No received observations" in "\n".join(gap.investigation.detail_lines(gap, 75))
    print("\nCoverage gap: modeled related transfers are visible; collector evidence is unavailable.")
    gap.process_shell_command("recover COL-ATH")
    gap.update(5)
    print("Recovered chronology preserves occurrence and actual delayed receipt:")
    for observation in original.timeline:
        print(f"  {observation.identifier} {observation.stage}: occurred={observation.timestamp:.2f} "
              f"received={observation.received_at:.2f}s")
    gap.handle_key("p")
    now = gap.simulation.now
    gap.update(10)
    assert gap.simulation.now == now
    print(f"P freezes inspection at t={now:.2f}s. All checks use simulation steps, without sleeps.")


if __name__ == "__main__":
    main()
