"""Async job queue for long-running MT5 work.

The desktop app must never freeze while a backtest runs. So MT5 work is submitted
as a **job**: the call returns immediately with a ``job_id``; a single background
worker thread runs jobs FIFO (MT5 is serial anyway) and exposes
status/progress/logs/result that the UI polls.

Safety: jobs only run the same guarded Strategy-Tester operations as the CLI.
Cancellation is cooperative (a handler checks ``ctx.is_cancelled()``); a running
MT5 process is never force-killed mid-write.
"""

from __future__ import annotations

import queue
import threading
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class JobRecord:
    id: str
    type: str
    title: str
    params: dict[str, Any]
    status: str = "queued"  # queued | running | succeeded | failed | cancelled
    progress: float = 0.0
    message: str = ""
    logs: list[str] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str = ""
    created_at: str = field(default_factory=_now)
    started_at: str = ""
    finished_at: str = ""
    cancel_requested: bool = False


class JobContext:
    """Handed to a job handler so it can report progress and check cancellation."""

    def __init__(self, queue_ref: "JobQueue", job_id: str) -> None:
        self._queue = queue_ref
        self._job_id = job_id

    def log(self, message: str) -> None:
        self._queue._append_log(self._job_id, message)

    def set_progress(self, progress: float, message: str = "") -> None:
        self._queue._set_progress(self._job_id, progress, message)

    def is_cancelled(self) -> bool:
        record = self._queue.get(self._job_id)
        return bool(record and record.cancel_requested)


JobHandler = Callable[[JobContext, dict[str, Any]], dict[str, Any]]


class JobQueue:
    def __init__(self) -> None:
        self._records: dict[str, JobRecord] = {}
        self._handlers: dict[str, JobHandler] = {}
        self._lock = threading.RLock()
        self._pending: "queue.Queue[str]" = queue.Queue()
        self._worker: threading.Thread | None = None
        self._order: list[str] = []

    # -- registration -------------------------------------------------------- #
    def register(self, job_type: str, handler: JobHandler) -> None:
        with self._lock:
            self._handlers[job_type] = handler

    # -- submission ---------------------------------------------------------- #
    def submit(self, job_type: str, params: dict[str, Any] | None = None, *, title: str = "") -> JobRecord:
        with self._lock:
            if job_type not in self._handlers:
                raise ValueError(f"Unknown job type: {job_type}")
            job_id = uuid.uuid4().hex[:12]
            record = JobRecord(
                id=job_id,
                type=job_type,
                title=title or job_type,
                params=dict(params or {}),
            )
            self._records[job_id] = record
            self._order.append(job_id)
        self._pending.put(job_id)
        self._ensure_worker()
        return record

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return
            self._worker = threading.Thread(target=self._run_worker, name="mt5-job-worker", daemon=True)
            self._worker.start()

    def _run_worker(self) -> None:
        while True:
            try:
                job_id = self._pending.get(timeout=1.0)
            except queue.Empty:
                with self._lock:
                    has_more = any(r.status == "queued" for r in self._records.values())
                if has_more:
                    continue
                return
            self._execute(job_id)
            self._pending.task_done()

    def _execute(self, job_id: str) -> None:
        with self._lock:
            record = self._records.get(job_id)
            if record is None:
                return
            if record.cancel_requested or record.status == "cancelled":
                record.status = "cancelled"
                record.finished_at = _now()
                return
            handler = self._handlers.get(record.type)
            record.status = "running"
            record.started_at = _now()
        if handler is None:
            self._finish(job_id, status="failed", error=f"No handler for job type {record.type}")
            return
        context = JobContext(self, job_id)
        try:
            result = handler(context, dict(record.params))
            with self._lock:
                current = self._records[job_id]
                if current.cancel_requested:
                    self._finish(job_id, status="cancelled")
                    return
            self._finish(job_id, status="succeeded", result=result, progress=1.0)
        except Exception as exc:  # surfaced to the UI, never swallowed
            self._finish(job_id, status="failed", error=f"{type(exc).__name__}: {exc}")

    def _finish(
        self,
        job_id: str,
        *,
        status: str,
        result: dict[str, Any] | None = None,
        error: str = "",
        progress: float | None = None,
    ) -> None:
        with self._lock:
            record = self._records.get(job_id)
            if record is None:
                return
            record.status = status
            record.finished_at = _now()
            if result is not None:
                record.result = result
            if error:
                record.error = error
                record.logs.append(f"error: {error}")
            if progress is not None:
                record.progress = progress

    # -- mutation from the context ------------------------------------------ #
    def _append_log(self, job_id: str, message: str) -> None:
        with self._lock:
            record = self._records.get(job_id)
            if record is not None:
                record.logs.append(message)
                record.message = message
                record.logs = record.logs[-200:]

    def _set_progress(self, job_id: str, progress: float, message: str) -> None:
        with self._lock:
            record = self._records.get(job_id)
            if record is not None:
                record.progress = max(0.0, min(1.0, progress))
                if message:
                    record.message = message
                    record.logs.append(message)

    # -- queries ------------------------------------------------------------- #
    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._records.get(job_id)

    def list(self, limit: int = 50) -> list[JobRecord]:
        with self._lock:
            ordered = [self._records[jid] for jid in reversed(self._order) if jid in self._records]
        return ordered[:limit]

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            record = self._records.get(job_id)
            if record is None:
                return False
            if record.status in {"succeeded", "failed", "cancelled"}:
                return False
            record.cancel_requested = True
            if record.status == "queued":
                record.status = "cancelled"
                record.finished_at = _now()
            return True

    def wait(self, job_id: str, timeout: float = 10.0) -> JobRecord | None:
        """Block until a job is terminal. For tests and synchronous callers."""

        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            record = self.get(job_id)
            if record is not None and record.status in {"succeeded", "failed", "cancelled"}:
                return record
            time.sleep(0.02)
        return self.get(job_id)


