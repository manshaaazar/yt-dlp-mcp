"""Background download jobs, so long downloads never hit a tool-call timeout."""
from __future__ import annotations

import asyncio
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

from yt_dlp.utils import DownloadCancelled


class JobCancelled(DownloadCancelled):
    """Raised inside a job when the user cancels it. yt-dlp lets this propagate."""

    msg = "Cancelled by user"


@dataclass
class Job:
    id: str
    kind: str
    url: str
    status: str = "queued"  # queued | running | done | failed | cancelled
    progress: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    cancel_requested: bool = False
    future: Future | None = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def raise_if_cancelled(self) -> None:
        if self.cancel_requested:
            raise JobCancelled()

    def update_progress(self, **fields: Any) -> None:
        with self._lock:
            self.progress.update(fields)

    @property
    def finished(self) -> bool:
        return self.status in ("done", "failed", "cancelled")

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            progress = dict(self.progress)
        end = self.finished_at or time.time()
        data: dict[str, Any] = {
            "job_id": self.id,
            "kind": self.kind,
            "url": self.url,
            "status": self.status,
            "elapsed_seconds": round(end - self.created_at, 1),
            "progress": progress,
        }
        if self.result is not None:
            data.update(self.result)
        if self.error:
            data["error"] = self.error
        return data


class JobManager:
    def __init__(self, max_workers: int = 2, keep: int = 50):
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ytdlp-job")
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._keep = keep

    def submit(self, kind: str, url: str, fn: Callable[[Job], dict[str, Any]]) -> Job:
        job = Job(id=uuid.uuid4().hex[:8], kind=kind, url=url)
        with self._lock:
            self._jobs[job.id] = job
            self._prune()
        job.future = self._pool.submit(self._run, job, fn)
        return job

    def _run(self, job: Job, fn: Callable[[Job], dict[str, Any]]) -> None:
        if job.cancel_requested:
            job.status = "cancelled"
            job.finished_at = time.time()
            return
        job.status = "running"
        try:
            job.result = fn(job)
            job.status = "done"
        except DownloadCancelled:
            job.status = "cancelled"
        except Exception as exc:  # recorded for the user, never raised into the pool
            job.error = _clean_error(exc)
            job.status = "failed"
        finally:
            job.finished_at = time.time()

    def _prune(self) -> None:
        finished = [j for j in self._jobs.values() if j.finished]
        for job in sorted(finished, key=lambda j: j.created_at)[: max(0, len(self._jobs) - self._keep)]:
            del self._jobs[job.id]

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        with self._lock:
            jobs = list(self._jobs.values())
        return list(reversed(jobs))

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if job is None or job.finished:
            return False
        job.cancel_requested = True
        if job.future is not None and job.future.cancel():
            job.status = "cancelled"
            job.finished_at = time.time()
        return True

    async def wait(self, job_id: str, timeout: float) -> Job:
        job = self.get(job_id)
        if job is None:
            raise KeyError(job_id)
        if job.future is None or job.future.done():
            return job
        try:
            await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(job.future)), timeout)
        except asyncio.TimeoutError:
            pass
        except asyncio.CancelledError:
            if not job.future.cancelled():
                raise
        return job

    def shutdown(self) -> None:
        for job in self.list():
            job.cancel_requested = True
        self._pool.shutdown(wait=False, cancel_futures=True)


def _clean_error(exc: Exception) -> str:
    text = str(exc) or type(exc).__name__
    return text.removeprefix("ERROR: ").strip()
