"""A bounded training world using the dashboard's real simulation and inspection.

The owner stays untouched while this child advances. Closing discards training
policies and shifts the owner's wall-clock camera references by the time away.
There is no score, and no outcome is inferred from keyboard speed.
"""

import textwrap
import time


class DecisionDrill:
    CASES = ("exfiltration", "benign", "partial")
    SEED = 13
    START_UTC = 1767225600.0  # 2026-01-01 UTC, independent of host wall clock.
    WINDOW = 35.0

    def __init__(self, owner, case, factory, sound_enabled):
        if case not in self.CASES:
            raise ValueError("Use drill [exfiltration|benign|partial]")
        self.case = case
        self.opened_at = time.monotonic()
        self.world = factory(initial_theme=owner.theme_key, initial_sound=sound_enabled,
                             initial_speed=1.0, seed=self.SEED,
                             initial_auto_follow=False, initial_pinned=True)
        world = self.world
        world.clock_base = self.START_UTC
        world.simulation.automatic = world.incidents.automatic = False
        self.incident = world.start_critical_incident(case)
        world.update(2 if case == "benign" else 49)
        self.started_at = world.simulation.now
        self.deadline = self.started_at + self.WINDOW
        self.legitimate = world.simulation.create(
            world.organization.connect("ATH-WS1", "FRA-APP", "HTTPS"))
        world.add_session_route(self.legitimate)
        world.paused = owner.paused
        world.speed_multiplier = owner.speed_multiplier
        self.selected_id = self.targets()[0].identifier
        self.preview = None
        self.message = "Inspect evidence before choosing a response. No speed score."
        self.waits = 0
        self.debrief = None
        self.offset = 0
        self.closed = False

    def targets(self):
        live = [s for s in self.incident.sessions if not s.complete]
        return live or list(self.incident.sessions)

    def target(self):
        return next((s for s in self.incident.sessions if s.identifier == self.selected_id),
                    self.incident.sessions[-1])

    def advance(self, dt):
        if self.debrief is not None or self.world.paused:
            return
        # Clamp at the simulation-time deadline, including a large caller step.
        step = min(dt, max(0.0, self.deadline - self.world.simulation.now) /
                   self.world.speed_multiplier)
        self.world.update(step)
        if self.world.simulation.now >= self.deadline - 1e-9:
            self.finish("Timed out")

    def preview_action(self, key):
        session = self.target()
        source, peer = session.connection.source_id, session.connection.peer_id
        options = {
            "b": ("block", "peer", source, peer),
            "k": ("block", "session", session.identifier, ""),
            "l": ("isolate", "endpoint", source, ""),
            "j": ("dismiss", "incident", self.incident.identifier, ""),
            "w": ("wait", "seconds", "5", ""),
        }
        self.preview = options[key]

    def preview_lines(self):
        kind, scope, target, peer = self.preview
        lines = [f"PREVIEW: {kind} {scope}={target}" + (f">{peer}" if peer else "")]
        if kind == "block":
            lines += ["Only this session; future connections allowed." if scope == "session" else
                      "All egress from this asset to this peer, including future connections.",
                      "Requested now; applies +1s; verifies +2s on the simulation clock."]
        elif kind == "isolate":
            lines += ["LOCAL endpoint: all incoming/outgoing traffic, including legitimate service.",
                      "Requested now; applies +1s; verifies +2s on the simulation clock."]
        elif kind == "dismiss":
            lines += ["Record operator dismissal; retain evidence; apply no traffic policy."]
        else:
            lines += ["Advance 5 simulation seconds for evidence; no policy. P must be LIVE."]
        if kind in ("block", "isolate"):
            def matches(s):
                c = s.connection
                return (s.identifier == target if scope == "session" else
                        target in (c.source_id, c.peer_id) if scope == "endpoint" else
                        c.source_id == target and c.peer_id == peer)
            affected = [s for s in self.world.simulation.sessions if matches(s)]
            lines.append("Matching live IDs now: " + (", ".join(s.identifier for s in affected) or "none"))
            lines += [f"  {s.identifier} {s.connection.source_id}>{s.connection.peer_id} {s.service} "
                      f"{'incident' if s.incident_id else 'legitimate service'}" for s in affected]
        return lines + ["Enter CONFIRM | Esc discard preview (no request sent)"]

    def confirm(self):
        kind, scope, target, peer = self.preview
        try:
            if kind == "wait":
                if self.world.paused:
                    self.message = "Paused: wait did not advance; P resumes exercise."
                else:
                    self.waits += 1
                    self.advance(5 / self.world.speed_multiplier)
                    self.message = "Waited 5 simulation seconds; inspect newly received evidence."
            elif kind == "dismiss":
                self.world.incidents.dismiss("trainee dismissal after investigation")
                self.message = "Dismissal recorded. Traffic continues; H reviews consequences."
            else:
                action = self.world.incidents.request_response(kind, scope, target, peer)
                self.message = f"{action.identifier} {action.status}; observe application/verification."
        except ValueError as error:
            self.message = str(error)
        self.preview = None

    def finish(self, reason="Finished"):
        if self.debrief is not None:
            return
        world, incident = self.world, self.incident
        authorized = incident.assessment.startswith("authorized ")
        stopped = [s for s in incident.sessions if s.response_action_id]
        disrupted = [s for s in [self.legitimate] + (incident.sessions if authorized else [])
                     if s.response_action_id]
        pending = [a for a in incident.actions if a.status in ("requested", "applied")]
        if pending:
            outcome = "Response pending; containment unverified"
        elif authorized and disrupted:
            outcome = "False-positive response; authorized service disrupted"
        elif authorized and incident.disposition == "dismissed":
            outcome = "False-positive dismissed"
        elif authorized:
            outcome = ("Authorized transfer recognized after waiting; no service disrupted" if self.waits else
                       "Authorized transfer; no policy needed")
        elif incident.contained:
            outcome = ("Contained with service disruption" if disrupted else
                       "Dismissed after verified containment" if incident.disposition == "dismissed" else
                       "Scoped containment verified")
        elif stopped:
            outcome = "Partial containment; related activity remains unresolved"
        elif incident.disposition == "dismissed":
            outcome = "Incorrect dismissal; suspicion unresolved"
        elif self.waits:
            outcome = "Waited for evidence; no containment applied"
        else:
            outcome = "Unresolved; no containment applied"
        lines = [f"{reason}: {outcome}",
                 f"Case={self.case} seed={self.SEED}; t={world.simulation.now:.2f}s; waits={self.waits}; no speed score.",
                 f"Assessment={incident.assessment}; confidence={incident.confidence}; disposition={incident.disposition}",
                 "Residual risk: " + incident.residual_risk,
                 f"Incident payload out/in={sum(s.orig_bytes for s in incident.sessions):,}/"
                 f"{sum(s.resp_bytes for s in incident.sessions):,}B; encrypted content unknown.",
                 "CHOSEN POLICIES (actual actuator results)"]
        lines += [line for action in incident.actions for line in action.detail_lines()] or ["No policy requested."]
        if incident.dismissal_reason:
            lines.append("Dismissal: " + incident.dismissal_reason + "; no network policy.")
        lines += ["SERVICE CONSEQUENCES",
                  f"Legitimate {self.legitimate.identifier} ATH-WS1>FRA-APP HTTPS: "
                  f"state={self.legitimate.state}; out/in={self.legitimate.orig_bytes:,}/{self.legitimate.resp_bytes:,}B; "
                  f"policy={self.legitimate.response_action_id or 'none'}.",
                  "Disrupted legitimate IDs: " + (", ".join(s.identifier for s in disrupted) or "none"),
                  "RELATED SESSION FACTS"]
        lines += [s.summary() + f"; policy={s.response_action_id or 'none'}" for s in incident.sessions]
        lines.append("RECEIVED EVIDENCE (original IDs/times; intent and TLS content remain uncertain)")
        lines += [f"t={o.timestamp:g} {o.identifier} {o.stage}: {o.message}" for o in incident.timeline]
        lines.append("Esc/Enter closes debrief and restores original dashboard; training policies discarded.")
        self.debrief = lines
        self.preview = None
        world.investigation.stack.clear()

    def close(self, owner):
        if self.closed:
            return
        self.closed = True
        away = max(0.0, time.monotonic() - self.opened_at)
        owner.last_auto_zoom += away
        owner.last_map_interaction += away
        owner.active_mode = "dashboard"
        owner.drill = None

    def handle_key(self, owner, key):
        if key == "quit" or (key == "q" and not self.world.investigation.editing):
            self.close(owner)
            return False
        if self.debrief is not None:
            if key in ("escape", "enter"):
                self.close(owner)
            elif key in ("u", "d"):
                self.offset = max(0, self.offset + (-1 if key == "u" else 1) *
                                  max(1, owner.canvas.height - 6))
            return True
        world = self.world
        if world.active_mode == "inspection":
            world.handle_key(key)
            return True
        if key == "escape":
            if self.preview:
                self.preview = None
            else:
                self.finish("Cancelled")
                self.close(owner)
        elif key == "enter" and self.preview:
            self.confirm()
        elif key in ("b", "k", "l", "j", "w"):
            self.preview_action(key)
        elif key in ("i", "e", "o", "v"):
            self.preview = None
            world.investigation.open_list(world, {"i": "incidents", "e": "flows", "o": "events", "v": "incidents"}[key],
                                          archive=key == "v")
            world.active_mode = "inspection"
        elif key == "t" and not self.preview:
            targets = self.targets()
            index = next((i for i, s in enumerate(targets) if s.identifier == self.selected_id), -1)
            self.selected_id = targets[(index + 1) % len(targets)].identifier
        elif key == "h":
            self.finish()
        elif key == "p":
            world.paused = not world.paused
        elif key in ("+", "=", "-"):
            world.speed_multiplier = max(0.25, min(4, world.speed_multiplier + (-0.25 if key == "-" else 0.25)))
        return True

    def draw(self, owner):
        world = self.world
        world.canvas = owner.canvas
        width, height = owner.canvas.width, owner.canvas.height
        if world.active_mode == "inspection" and self.debrief is None:
            world.investigation.draw(world)
            owner.text(1, 0, width - 2, f"EXERCISE INVESTIGATION / t={world.simulation.now:.2f}s / "
                       f"{'PAUSED' if world.paused else 'LIVE'} / {world.speed_multiplier:g}x", "accent")
            return
        owner.text(1, 0, width - 2, f"DECISION EXERCISE / {self.case} / "
                   f"{'PAUSED' if world.paused else 'LIVE'} / {world.speed_multiplier:g}x", "accent")
        if self.debrief is not None:
            lines = [part for line in self.debrief for part in textwrap.wrap(line, width - 4) or [""]]
            self.offset = min(self.offset, max(0, len(lines) - (height - 4)))
            for row, line in enumerate(lines[self.offset:self.offset + height - 4]):
                owner.text(2, row + 2, width - 4, line)
            owner.text(1, height - 1, width - 2, "DEBRIEF | U/D scroll | Enter/Esc restore dashboard | Q quit", "accent")
            return
        session = self.target()
        lines = [f"t={world.simulation.now:.2f}s; deadline={self.deadline:g}s; original dashboard frozen",
                 f"{self.incident.identifier}: {self.incident.visible_stage}; confidence={self.incident.confidence}",
                 "Assessment: " + self.incident.assessment,
                 f"TARGET {session.identifier}: {session.connection.source_id}>{session.connection.peer_id} {session.service}",
                 f"State={session.state}; out/in={session.orig_bytes:,}/{session.resp_bytes:,}B",
                 f"Legitimate {self.legitimate.identifier} ATH-WS1>FRA-APP HTTPS: {self.legitimate.state}, "
                 f"{self.legitimate.orig_bytes + self.legitimate.resp_bytes:,}B",
                 self.incident.response_status, self.message]
        if self.preview:
            lines += self.preview_lines()
        else:
            lines += ["I inspect incident | E flows | O received events | V history",
                      "T next target | B peer egress block | K session block",
                      "L local endpoint isolation | J dismiss | W wait 5 sim seconds",
                      "Actions preview first; Enter explicitly confirms the shown scope."]
        wrapped = [part for line in lines for part in textwrap.wrap(line, width - 4) or [""]]
        for row, line in enumerate(wrapped[:height - 4]):
            owner.text(2, row + 2, width - 4, line, "warn" if line.startswith("PREVIEW") else "text")
        owner.text(1, height - 1, width - 2,
                   "Enter CONFIRM scope | Esc discard preview | P pause | +/- speed" if self.preview else
                   "P pause | +/- speed | H finish/debrief | Esc cancel | Q quit", "accent")
