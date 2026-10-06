"""Fixed-offset local workload calendars on the shared simulation clock.

Jobs create ordinary sessions, and maintenance owns only its own collector
control. No throughput or observations are invented independently of sessions.
"""

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import math
import random


SEEDED_START_UTC = 1767225600.0  # 2026-01-01T00:00:00Z
DAY = 86400.0


def parse_start_utc(value):
    """Accept a finite epoch or an explicit UTC ISO timestamp (Python 3.9)."""
    try:
        if isinstance(value, bool):
            raise ValueError
        if isinstance(value, str):
            try:
                epoch = float(value)
            except ValueError:
                stamp = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
                if stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
                    raise ValueError
                epoch = stamp.timestamp()
        else:
            epoch = float(value)
        if not math.isfinite(epoch) or epoch < 0:
            raise ValueError
        datetime.fromtimestamp(epoch, timezone.utc)
        return epoch
    except (ValueError, TypeError, OverflowError, OSError):
        raise ValueError("Start UTC must be finite epoch seconds from 1970 onward or ISO UTC, e.g. 2026-01-01T00:00:00Z") from None


def utc_text(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class ScheduleJob:
    identifier: str
    kind: str
    site_id: str
    local_day: str
    due_at: float
    ends_at: float
    owner: str
    source_id: str = ""
    peer_id: str = ""
    service: str = ""
    collector_id: str = ""
    status: str = "pending"
    started_at: float = None
    finished_at: float = None
    session_id: str = ""
    total_bytes: int = 0
    retry_at: float = math.inf

    def summary(self, epoch):
        return (f"{self.identifier} {self.kind} {self.status} owner={self.owner}; "
                f"site={self.site_id} local-day={self.local_day} due={utc_text(epoch + self.due_at)} "
                f"started={utc_text(epoch + self.started_at) if self.started_at is not None else 'none'} "
                f"finished={utc_text(epoch + self.finished_at) if self.finished_at is not None else 'none'}; "
                f"{self.source_id}>{self.peer_id} {self.service} collector={self.collector_id or 'n/a'} "
                f"session={self.session_id or 'none'} payload={self.total_bytes}B")


class WorkloadSchedules:
    HISTORY_LIMIT = 64
    BACKUP_START = 2 * 3600
    BACKUP_WINDOW = 300
    MAINTENANCE_START = 3 * 3600
    MAINTENANCE_WINDOW = 300
    MORNING_START = 8 * 3600
    WORK_START = 9 * 3600
    QUIET_START = 18 * 3600
    BACKUPS = {"SITE-FRA": ("FRA-BKP", "SIN-STORE"),
               "SITE-SIN": ("SIN-STORE", "FRA-BKP")}

    def __init__(self, simulation, collectors, epoch, on_created, emit, seed=None):
        self.simulation, self.collectors = simulation, collectors
        self.epoch = parse_start_utc(epoch)
        self.on_created, self.emit = on_created, emit
        self.rng = random.Random(seed)
        self.enabled = True
        self.sites = {key: site for key, site in simulation.organization.sites.items()
                      if site.role != "external"}
        self.jobs = deque(maxlen=self.HISTORY_LIMIT)
        # One last issued local day per finite site/job pair; no ever-growing ID set.
        self.last_job_day = {}
        self.pending_backups = {}
        self.running_backups = {}
        self.maintenance = {}
        self.phases = {}
        self.next_spawns = {key: 0.0 for key in self.sites}
        simulation.background_managed = True

    @property
    def active(self):
        return self.enabled and self.simulation.automatic

    def local(self, site, now=None):
        now = self.simulation.now if now is None else now
        shifted = self.epoch + now + site.utc_offset_minutes * 60
        day = math.floor(shifted / DAY)
        return day, shifted - day * DAY

    def phase(self, site, now=None):
        _, seconds = self.local(site, now)
        if site.city_code and self.MAINTENANCE_START <= seconds < self.MAINTENANCE_START + self.MAINTENANCE_WINDOW:
            return "maintenance"
        if site.identifier in self.BACKUPS and self.BACKUP_START <= seconds < self.BACKUP_START + self.BACKUP_WINDOW:
            return "backup"
        return ("morning" if self.MORNING_START <= seconds < self.WORK_START else
                "work" if self.WORK_START <= seconds < self.QUIET_START else "quiet")

    def local_text(self, site):
        shifted = self.epoch + self.simulation.now + site.utc_offset_minutes * 60
        return datetime.fromtimestamp(shifted, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    def compact_context(self):
        state = "SCHEDULE" if self.active else "SCHEDULE OFF"
        return state + " " + " ".join(f"{site.code}:{self.phase(site)}" for site in self.sites.values())

    def context_lines(self):
        return [f"UTC {utc_text(self.epoch + self.simulation.now)}; fixed site offsets (no DST); "
                f"scheduled work {'on' if self.active else 'off'}"] + [
            f"{site.code} {self.local_text(site)} UTC{site.utc_offset_minutes / 60:+g} "
            f"{self.phase(site)} / owner={site.owner}" for site in self.sites.values()]

    def calendar_boundary(self):
        now = self.simulation.now
        edges = (0, self.BACKUP_START, self.BACKUP_START + self.BACKUP_WINDOW,
                 self.MAINTENANCE_START, self.MAINTENANCE_START + self.MAINTENANCE_WINDOW,
                 self.MORNING_START, self.WORK_START, self.QUIET_START, DAY)
        return min((day * DAY - site.utc_offset_minutes * 60 - self.epoch + edge
                    for site in self.sites.values() for day, _ in (self.local(site),)
                    for edge in edges if day * DAY - site.utc_offset_minutes * 60 - self.epoch + edge > now + 1e-9),
                   default=math.inf)

    def next_boundary(self):
        # Already started work/maintenance completes even if future work is disabled.
        ends = min((job.ends_at for job in self.maintenance.values()), default=math.inf)
        if not self.active:
            return ends
        return min(ends, self.calendar_boundary(), min((max(self.simulation.now, due) for due in self.next_spawns.values()), default=math.inf),
                   min((job.retry_at for job in self.pending_backups.values()), default=math.inf))

    def job(self, site, kind, start, window):
        day, _ = self.local(site)
        key = (site.identifier, kind)
        if self.last_job_day.get(key) == day:
            return None
        self.last_job_day[key] = day
        local_day = datetime.fromtimestamp(day * DAY, timezone.utc).strftime("%Y-%m-%d")
        due = day * DAY - site.utc_offset_minutes * 60 - self.epoch + start
        job = ScheduleJob(f"JOB-{kind.upper()}-{site.code}-{local_day}", kind, site.identifier,
                          local_day, due, due + window, site.owner)
        self.jobs.append(job)
        return job

    def finish_jobs(self):
        now = self.simulation.now
        for identifier, (job, session) in list(self.running_backups.items()):
            job.total_bytes = session.orig_bytes + session.resp_bytes
            if session.complete:
                job.status, job.finished_at = session.state, now
                job.total_bytes = session.orig_bytes + session.resp_bytes
                self.emit(job.summary(self.epoch))
                del self.running_backups[identifier]
        for identifier, job in list(self.maintenance.items()):
            if now + 1e-9 >= job.ends_at:
                restored = self.collectors.end_maintenance(job.collector_id, identifier, now)
                job.status = "recovery started" if restored else "operator control retained"
                job.finished_at = now
                self.emit(job.summary(self.epoch))
                del self.maintenance[identifier]
        for identifier, job in list(self.pending_backups.items()):
            if now + 1e-9 >= job.ends_at:
                job.status, job.finished_at = "missed: capacity unavailable", now
                self.emit(job.summary(self.epoch))
                del self.pending_backups[identifier]

    def process_boundary(self):
        now = self.simulation.now
        self.finish_jobs()
        if not self.active:
            return
        for site in self.sites.values():
            phase = self.phase(site)
            previous = self.phases.get(site.identifier)
            if phase != previous:
                self.phases[site.identifier] = phase
                self.emit(f"Schedule {site.code}: {phase}; local {self.local_text(site)} "
                          f"UTC{site.utc_offset_minutes / 60:+g}; fixed offset / {site.owner}")
                self.next_spawns[site.identifier] = now
            if phase == "backup":
                job = self.job(site, "backup", self.BACKUP_START, self.BACKUP_WINDOW)
                if job:
                    job.source_id, job.peer_id = self.BACKUPS[site.identifier]
                    job.service, job.retry_at = "BACKUP", now
                    job.collector_id = self.simulation.organization.assets[job.source_id].collector_id
                    self.pending_backups[job.identifier] = job
                    self.emit(job.summary(self.epoch))
            elif phase == "maintenance":
                job = self.job(site, "maintenance", self.MAINTENANCE_START, self.MAINTENANCE_WINDOW)
                if job:
                    job.collector_id = "COL-" + site.city_code
                    job.started_at = now
                    owned = self.collectors.begin_maintenance(job.collector_id, job.identifier, now,
                                                             job.ends_at, utc_text(self.epoch + job.ends_at))
                    job.status = "planned collector outage" if owned else "operator control preserved"
                    self.maintenance[job.identifier] = job
                    self.emit(job.summary(self.epoch))
        for identifier, job in list(self.pending_backups.items()):
            if now + 1e-9 < job.retry_at:
                continue
            if self.room():
                context = {"job_id": identifier, "site_id": job.site_id, "local_day": job.local_day,
                           "phase": "backup", "approved_by": job.owner, "source_id": job.source_id,
                           "peer_id": job.peer_id, "service": "BACKUP", "purpose": "approved daily replication",
                           "scheduled_utc": utc_text(self.epoch + job.due_at)}
                session = self.create(job.source_id, job.peer_id, "BACKUP", context)
                if session is None:
                    job.retry_at = now + 1
                    continue
                job.started_at, job.session_id, job.status = now, session.identifier, session.state
                self.running_backups[identifier] = (job, session)
                del self.pending_backups[identifier]
                self.emit(job.summary(self.epoch))
            else:
                job.status, job.retry_at = "deferred: session capacity", now + 1
        for site in self.sites.values():
            if now + 1e-9 < self.next_spawns[site.identifier]:
                continue
            phase = self.phase(site)
            if phase not in ("morning", "work"):
                self.next_spawns[site.identifier] = math.inf
                continue
            morning = phase == "morning"
            if len(self.simulation.sessions) < 5 and self.room():
                connection = self.simulation.organization.choose_connection(
                    source_sites=(site.identifier,),
                    services=("DNS", "HTTPS") if morning else ("DNS", "HTTPS", "SSH"))
                if connection:
                    context = {"site_id": site.identifier, "local_day": self.local_text(site).split()[0],
                               "phase": phase, "approved_by": site.owner,
                               "purpose": connection.purpose}
                    self.create(connection.source_id, connection.peer_id, connection.service, context, connection)
            self.next_spawns[site.identifier] = round(now + self.rng.uniform(1, 2) if morning else
                                                     now + self.rng.uniform(8, 15), 12)

    def room(self):
        return len(self.simulation.sessions) < self.simulation.MAX_ACTIVE - self.simulation.reserved_slots

    def create(self, source, peer, service, context, connection=None):
        organization = self.simulation.organization
        connection = connection or organization.connect(source, peer, service)
        credential = next((key for key, owner in organization.credentials.items() if owner == source), None)
        session = self.simulation.create(connection, credential_id=credential if connection.expected else None)
        if session is None:
            return None
        session.schedule_context = dict(context)
        session.auth_result = ("rejected" if session.state == "denied" else "accepted") if (
            service == "HTTPS" and context["phase"] == "morning" and session.credential_id) else None
        self.on_created(session)
        return session
