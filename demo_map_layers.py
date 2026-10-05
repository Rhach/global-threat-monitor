#!/usr/bin/env python3
"""Compare four map layers at one fixed offline simulation moment."""
import importlib.util
from pathlib import Path

from map_layers import LAYERS, LEGENDS, layer_nodes


def main():
    spec = importlib.util.spec_from_file_location(
        "monitor_demo", Path(__file__).with_name("global-threat-monitor.py"))
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)
    app = monitor.CyberMonitor(initial_theme="ice", seed=12)
    app.simulation.automatic = app.incidents.automatic = False
    incident = app.start_critical_incident()
    app.update(43)
    app.trigger_attack(app.organization.connect("FRA-BKP", "SIN-STORE", "BACKUP"))
    app.process_shell_command("outage COL-PER")
    app.update(6)
    app.paused = True
    app.view = "WORLD"
    app.map_views["WORLD"].reset()
    app.canvas = monitor.Canvas(119, 40)
    moment = app.simulation.now
    for layer in LAYERS:
        app.process_shell_command("layer " + layer)
        nodes = layer_nodes(app)
        app.canvas.clear()
        app.draw_map(0, 0, 100, 20)
        print(f"\n{layer.upper()} t={moment:g}s (same paused state): {LEGENDS[layer]}")
        for code in ("ATH", "FRA", "SIN", "PER"):
            node = nodes[code]
            print(f"  {code}: {node.symbol}, value={node.value:g}, collector={app.collectors.collectors['COL-' + code].state}")
        for row in app.canvas.grid[:20]:
            print("".join(row[:100]))
        assert app.simulation.now == moment
    app.map_layer = "traffic"
    assert layer_nodes(app)["FRA"].symbol == "3"
    app.map_layer = "health"
    assert layer_nodes(app)["PER"].symbol == "!"
    transfer = incident.sessions[-1]
    app.incidents.request_response("block", "session", transfer.identifier)
    app.paused = False
    app.update(2)
    app.paused = True
    assert incident.contained and transfer.rate == 0
    for layer in ("incidents", "density"):
        app.map_layer = layer
        node = layer_nodes(app)["ATH"]
        assert node.symbol == "✓"
        print(f"\nContained at t={app.simulation.now:g}s: {layer} ATH={node.symbol}, endpoint bytes={node.value:g}")
    print("Transfer stopped; density retains its actual prior payload until the 60s window expires.")


if __name__ == "__main__":
    main()
