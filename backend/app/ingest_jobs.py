from dataclasses import dataclass, field
from threading import Lock
from time import time
from uuid import uuid4


@dataclass
class IngestJob:
    job_id: str
    status: str = "running"
    progress: float = 0.0
    error: str | None = None
    total_bytes: int = 0
    processed_bytes: int = 0
    created_at: float = field(default_factory=time)
    updated_at: float = field(default_factory=time)


_jobs: dict[str, IngestJob] = {}
_lock = Lock()


def create_job(total_bytes: int) -> IngestJob:
    job_id = uuid4().hex
    job = IngestJob(job_id=job_id, total_bytes=total_bytes)
    with _lock:
        _jobs[job_id] = job
    return job


def get_job(job_id: str) -> IngestJob | None:
    with _lock:
        return _jobs.get(job_id)


def update_progress(job_id: str, processed_bytes: int) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job or job.status != "running":
            return
        job.processed_bytes = processed_bytes
        if job.total_bytes:
            progress = min(processed_bytes / job.total_bytes, 0.99)
            job.progress = max(job.progress, progress)
        job.updated_at = time()


def mark_done(job_id: str) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job.status = "done"
        job.progress = 1.0
        job.updated_at = time()


def mark_error(job_id: str, error: str) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job.status = "error"
        job.error = error
        job.updated_at = time()


def cancel_job(job_id: str) -> bool:
    with _lock:
        job = _jobs.get(job_id)
        if not job or job.status != "running":
            return False
        job.status = "canceled"
        job.updated_at = time()
        return True
