from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import monotonic
from typing import Any, Callable

from mt5_research_agent.config import AppConfig, load_config
from mt5_research_agent.inspect import utc_timestamp
from mt5_research_agent.mt5_diagnostics import (
    REPORT_EXTENSIONS,
    collect_terminal_log_candidates,
    collect_tester_log_candidates,
    compile_ea_payload,
    describe_terminal_info as describe_terminal_info_payload,
    get_experts_folder_candidates,
    get_likely_report_folders,
    get_metaquotes_tester_folder_candidates,
    get_terminal_data_folder_candidates,
    get_tester_log_folders,
    infer_expert_value,
    locate_ea_payload,
    symbol_preflight_payload,
    terminal_log_roots,
)
from mt5_research_agent.mt5_process import (
    mt5_process_status_payload,
    render_mt5_process_status,
    render_stop_mt5_payload,
    stop_mt5_payload,
)
from mt5_research_agent.report_parser import parse_report_file, parsed_report_to_payload
from mt5_research_agent.result_store import (
    AcceptanceEvaluation,
    RunAttempt,
    build_stored_run,
    evaluate_acceptance,
    fetch_latest_run_attempt,
    fetch_runs,
    make_attempt_id,
    make_test_id,
    store_parsed_report_json,
    store_run,
    store_run_attempt,
    update_leaderboard_csv,
    update_summary_md,
)
from mt5_research_agent.task import ResearchTask, load_task, task_to_payload, validate_task_payload


MODEL_MAP = {
    "Every tick": "0",
    "1 minute OHLC": "1",
    "Open prices only": "2",
    "Every tick based on real ticks": "4",
}

REPORT_PATH_STRATEGIES = (
    "artifacts_absolute_current",
    "terminal_relative_reports",
    "terminal_root_stem",
    "terminal_mql5_files",
)


@dataclass(slots=True)
class GeneratedMt5Files:
    test_id: str
    task_path: Path
    set_path: Path
    native_set_path: Path
    ini_path: Path
    report_path: Path
    report_path_strategy: str
    mt5_report_value: str
    expected_native_report_paths: list[Path]
    log_path: Path


@dataclass(slots=True)
class CliRunResult:
    exit_code: int
    status: str
    test_id: str
    raw_report_path: str
    parsed_report_path: str
    log_path: str
    process_id: int | None
    process_exit_code: int | None
    safety_ui_failure: bool


@dataclass(slots=True)
class ReportDiscoveryResult:
    discovered_path: Path | None
    nearby_files: list[dict[str, Any]]
    report_candidates: list[dict[str, Any]]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_utc_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def configured_artifacts_dir(config: AppConfig | None = None) -> Path:
    current = config or load_config()
    path = Path(current.artifacts_dir).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_background_directories() -> dict[str, Path]:
    config = load_config()
    artifacts_root = configured_artifacts_dir(config)
    directories = {
        "generated_tasks": artifacts_root / "generated_tasks",
        "generated_sets": artifacts_root / "generated_sets",
        "generated_ini": artifacts_root / "generated_ini",
        "raw_reports": artifacts_root / "raw_reports",
        "parsed_reports": artifacts_root / "parsed_reports",
        "logs": artifacts_root / "logs",
        "results": Path(config.results_dir).resolve(),
    }
    for path in directories.values():
        path.mkdir(parents=True, exist_ok=True)
    return directories


def resolve_task_path(task_path: str | Path) -> Path:
    path = Path(task_path)
    if path.exists():
        return path

    parts = path.parts
    if len(parts) >= 3 and parts[0] == "artifacts" and parts[1] == "generated_tasks":
        candidate = ensure_background_directories()["generated_tasks"] / parts[-1]
        if candidate.exists():
            return candidate
    return path


def task_id_prefix(task: ResearchTask) -> str:
    source = task.ea
    if source.casefold().endswith("ea"):
        source = source[:-2]
    token = "".join(char for char in source if char.isalnum()).upper()
    return token or "TASK"


def model_code(model: str) -> str:
    return MODEL_MAP.get(model, model)


def make_generated_task_path(test_id: str) -> Path:
    directories = ensure_background_directories()
    return directories["generated_tasks"] / f"{test_id}.json"


def write_generated_task(task_payload: dict[str, Any]) -> Path:
    test_id = str(task_payload["test_id"])
    output_path = make_generated_task_path(test_id)
    output_path.write_text(json.dumps(task_payload, indent=2), encoding="utf-8")
    return output_path


def build_smoke_task_payload(
    *,
    test_id: str,
    ea: str,
    symbol: str,
    timeframe: str,
    period_from: str,
    period_to: str,
    deposit: float,
    model: str = "Every tick based on real ticks",
) -> dict[str, Any]:
    return {
        "test_id": test_id,
        "name": test_id.casefold().replace("_", "-"),
        "ea": ea,
        "symbol": symbol,
        "timeframe": timeframe,
        "period_from": period_from,
        "period_to": period_to,
        "deposit": deposit,
        "model": model,
        "inputs": {},
        "acceptance": {
            "min_profit": -999999,
            "min_profit_factor": 0,
            "max_equity_dd_pct": 100,
            "min_trades": 0,
        },
    }


def generated_mt5_paths(task: ResearchTask) -> GeneratedMt5Files:
    directories = ensure_background_directories()
    test_id = task.test_id or make_test_id(task.name)
    return GeneratedMt5Files(
        test_id=test_id,
        task_path=make_generated_task_path(test_id),
        set_path=directories["generated_sets"] / f"{test_id}.set",
        native_set_path=directories["generated_sets"] / f"{test_id}.set",
        ini_path=directories["generated_ini"] / f"{test_id}.ini",
        report_path=directories["raw_reports"] / f"{test_id}.htm",
        report_path_strategy="artifacts_absolute_current",
        mt5_report_value=str((directories["raw_reports"] / f"{test_id}").resolve()),
        expected_native_report_paths=[directories["raw_reports"] / f"{test_id}.htm"],
        log_path=directories["logs"] / f"run_task_cli_{test_id}_{utc_timestamp()}.json",
    )


