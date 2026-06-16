from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from mt5_research_agent.config import AppConfig, load_config


REPORT_EXTENSIONS = {".htm", ".html", ".xml", ".csv"}
TESTER_LOG_EXTENSIONS = {".log", ".txt", ".journal"}


def artifacts_logs_dir(config: AppConfig | None = None) -> Path:
    current = config or load_config()
    path = Path(current.artifacts_dir).resolve() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def utc_now_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def describe_file(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "name": path.name,
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }


def read_text_with_fallbacks(path: Path) -> str:
    for encoding in ("utf-8", "utf-16", "utf-16-le", "utf-16-be"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def get_experts_folder_candidates(config: AppConfig | None = None) -> list[Path]:
    current = config or load_config()
    candidates: list[Path] = []
    if current.terminal_path:
        terminal_path = Path(current.terminal_path).expanduser()
        candidates.append(terminal_path.parent / "MQL5" / "Experts")

    for root in get_terminal_data_folder_candidates(current):
        candidates.append(root / "MQL5" / "Experts")

    return unique_paths(candidates)


def unique_paths(paths: Iterable[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in paths:
        key = str(candidate.resolve()) if candidate.exists() else str(candidate)
        if key not in seen:
            unique.append(candidate)
            seen.add(key)
    return unique


def get_terminal_data_folder_candidates(config: AppConfig | None = None) -> list[Path]:
    current = config or load_config()
    candidates: list[Path] = []
    if current.terminal_path:
        terminal_dir = Path(current.terminal_path).expanduser().parent
        if current.portable_mode:
            candidates.append(terminal_dir)

    for env_name in ("APPDATA", "LOCALAPPDATA"):
        root = Path(os.environ.get(env_name, "")) / "MetaQuotes" / "Terminal"
        if root.exists():
            candidates.extend(path for path in root.iterdir() if path.is_dir())

    return unique_paths(candidates)


def get_likely_report_folders(config: AppConfig | None = None) -> list[Path]:
    candidates: list[Path] = []
    for root in get_terminal_data_folder_candidates(config):
        candidates.extend(
            [
                root,
                root / "reports",
                root / "Reports",
                root / "tester",
                root / "Tester",
                root / "tester" / "cache",
                root / "Tester" / "cache",
                root / "tester" / "reports",
                root / "Tester" / "reports",
            ]
        )
    for root in get_metaquotes_tester_folder_candidates():
        candidates.extend(
            [
                root,
                root / "reports",
                root / "Reports",
                root / "cache",
            ]
        )
    return unique_paths(candidates)


def get_tester_log_folders(config: AppConfig | None = None) -> list[Path]:
    candidates: list[Path] = []
    for root in get_terminal_data_folder_candidates(config):
        candidates.extend(
            [
                root / "logs",
                root / "Logs",
                root / "tester",
                root / "Tester",
                root / "tester" / "logs",
                root / "Tester" / "logs",
                root / "tester" / "cache",
                root / "Tester" / "cache",
                root / "Agent",
                root / "Agents",
            ]
        )
        for child in root.iterdir() if root.exists() else []:
            name = child.name.casefold()
            if not child.is_dir():
                continue
            if any(token in name for token in ("tester", "agent", "log", "journal")):
                candidates.append(child)
    for root in get_metaquotes_tester_folder_candidates():
        candidates.extend(
            [
                root,
                root / "logs",
                root / "Logs",
            ]
        )
        for child in root.iterdir() if root.exists() else []:
            if child.is_dir():
                candidates.append(child)
                candidates.append(child / "logs")
    return unique_paths(candidates)


def get_metaquotes_tester_folder_candidates() -> list[Path]:
    candidates: list[Path] = []
    for env_name in ("APPDATA", "LOCALAPPDATA"):
        root = Path(os.environ.get(env_name, "")) / "MetaQuotes" / "Tester"
        if root.exists():
            candidates.extend(path for path in root.iterdir() if path.is_dir())
    return unique_paths(candidates)


def describe_terminal_info(config: AppConfig | None = None) -> dict[str, Any]:
    current = config or load_config()
    return {
        "terminal_path": current.terminal_path,
        "portable_mode": current.portable_mode,
        "artifacts_dir": current.artifacts_dir,
        "results_dir": current.results_dir,
        "shutdown_terminal_after_run": current.shutdown_terminal_after_run,
        "terminal_data_folder_candidates": [str(path) for path in get_terminal_data_folder_candidates(current)],
        "tester_data_folder_candidates": [str(path) for path in get_metaquotes_tester_folder_candidates()],
        "experts_folder_candidates": [str(path) for path in get_experts_folder_candidates(current)],
        "likely_report_folders": [str(path) for path in get_likely_report_folders(current)],
        "tester_log_folders": [str(path) for path in get_tester_log_folders(current)],
        "instructions": "The compiled .ex5 EA must exist in an MQL5/Experts folder visible to this MT5 terminal.",
    }


def _normalize_ea_name(ea_name: str) -> str:
    return ea_name.strip().removesuffix(".mq5").removesuffix(".ex5")


def _relative_expert_value(file_path: Path, experts_root: Path) -> str:
    relative = file_path.relative_to(experts_root)
    return str(relative.with_suffix("")).replace("/", "\\")


def locate_ea_payload(ea_name: str, config: AppConfig | None = None) -> dict[str, Any]:
    current = config or load_config()
    normalized = _normalize_ea_name(ea_name)
    found_mq5: list[dict[str, Any]] = []
    found_ex5: list[dict[str, Any]] = []
    recommended_expert_value = ea_name

    for experts_root in get_experts_folder_candidates(current):
        if not experts_root.exists():
            continue
        for match in experts_root.rglob(f"{normalized}.mq5"):
            found_mq5.append({**describe_file(match), "experts_root": str(experts_root)})
        for match in experts_root.rglob(f"{normalized}.ex5"):
            found_ex5.append(
                {
                    **describe_file(match),
                    "experts_root": str(experts_root),
                    "recommended_expert_value": _relative_expert_value(match, experts_root),
                }
            )

    found_mq5.sort(key=lambda item: item["modified_at"], reverse=True)
    found_ex5.sort(key=lambda item: item["modified_at"], reverse=True)

    ex5_exists = bool(found_ex5)
    ex5_newer_than_mq5 = False
    if found_ex5:
        recommended_expert_value = str(found_ex5[0]["recommended_expert_value"])
    if found_mq5 and found_ex5:
        ex5_newer_than_mq5 = found_ex5[0]["modified_at"] >= found_mq5[0]["modified_at"]

    warnings: list[str] = []
    if found_mq5 and not found_ex5:
        warnings.append("Source .mq5 exists but compiled .ex5 is missing.")
    if found_ex5 and found_mq5 and not ex5_newer_than_mq5:
        warnings.append("Compiled .ex5 is older than the newest .mq5 source.")
    if not found_mq5 and not found_ex5:
        warnings.append("No matching .mq5 or .ex5 was found in the likely Experts folders.")

    return {
        "ea_name": ea_name,
        "normalized_name": normalized,
        "found_mq5": found_mq5,
        "found_ex5": found_ex5,
        "ex5_exists": ex5_exists,
        "ex5_newer_than_mq5": ex5_newer_than_mq5,
        "recommended_expert_value": recommended_expert_value,
        "warnings": warnings,
    }


def infer_expert_value(task_ea: str, config: AppConfig | None = None) -> tuple[str, dict[str, Any]]:
    if "\\" in task_ea or "/" in task_ea:
        return task_ea, locate_ea_payload(task_ea, config)
    payload = locate_ea_payload(task_ea, config)
    return str(payload.get("recommended_expert_value") or task_ea), payload


def find_metaeditor_path(config: AppConfig | None = None) -> Path | None:
    current = config or load_config()
    if not current.terminal_path:
        return None
    terminal_dir = Path(current.terminal_path).expanduser().parent
    for candidate_name in ("MetaEditor64.exe", "metaeditor64.exe", "MetaEditor.exe", "metaeditor.exe"):
        candidate = terminal_dir / candidate_name
        if candidate.exists():
            return candidate
    return None


def compile_ea_payload(ea_name: str, config: AppConfig | None = None) -> dict[str, Any]:
    current = config or load_config()
    locate = locate_ea_payload(ea_name, current)
    metaeditor_path = find_metaeditor_path(current)
    log_dir = artifacts_logs_dir(current)
    compile_log = log_dir / f"compile_{_normalize_ea_name(ea_name)}_{utc_now_timestamp()}.log"
    record_path = log_dir / f"compile_{_normalize_ea_name(ea_name)}_{utc_now_timestamp()}.json"

    if metaeditor_path is None:
        payload = {
            "ok": False,
            "ea_name": ea_name,
            "metaeditor_path": "",
            "compile_log_path": str(compile_log),
            "record_path": str(record_path),
            "warnings": ["MetaEditor executable was not found near the configured terminal_path."],
            "manual_instructions": [
                "Open MetaEditor64.exe manually from the MT5 installation folder.",
                f"Open {_normalize_ea_name(ea_name)}.mq5 and press F7 to compile.",
            ],
        }
        record_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    if not locate["found_mq5"]:
        payload = {
            "ok": False,
            "ea_name": ea_name,
            "metaeditor_path": str(metaeditor_path),
            "compile_log_path": str(compile_log),
            "record_path": str(record_path),
            "warnings": ["No .mq5 source file was found in the likely Experts folders."],
            "manual_instructions": [
                "Place the .mq5 source in an MT5 MQL5\\Experts folder visible to this terminal.",
                "Then re-run compile-ea or compile manually in MetaEditor.",
            ],
        }
        record_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    source_path = Path(locate["found_mq5"][0]["path"])
    command = [
        str(metaeditor_path),
        f"/compile:{source_path}",
        f"/log:{compile_log}",
    ]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except Exception as exc:
        payload = {
            "ok": False,
            "ea_name": ea_name,
            "metaeditor_path": str(metaeditor_path),
            "source_path": str(source_path),
            "compile_log_path": str(compile_log),
            "record_path": str(record_path),
            "warnings": [str(exc)],
            "manual_instructions": [
                f"Run MetaEditor manually: {metaeditor_path}",
                f"Open {source_path} and press F7 to compile.",
            ],
        }
        record_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    refreshed = locate_ea_payload(ea_name, current)
    payload = {
        "ok": completed.returncode == 0 and refreshed["ex5_exists"],
        "ea_name": ea_name,
        "metaeditor_path": str(metaeditor_path),
        "source_path": str(source_path),
        "compile_log_path": str(compile_log),
        "record_path": str(record_path),
        "command_line": subprocess.list2cmdline(command),
        "process_exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "warnings": refreshed["warnings"],
        "manual_instructions": [] if completed.returncode == 0 else [
            f"Run MetaEditor manually: {metaeditor_path}",
            f"Open {source_path} and press F7 to compile.",
        ],
    }
    record_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def symbol_preflight_payload(symbol: str, config: AppConfig | None = None) -> dict[str, Any]:
    current = config or load_config()
    if importlib.util.find_spec("MetaTrader5") is None:
        return {
            "ok": False,
            "skipped": True,
            "warning": "MetaTrader5 package is not installed. Symbol preflight skipped.",
            "exact_match": False,
            "alternatives": [],
        }

    import MetaTrader5 as mt5

    initialized = mt5.initialize(path=current.terminal_path or None)
    if not initialized:
        return {
            "ok": False,
            "skipped": True,
            "warning": f"MetaTrader5.initialize failed: {mt5.last_error()}",
            "exact_match": False,
            "alternatives": [],
        }

    try:
        exact = mt5.symbol_info(symbol) is not None
        alternatives: list[str] = []
        for entry in mt5.symbols_get() or []:
            name = getattr(entry, "name", "")
            folded = name.casefold()
            if symbol.casefold() in folded or any(token in folded for token in ("us30", "us30.cash", "us30cash", "dji", "dow")):
                alternatives.append(name)
        return {
            "ok": exact,
            "skipped": False,
            "warning": "",
            "exact_match": exact,
            "alternatives": sorted(dict.fromkeys(alternatives)),
        }
    finally:
        mt5.shutdown()


def terminal_log_roots(config: AppConfig | None = None) -> list[Path]:
    current = config or load_config()
    roots: list[Path] = []
    if current.terminal_path:
        roots.append(Path(current.terminal_path).expanduser().parent / "logs")
    for root in get_terminal_data_folder_candidates(current):
        roots.append(root / "logs")
    return unique_paths(roots)


def collect_terminal_log_candidates(
    *,
    test_id: str,
    process_started_at: datetime | None,
    config: AppConfig | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    current = config or load_config()
    log_dir = artifacts_logs_dir(current)
    candidates: list[dict[str, Any]] = []
    threshold = process_started_at - timedelta(seconds=5) if process_started_at else None
    for root in terminal_log_roots(current):
        if not root.exists():
            continue
        for path in sorted(root.glob("*.log"), key=lambda item: item.stat().st_mtime, reverse=True):
            modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if threshold is not None and modified_at < threshold:
                continue
            text = read_text_with_fallbacks(path)
            lines = text.splitlines()
            snippet_lines = lines[-20:]
            snippet_path = log_dir / f"{test_id}_terminallog_{path.stem}_{utc_now_timestamp()}.txt"
            snippet_path.write_text("\n".join(snippet_lines), encoding="utf-8")
            candidates.append(
                {
                    **describe_file(path),
                    "snippet_path": str(snippet_path),
                    "snippet_preview": "\n".join(snippet_lines[-5:]),
                }
            )
            if len(candidates) >= limit:
                return candidates
    return candidates


def collect_tester_log_candidates(
    *,
    test_id: str,
    process_started_at: datetime | None,
    config: AppConfig | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    current = config or load_config()
    log_dir = artifacts_logs_dir(current)
    candidates: list[dict[str, Any]] = []
    threshold = process_started_at - timedelta(seconds=5) if process_started_at else None
    for root in get_tester_log_folders(current):
        if not root.exists():
            continue
        for path in sorted(root.rglob("*"), key=lambda item: item.stat().st_mtime, reverse=True):
            if not path.is_file() or path.suffix.casefold() not in TESTER_LOG_EXTENSIONS:
                continue
            modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if threshold is not None and modified_at < threshold:
                continue
            text = read_text_with_fallbacks(path)
            lines = text.splitlines()
            snippet_lines = lines[-30:]
            snippet_path = log_dir / f"{test_id}_testerlog_{path.stem}_{utc_now_timestamp()}.txt"
            snippet_path.write_text("\n".join(snippet_lines), encoding="utf-8")
            candidates.append(
                {
                    **describe_file(path),
                    "snippet_path": str(snippet_path),
                    "snippet_preview": "\n".join(snippet_lines[-8:]),
                }
            )
            if len(candidates) >= limit:
                return candidates
    return candidates