def job_to_payload(record: JobRecord) -> dict[str, Any]:
    return asdict(record)


# Process-wide queue used by the API. Handlers are registered lazily by
# ``register_default_handlers`` so importing this module stays cheap and
# side-effect free.
_QUEUE: JobQueue | None = None


def get_queue() -> JobQueue:
    global _QUEUE
    if _QUEUE is None:
        _QUEUE = JobQueue()
        register_default_handlers(_QUEUE)
    return _QUEUE


def register_default_handlers(job_queue: JobQueue) -> None:
    job_queue.register("smoke", _handle_smoke)
    job_queue.register("optimization", _handle_optimization)
    job_queue.register("research", _handle_research)
    job_queue.register("session_start", _handle_session_start)
    job_queue.register("session_stop", _handle_session_stop)


def _handle_research(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    from mt5_research_agent.research_workflow import (
        parse_research_request,
        research_report_path,
        run_research_command,
    )

    request_path = str(params["request_path"])
    ctx.set_progress(0.1, "validating research request")
    request = parse_research_request(request_path)
    if request.todos:
        ctx.set_progress(1.0, "request is ambiguous")
        return {"ok": False, "todos": request.todos, "message": "Resolve request TODOs before running."}
    ctx.set_progress(0.2, "running sweep + split validation (deep goal-seek)")
    exit_code = run_research_command(
        request_path, allow_gui_clicks=False, timeout_seconds=int(params.get("timeout_seconds", 1800))
    )
    report = research_report_path(request.slug)
    ctx.set_progress(1.0, "research finished")
    return {
        "ok": exit_code == 0,
        "exit_code": exit_code,
        "slug": request.slug,
        "report_path": str(report),
    }


def _handle_smoke(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    from mt5_research_agent.background_runner import (
        build_smoke_task_payload,
        run_task_cli,
        write_generated_task,
    )

    ctx.set_progress(0.05, "preparing smoke task")
    test_id = str(params.get("test_id", "UI-SMOKE-0001"))
    payload = build_smoke_task_payload(
        test_id=test_id,
        ea=str(params["ea"]),
        symbol=str(params.get("symbol", "US30")),
        timeframe=str(params.get("timeframe", "M15")),
        period_from=str(params.get("period_from", "2024.01.01")),
        period_to=str(params.get("period_to", "2024.02.01")),
        deposit=float(params.get("deposit", 10000)),
        model=str(params.get("model", "1 minute OHLC")),
    )
    task_path = write_generated_task(payload)
    ctx.set_progress(0.2, "launching MT5 Strategy Tester")
    result = run_task_cli(str(task_path), int(params.get("timeout_seconds", 900)))
    ctx.set_progress(1.0, f"finished: {result.status}")
    return {
        "test_id": result.test_id,
        "status": result.status,
        "raw_report_path": result.raw_report_path,
        "log_path": result.log_path,
    }


def _handle_optimization(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    from mt5_research_agent.optimizer import load_optimization_spec, run_optimization

    spec = load_optimization_spec(str(params["spec_path"]))
    ctx.set_progress(0.1, f"optimizing {spec.test_id} (grid up to many combos)")
    result = run_optimization(spec, timeout_seconds=int(params.get("timeout_seconds", 3600)), launch=True)
    ctx.set_progress(1.0, f"finished: {result.status}")
    return {
        "test_id": result.test_id,
        "status": result.status,
        "total_passes": result.total_passes,
        "passed_filters": result.passed_filters,
        "summary_path": result.summary_path,
    }


def _handle_session_start(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    from mt5_research_agent.session import start_session

    ctx.set_progress(0.5, "starting research terminal")
    result = start_session(confirm=bool(params.get("confirm", False)))
    ctx.set_progress(1.0, str(result.get("status", "")))
    return result


def _handle_session_stop(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    from mt5_research_agent.session import stop_session

    ctx.set_progress(0.5, "stopping research terminal")
    result = stop_session(confirm=bool(params.get("confirm", False)))
    ctx.set_progress(1.0, str(result.get("status", "")))
    return result
