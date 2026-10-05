#!/usr/bin/env python3
"""Same fixed training case, scoped/broad response and real service collateral."""

import importlib.util
from pathlib import Path


def main():
    spec = importlib.util.spec_from_file_location(
        "monitor_drill_demo", Path(__file__).with_name("global-threat-monitor.py"))
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)
    results = []
    for key, label in (("b", "Scoped peer block"), ("l", "Broad local isolation")):
        owner = monitor.CyberMonitor(initial_theme="ice", seed=99)
        owner.simulation.automatic = owner.incidents.automatic = False
        owner.start_critical_incident()
        owner.update(3)
        original_time, original_bytes = owner.simulation.now, owner.simulation.total_bytes
        drill = owner.start_drill()
        owner.handle_key("i")
        owner.handle_key("enter")
        assert any("10,000,000" in line for line in
                   drill.world.investigation.detail_lines(drill.world, 72))
        owner.handle_key("escape")
        owner.handle_key("escape")
        owner.handle_key(key)
        print("\n" + label + "\n" + "\n".join(drill.preview_lines()))
        assert not drill.incident.actions
        owner.handle_key("enter")
        owner.update(2)
        assert drill.incident.contained
        assert drill.incident.sessions[-1].orig_bytes == 12000000
        owner.update(10)
        owner.handle_key("h")
        print("\n".join(drill.debrief[:15]))
        results.append((drill.legitimate.orig_bytes + drill.legitimate.resp_bytes,
                        drill.legitimate.state, drill.incident.sessions[-1].orig_bytes))
        owner.handle_key("enter")
        assert owner.active_mode == "dashboard" and owner.drill is None
        assert (owner.simulation.now, owner.simulation.total_bytes) == (original_time, original_bytes)
        assert not owner.simulation.policies
    assert results == [(723600, "completed", 12000000), (169200, "isolated", 12000000)]
    print(f"\nSame incident stopped at 12,000,000 upload bytes. Legitimate payload: "
          f"scoped={results[0][0]:,}B, broad={results[1][0]:,}B; "
          "only broad isolation interrupts service. Original dashboard restored in both runs.")

    owner.start_drill("benign")
    owner.handle_key("w")
    owner.handle_key("enter")
    assert owner.drill.incident.assessment == "authorized transfer"
    owner.handle_key("j")
    owner.handle_key("enter")
    owner.handle_key("h")
    assert "False-positive dismissed" in owner.drill.debrief[0]
    print("\n" + owner.drill.debrief[0])
    owner.handle_key("enter")


if __name__ == "__main__":
    main()
