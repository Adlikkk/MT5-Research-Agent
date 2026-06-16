from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from mt5_research_agent.config import AppConfig, load_config
from mt5_research_agent.mt5_diagnostics import artifacts_logs_dir, utc_now_timestamp


def normalize_process_path(value: str) -> str:
    if not value:
        return ""
    try:
        return str(Path(value).resolve()).casefold()
    except OSError:
        return str(Path(value)).casefold()


def list_mt5_processes() -> list[dict[str, Any]]:
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        "Get-CimInstance Win32_Process -Filter \"name = 'terminal64.exe'\" | Select-Object ProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Depth 3",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=30)
    if completed.returncode != 0:
        return []
    raw = completed.stdout.strip()
    if not raw:
        return []
    payload = json.loads(raw)
    rows = payload if isinstance(payload, list) else [payload]
    processes: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        processes.append(
            {
                "pid": int(row.get("ProcessId", 0)),
                "path": str(row.get("ExecutablePath") or ""),
                "command_line": str(row.get("CommandLine") or ""),
            }
        )
    return processes


def matching_mt5_processes(config: AppConfig | None = None, processes: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    current = config or load_config()
    items = processes if processes is not None else list_mt5_processes()
    expected = normalize_process_path(current.terminal_path)
    matches: list[dict[str, Any]] = []
    for item in items:
        path = str(item.get("path") or "")
        normalized = normalize_process_path(path)
        record = {
            **item,
            "path_matches_config": bool(expected and normalized == expected),
        }
        if record["path_matches_config"]:
            matches.append(record)
    return matches


def mt5_process_status_payload(config: AppConfig | None = None, processes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    current = config or load_config()
    items = processes if processes is not None else list_mt5_processes()
    expected = normalize_process_path(current.terminal_path)
    enriched = [
        {
            **item,
            "path_matches_config": bool(expected and normalize_process_path(str(item.get("path") or "")) == expected),
        }
        for item in items
    ]
    matching = [item for item in enriched if item["path_matches_config"]]
    if matching:
        recommended_action = "Run `python -m mt5_research_agent stop-mt5 --confirm` before a background CLI test."
    elif enriched:
        recommended_action = "Configured MT5 path is not currently running. Unrelated terminal64.exe processes were left untouched."
    else:
        recommended_action = "No MT5 terminal64.exe process is running."
    return {
        "running": bool(enriched),
        "matching_running": bool(matching),
        "configured_terminal_path": current.terminal_path,
        "processes": enriched,
        "recommended_action": recommended_action,
    }


def render_mt5_process_status(payload: dict[str, Any]) -> str:
    lines = [
        f"running: {payload['running']}",
        f"matching_running: {payload['matching_running']}",
        f"configured_terminal_path: {payload['configured_terminal_path'] or '<missing>'}",
        f"recommended_action: {payload['recommended_action']}",
    ]
    for process in payload["processes"]:
        lines.append(
            f"pid={process['pid']} path={process.get('path', '') or '<unknown>'} path_matches_config={process['path_matches_config']}"
        )
    return "\n".join(lines)


def render_stop_mt5_payload(payload: dict[str, Any]) -> str:
    lines = [
        f"confirm: {payload['confirm']}",
        f"all_processes: {payload['all_processes']}",
        f"configured_terminal_path: {payload['configured_terminal_path'] or '<missing>'}",
        f"target_count: {len(payload['targets'])}",
        f"skipped_count: {len(payload['skipped'])}",
        f"recommended_action: {payload['recommended_action']}",
    ]
    for target in payload["targets"]:
        lines.append(f"target pid={target['pid']} path={target.get('path', '') or '<unknown>'}")
    for skipped in payload["skipped"]:
        lines.append(f"skipped pid={skipped['pid']} path={skipped.get('path', '') or '<unknown>'}")
    if payload.get("stopped_pids"):
        lines.append(f"stopped_pids: {payload['stopped_pids']}")
    if payload.get("log_path"):
        lines.append(f"log_path: {payload['log_path']}")
    return "\n".join(lines)


def stop_process_by_pid(pid: int) -> None:
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", f"Stop-Process -Id {pid} -Force"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )


def wait_for_pids_exit(pids: list[int], timeout_seconds: int = 30) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        active = {int(item["pid"]) for item in list_mt5_processes()}
        if not any(pid in active for pid in pids):
            return True
        time.sleep(0.5)
    return False


def stop_mt5_payload(
    *,
    confirm: bool,
    all_processes: bool,
    config: AppConfig | None = None,
    processes: list[dict[str, Any]] | None = None,
    stop_fn=stop_process_by_pid,
    wait_fn=wait_for_pids_exit,
) -> dict[str, Any]:
    current = config or load_config()
    items = processes if processes is not None else list_mt5_processes()
    expected = normalize_process_path(current.terminal_path)
    targets: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for item in items:
        path = str(item.get("path") or "")
        matches = bool(expected and normalize_process_path(path) == expected)
        enriched = {**item, "path_matches_config": matches}
        if matches or all_processes:
            targets.append(enriched)
        else:
            skipped.append(enriched)

    payload = {
        "ok": True,
        "confirm": confirm,
        "all_processes": all_processes,
        "configured_terminal_path": current.terminal_path,
        "targets": targets,
        "skipped": skipped,
        "stopped_pids": [],
        "wait_succeeded": True,
        "log_path": "",
        "recommended_action": "",
    }

    if not confirm:
        payload["recommended_action"] = "Re-run with --confirm to stop the matching configured MT5 terminal."
        return payload

    stopped_pids: list[int] = []
    for target in targets:
        pid = int(target["pid"])
        stop_fn(pid)
        stopped_pids.append(pid)

    payload["stopped_pids"] = stopped_pids
    payload["wait_succeeded"] = wait_fn(stopped_pids) if stopped_pids else True
    log_path = artifacts_logs_dir(current) / f"stop_mt5_{utc_now_timestamp()}.json"
    payload["log_path"] = str(log_path)
    payload["recommended_action"] = "Re-run the background CLI smoke task after the configured MT5 process has fully exited."
    log_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
