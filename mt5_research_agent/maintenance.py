"""Maintenance and convenience commands.

- ``export-bundle``: zip the artifacts for one run or research request for sharing.
- ``clean-artifacts --safe``: remove only fully regeneratable scaffolding
  (generated .set / .ini files). Reports, parsed reports, logs, the results
  database, leaderboards, summaries, and the EA Lab are always preserved, in
  line with the safety rule to never hide or delete diagnostics.
- ``config-wizard``: detect the MT5 terminal and write/update config.json
  without clobbering existing values.
"""

from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mt5_research_agent.config import AppConfig, load_config, resolve_config_path
from mt5_research_agent.mt5_diagnostics import (
    find_metaeditor_path,
    get_experts_folder_candidates,
    get_metaquotes_tester_folder_candidates,
    get_terminal_data_folder_candidates,
)
from mt5_research_agent.result_store import fetch_latest_run_attempt, fetch_run, get_results_dir


# Subdirectories under artifacts/ that are pure MT5 input scaffolding and can be
# safely regenerated from the stored task JSON files. Never list reports, logs,
# parsed_reports, or ea_lab here.
SAFE_REMOVABLE_SUBDIRS = ("generated_sets", "generated_ini")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def bundles_dir() -> Path:
    path = get_results_dir() / "bundles"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _collect_run_files(test_id: str) -> list[Path]:
    files: list[Path] = []
    run_row = fetch_run(test_id)
    attempt = fetch_latest_run_attempt(test_id)
    for source in (run_row or {}, attempt or {}):
        for key in (
            "raw_report_path",
            "parsed_report_path",
            "log_path",
            "set_path",
            "ini_path",
        ):
            value = source.get(key)
            if value:
                path = Path(str(value))
                if path.exists() and path not in files:
                    files.append(path)
    return files


def _collect_request_files(slug: str) -> list[Path]:
    config = load_config()
    artifacts = Path(config.artifacts_dir).resolve()
    results = get_results_dir()
    candidates = [
        results / f"research_{slug}.md",
        results / f"final_report_{slug}.md",
        results / f"split_validation_{slug}_split_validation.md",
        artifacts / "research_plans" / slug,
    ]
    files: list[Path] = []
    for candidate in candidates:
        if candidate.is_dir():
            files.extend(p for p in candidate.rglob("*") if p.is_file())
        elif candidate.exists():
            files.append(candidate)
    return files


def export_bundle(identifier: str) -> tuple[Path, int]:
    files = _collect_run_files(identifier)
    kind = "run"
    if not files:
        files = _collect_request_files(identifier)
        kind = "request"

    output_path = bundles_dir() / f"{kind}_{identifier}_{_stamp()}.zip"
    written = 0
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            try:
                archive.write(path, arcname=path.name)
                written += 1
            except OSError:
                continue
        manifest = {
            "identifier": identifier,
            "kind": kind,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "files": [str(path) for path in files],
        }
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
    return output_path, written


def run_export_bundle_command(identifier: str) -> int:
    try:
        output_path, written = export_bundle(identifier)
    except Exception as exc:
        print(str(exc))
        return 1
    print(f"bundle: {output_path}")
    print(f"files included: {written}")
    if written == 0:
        print("warning: no matching run or request files were found for this identifier.")
        return 1
    return 0


def plan_clean_artifacts() -> list[Path]:
    config = load_config()
    artifacts = Path(config.artifacts_dir).resolve()
    removable: list[Path] = []
    for subdir in SAFE_REMOVABLE_SUBDIRS:
        directory = artifacts / subdir
        if not directory.exists():
            continue
        removable.extend(p for p in directory.rglob("*") if p.is_file())
    return removable


def run_clean_artifacts_command(safe: bool) -> int:
    removable = plan_clean_artifacts()
    if not safe:
        print("clean-artifacts preview (no files removed). Re-run with --safe to delete.")
        print(f"regeneratable scaffolding files: {len(removable)}")
        for path in removable[:20]:
            print(f"  {path}")
        print("Reports, parsed reports, logs, results DB, and EA Lab are always preserved.")
        return 0

    removed = 0
    for path in removable:
        try:
            path.unlink()
            removed += 1
        except OSError:
            continue
    print(f"removed regeneratable scaffolding files: {removed}")
    print("Reports, parsed reports, logs, results DB, and EA Lab were preserved.")
    return 0


COMMON_TERMINAL_PATHS = (
    r"C:\Program Files\MetaTrader 5\terminal64.exe",
    r"C:\Program Files\FP Markets MetaTrader 5\terminal64.exe",
)


