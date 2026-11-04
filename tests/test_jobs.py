import asyncio
import threading

import pytest

from ytdlp_mcp.jobs import JobCancelled, JobManager


@pytest.fixture
def manager():
    mgr = JobManager(max_workers=2)
    yield mgr
    mgr.shutdown()


def test_finished_job_returns_result(manager):
    job = manager.submit("video", "https://x", lambda job: {"files": ["a.mp4"]})
    job = asyncio.run(manager.wait(job.id, timeout=5))
    assert job.status == "done"
    assert job.result == {"files": ["a.mp4"]}


def test_wait_timeout_leaves_job_running(manager):
    release = threading.Event()

    def slow(job):
        release.wait(5)
        return {"files": []}

    job = manager.submit("video", "https://x", slow)
    waited = asyncio.run(manager.wait(job.id, timeout=0.05))
    assert waited.status == "running"
    release.set()
    assert asyncio.run(manager.wait(job.id, timeout=5)).status == "done"


def test_failure_is_recorded_not_raised(manager):
    def boom(job):
        raise RuntimeError("video unavailable")

    job = asyncio.run(manager.wait(manager.submit("audio", "https://x", boom).id, timeout=5))
    assert job.status == "failed"
    assert "video unavailable" in job.error


def test_cancel_stops_job_at_next_check(manager):
    started = threading.Event()

    def loop(job):
        started.set()
        while True:
            job.raise_if_cancelled()
            threading.Event().wait(0.01)

    job = manager.submit("video", "https://x", loop)
    started.wait(5)
    assert manager.cancel(job.id) is True
    assert asyncio.run(manager.wait(job.id, timeout=5)).status == "cancelled"


def test_cancel_unknown_or_finished_job_returns_false(manager):
    assert manager.cancel("nope") is False
    job = asyncio.run(manager.wait(manager.submit("video", "u", lambda j: {}).id, timeout=5))
    assert manager.cancel(job.id) is False


def test_raise_if_cancelled_raises_job_cancelled(manager):
    job = manager.submit("video", "u", lambda j: {})
    job.cancel_requested = True
    with pytest.raises(JobCancelled):
        job.raise_if_cancelled()


def test_to_dict_exposes_progress_and_status(manager):
    def report(job):
        job.update_progress(percent=50.0, speed="1.0MiB/s")
        return {}

    job = asyncio.run(manager.wait(manager.submit("video", "u", report).id, timeout=5))
    data = job.to_dict()
    assert data["status"] == "done"
    assert data["progress"]["percent"] == 50.0
    assert data["kind"] == "video"


def test_list_returns_newest_first(manager):
    a = manager.submit("video", "a", lambda j: {})
    b = manager.submit("audio", "b", lambda j: {})
    asyncio.run(manager.wait(b.id, timeout=5))
    asyncio.run(manager.wait(a.id, timeout=5))
    assert [j.id for j in manager.list()][:2] == [b.id, a.id]
