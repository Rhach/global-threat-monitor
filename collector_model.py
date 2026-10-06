"""Bounded simulated collector delivery, heartbeat and ingestion measurements."""

from collections import deque
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class IngestEvent:
    identifier: str
    collector_id: str
    occurred_at: float
    kind: str
    payload: object
    received_at: float = None


class CollectorHealth:
    HEARTBEAT = 2.0
    STALE_AFTER = 6.0
    OFFLINE_AFTER = 10.0
    QUEUE_LIMIT = 32
    SAMPLE_LIMIT = 256
    WINDOW = 60.0
    DRAIN_INTERVAL = 0.5

    def __init__(self, identifier):
        self.identifier = identifier
        self.mode = "healthy"
        self.control_owner = "baseline"
        self.planned_maintenance = None
        self.now = self.last_heartbeat = 0.0
        self.delay = 0.0
        self.queue = deque()
        self.next_drain = math.inf
        self.dropped = self.processed = self.submitted = 0
        self.samples = deque(maxlen=self.SAMPLE_LIMIT)
        self.counts = deque(maxlen=61)  # Per-second submitted/dropped counts.
        self.seen = deque(maxlen=256)
        self.seen_ids = set()
        self.last_payload_bytes = 0
        self.payload_gap = False
        self.observed_payload_rate = 0.0
        self.cpu = 18.0

    @property
    def state(self):
        if self.mode == "outage":
            age = self.now - self.last_heartbeat
            return "offline" if age >= self.OFFLINE_AFTER else "stale" if age >= self.STALE_AFTER else "delayed"
        if self.mode == "recovering" and self.queue:
            return "recovering"
        if self.mode == "delayed":
            return "delayed"
        return "healthy"

    @property
    def lag(self):
        return max(0.0, self.now - self.queue[0].occurred_at) if self.queue else 0.0

    def count(self, dropped=False):
        bucket = math.floor(self.now)
        if not self.counts or self.counts[-1][0] != bucket:
            self.counts.append([bucket, 0, 0])
        self.counts[-1][2 if dropped else 1] += 1

    def remember(self, identifier):
        if identifier in self.seen_ids:
            return False
        if len(self.seen) == self.seen.maxlen:
            self.seen_ids.remove(self.seen.popleft())
        self.seen.append(identifier)
        self.seen_ids.add(identifier)
        return True

    def summary(self):
        payload = "missing" if self.observed_payload_rate is None else f"{self.observed_payload_rate:.4f}Mb/s"
        return (f"{self.identifier} {self.state}; heartbeat={self.last_heartbeat:.2f} "
                f"age={self.now - self.last_heartbeat:.2f}s lag={self.lag:.2f}s "
                f"queue={len(self.queue)}/{self.QUEUE_LIMIT} dropped={self.dropped} "
                f"received={self.processed}; observed payload={payload}; CPU estimate={self.cpu:.1f}%"
                f"; mode={self.mode} owner={self.control_owner}; "
                f"planned maintenance={self.planned_maintenance or 'none'}")


