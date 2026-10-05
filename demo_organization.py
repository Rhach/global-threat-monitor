#!/usr/bin/env python3
"""Reproducible offline baseline demonstration; no terminal or sleeps required."""

import importlib.util
from pathlib import Path

from simulation_model import Organization


def main():
    spec = importlib.util.spec_from_file_location(
        "monitor_demo", Path(__file__).with_name("global-threat-monitor.py"))
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)
    organization = Organization(monitor.CITIES, seed=12)
    for peer in ("FRA-APP", "EXT-UNK"):
        connection = organization.connect("ATH-WS1", peer, "HTTPS")
        print(organization.describe(connection))
    remote = organization.connect("REM-UNK", "FRA-APP", "HTTPS")
    print(organization.describe(remote))
    print(f"Coverage: {len(organization.collectors)} stable city collectors; "
          "unknown peer coordinates remain unknown.")


if __name__ == "__main__":
    main()