def apply_config_updates(updates: dict[str, Any]) -> Path:
    """Merge UI-provided config fields into config.json (non-clobbering).

    Lets the desktop app save the terminal path and folders without the CLI.
    Only known fields are written; unknown keys are ignored.
    """

    config_path = resolve_config_path()
    existing: dict[str, Any] = {}
    if config_path.exists():
        try:
            loaded = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except (OSError, json.JSONDecodeError):
            existing = {}
    current = AppConfig.from_dict(existing)

    def pick(key: str, fallback: Any) -> Any:
        return updates[key] if key in updates and updates[key] is not None else fallback

    merged = {
        "terminal_path": str(pick("terminal_path", current.terminal_path)),
        "portable_mode": bool(pick("portable_mode", current.portable_mode)),
        "mt5_window_title_contains": str(pick("mt5_window_title_contains", current.mt5_window_title_contains)),
        "artifacts_dir": str(pick("artifacts_dir", current.artifacts_dir)),
        "results_dir": str(pick("results_dir", current.results_dir)),
        "default_timeout_seconds": int(pick("default_timeout_seconds", current.default_timeout_seconds)),
        "shutdown_terminal_after_run": bool(pick("shutdown_terminal_after_run", current.shutdown_terminal_after_run)),
        "report_path_strategy": str(pick("report_path_strategy", current.report_path_strategy)),
        "allow_stop_existing_terminal": bool(pick("allow_stop_existing_terminal", current.allow_stop_existing_terminal)),
        "max_parallel_mt5_processes": int(pick("max_parallel_mt5_processes", current.max_parallel_mt5_processes)),
        "process_priority": str(pick("process_priority", current.process_priority)),
    }
    config_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return config_path


def detect_terminal_path() -> str:
    import os

    for candidate in COMMON_TERMINAL_PATHS:
        if Path(candidate).exists():
            return candidate
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    root = Path(program_files)
    if root.exists():
        for path in root.glob("*MetaTrader 5*/terminal64.exe"):
            return str(path)
    return ""


def run_config_wizard_command(
    *,
    terminal_path: str | None,
    artifacts_dir: str | None,
    results_dir: str | None,
    portable: bool | None,
) -> int:
    config_path = resolve_config_path()
    existing: dict[str, Any] = {}
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}

    current = AppConfig.from_dict(existing)
    resolved_terminal = terminal_path or current.terminal_path or detect_terminal_path()

    merged = {
        "terminal_path": resolved_terminal,
        "portable_mode": current.portable_mode if portable is None else portable,
        "mt5_window_title_contains": current.mt5_window_title_contains,
        "artifacts_dir": artifacts_dir or current.artifacts_dir,
        "results_dir": results_dir or current.results_dir,
        "default_timeout_seconds": current.default_timeout_seconds,
        "shutdown_terminal_after_run": current.shutdown_terminal_after_run,
        "report_path_strategy": current.report_path_strategy,
        "allow_stop_existing_terminal": current.allow_stop_existing_terminal,
        "max_parallel_mt5_processes": current.max_parallel_mt5_processes,
        "process_priority": current.process_priority,
    }
    config_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")

    print(f"config written: {config_path}")
    print(f"terminal_path: {merged['terminal_path'] or '<not detected; set manually>'}")
    print(f"artifacts_dir: {merged['artifacts_dir']}")
    print(f"results_dir: {merged['results_dir']}")
    print("")
    print("detected MT5 environment:")
    for label, ok, detail in config_wizard_detection(AppConfig.from_dict(merged)):
        status = "PASS" if ok else "WARN"
        print(f"  [{status}] {label}: {detail}")
    print("")
    print("next: run `doctor` to re-check, then `first-smoke --dry-run`.")
    if not merged["terminal_path"]:
        print("warning: MT5 terminal was not detected. Set terminal_path manually before running tests.")
        return 1
    return 0


def _first_or_none(paths: list[Path]) -> Path | None:
    # Prefer the first candidate that actually exists; fall back to the first.
    for path in paths:
        if path.exists():
            return path
    return paths[0] if paths else None


def _report_path_writable(config: AppConfig) -> tuple[bool, str]:
    candidates = get_terminal_data_folder_candidates(config)
    root = _first_or_none(candidates)
    if root is None:
        return False, "no terminal data folder detected"
    reports_dir = root / "reports"
    try:
        reports_dir.mkdir(parents=True, exist_ok=True)
        probe = reports_dir / ".write_probe.tmp"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True, str(reports_dir)
    except OSError as exc:
        return False, f"{reports_dir} ({exc})"


def config_wizard_detection(config: AppConfig) -> list[tuple[str, bool, str]]:
    """Detect the MT5 environment a new user needs: data folder, Experts,
    Tester profile, report-path writability, and MetaEditor."""

    data_root = _first_or_none(get_terminal_data_folder_candidates(config))
    experts = _first_or_none(get_experts_folder_candidates(config))
    tester = _first_or_none(get_metaquotes_tester_folder_candidates())
    writable, write_detail = _report_path_writable(config)
    metaeditor = find_metaeditor_path(config)

    return [
        (
            "terminal data folder",
            data_root is not None and data_root.exists(),
            str(data_root) if data_root else "<not detected>",
        ),
        (
            "MQL5\\Experts",
            experts is not None and experts.exists(),
            str(experts) if experts else "<not detected>",
        ),
        (
            "MQL5\\Profiles\\Tester",
            tester is not None and tester.exists(),
            str(tester) if tester else "<not detected; created on first run>",
        ),
        ("report path writable", writable, write_detail),
        (
            "MetaEditor",
            metaeditor is not None,
            str(metaeditor) if metaeditor else "<not detected; compile manually with F7>",
        ),
    ]
