"""A staged, entirely simulated priority incident and its geographic trail."""

import math


class CriticalIncident:
    STAGES = ((0, "SIGNAL ACQUIRED"), (2, "TRACING FLOW"),
              (14, "QUARANTINING"), (17, "CONTAINED"))
    LIFETIME = 21.0

    def __init__(self, route, number):
        self.route = route
        self.identifier = f"CT-{number:03d}"
        self.age = 0.0
        self.following = True
        route.critical = True
        route.flagged = True
        route.kind = "HTTPS"
        route.rate = 96.0

    @property
    def stage_index(self):
        return max(i for i, (start, _) in enumerate(self.STAGES) if self.age >= start)

    @property
    def stage(self):
        return self.STAGES[self.stage_index][1]

    @property
    def contained(self):
        return self.age >= 17

    @property
    def complete(self):
        return self.age >= self.LIFETIME

    def position(self, progress=None):
        """The same geographic arc drives both the camera and rendered packet."""
        t = self.route.progress if progress is None else progress
        sx, sy = self.route.src_city[:2]
        dx, dy = self.route.dst_city[:2]
        bend = min(12.0, abs(dx - sx) * 0.12)
        return (sx + (dx - sx) * t,
                min(80.0, sy + (dy - sy) * t + 4 * bend * t * (1 - t)))

    def update(self, dt):
        previous = self.stage_index
        self.age += max(0.0, dt)
        self.route.age = self.age
        self.route.progress = min(1.0, max(0.0, (self.age - 2) / 12))
        self.route.complete = self.complete
        return [stage for _, stage in self.STAGES[previous + 1:self.stage_index + 1]]

    def follow(self, viewport, dt):
        if not self.following or dt <= 0:
            return
        lon, lat = self.position()
        # Follow just ahead of the packet while it moves; smoothly acquire the
        # source at the start and hold the destination during containment.
        if 0 < self.route.progress < 1:
            lon, lat = self.position(min(1.0, self.route.progress + 0.025))
        blend = 1 - math.exp(-4 * dt)
        viewport.zoom += (6.0 - viewport.zoom) * blend
        viewport.longitude += (lon - viewport.longitude) * blend
        viewport.latitude += (lat - viewport.latitude) * blend
        viewport._clamp_center()
