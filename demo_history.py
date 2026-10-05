#!/usr/bin/env python3
"""Resolve, lose live routes, find an archived ID, and trace delayed evidence."""

from demo_investigation import application


def main():
    app = application()
    original = app.start_critical_incident()
    app.update(49)
    transfer = original.sessions[-1]
    action = app.incidents.request_response("block", "session", transfer.identifier)
    app.update(25)
    assert original.complete and original.disposition == "contained" and not app.attacks
    print(f"Resolved {original.identifier}: {original.disposition}; live routes={len(app.attacks)}; "
          f"transfer={transfer.identifier} out={transfer.orig_bytes:,}B; action={action.identifier} {action.status}")
    expression = f"site=ATH location=Dubai severity=critical service=HTTPS incident={original.identifier}"
    app.process_shell_command("filter " + expression)
    app.handle_key("v")
    assert [i.identifier for i in app.investigation.rows(app)] == [original.identifier]
    print("\nV retained archive; combined filters:", app.investigation.filters.label())
    app.handle_key("enter")
    lines = app.investigation.detail_lines(app, 75)
    assert "RETAINED FINAL SUMMARY" in "\n".join(lines)
    print("\nRetained evidence, linked completed sessions and response lifecycle:")
    print("\n".join(lines))
    app.handle_key("e")
    app.handle_key("m")
    app.handle_key("enter")
    assert app.investigation.current.kind == "flow"
    print("\nHistorical session inspection works after its live map route disappeared.")
    app.handle_key("escape")
    app.handle_key("escape")
    app.handle_key("escape")
    app.handle_key("escape")
    assert app.active_mode == "dashboard"
    app.handle_key("o")
    app.draw()
    print("\nO received events at 80x24, ordered by occurrence with separate receipt and lag:")
    print("\n".join("".join(row) for row in app.canvas.grid))
    selected = app.investigation.current.selected_id
    newer = app.start_critical_incident()
    app.update(2)
    app.investigation.rows(app)
    assert app.investigation.current.selected_id == selected
    assert app.investigation.filters.values["incident"] == original.identifier
    print(f"\nNew {newer.identifier} neither steals selection nor clears filters; still selected {selected}.")

    gap = application()
    gap.process_shell_command("outage COL-ATH")
    historical = gap.start_critical_incident()
    gap.update(74)
    gap.process_shell_command(f"filter incident={historical.identifier} severity=critical")
    gap.handle_key("o")
    assert not gap.investigation.rows(gap)
    gap.draw()
    print("\nNo received matches during outage is distinct from coverage state:")
    print("\n".join("".join(row) for row in gap.canvas.grid))
    gap.process_shell_command("recover COL-ATH")
    gap.update(8)
    records = gap.investigation.rows(gap)
    assert records and all(r.received_at > r.occurred_at for r in records)
    assert gap.investigation.current.selected_id == ""
    gap.handle_key("m")
    gap.handle_key("enter")
    print("\nExplicit M selects a recovered record. Frozen original facts and delayed receipt:")
    print("\n".join(gap.investigation.detail_lines(gap, 75)))
    gap.handle_key("i")
    assert gap.investigation.current.selected_id == historical.identifier
    print("\nI resolves the same archived incident; its timeline preserves original occurrence order.")


if __name__ == "__main__":
    main()
