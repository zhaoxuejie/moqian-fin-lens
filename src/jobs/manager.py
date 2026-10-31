from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class Job:
    job_id: str
    filing_id: str
    session_id: str
    state: str = "queued"
    progress: float = 0.0
    stage: str = "queued"
    attempts: int = 0
    error: dict | None = None
    created_at: str = field(default_factory=_now)
    started_at: str | None = None
    finished_at: str | None = None
    queue_position: int = 0


class JobManager:
    """进程内任务管理器：最多 5 个并发解析，其余排队（ADR-004）。"""

    def __init__(self, max_workers: int = 5) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="parse")
        self._lock = threading.Lock()
        self.jobs: dict[str, Job] = {}
        self._waiting: list[str] = []
        self._active = 0

    def create(self, job: Job) -> int:
        with self._lock:
            self.jobs[job.job_id] = job
            self._waiting.append(job.job_id)
            position = len(self._waiting)
            job.queue_position = position
        return position

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def update(self, job_id: str, *, state: str | None = None, progress: float | None = None, stage: str | None = None) -> None:
        with self._lock:
            job = self.jobs.get(job_id)
            if job is None:
                return
            if state:
                job.state = state
            if progress is not None:
                job.progress = progress
            if stage:
                job.stage = stage

    def submit(
        self,
        job_id: str,
        task: Callable[[Callable[[str, float], None]], object],
        on_success: Callable[[object], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        def runner() -> None:
            with self._lock:
                if job_id in self._waiting:
                    self._waiting.remove(job_id)
                self._active += 1
                job = self.jobs.get(job_id)
                if job is not None:
                    job.started_at = _now()
                    job.state = "parsing"
                    job.stage = "parsing"
                    job.queue_position = 0
                self._refresh_positions_locked()

            def progress(stage: str, ratio: float) -> None:
                self.update(job_id, state="parsing" if stage == "parsing" else job_state(stage), progress=ratio, stage=stage)

            try:
                result = task(progress)
            except Exception as exc:  # 任务失败不抛出到线程池
                with self._lock:
                    self._active -= 1
                    job = self.jobs.get(job_id)
                    if job is not None:
                        job.state = "failed"
                        job.stage = "failed"
                        job.error = {
                            "code": getattr(exc, "code", 42201),
                            "msg": str(exc)[:300],
                            "detail": getattr(exc, "detail", None),
                            "stage": job.stage,
                        }
                        job.finished_at = _now()
                    self._refresh_positions_locked()
                on_error(exc)
                return
            with self._lock:
                self._active -= 1
                job = self.jobs.get(job_id)
                if job is not None:
                    job.state = "done"
                    job.stage = "done"
                    job.progress = 1.0
                    job.finished_at = _now()
                self._refresh_positions_locked()
            on_success(result)

        self._executor.submit(runner)

    def _refresh_positions_locked(self) -> None:
        for index, waiting_id in enumerate(self._waiting, start=1):
            job = self.jobs.get(waiting_id)
            if job is not None:
                job.queue_position = index

    @property
    def active(self) -> int:
        return self._active


def job_state(stage: str) -> str:
    return {
        "parsing": "parsing",
        "aligning": "aligning",
        "computing": "computing",
    }.get(stage, "parsing")


class RateLimiter:
    def __init__(self, limit: int = 10, window_seconds: int = 3600) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, int]:
        now = time.time()
        with self._lock:
            hits = [item for item in self._hits.get(key, []) if now - item < self.window]
            if len(hits) >= self.limit:
                retry_after = int(self.window - (now - hits[0])) + 1
                self._hits[key] = hits
                return False, retry_after
            hits.append(now)
            self._hits[key] = hits
            return True, 0