def write_set_file(task: ResearchTask, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["; generated by mt5_research_agent"]
    for key, value in task.inputs.items():
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def normalize_report_path_strategy(value: str | None) -> str:
    candidate = str(value or "").strip() or "terminal_relative_reports"
    if candidate not in REPORT_PATH_STRATEGIES:
        raise ValueError(
            f"Unsupported report_path_strategy: {candidate}. Expected one of {', '.join(REPORT_PATH_STRATEGIES)}."
        )
    return candidate


def infer_terminal_data_root(task: ResearchTask, config: AppConfig) -> Path:
    _, locate = infer_expert_value(task.ea, config)
    for bucket in ("found_ex5", "found_mq5"):
        for item in locate.get(bucket, []):
            experts_root = Path(item.get("experts_root", ""))
            if experts_root.name == "Experts" and experts_root.parent.name == "MQL5":
                return experts_root.parent.parent

    candidates = get_terminal_data_folder_candidates(config)
    for candidate in candidates:
        if (candidate / "MQL5" / "Experts").exists():
            return candidate
    if candidates:
        return candidates[0]
    if config.terminal_path:
        return Path(config.terminal_path).expanduser().parent
    return configured_artifacts_dir(config)


def ensure_native_set_file(task: ResearchTask, config: AppConfig, artifact_set_path: Path) -> Path:
    terminal_data_root = infer_terminal_data_root(task, config)
    native_dir = terminal_data_root / "MQL5" / "Profiles" / "Tester"
    native_dir.mkdir(parents=True, exist_ok=True)
    native_path = native_dir / f"{task.test_id or make_test_id(task.name)}.set"
    shutil.copy2(artifact_set_path, native_path)
    return native_path


def build_report_targets(
    task: ResearchTask,
    config: AppConfig,
    strategy: str,
) -> tuple[Path, str, list[Path]]:
    directories = ensure_background_directories()
    artifact_report_path = directories["raw_reports"] / f"{task.test_id or make_test_id(task.name)}.htm"
    terminal_data_root = infer_terminal_data_root(task, config)
    test_id = task.test_id or make_test_id(task.name)

    if strategy == "artifacts_absolute_current":
        report_stem_path = artifact_report_path.with_suffix("")
        return artifact_report_path, str(report_stem_path.resolve()), [artifact_report_path]

    if strategy == "terminal_relative_reports":
        reports_dir = terminal_data_root / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        mt5_report_value = f"reports\\{test_id}"
        expected = [
            reports_dir / f"{test_id}.htm",
            reports_dir / f"{test_id}.html",
            reports_dir / f"{test_id}.xml",
            terminal_data_root / f"{test_id}.htm",
            terminal_data_root / f"{test_id}.xml",
        ]
        return artifact_report_path, mt5_report_value, expected

    if strategy == "terminal_root_stem":
        expected = [
            terminal_data_root / f"{test_id}.htm",
            terminal_data_root / f"{test_id}.html",
            terminal_data_root / f"{test_id}.xml",
        ]
        return artifact_report_path, test_id, expected

    files_dir = terminal_data_root / "MQL5" / "Files"
    files_dir.mkdir(parents=True, exist_ok=True)
    mt5_report_value = f"MQL5\\Files\\{test_id}"
    expected = [
        files_dir / f"{test_id}.htm",
        files_dir / f"{test_id}.html",
        files_dir / f"{test_id}.xml",
    ]
    return artifact_report_path, mt5_report_value, expected


def verify_report_targets_writable(paths: list[Path]) -> tuple[bool, str]:
    if not paths:
        return False, "No report paths were provided."
    probe_dir = paths[0].parent
    probe_dir.mkdir(parents=True, exist_ok=True)
    probe = probe_dir / f".write_probe_{utc_timestamp()}.tmp"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True, str(probe_dir)
    except OSError as exc:
        return False, str(exc)


def effective_shutdown_terminal_after_run(
    config: AppConfig,
    keep_terminal_open: bool = False,
) -> bool:
    return False if keep_terminal_open else config.shutdown_terminal_after_run


def write_ini_file(
    task: ResearchTask,
    config: AppConfig,
    set_path: str | Path,
    report_value: str,
    output_path: str | Path,
    *,
    keep_terminal_open: bool = False,
    native_tester_set_mode: bool = True,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    set_value = Path(set_path).name if native_tester_set_mode else str(Path(set_path).resolve())
    resolved_expert_value, _ = infer_expert_value(task.ea, config)
    lines = [
        "; generated by mt5_research_agent",
        "[Tester]",
        f"Expert={resolved_expert_value}",
        f"ExpertParameters={set_value}",
        f"Symbol={task.symbol}",
        f"Period={task.timeframe}",
        f"Model={model_code(task.model)}",
        f"FromDate={task.period_from}",
        f"ToDate={task.period_to}",
        f"Deposit={int(task.deposit) if task.deposit.is_integer() else task.deposit}",
        "Optimization=0",
        "Visual=0",
        f"Report={report_value}",
        "ReplaceReport=1",
        f"ShutdownTerminal={1 if effective_shutdown_terminal_after_run(config, keep_terminal_open) else 0}",
        f"Portable={1 if config.portable_mode else 0}",
    ]
    path.write_text("\n".join(str(line) for line in lines) + "\n", encoding="utf-8")
    return path


def build_mt5_command(config: AppConfig, ini_path: str | Path) -> list[str]:
    if not config.terminal_path:
        return []
    command = [str(Path(config.terminal_path).expanduser()), f"/config:{Path(ini_path).resolve()}"]
    if config.portable_mode:
        command.insert(1, "/portable")
    return command


def render_mt5_command(command: list[str]) -> str:
    return subprocess.list2cmdline(command) if command else ""


def generate_mt5_files(
    task_path: str | Path,
    *,
    keep_terminal_open: bool = False,
    report_path_strategy: str | None = None,
) -> GeneratedMt5Files:
    resolved_task_path = resolve_task_path(task_path)
    task = load_task(resolved_task_path)
    files = generated_mt5_paths(task)
    source_path = resolved_task_path
    if source_path.exists() and source_path.resolve() != files.task_path.resolve():
        files.task_path.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
    write_set_file(task, files.set_path)
    config = load_config()
    strategy = normalize_report_path_strategy(report_path_strategy or config.report_path_strategy)
    native_set_path = ensure_native_set_file(task, config, files.set_path)
    artifact_report_path, mt5_report_value, expected_native_report_paths = build_report_targets(task, config, strategy)
    files.native_set_path = native_set_path
    files.report_path = artifact_report_path
    files.report_path_strategy = strategy
    files.mt5_report_value = mt5_report_value
    files.expected_native_report_paths = expected_native_report_paths
    write_ini_file(
        task,
        config,
        files.native_set_path,
        files.mt5_report_value,
        files.ini_path,
        keep_terminal_open=keep_terminal_open,
        native_tester_set_mode=True,
    )
    return files


def load_generated_file_text(
    task_path: str | Path,
    file_kind: str,
    *,
    keep_terminal_open: bool = False,
    report_path_strategy: str | None = None,
) -> tuple[GeneratedMt5Files, str]:
    resolved_task_path = resolve_task_path(task_path)
    files = generate_mt5_files(
        resolved_task_path,
        keep_terminal_open=keep_terminal_open,
        report_path_strategy=report_path_strategy,
    )
    target = files.ini_path if file_kind == "ini" else files.set_path
    return files, target.read_text(encoding="utf-8")


def record_attempt(
    *,
    test_id: str,
    task_name: str,
    run_status: str,
    execution_mode: str,
    run_kind: str,
    parent_candidate_id: str,
    split_id: str,
    raw_report_path: str = "",
    parsed_report_path: str = "",
    log_path: str = "",
    set_path: str = "",
    ini_path: str = "",
    command_line: str = "",
    expected_report_path: str = "",
    discovered_report_path: str = "",
    process_id: int | None = None,
    process_exit_code: int | None = None,
    process_started_at: str = "",
    process_ended_at: str = "",
    duration_seconds: float | None = None,
    parsed_metrics_json: dict[str, Any] | None = None,
    decision_reason: str = "",
    per_rule_results: list[dict[str, Any]] | None = None,
    error: str = "",
) -> None:
    store_run_attempt(
        RunAttempt(
            attempt_id=make_attempt_id(test_id, run_status),
            test_id=test_id,
            run_status=run_status,
            execution_mode=execution_mode,
            run_kind=run_kind,
            parent_candidate_id=parent_candidate_id,
            split_id=split_id,
            task_name=task_name,
            raw_report_path=raw_report_path,
            parsed_report_path=parsed_report_path,
            log_path=log_path,
            set_path=set_path,
            ini_path=ini_path,
            command_line=command_line,
            expected_report_path=expected_report_path,
            discovered_report_path=discovered_report_path,
            process_id=process_id,
            process_exit_code=process_exit_code,
            process_started_at=process_started_at,
            process_ended_at=process_ended_at,
            duration_seconds=duration_seconds,
            parsed_metrics_json=parsed_metrics_json or {},
            decision_reason=decision_reason,
            per_rule_results=per_rule_results or [],
            error=error,
            created_at=utc_now_iso(),
        )
    )


def coerce_acceptance_evaluation(result: AcceptanceEvaluation | tuple[bool, str]) -> AcceptanceEvaluation:
    if isinstance(result, AcceptanceEvaluation):
        return result
    passed, rejection_reason = result
    final_status = "PASS" if passed else "FAIL"
    return AcceptanceEvaluation(
        passed=passed,
        status=final_status,
        rejection_reason=rejection_reason,
        decision_reason="Legacy evaluator result.",
        per_rule_results=[],
        missing_metrics=[],
        metrics_used={},
    )


def describe_file(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "name": path.name,
        "path": str(path),
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }


def list_nearby_files(directory: str | Path, limit: int = 10) -> list[dict[str, Any]]:
    path = Path(directory)
    if not path.exists():
        return []
    files = sorted(
        (candidate for candidate in path.iterdir() if candidate.is_file()),
        key=lambda candidate: candidate.stat().st_mtime,
        reverse=True,
    )[:limit]
    return [describe_file(candidate) for candidate in files]


def report_search_roots(
    expected_report_path: Path,
    config: AppConfig | None = None,
    extra_paths: list[Path] | None = None,
) -> list[Path]:
    roots = [expected_report_path.parent]
    if extra_paths:
        roots.extend(path.parent for path in extra_paths)
    if config is not None:
        roots.extend(get_likely_report_folders(config))
        roots.extend(get_terminal_data_folder_candidates(config))
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root.resolve()) if root.exists() else str(root)
        if key not in seen:
            unique.append(root)
            seen.add(key)
    return unique


def _score_report_candidate(
    candidate: Path,
    *,
    expected_stem: str,
    report_stem: str,
    process_started_at: datetime | None,
) -> tuple[int, int, float]:
    modified_at = datetime.fromtimestamp(candidate.stat().st_mtime, tz=timezone.utc)
    after_start = process_started_at is None or modified_at >= process_started_at - timedelta(seconds=2)
    lowered_name = candidate.name.casefold()
    expected_folded = expected_stem.casefold()
    report_folded = report_stem.casefold()
    stem_match = bool(expected_folded) and (
        candidate.stem.casefold() == expected_folded or lowered_name.startswith(expected_folded)
    )
    report_match = bool(report_folded) and (
        candidate.stem.casefold() == report_folded or lowered_name.startswith(report_folded)
    )
    score = 0
    if stem_match:
        score += 6
    if report_match:
        score += 5
    if after_start:
        score += 3
    return score, 1 if stem_match or report_match else 0, candidate.stat().st_mtime


def collect_report_candidates(
    roots: list[Path],
    *,
    expected_stem: str,
    report_stem: str,
    process_started_at: datetime | None,
    limit: int = 30,
) -> list[dict[str, Any]]:
    candidates: list[tuple[tuple[int, int, float], Path, bool, bool]] = []
    for root in roots:
        if not root.exists():
            continue
        for candidate in root.rglob("*"):
            if not candidate.is_file() or candidate.suffix.casefold() not in REPORT_EXTENSIONS:
                continue
            modified_at = datetime.fromtimestamp(candidate.stat().st_mtime, tz=timezone.utc)
            after_start = process_started_at is None or modified_at >= process_started_at - timedelta(seconds=2)
            lowered_name = candidate.name.casefold()
            expected_folded = expected_stem.casefold()
            report_folded = report_stem.casefold()
            expected_match = bool(expected_folded) and (
                candidate.stem.casefold() == expected_folded or lowered_name.startswith(expected_folded)
            )
            report_match = bool(report_folded) and (
                candidate.stem.casefold() == report_folded or lowered_name.startswith(report_folded)
            )
            if expected_match or report_match or after_start:
                candidates.append(
                    (
                        _score_report_candidate(
                            candidate,
                            expected_stem=expected_stem,
                            report_stem=report_stem,
                            process_started_at=process_started_at,
                        ),
                        candidate,
                        expected_match,
                        report_match,
                    )
                )

    candidates.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            **describe_file(candidate),
            "likely_test_id_match": expected_match,
            "report_stem_match": report_match,
            "after_process_start": datetime.fromtimestamp(candidate.stat().st_mtime, tz=timezone.utc) >= process_started_at - timedelta(seconds=2)
            if process_started_at is not None
            else True,
        }
        for _, candidate, expected_match, report_match in candidates[:limit]
    ]