class CollectorSimulation:
    """Healthy delivery is immediate; recovery/delay delivers at most two/s.

    Heartbeats and drain boundaries are exact simulation times. Overflow drops
    new events (preserving oldest queued evidence) and counts explicit loss.
    Payload rates are collector-observed one-second buckets, not wire latency.
    """

    def __init__(self, catalog, deliver, on_loss=None):
        self.collectors = {identifier: CollectorHealth(identifier) for identifier in catalog}
        self.deliver = deliver
        self.on_loss = on_loss
        self.now = 0.0
        self.next_heartbeat = 2.0
        self.sequence = 0
        self._p95_dirty = True
        self._p95_value = None

    def next_boundary(self):
        return min(self.next_heartbeat,
                   min((c.next_drain for c in self.collectors.values()), default=math.inf))

    def set_mode(self, identifier, mode, now, delay=3.0, owner="operator"):
        if identifier not in self.collectors:
            raise ValueError("Unknown collector ID; use collectors")
        if mode not in ("outage", "recovering", "delayed"):
            raise ValueError("Use outage, recover or delay")
        if not math.isfinite(now) or now < self.now:
            raise ValueError("Collector control time cannot move backwards")
        if not math.isfinite(delay) or not 0 < delay <= 60:
            raise ValueError("Delay must be from 0 to 60 simulation seconds, excluding zero")
        self.advance_to(now)
        collector = self.collectors[identifier]
        collector.mode, collector.delay = mode, delay if mode == "delayed" else 0.0
        collector.control_owner = owner
        if mode == "recovering" and not collector.queue:
            collector.mode = "healthy"
        if mode != "outage":
            collector.last_heartbeat = now
        collector.next_drain = now + collector.DRAIN_INTERVAL if collector.queue and mode != "outage" else math.inf
        return collector

    def begin_maintenance(self, identifier, token, now, ends_at, ends_utc):
        self.advance_to(now)
        collector = self.collectors[identifier]
        collector.planned_maintenance = (token, ends_at, ends_utc)
        if collector.mode != "healthy":
            return False
        self.set_mode(identifier, "outage", now, owner=token)
        return True

    def end_maintenance(self, identifier, token, now):
        self.advance_to(now)
        collector = self.collectors[identifier]
        if collector.planned_maintenance and collector.planned_maintenance[0] == token:
            collector.planned_maintenance = None
        if collector.control_owner != token:
            return False
        self.set_mode(identifier, "recovering", now, owner="baseline")
        return True

    def submit(self, identifier, occurred_at, kind, payload, event_id=None):
        collector = self.collectors[identifier]
        self.sequence += 1
        event = IngestEvent(event_id or f"TELEM-{self.sequence:08d}", identifier, occurred_at, kind, payload)
        collector.now = self.now
        if any(item.identifier == event.identifier for item in collector.queue) or not collector.remember(event.identifier):
            return False
        collector.submitted += 1
        collector.count()
        if collector.mode == "healthy" or (collector.mode == "recovering" and not collector.queue):
            self.receive(collector, event)
        elif len(collector.queue) >= collector.QUEUE_LIMIT:
            collector.dropped += 1
            collector.count(dropped=True)
            if self.on_loss:
                self.on_loss(event)
        else:
            collector.queue.append(event)
            if collector.mode != "outage" and not math.isfinite(collector.next_drain):
                collector.next_drain = self.now + collector.DRAIN_INTERVAL
        return True

    def receive(self, collector, event):
        collector.processed += 1
        collector.samples.append((self.now, max(0.0, self.now - event.occurred_at)))
        self._p95_dirty = True
        self.deliver(IngestEvent(event.identifier, event.collector_id, event.occurred_at,
                                 event.kind, event.payload, self.now))

    def advance_to(self, now):
        if now < self.now or not math.isfinite(now):
            return
        while self.now < now:
            self._process_to(min(now, self.next_boundary()))
        self._process_to(now)

    def _process_to(self, now):
        elapsed = now - self.now
        self.now = now
        for collector in self.collectors.values():
            if elapsed > 0 and collector.mode == "outage":
                collector.payload_gap = True
            collector.now = now
            while collector.samples and collector.samples[0][0] <= now - collector.WINDOW:
                collector.samples.popleft()
                self._p95_dirty = True
            while collector.counts and collector.counts[0][0] <= now - collector.WINDOW:
                collector.counts.popleft()
        if now + 1e-9 >= self.next_heartbeat:
            for collector in self.collectors.values():
                if collector.mode != "outage":
                    collector.last_heartbeat = now
            self.next_heartbeat += 2.0
        for collector in self.collectors.values():
            if now + 1e-9 < collector.next_drain:
                continue
            if collector.queue and collector.mode != "outage":
                event = collector.queue[0]
                if now + 1e-9 >= event.occurred_at + collector.delay:
                    self.receive(collector, collector.queue.popleft())
                collector.next_drain = now + collector.DRAIN_INTERVAL if collector.queue else math.inf
            else:
                collector.next_drain = math.inf
            if collector.mode == "recovering" and not collector.queue:
                collector.mode = "healthy"

    def sample_payload(self, totals):
        for identifier, collector in self.collectors.items():
            total = totals.get(identifier, 0)
            delta = total - collector.last_payload_bytes
            collector.last_payload_bytes = total
            # A partially blind bucket cannot be reconstructed by recovery.
            collector.observed_payload_rate = None if collector.payload_gap or collector.mode == "outage" else delta * 8 / 1000000
            collector.payload_gap = False
            processing = sum(1 for timestamp, _ in collector.samples if timestamp > self.now - 1)
            collector.cpu = min(95.0, 18 + (collector.observed_payload_rate or 0) * 0.09 +
                                processing * 0.6 + len(collector.queue) * 0.15)

    def metrics(self):
        collectors = list(self.collectors.values())
        if self._p95_dirty:
            lags = sorted(lag * 1000 for c in collectors for _, lag in c.samples)
            self._p95_value = lags[max(0, math.ceil(len(lags) * 0.95) - 1)] if lags else None
            self._p95_dirty = False
        submitted = sum(bucket[1] for c in collectors for bucket in c.counts)
        dropped = sum(bucket[2] for c in collectors for bucket in c.counts)
        backlog = sum(len(c.queue) for c in collectors)
        return {"healthy": sum(c.state == "healthy" for c in collectors),
                "backlog": backlog, "dropped": sum(c.dropped for c in collectors),
                "p95_ms": self._p95_value,
                "loss_percent": dropped * 100 / submitted if submitted else 0.0,
                "cpu": max((c.cpu for c in collectors), default=18.0),
                "ram": 62 + backlog / (len(collectors) * CollectorHealth.QUEUE_LIMIT) * 20,
                "buffer_kib": backlog * 2}
