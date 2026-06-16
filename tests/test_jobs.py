from __future__ import annotations

import threading
import time

from mt5_research_agent.jobs import JobContext, JobQueue, job_to_payload


def test_job_runs_async_and_reports_progress() -> None:
    q = JobQueue()
    started = threading.Event()

    def handler(ctx: JobContext, params: dict) -> dict:
        started.set()
        ctx.set_progress(0.5, "halfway")
        return {"echo": params.get("value")}

    q.register("demo", handler)
    record = q.submit("demo", {"value": 42}, title="Demo job")
    # submit returns immediately (non-blocking) with a queued/running job.
    assert record.status in {"queued", "running"}
    assert started.wait(2.0)

    final = q.wait(record.id, timeout=3.0)
    assert final is not None
    assert final.status == "succeeded"
    assert final.result == {"echo": 42}
    assert final.progress == 1.0
    assert any("halfway" in line for line in final.logs)


def test_job_failure_is_recorded_not_swallowed() -> None:
    q = JobQueue()

    def boom(ctx: JobContext, params: dict) -> dict:
        raise RuntimeError("kaboom")

    q.register("boom", boom)
    record = q.submit("boom")
    final = q.wait(record.id, timeout=3.0)
    assert final is not None
    assert final.status == "failed"
    assert "kaboom" in final.error


def test_unknown_job_type_is_rejected() -> None:
    q = JobQueue()
    try:
        q.submit("nope")
    except ValueError as exc:
        assert "Unknown job type" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for unknown job type")


def test_queued_job_can_be_cancelled_before_running() -> None:
    q = JobQueue()
    gate = threading.Event()

    def slow(ctx: JobContext, params: dict) -> dict:
        gate.wait(2.0)
        return {}

    q.register("slow", slow)
    q.submit("slow")  # occupies the single worker so the next job stays queued
    second = q.submit("slow")
    # The second job is queued behind the first; cancel it before it runs.
    assert q.cancel(second.id) is True
    gate.set()
    final = q.wait(second.id, timeout=3.0)
    assert final is not None
    assert final.status == "cancelled"


def test_running_job_sees_cooperative_cancel() -> None:
    q = JobQueue()
    saw_cancel = threading.Event()

    def cooperative(ctx: JobContext, params: dict) -> dict:
        for _ in range(200):
            if ctx.is_cancelled():
                saw_cancel.set()
                return {"cancelled": True}
            time.sleep(0.01)
        return {"cancelled": False}

    q.register("coop", cooperative)
    record = q.submit("coop")
    time.sleep(0.1)
    assert q.cancel(record.id) is True
    assert saw_cancel.wait(2.0)
    final = q.wait(record.id, timeout=3.0)
    assert final is not None
    assert final.status == "cancelled"


def test_list_returns_most_recent_first_and_payload_serializes() -> None:
    q = JobQueue()
    q.register("noop", lambda ctx, params: {})
    a = q.submit("noop", title="A")
    b = q.submit("noop", title="B")
    q.wait(a.id, timeout=3.0)
    q.wait(b.id, timeout=3.0)
    listed = q.list()
    assert listed[0].id == b.id  # most recent first
    payload = job_to_payload(listed[0])
    assert payload["id"] == b.id
    assert "status" in payload and "progress" in payload