def discover_report(
    expected_report_path: str | Path,
    process_started_at: datetime | None = None,
    *,
    config: AppConfig | None = None,
    explicit_expected_paths: list[Path] | None = None,
) -> ReportDiscoveryResult:
    path = Path(expected_report_path)
    directory = path.parent
    explicit_expected_paths = explicit_expected_paths or []
    roots = report_search_roots(path, config, extra_paths=explicit_expected_paths)
    candidates = collect_report_candidates(
        roots,
        expected_stem=path.stem,
        report_stem=path.stem,
        process_started_at=process_started_at,
    )

    for explicit_path in explicit_expected_paths:
        if explicit_path.exists():
            return ReportDiscoveryResult(explicit_path, list_nearby_files(explicit_path.parent), candidates)
    if path.exists():
        return ReportDiscoveryResult(path, list_nearby_files(directory), candidates)

    discovered = Path(candidates[0]["path"]) if candidates else None
    return ReportDiscoveryResult(discovered, list_nearby_files(directory), candidates)


def build_find_reports_payload(since_minutes: int, config: AppConfig | None = None) -> dict[str, Any]:
    current = config or load_config()
    roots = [
        configured_artifacts_dir(current) / "raw_reports",
        *get_likely_report_folders(current),
        *get_terminal_data_folder_candidates(current),
    ]
    since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
    candidates = collect_report_candidates(
        roots,
        expected_stem="",
        report_stem="",
        process_started_at=since,
        limit=50,
    )
    return {
        "since_minutes": since_minutes,
        "searched_roots": [str(path) for path in report_search_roots(configured_artifacts_dir(current) / "raw_reports" / "placeholder.htm", current)],
        "candidates": candidates,
    }


def build_terminal_folders_payload(config: AppConfig | None = None) -> dict[str, Any]:
    current = config or load_config()
    terminal_path = Path(current.terminal_path).expanduser() if current.terminal_path else Path()
    return {
        "terminal_path": current.terminal_path,
        "portable_mode": current.portable_mode,
        "terminal_executable_dir": str(terminal_path.parent) if current.terminal_path else "",
        "terminal_data_folders": [str(path) for path in get_terminal_data_folder_candidates(current)],
        "tester_data_folders": [str(path) for path in get_metaquotes_tester_folder_candidates()],
        "experts_folders": [str(path) for path in get_experts_folder_candidates(current)],
        "logs_folders": [str(path) for path in terminal_log_roots(current)],
        "tester_log_folders": [str(path) for path in get_tester_log_folders(current)],
        "likely_report_folders": [str(path) for path in get_likely_report_folders(current)],
    }


def render_task_summary(task: ResearchTask) -> str:
    acceptance = task.acceptance
    lines = [
        f"test_id: {task.test_id or '<missing>'}",
        f"ea: {task.ea}",
        f"symbol: {task.symbol}",
        f"timeframe: {task.timeframe}",
        f"period: {task.period_from} -> {task.period_to}",
        f"deposit: {task.deposit:g}",
        f"model: {task.model}",
        f"input count: {len(task.inputs)}",
        "acceptance:",
        f"  min_profit={acceptance.min_profit:g}",
        f"  min_profit_factor={acceptance.min_profit_factor:g}",
        f"  max_equity_dd_pct={acceptance.max_equity_dd_pct:g}",
        f"  min_trades={acceptance.min_trades}",
    ]
    return "\n".join(lines)


