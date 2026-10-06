"""Bounded incident pacing; calendars and all incident model APIs stay shared."""

import random

from scenario_families import FAMILIES


class OperatingPresets:
    NAMES = ("operations", "showcase")
    SHOWCASE_SCALE = 0.1
    SHOWCASE_BOUND = 90.0
    OPERATIONS_QUIET = (900.0, 1200.0)
    OPERATIONS_CHECK = 300.0
    WORKLOAD_RECENCY = 60.0

    def __init__(self, seed=None, name="operations"):
        self.rng = random.Random(seed)
        self.name = "operations"
        self.last_workload = None
        self.bag = []  # At most three variants, including one benign alternative.
        self.pending_variant = None
        self.set(name)

    def set(self, name):
        if name not in self.NAMES:
            raise ValueError("Use preset operations|showcase")
        if name != self.name and name == "showcase":
            self.bag.clear()
            self.pending_variant = None
        self.name = name

    @property
    def timing_scale(self):
        return self.SHOWCASE_SCALE if self.name == "showcase" else 1.0

    def delay(self):
        return self.rng.uniform(5, 10) if self.name == "showcase" else self.rng.uniform(*self.OPERATIONS_QUIET)

    def note_workload(self, session):
        context = session.schedule_context
        if session.state == "active" and context.get("phase") in ("morning", "work", "backup"):
            self.last_workload = (session.started_at, session.identifier,
                                  session.connection.source_id, context["phase"])

    def candidate(self, now):
        if self.name == "operations":
            return ("seeded" if self.last_workload and
                    0 <= now - self.last_workload[0] <= self.WORKLOAD_RECENCY and
                    self.rng.random() < 0.25 else None)
        if self.pending_variant is None:
            if not self.bag:
                families = list(FAMILIES)
                self.rng.shuffle(families)
                benign_index = self.rng.randrange(len(families))
                alternatives = {"exfiltration": "benign", "credential-misuse": "credential-benign",
                                "lateral-movement": "lateral-benign"}
                self.bag = [alternatives[family] if index == benign_index else
                            self.rng.choice(("exfiltration", "delayed", "partial")) if family == "exfiltration" else family
                            for index, family in enumerate(families)]
            self.pending_variant = self.bag[0]
        return self.pending_variant

    def issued(self):
        if self.name == "showcase" and self.pending_variant is not None:
            self.bag.pop(0)
        self.pending_variant = None

    def summary(self, now, next_start):
        opportunity = (f"{self.last_workload[1]} {self.last_workload[2]} {self.last_workload[3]} "
                       f"at t={self.last_workload[0]:.2f}s" if self.last_workload else "none")
        return (f"Preset {self.name}; future incident timing x{self.timing_scale:g}; "
                f"next scheduler check in {max(0, next_start - now):.2f}s; "
                f"last actual calendar workload={opportunity}")