def read_log_payload(log_path: str) -> dict[str, Any] | None:
    if not log_path:
        return None
    path = Path(log_path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def classify_log_snippets(log_items: list[dict[str, Any]]) -> list[str]:
    reasons: list[str] = []
    mapping = {
        "cannot open expert": "Tester could not open the expert.",
        "cannot load expert": "Tester could not load the expert.",
        "symbol not found": "The requested symbol was not found.",
        "no history": "Required history data is missing.",
        "report cannot be written": "MT5 could not write the report file.",
        "tester stopped": "Strategy Tester stopped before producing a report.",
        "initialization failed": "EA or tester initialization failed.",
    }
    for item in log_items:
        preview = str(item.get("snippet_preview", "")).casefold()
        for token, reason in mapping.items():
            if token in preview and reason not in reasons:
                reasons.append(reason)
    return reasons


def likely_diagnosis(attempt: dict[str, Any], log_payload: dict[str, Any] | None = None) -> str:
    duration_seconds = attempt.get("duration_seconds")
    discovered_report_path = attempt.get("discovered_report_path") or ""
    terminal_logs = (log_payload or {}).get("terminal_log_candidates", [])
    tester_logs = (log_payload or {}).get("tester_log_candidates", [])
    for item in terminal_logs:
        preview = str(item.get("snippet_preview", "")).casefold()
        if "terminal process already started" in preview:
            return "MT5 refused the CLI launch because a terminal process was already running. Fully close the terminal or use a separate terminal instance before re-running the smoke task."
    log_reasons = classify_log_snippets(tester_logs + terminal_logs)
    if log_reasons:
        return " ".join(log_reasons)
    if attempt.get("run_status") == "REPORT_MISSING" and duration_seconds is not None and duration_seconds < 3 and not discovered_report_path:
        task = (log_payload or {}).get("task", {})
        ea = task.get("ea", "")
        symbol = task.get("symbol", "")
        return (
            "MT5 exited almost immediately with no report. The tester likely could not resolve the EA, symbol, "
            f"or tester config. Check compiled EA availability for '{ea}' and symbol availability for '{symbol}'."
        )
    tester_preview = "\n".join(
        str(item.get("snippet_preview", "")) for item in (log_payload or {}).get("tester_log_candidates", [])
    ).casefold()
    if "automatical testing finished" in tester_preview and attempt.get("run_status") == "REPORT_MISSING":
        return "Tester appears to complete, but no report was emitted. Try test-report-strategies."
    if attempt.get("run_status") == "REPORT_MISSING" and duration_seconds is not None and duration_seconds > 10 and not discovered_report_path:
        return "MT5 likely started but report discovery or tester config still failed. Inspect tester logs and find-reports output."
    return ""


def render_attempt_summary(attempt: dict[str, Any], log_payload: dict[str, Any] | None = None) -> str:
    nearby_files = []
    report_candidates = []
    terminal_logs = []
    tester_logs = []
    shutdown_value = ""
    native_set_path = ""
    report_path_strategy = ""
    mt5_report_value = ""
    expected_native_report_paths = []
    copied_artifact_report_path = ""
    parsed_metrics_payload = attempt.get("parsed_metrics_payload", {})
    decision_reason = str(attempt.get("decision_reason", ""))
    per_rule_results = attempt.get("per_rule_results", [])
    if log_payload is not None:
        nearby_files = log_payload.get("nearby_report_files", [])
        report_candidates = log_payload.get("report_candidates", [])
        terminal_logs = log_payload.get("terminal_log_candidates", [])
        tester_logs = log_payload.get("tester_log_candidates", [])
        shutdown_value = str(log_payload.get("generated_ini_shutdown_terminal_value", ""))
        native_set_path = str(log_payload.get("native_set_path", ""))
        report_path_strategy = str(log_payload.get("report_path_strategy", ""))
        mt5_report_value = str(log_payload.get("mt5_report_value", ""))
        expected_native_report_paths = log_payload.get("expected_native_report_paths", [])
        copied_artifact_report_path = str(log_payload.get("copied_artifact_report_path", ""))
        parsed_metrics_payload = log_payload.get("parsed_metrics", parsed_metrics_payload)
        decision_reason = str(log_payload.get("decision_reason", decision_reason))
        per_rule_results = log_payload.get("per_rule_results", per_rule_results)
    lines = [
        f"latest status: {attempt.get('run_status', '')}",
        f"command line: {attempt.get('command_line', '') or '<none>'}",
        f"process exit code: {attempt.get('process_exit_code', '')}",
        f"process duration: {attempt.get('duration_seconds', '')}",
        f"generated ini path: {attempt.get('ini_path', '') or '<none>'}",
        f"generated ini ShutdownTerminal: {shutdown_value or '<unknown>'}",
        f"generated set path: {attempt.get('set_path', '') or '<none>'}",
        f"native set path: {native_set_path or '<none>'}",
        f"report path strategy: {report_path_strategy or '<none>'}",
        f"mt5 Report value: {mt5_report_value or '<none>'}",
        f"expected native report paths: {json.dumps(expected_native_report_paths, ensure_ascii=True)}",
        f"expected report path: {attempt.get('expected_report_path', '') or '<none>'}",
        f"discovered report path: {attempt.get('discovered_report_path', '') or '<none>'}",
        f"copied artifact report path: {copied_artifact_report_path or '<none>'}",
        f"nearby report files: {json.dumps(nearby_files, ensure_ascii=True)}",
        f"report candidates: {json.dumps(report_candidates, ensure_ascii=True)}",
        f"tester log candidates: {json.dumps(tester_logs, ensure_ascii=True)}",
        f"terminal log candidates: {json.dumps(terminal_logs, ensure_ascii=True)}",
        f"parsed metrics: {json.dumps(parsed_metrics_payload.get('normalized_metrics', parsed_metrics_payload), ensure_ascii=True)}",
        f"parser warnings: {json.dumps(parsed_metrics_payload.get('parser_warnings', []), ensure_ascii=True)}",
        f"decision reason: {decision_reason or '<none>'}",
        f"per-rule results: {json.dumps(per_rule_results, ensure_ascii=True)}",
        f"log path: {attempt.get('log_path', '') or '<none>'}",
    ]
    diagnosis = likely_diagnosis(attempt, log_payload)
    if diagnosis:
        lines.append(f"likely diagnosis: {diagnosis}")
    return "\n".join(lines)


def build_preflight_warnings(task: ResearchTask) -> list[str]:
    warnings: list[str] = []
    if task.ea.casefold() == "goldea":
        warnings.append("EA looks like a placeholder task value: GoldEA.")
    if task.ea.casefold().endswith(".mq5"):
        warnings.append("EA name ends with .mq5. Strategy Tester needs the compiled .ex5 to be installed and visible.")
    start_date = datetime.strptime(task.period_from, "%Y.%m.%d")
    end_date = datetime.strptime(task.period_to, "%Y.%m.%d")
    if (end_date - start_date).days > 90:
        warnings.append("Smoke period is longer than 90 days. Prefer a shorter range for first-run diagnosis.")
    return warnings


def describe_terminal_info(config: AppConfig | None = None) -> dict[str, Any]:
    return describe_terminal_info_payload(config)


def read_ini_shutdown_value(ini_path: str | Path) -> str:
    path = Path(ini_path)
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("ShutdownTerminal="):
            return line.split("=", 1)[1].strip()
    return ""


def build_task_status_payload(test_id: str) -> dict[str, Any]:
    attempt = fetch_latest_run_attempt(test_id)
    if attempt is None:
        return {"ok": False, "error": "TEST_ID_NOT_FOUND", "test_id": test_id}
    log_payload = read_log_payload(str(attempt.get("log_path", ""))) or {}
    return {
        "ok": True,
        "test_id": test_id,
        "latest_status": attempt.get("run_status"),
        "command_line": attempt.get("command_line"),
        "process_exit_code": attempt.get("process_exit_code"),
        "duration_seconds": attempt.get("duration_seconds"),
        "ini_path": attempt.get("ini_path"),
        "set_path": attempt.get("set_path"),
        "native_set_path": log_payload.get("native_set_path", ""),
        "report_path_strategy": log_payload.get("report_path_strategy", ""),
        "mt5_report_value": log_payload.get("mt5_report_value", ""),
        "expected_native_report_paths": log_payload.get("expected_native_report_paths", []),
        "copied_artifact_report_path": log_payload.get("copied_artifact_report_path", ""),
        "expected_report_path": attempt.get("expected_report_path"),
        "discovered_report_path": attempt.get("discovered_report_path"),
        "nearby_report_files": log_payload.get("nearby_report_files", []),
        "report_candidates": log_payload.get("report_candidates", []),
        "tester_log_candidates": log_payload.get("tester_log_candidates", []),
        "terminal_log_candidates": log_payload.get("terminal_log_candidates", []),
        "generated_ini_shutdown_terminal_value": log_payload.get(
            "generated_ini_shutdown_terminal_value",
            read_ini_shutdown_value(str(attempt.get("ini_path", ""))),
        ),
        "parsed_metrics": log_payload.get("parsed_metrics", attempt.get("parsed_metrics_payload", {})),
        "decision_reason": log_payload.get("decision_reason", attempt.get("decision_reason", "")),
        "per_rule_results": log_payload.get("per_rule_results", attempt.get("per_rule_results", [])),
        "log_path": attempt.get("log_path"),
        "likely_diagnosis": likely_diagnosis(attempt, log_payload),
    }


def check_report_path_writable(report_path: Path) -> tuple[bool, str]:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    probe = report_path.parent / f".write_probe_{utc_timestamp()}.tmp"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True, str(report_path.parent)
    except OSError as exc:
        return False, str(exc)


def render_preflight_summary(payload: dict[str, Any]) -> str:
    checks = payload["checks"]
    lines = [
        f"task: {payload['task_path']}",
        f"terminal_path_ok: {checks['terminal_path_ok']}",
        f"report_path_writable: {checks['report_path_writable']}",
        f"ea_ex5_exists: {checks['ea_ex5_exists']}",
        f"ea_ex5_fresh: {checks['ea_ex5_fresh']}",
        f"symbol_exact_match: {checks['symbol_exact_match']}",
        f"resolved_expert_value: {payload['resolved_expert_value']}",
        f"preflight_ok: {payload['ok']}",
    ]
    for warning in payload.get("warnings", []):
        lines.append(f"warning: {warning}")
    return "\n".join(lines)


def render_generated_files_summary(files: GeneratedMt5Files) -> str:
    report_writable, report_detail = verify_report_targets_writable(files.expected_native_report_paths)
    lines = [
        f"test_id: {files.test_id}",
        f"artifact set: {files.set_path}",
        f"native set: {files.native_set_path}",
        f"ini: {files.ini_path}",
        f"artifact report target: {files.report_path}",
        f"report path strategy: {files.report_path_strategy}",
        f"mt5 Report value: {files.mt5_report_value}",
        f"report target writable: {report_writable}",
        f"report target detail: {report_detail}",
        "expected native report paths:",
    ]
    lines.extend(f"  {path}" for path in files.expected_native_report_paths)
    return "\n".join(lines)


def run_task_cli(
    task_path: str,
    timeout_seconds: int,
    *,
    allow_stop_existing_terminal: bool = False,
    keep_terminal_open: bool = False,
    report_path_strategy: str | None = None,
    run_kind: str = "full_period",
    parent_candidate_id: str = "",
    split_id: str = "",
    acceptance_evaluator: Callable[[Any, Any], tuple[bool, str]] | None = None,
) -> CliRunResult:
    config = load_config()
    resolved_task_path = resolve_task_path(task_path)
    task = load_task(resolved_task_path)
    test_id = task.test_id or make_test_id(task.name)
    files = generate_mt5_files(
        resolved_task_path,
        keep_terminal_open=keep_terminal_open,
        report_path_strategy=report_path_strategy,
    )
    resolved_expert_value, locate_info = infer_expert_value(task.ea, config)
    shutdown_value = read_ini_shutdown_value(files.ini_path)
    native_report_paths = [Path(path) for path in files.expected_native_report_paths]

    record_attempt(
        test_id=test_id,
        task_name=task.name,
        run_status="FILES_GENERATED",
        execution_mode="cli",
        run_kind=run_kind,
        parent_candidate_id=parent_candidate_id,
        split_id=split_id,
        set_path=str(files.set_path),
        ini_path=str(files.ini_path),
        log_path=str(files.log_path),
        expected_report_path=str(files.report_path),
    )

    terminal_path = Path(config.terminal_path).expanduser() if config.terminal_path else None
    command = build_mt5_command(config, files.ini_path)
    effective_allow_stop = allow_stop_existing_terminal or config.allow_stop_existing_terminal
    if terminal_path is None or not terminal_path.exists():
        payload: dict[str, Any] = {
            "timestamp": utc_timestamp(),
            "task_path": str(resolved_task_path),
            "task": task_to_payload(task),
            "execution_mode": "cli",
            "resolved_expert_value": resolved_expert_value,
            "ea_locate": locate_info,
            "command_line": render_mt5_command(command),
            "error": "Configured terminal_path does not exist.",
            "set_path": str(files.set_path),
            "native_set_path": str(files.native_set_path),
            "ini_path": str(files.ini_path),
            "report_path_strategy": files.report_path_strategy,
            "mt5_report_value": files.mt5_report_value,
            "expected_native_report_paths": [str(path) for path in files.expected_native_report_paths],
            "generated_ini_shutdown_terminal_value": shutdown_value,
            "expected_report_path": str(files.report_path),
            "status": "PROCESS_FAILED",
        }
        files.log_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        record_attempt(
            test_id=test_id,
            task_name=task.name,
            run_status="PROCESS_FAILED",
            execution_mode="cli",
            run_kind=run_kind,
            parent_candidate_id=parent_candidate_id,
            split_id=split_id,
            log_path=str(files.log_path),
            set_path=str(files.set_path),
            ini_path=str(files.ini_path),
            command_line=render_mt5_command(command),
            expected_report_path=str(files.report_path),
            error="Configured terminal_path does not exist.",
        )
        stored = build_stored_run(
            test_id=test_id,
            task=task,
            parsed_report=None,
            passed=False,
            rejection_reason="PROCESS_FAILED",
            raw_report_path="",
            parsed_report_path="",
            screenshot_path="",
            run_status="PROCESS_FAILED",
            execution_mode="cli",
            run_kind=run_kind,
            parent_candidate_id=parent_candidate_id,
            split_id=split_id,
        )
        store_run(stored)
        update_leaderboard_csv()
        update_summary_md()
        return CliRunResult(1, "PROCESS_FAILED", test_id, "", "", str(files.log_path), None, None, False)

    process_status = mt5_process_status_payload(config)
    if process_status["matching_running"]:
        if effective_allow_stop:
            stop_payload = stop_mt5_payload(confirm=True, all_processes=False, config=config)
            if not stop_payload.get("wait_succeeded", False):
                payload = {
                    "timestamp": utc_timestamp(),
                    "task_path": str(resolved_task_path),
                    "task": task_to_payload(task),
                    "execution_mode": "cli",
                    "resolved_expert_value": resolved_expert_value,
                    "ea_locate": locate_info,
                    "mt5_process_status": process_status,
                    "stop_action": stop_payload,
                    "error": "Configured terminal process did not exit after stop request.",
                    "set_path": str(files.set_path),
                    "native_set_path": str(files.native_set_path),
                    "ini_path": str(files.ini_path),
                    "report_path_strategy": files.report_path_strategy,
                    "mt5_report_value": files.mt5_report_value,
                    "expected_native_report_paths": [str(path) for path in files.expected_native_report_paths],
                    "generated_ini_shutdown_terminal_value": shutdown_value,
                    "expected_report_path": str(files.report_path),
                    "status": "PROCESS_FAILED",
                }
                files.log_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                record_attempt(
                    test_id=test_id,
                    task_name=task.name,
                    run_status="PROCESS_FAILED",
                    execution_mode="cli",
                    run_kind=run_kind,
                    parent_candidate_id=parent_candidate_id,
                    split_id=split_id,
                    log_path=str(files.log_path),
                    set_path=str(files.set_path),
                    ini_path=str(files.ini_path),
                    command_line=render_mt5_command(command),
                    expected_report_path=str(files.report_path),
                    error="Configured terminal process did not exit after stop request.",
                )
                stored = build_stored_run(
                    test_id=test_id,
                    task=task,
                    parsed_report=None,
                    passed=False,
                    rejection_reason="PROCESS_FAILED",
                    raw_report_path="",
                    parsed_report_path="",
                    screenshot_path="",
                    run_status="PROCESS_FAILED",
                    execution_mode="cli",
                    run_kind=run_kind,
                    parent_candidate_id=parent_candidate_id,
                    split_id=split_id,
                )
                store_run(stored)
                update_leaderboard_csv()
                update_summary_md()
                return CliRunResult(1, "PROCESS_FAILED", test_id, "", "", str(files.log_path), None, None, False)
        else:
            payload = {
                "timestamp": utc_timestamp(),
                "task_path": str(resolved_task_path),
                "task": task_to_payload(task),
                "execution_mode": "cli",
                "resolved_expert_value": resolved_expert_value,
                "ea_locate": locate_info,
                "mt5_process_status": process_status,
                "error": "Configured terminal_path is already running. Stop the matching terminal before launching a background CLI run.",
                "next_command": "python -m mt5_research_agent stop-mt5 --confirm",
                "set_path": str(files.set_path),
                "native_set_path": str(files.native_set_path),
                "ini_path": str(files.ini_path),
                "report_path_strategy": files.report_path_strategy,
                "mt5_report_value": files.mt5_report_value,
                "expected_native_report_paths": [str(path) for path in files.expected_native_report_paths],
                "generated_ini_shutdown_terminal_value": shutdown_value,
                "expected_report_path": str(files.report_path),
                "status": "TERMINAL_ALREADY_RUNNING",
            }
            files.log_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            record_attempt(
                test_id=test_id,
                task_name=task.name,
                run_status="TERMINAL_ALREADY_RUNNING",
                execution_mode="cli",
                run_kind=run_kind,
                parent_candidate_id=parent_candidate_id,
                split_id=split_id,
                log_path=str(files.log_path),
                set_path=str(files.set_path),
                ini_path=str(files.ini_path),
                command_line=render_mt5_command(command),
                expected_report_path=str(files.report_path),
                error="Configured terminal_path is already running.",
            )
            stored = build_stored_run(
                test_id=test_id,
                task=task,
                parsed_report=None,
                passed=False,
                rejection_reason="TERMINAL_ALREADY_RUNNING",
                raw_report_path="",
                parsed_report_path="",
                screenshot_path="",
                run_status="TERMINAL_ALREADY_RUNNING",
                execution_mode="cli",
                run_kind=run_kind,
                parent_candidate_id=parent_candidate_id,
                split_id=split_id,
            )
            store_run(stored)
            update_leaderboard_csv()
            update_summary_md()
            return CliRunResult(1, "TERMINAL_ALREADY_RUNNING", test_id, "", "", str(files.log_path), None, None, False)

    record_attempt(
        test_id=test_id,
        task_name=task.name,
        run_status="RUNNING",
        execution_mode="cli",
        run_kind=run_kind,
        parent_candidate_id=parent_candidate_id,
        split_id=split_id,
        log_path=str(files.log_path),
        set_path=str(files.set_path),
        ini_path=str(files.ini_path),
        command_line=render_mt5_command(command),
        expected_report_path=str(files.report_path),
    )

    process: subprocess.Popen[str] | None = None
    started_at_iso = utc_now_iso()
    started_at_monotonic = monotonic()
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        ended_at_iso = utc_now_iso()
        duration_seconds = round(monotonic() - started_at_monotonic, 3)
        payload = {
            "timestamp": utc_timestamp(),
            "task_path": str(resolved_task_path),
            "task": task_to_payload(task),
            "execution_mode": "cli",
            "resolved_expert_value": resolved_expert_value,
            "ea_locate": locate_info,
            "command": command,
            "command_line": render_mt5_command(command),
            "process_id": process.pid,
            "process_exit_code": process.returncode,
            "process_started_at": started_at_iso,
            "process_ended_at": ended_at_iso,
            "duration_seconds": duration_seconds,
            "stdout": stdout,
            "stderr": stderr,
            "set_path": str(files.set_path),
            "native_set_path": str(files.native_set_path),
            "ini_path": str(files.ini_path),
            "report_path_strategy": files.report_path_strategy,
            "mt5_report_value": files.mt5_report_value,
            "expected_native_report_paths": [str(path) for path in files.expected_native_report_paths],
            "generated_ini_shutdown_terminal_value": shutdown_value,
            "expected_report_path": str(files.report_path),
        }
    except subprocess.TimeoutExpired as exc:
        if process is not None:
            process.kill()
            stdout, stderr = process.communicate()
        else:
            stdout = ""
            stderr = ""
        ended_at_iso = utc_now_iso()
        duration_seconds = round(monotonic() - started_at_monotonic, 3)
        payload = {
            "timestamp": utc_timestamp(),
            "task_path": str(resolved_task_path),
            "task": task_to_payload(task),
            "execution_mode": "cli",
            "resolved_expert_value": resolved_expert_value,
            "ea_locate": locate_info,
            "command": command,
            "command_line": render_mt5_command(command),
            "process_id": process.pid if process is not None else None,
            "process_exit_code": process.returncode if process is not None else None,
            "process_started_at": started_at_iso,
            "process_ended_at": ended_at_iso,
            "duration_seconds": duration_seconds,
            "stdout": stdout,
            "stderr": stderr,
            "timeout_seconds": timeout_seconds,
            "error": str(exc),
            "set_path": str(files.set_path),
            "native_set_path": str(files.native_set_path),
            "ini_path": str(files.ini_path),
            "report_path_strategy": files.report_path_strategy,
            "mt5_report_value": files.mt5_report_value,
            "expected_native_report_paths": [str(path) for path in files.expected_native_report_paths],
            "generated_ini_shutdown_terminal_value": shutdown_value,
            "expected_report_path": str(files.report_path),
            "status": "PROCESS_FAILED",
        }
        files.log_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        record_attempt(
            test_id=test_id,
            task_name=task.name,
            run_status="PROCESS_FAILED",
            execution_mode="cli",
            run_kind=run_kind,
            parent_candidate_id=parent_candidate_id,
            split_id=split_id,
            log_path=str(files.log_path),
            set_path=str(files.set_path),
            ini_path=str(files.ini_path),
            command_line=render_mt5_command(command),
            expected_report_path=str(files.report_path),
            process_id=process.pid if process is not None else None,
            process_exit_code=process.returncode if process is not None else None,
            process_started_at=started_at_iso,
            process_ended_at=ended_at_iso,
            duration_seconds=duration_seconds,
            error=str(exc),
        )
        stored = build_stored_run(
            test_id=test_id,
            task=task,
            parsed_report=None,
            passed=False,
            rejection_reason="PROCESS_FAILED",
            raw_report_path="",
            parsed_report_path="",
            screenshot_path="",
            run_status="PROCESS_FAILED",
            execution_mode="cli",
            run_kind=run_kind,
            parent_candidate_id=parent_candidate_id,
            split_id=split_id,
        )
        store_run(stored)
        update_leaderboard_csv()
        update_summary_md()
        return CliRunResult(1, "PROCESS_FAILED", test_id, "", "", str(files.log_path), process.pid if process is not None else None, None, False)

    files.log_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if process.returncode not in (0, None):
        record_attempt(
            test_id=test_id,
            task_name=task.name,
            run_status="PROCESS_FAILED",
            execution_mode="cli",
            run_kind=run_kind,
            parent_candidate_id=parent_candidate_id,
            split_id=split_id,
            log_path=str(files.log_path),
            set_path=str(files.set_path),
            ini_path=str(files.ini_path),
            command_line=render_mt5_command(command),
            expected_report_path=str(files.report_path),
            process_id=process.pid,
            process_exit_code=process.returncode,
            process_started_at=started_at_iso,
            process_ended_at=ended_at_iso,
            duration_seconds=payload.get("duration_seconds"),
            error="MT5 process returned a non-zero exit code.",
        )
        stored = build_stored_run(
            test_id=test_id,
            task=task,
            parsed_report=None,
            passed=False,
            rejection_reason="PROCESS_FAILED",
            raw_report_path="",
            parsed_report_path="",
            screenshot_path="",
            run_status="PROCESS_FAILED",
            execution_mode="cli",
            run_kind=run_kind,
            parent_candidate_id=parent_candidate_id,
            split_id=split_id,
        )
        store_run(stored)
        update_leaderboard_csv()
        update_summary_md()
        return CliRunResult(1, "PROCESS_FAILED", test_id, "", "", str(files.log_path), process.pid, process.returncode, False)

    report_discovery = discover_report(
        files.report_path,
        parse_utc_iso(started_at_iso),
        config=config,
        explicit_expected_paths=native_report_paths,
    )
    payload["nearby_report_files"] = report_discovery.nearby_files
    payload["report_candidates"] = report_discovery.report_candidates
    payload["native_set_path"] = str(files.native_set_path)
    payload["report_path_strategy"] = files.report_path_strategy
    payload["mt5_report_value"] = files.mt5_report_value
    payload["expected_native_report_paths"] = [str(path) for path in files.expected_native_report_paths]
    if report_discovery.discovered_path is not None:
        payload["discovered_report_path"] = str(report_discovery.discovered_path)

    payload["tester_log_candidates"] = collect_tester_log_candidates(
        test_id=test_id,
        process_started_at=parse_utc_iso(started_at_iso),
        config=config,
    )
    payload["terminal_log_candidates"] = collect_terminal_log_candidates(
        test_id=test_id,
        process_started_at=parse_utc_iso(started_at_iso),
        config=config,
    )

    if report_discovery.discovered_path is None:
        payload["status"] = "REPORT_MISSING"
        files.log_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        record_attempt(
            test_id=test_id,
            task_name=task.name,
            run_status="REPORT_MISSING",
            execution_mode="cli",
            run_kind=run_kind,
            parent_candidate_id=parent_candidate_id,
            split_id=split_id,
            log_path=str(files.log_path),
            set_path=str(files.set_path),
            ini_path=str(files.ini_path),
            command_line=render_mt5_command(command),
            expected_report_path=str(files.report_path),
            process_id=process.pid,
            process_exit_code=process.returncode,
            process_started_at=started_at_iso,
            process_ended_at=ended_at_iso,
            duration_seconds=payload.get("duration_seconds"),
            error="MT5 process completed but no report was discovered.",
        )
        stored = build_stored_run(
            test_id=test_id,
            task=task,
            parsed_report=None,
            passed=False,
            rejection_reason="REPORT_MISSING",
            raw_report_path="",
            parsed_report_path="",
            screenshot_path="",
            run_status="REPORT_MISSING",
            execution_mode="cli",
            run_kind=run_kind,
            parent_candidate_id=parent_candidate_id,
            split_id=split_id,
        )
        store_run(stored)
        update_leaderboard_csv()
        update_summary_md()
        return CliRunResult(1, "REPORT_MISSING", test_id, "", "", str(files.log_path), process.pid, process.returncode, False)

    report_candidate = report_discovery.discovered_path
    payload["status"] = "REPORT_FOUND"
    artifact_report_copy_path = files.report_path.with_suffix(report_candidate.suffix or files.report_path.suffix)
    if report_candidate.resolve() != artifact_report_copy_path.resolve():
        shutil.copy2(report_candidate, artifact_report_copy_path)
    payload["copied_artifact_report_path"] = str(artifact_report_copy_path)
    files.log_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    raw_report_path = str(artifact_report_copy_path)
    record_attempt(
        test_id=test_id,
        task_name=task.name,
        run_status="REPORT_FOUND",
        execution_mode="cli",
        run_kind=run_kind,
        parent_candidate_id=parent_candidate_id,
        split_id=split_id,
        raw_report_path=raw_report_path,
        log_path=str(files.log_path),
        set_path=str(files.set_path),
        ini_path=str(files.ini_path),
        command_line=render_mt5_command(command),
        expected_report_path=str(files.report_path),
        discovered_report_path=str(report_candidate),
        process_id=process.pid,
        process_exit_code=process.returncode,
        process_started_at=started_at_iso,
        process_ended_at=ended_at_iso,
        duration_seconds=payload.get("duration_seconds"),
    )

    try:
        parsed_report = parse_report_file(artifact_report_copy_path)
        parsed_report_path = store_parsed_report_json(test_id, parsed_report)
        payload["parsed_metrics"] = parsed_report_to_payload(parsed_report)
        files.log_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception as exc:
        record_attempt(
            test_id=test_id,
            task_name=task.name,
            run_status="PARSE_FAILED",
            execution_mode="cli",
            run_kind=run_kind,
            parent_candidate_id=parent_candidate_id,
            split_id=split_id,
            raw_report_path=raw_report_path,
            log_path=str(files.log_path),
            set_path=str(files.set_path),
            ini_path=str(files.ini_path),
            command_line=render_mt5_command(command),
            expected_report_path=str(files.report_path),
            discovered_report_path=str(report_candidate),
            process_id=process.pid,
            process_exit_code=process.returncode,
            process_started_at=started_at_iso,
            process_ended_at=ended_at_iso,
            duration_seconds=payload.get("duration_seconds"),
            parsed_metrics_json={},
            decision_reason="MT5 report parsing raised an exception.",
            per_rule_results=[],
            error=str(exc),
        )
        stored = build_stored_run(
            test_id=test_id,
            task=task,
            parsed_report=None,
            passed=False,
            rejection_reason="PARSE_FAILED",
            decision_reason="MT5 report parsing raised an exception.",
            per_rule_results=[],
            raw_report_path=raw_report_path,
            parsed_report_path="",
            screenshot_path="",
            run_status="PARSE_FAILED",
            execution_mode="cli",
            run_kind=run_kind,
            parent_candidate_id=parent_candidate_id,
            split_id=split_id,
        )
        store_run(stored)
        update_leaderboard_csv()
        update_summary_md()
        return CliRunResult(1, "PARSE_FAILED", test_id, raw_report_path, "", str(files.log_path), process.pid, process.returncode, False)

    evaluator = acceptance_evaluator or evaluate_acceptance
    evaluation = coerce_acceptance_evaluation(evaluator(parsed_report, task.acceptance))
    payload["decision_reason"] = evaluation.decision_reason
    payload["per_rule_results"] = evaluation.per_rule_results
    files.log_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    record_attempt(
        test_id=test_id,
        task_name=task.name,
        run_status=evaluation.status,
        execution_mode="cli",
        run_kind=run_kind,
        parent_candidate_id=parent_candidate_id,
        split_id=split_id,
        raw_report_path=raw_report_path,
        parsed_report_path=str(parsed_report_path),
        log_path=str(files.log_path),
        set_path=str(files.set_path),
        ini_path=str(files.ini_path),
        command_line=render_mt5_command(command),
        expected_report_path=str(files.report_path),
        discovered_report_path=str(report_candidate),
        process_id=process.pid,
        process_exit_code=process.returncode,
        process_started_at=started_at_iso,
        process_ended_at=ended_at_iso,
        duration_seconds=payload.get("duration_seconds"),
        parsed_metrics_json=payload["parsed_metrics"],
        decision_reason=evaluation.decision_reason,
        per_rule_results=evaluation.per_rule_results,
        error=evaluation.rejection_reason,
    )
    stored = build_stored_run(
        test_id=test_id,
        task=task,
        parsed_report=parsed_report,
        passed=evaluation.passed,
        rejection_reason=evaluation.rejection_reason,
        decision_reason=evaluation.decision_reason,
        per_rule_results=evaluation.per_rule_results,
        raw_report_path=raw_report_path,
        parsed_report_path=str(parsed_report_path),
        screenshot_path="",
        run_status=evaluation.status,
        execution_mode="cli",
        run_kind=run_kind,
        parent_candidate_id=parent_candidate_id,
        split_id=split_id,
    )
    store_run(stored)
    update_leaderboard_csv()
    update_summary_md()
    return CliRunResult(
        0 if evaluation.passed else 1,
        evaluation.status,
        test_id,
        raw_report_path,
        str(parsed_report_path),
        str(files.log_path),
        process.pid,
        process.returncode,
        False,
    )


def run_generate_mt5_files_command(task_path: str) -> int:
    try:
        resolved_task_path = resolve_task_path(task_path)
        task = load_task(resolved_task_path)
        files = generate_mt5_files(resolved_task_path)
        record_attempt(
            test_id=files.test_id,
            task_name=task.name,
            run_status="FILES_GENERATED",
            execution_mode="cli",
            run_kind="full_period",
            parent_candidate_id="",
            split_id="",
            set_path=str(files.set_path),
            ini_path=str(files.ini_path),
            log_path=str(files.log_path),
            expected_report_path=str(files.report_path),
        )
    except Exception as exc:
        print(str(exc))
        return 1

    print(render_generated_files_summary(files))
    return 0


def run_prepare_mt5_files_command(task_path: str) -> int:
    try:
        resolved_task_path = resolve_task_path(task_path)
        files = generate_mt5_files(resolved_task_path)
    except Exception as exc:
        print(str(exc))
        return 1
    print(render_generated_files_summary(files))
    print(json.dumps(
        {
            "test_id": files.test_id,
            "set_path": str(files.set_path),
            "native_set_path": str(files.native_set_path),
            "ini_path": str(files.ini_path),
            "report_path_strategy": files.report_path_strategy,
            "mt5_report_value": files.mt5_report_value,
            "expected_native_report_paths": [str(path) for path in files.expected_native_report_paths],
        },
        indent=2,
        ensure_ascii=True,
    ))
    return 0


def run_show_task_command(task_path: str) -> int:
    try:
        task = load_task(resolve_task_path(task_path))
    except Exception as exc:
        print(str(exc))
        return 1

    print(render_task_summary(task))
    return 0


def run_create_smoke_task_command(
    *,
    test_id: str,
    ea: str,
    symbol: str,
    timeframe: str,
    period_from: str,
    period_to: str,
    deposit: float,
) -> int:
    try:
        payload = build_smoke_task_payload(
            test_id=test_id,
            ea=ea,
            symbol=symbol,
            timeframe=timeframe,
            period_from=period_from,
            period_to=period_to,
            deposit=deposit,
        )
        task = validate_task_payload(payload)
        output_path = write_generated_task(task_to_payload(task))
    except Exception as exc:
        print(str(exc))
        return 1

    print(f"task path: {output_path}")
    return 0


def run_print_ini_command(task_path: str) -> int:
    try:
        files, text = load_generated_file_text(task_path, "ini")
    except Exception as exc:
        print(str(exc))
        return 1
    print("native tester set mode: true")
    print(f"native set path: {files.native_set_path}")
    print(f"report path strategy: {files.report_path_strategy}")
    print(f"Report=: {files.mt5_report_value}")
    print(text, end="")
    return 0


def run_print_set_command(task_path: str) -> int:
    try:
        _, text = load_generated_file_text(task_path, "set")
    except Exception as exc:
        print(str(exc))
        return 1
    print(text, end="")
    return 0


def run_locate_ea_command(ea_name: str) -> int:
    payload = locate_ea_payload(ea_name)
    print(f"ea: {ea_name}")
    print(f"ex5 exists: {payload['ex5_exists']}")
    print(f"ex5 newer than mq5: {payload['ex5_newer_than_mq5']}")
    print(f"recommended Expert=: {payload['recommended_expert_value']}")
    for warning in payload.get("warnings", []):
        print(f"warning: {warning}")
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0 if payload["ex5_exists"] else 1


def run_compile_ea_command(ea_name: str) -> int:
    payload = compile_ea_payload(ea_name)
    print(f"ea: {ea_name}")
    print(f"metaeditor: {payload.get('metaeditor_path', '') or '<missing>'}")
    print(f"compile log: {payload.get('compile_log_path', '')}")
    for warning in payload.get("warnings", []):
        print(f"warning: {warning}")
    for instruction in payload.get("manual_instructions", []):
        print(f"instruction: {instruction}")
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0 if payload.get("ok") else 1


def build_preflight_payload(task_path: str) -> dict[str, Any]:
    config = load_config()
    resolved_task_path = resolve_task_path(task_path)
    task = load_task(resolved_task_path)
    files = generate_mt5_files(resolved_task_path)
    locate = locate_ea_payload(task.ea, config)
    resolved_expert_value, _ = infer_expert_value(task.ea, config)
    symbol = symbol_preflight_payload(task.symbol, config)
    report_writable, report_detail = verify_report_targets_writable(files.expected_native_report_paths)
    terminal_path = Path(config.terminal_path).expanduser() if config.terminal_path else Path()
    warnings = build_preflight_warnings(task) + locate.get("warnings", [])
    if symbol.get("warning"):
        warnings.append(str(symbol["warning"]))
    if resolved_expert_value != task.ea:
        warnings.append(f"Expert= could be improved from '{task.ea}' to '{resolved_expert_value}'.")
    payload = {
        "ok": bool(
            config.terminal_path
            and terminal_path.exists()
            and report_writable
            and locate["ex5_exists"]
            and (locate["ex5_newer_than_mq5"] or not locate["found_mq5"])
            and (symbol["exact_match"] or symbol["skipped"])
        ),
        "task_path": str(resolved_task_path),
        "resolved_expert_value": resolved_expert_value,
        "checks": {
            "terminal_path_ok": bool(config.terminal_path and terminal_path.exists()),
            "report_path_writable": report_writable,
            "ea_ex5_exists": locate["ex5_exists"],
            "ea_ex5_fresh": locate["ex5_newer_than_mq5"] or not locate["found_mq5"],
            "symbol_exact_match": symbol["exact_match"] or symbol["skipped"],
        },
        "report_path_detail": report_detail,
        "ea_locate": locate,
        "symbol_preflight": symbol,
        "generated_ini_path": str(files.ini_path),
        "generated_set_path": str(files.set_path),
        "native_set_path": str(files.native_set_path),
        "report_path_strategy": files.report_path_strategy,
        "mt5_report_value": files.mt5_report_value,
        "expected_native_report_paths": [str(path) for path in files.expected_native_report_paths],
        "expected_report_path": str(files.report_path),
        "warnings": warnings,
    }
    return payload


def run_preflight_task_command(task_path: str) -> int:
    try:
        payload = build_preflight_payload(task_path)
    except Exception as exc:
        print(str(exc))
        return 1
    print(render_preflight_summary(payload))
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0 if payload["ok"] else 1


def run_fix_smoke_task_command(task_path: str, in_place: bool) -> int:
    try:
        resolved_task_path = resolve_task_path(task_path)
        task = load_task(resolved_task_path)
        resolved_expert_value, locate = infer_expert_value(task.ea, load_config())
        if resolved_expert_value == task.ea:
            print("No better Expert= value could be inferred.")
            print(json.dumps({"ok": False, "reason": "NO_CHANGE", "task_path": str(resolved_task_path)}, ensure_ascii=True))
            return 1

        payload = task_to_payload(task)
        if not in_place:
            payload["test_id"] = f"{task.test_id}-FIXED" if task.test_id else "FIXED"
            payload["name"] = f"{task.name}-fixed"
        payload["ea"] = resolved_expert_value
        output_path = resolved_task_path if in_place else make_generated_task_path(str(payload["test_id"]))
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception as exc:
        print(str(exc))
        return 1

    next_task_path = str(output_path)
    print(f"patched task: {next_task_path}")
    print(f"next command: python -m mt5_research_agent smoke-cli {next_task_path}")
    print(json.dumps({
        "ok": True,
        "task_path": next_task_path,
        "resolved_expert_value": resolved_expert_value,
        "ea_locate": locate,
    }, indent=2, ensure_ascii=True))
    return 0


def run_terminal_info_command() -> int:
    print(json.dumps(describe_terminal_info(), indent=2, ensure_ascii=True))
    return 0


def run_print_terminal_folders_command() -> int:
    payload = build_terminal_folders_payload()
    print(f"terminal_path: {payload['terminal_path'] or '<missing>'}")
    print(f"portable_mode: {load_config().portable_mode}")
    print("terminal_data_folders:")
    for value in payload["terminal_data_folders"]:
        print(f"  {value}")
    print("experts_folders:")
    for value in payload["experts_folders"]:
        print(f"  {value}")
    print("tester_data_folders:")
    for value in payload["tester_data_folders"]:
        print(f"  {value}")
    print("logs_folders:")
    for value in payload["logs_folders"]:
        print(f"  {value}")
    print("tester_log_folders:")
    for value in payload["tester_log_folders"]:
        print(f"  {value}")
    print("likely_report_folders:")
    for value in payload["likely_report_folders"]:
        print(f"  {value}")
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0


def run_find_reports_command(since_minutes: int) -> int:
    payload = build_find_reports_payload(since_minutes)
    print(f"since_minutes: {since_minutes}")
    print("newest report candidates:")
    for item in payload["candidates"][:10]:
        print(
            f"  {item['path']} | size={item['size_bytes']} | modified_at={item['modified_at']} | likely_test_id_match={item['likely_test_id_match']}"
        )
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0 if payload["candidates"] else 1


def run_mt5_process_status_command() -> int:
    payload = mt5_process_status_payload()
    print(render_mt5_process_status(payload))
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0


def run_stop_mt5_command(confirm: bool, all_processes: bool) -> int:
    payload = stop_mt5_payload(confirm=confirm, all_processes=all_processes)
    print(render_stop_mt5_payload(payload))
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0 if (not confirm or payload.get("wait_succeeded", True)) else 1


def run_inspect_run_command(test_id: str) -> int:
    attempt = fetch_latest_run_attempt(test_id)
    if attempt is None:
        print(f"No attempts found for test_id: {test_id}")
        return 1
    log_payload = read_log_payload(str(attempt.get("log_path", ""))) or {}
    raw_report_path = str(attempt.get("raw_report_path", "") or log_payload.get("copied_artifact_report_path", ""))
    if not log_payload.get("parsed_metrics") and raw_report_path and Path(raw_report_path).exists():
        try:
            parsed_report = parse_report_file(raw_report_path)
            log_payload["parsed_metrics"] = parsed_report_to_payload(parsed_report)
            task_payload = log_payload.get("task")
            if isinstance(task_payload, dict):
                acceptance = validate_task_payload(task_payload).acceptance
                evaluation = evaluate_acceptance(parsed_report, acceptance)
                log_payload["decision_reason"] = evaluation.decision_reason
                log_payload["per_rule_results"] = evaluation.per_rule_results
        except Exception:
            pass
    print(render_attempt_summary(attempt, log_payload))
    return 0


def run_agent_run_task_command(task_path: str, timeout_seconds: int) -> int:
    result = run_task_cli(task_path, timeout_seconds)
    payload = {
        "ok": result.exit_code == 0,
        "test_id": result.test_id,
        "status": result.status,
        "raw_report_path": result.raw_report_path,
        "parsed_report_path": result.parsed_report_path,
        "log_path": result.log_path,
        "process_id": result.process_id,
        "process_exit_code": result.process_exit_code,
    }
    print(json.dumps(payload, ensure_ascii=True))
    return result.exit_code


def run_test_report_strategies_command(task_path: str, timeout_seconds: int) -> int:
    winning_strategy = ""
    final_status = "REPORT_MISSING"
    stop_statuses = {"PASS", "FAIL", "PARSE_FAILED"}
    for strategy in (
        "terminal_relative_reports",
        "terminal_root_stem",
        "terminal_mql5_files",
        "artifacts_absolute_current",
    ):
        print(f"strategy: {strategy}")
        result = run_task_cli(task_path, timeout_seconds, report_path_strategy=strategy)
        print(f"status: {result.status}")
        print(f"log: {result.log_path}")
        final_status = result.status
        if result.status in stop_statuses:
            winning_strategy = strategy
            break
        if result.status != "REPORT_MISSING":
            break

    if winning_strategy:
        print(f"winning strategy: {winning_strategy}")
        return 0
    return 0 if final_status in stop_statuses else 1


def run_agent_task_status_command(test_id: str) -> int:
    payload = build_task_status_payload(test_id)
    print(json.dumps(payload, ensure_ascii=True))
    return 0 if payload.get("ok") else 1


def run_agent_latest_results_command() -> int:
    rows = fetch_runs()[:10]
    payload = {
        "ok": True,
        "results": [
            {
                "test_id": row["test_id"],
                "run_status": row["run_status"],
                "execution_mode": row["execution_mode"],
                "task_name": row["task_name"],
                "symbol": row["symbol"],
                "timeframe": row["timeframe"],
                "created_at": row["created_at"],
                "rejection_reason": row["rejection_reason"],
            }
            for row in rows
        ],
    }
    print(json.dumps(payload, ensure_ascii=True))
    return 0


def run_smoke_cli_command(
    task_path: str,
    run: bool,
    timeout_seconds: int,
    allow_stop_existing_terminal: bool = False,
    keep_terminal_open: bool = False,
    report_path_strategy: str | None = None,
) -> int:
    try:
        resolved_task_path = resolve_task_path(task_path)
        task = load_task(resolved_task_path)
        files = generate_mt5_files(
            resolved_task_path,
            keep_terminal_open=keep_terminal_open,
            report_path_strategy=report_path_strategy,
        )
        config = load_config()
        command = build_mt5_command(config, files.ini_path)
    except Exception as exc:
        print(str(exc))
        return 1

    print(render_task_summary(task))
    print(f"task path: {resolved_task_path}")
    print(f"set: {files.set_path}")
    print(f"native set: {files.native_set_path}")
    print(f"ini: {files.ini_path}")
    print(f"expected report: {files.report_path}")
    print(f"report path strategy: {files.report_path_strategy}")
    print(f"Report=: {files.mt5_report_value}")
    print(f"ShutdownTerminal: {read_ini_shutdown_value(files.ini_path) or '<unknown>'}")
    print(f"command: {render_mt5_command(command) if command else '<terminal_path not configured>'}")
    for warning in build_preflight_warnings(task):
        print(f"warning: {warning}")

    if not run:
        print("Dry smoke complete. Re-run with --run to launch MT5 in background CLI mode.")
        return 0

    result = run_task_cli(
        str(resolved_task_path),
        timeout_seconds,
        allow_stop_existing_terminal=allow_stop_existing_terminal,
        keep_terminal_open=keep_terminal_open,
        report_path_strategy=report_path_strategy,
    )
    print(f"status: {result.status}")
    if result.raw_report_path:
        print(f"raw report: {result.raw_report_path}")
    if result.parsed_report_path:
        print(f"parsed report: {result.parsed_report_path}")
    print(f"log: {result.log_path}")
    if result.status == "TERMINAL_ALREADY_RUNNING":
        print("next command: python -m mt5_research_agent stop-mt5 --confirm")
    if task.test_id:
        attempt = fetch_latest_run_attempt(task.test_id)
        diagnosis = likely_diagnosis(attempt or {}, read_log_payload(result.log_path))
        if diagnosis:
            print(f"warning: {diagnosis}")
    return result.exit_code
