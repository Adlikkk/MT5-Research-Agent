from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mt5_research_agent.config import DEFAULT_CONFIG_ENV_VAR, load_config, resolve_config_path


@dataclass(slots=True)
class DoctorCheck:
    name: str
    ok: bool
    detail: str
    # An advisory check: failing it is a WARN (the deterministic CLI still
    # works), not a hard FAIL that blocks the whole environment.
    warn_only: bool = False

    @property
    def status(self) -> str:
        if self.ok:
            return "PASS"
        return "WARN" if self.warn_only else "FAIL"


def check_python_version(version_info: tuple[int, int, int] | None = None) -> DoctorCheck:
    current = version_info or sys.version_info[:3]
    ok = current >= (3, 11, 0)
    detail = f"Python {current[0]}.{current[1]}.{current[2]}"
    return DoctorCheck(name="python_version", ok=ok, detail=detail)


def check_config_exists(config_path: Path | None = None) -> DoctorCheck:
    path = config_path or resolve_config_path()
    ok = path.exists()
    detail = f"Config path: {path}"
    return DoctorCheck(name="config_file", ok=ok, detail=detail)


def check_terminal_path(config_path: Path | None = None) -> DoctorCheck:
    try:
        config = load_config(config_path)
    except FileNotFoundError:
        return DoctorCheck(name="terminal_path", ok=False, detail="Config file not found")

    if not config.terminal_path:
        return DoctorCheck(
            name="terminal_path",
            ok=False,
            detail="Configured terminal path: <missing>. Run `config-wizard` or set terminal_path to a real terminal64.exe. "
            "Deterministic planning still works without it.",
            warn_only=True,
        )

    terminal_path = Path(config.terminal_path).expanduser()
    if terminal_path.name.casefold() != "terminal64.exe":
        return DoctorCheck(
            name="terminal_path",
            ok=False,
            detail=f"Configured terminal path: {terminal_path} (must end with terminal64.exe)",
            warn_only=True,
        )
    ok = terminal_path.exists()
    detail = (
        f"Configured terminal path: {terminal_path}"
        if ok
        else f"Configured terminal path: {terminal_path} (file not found)"
    )
    return DoctorCheck(name="terminal_path", ok=ok, detail=detail, warn_only=not ok)


def check_pywinauto_import() -> DoctorCheck:
    ok = importlib.util.find_spec("pywinauto") is not None
    detail = "pywinauto import available" if ok else "pywinauto is not installed (only needed for GUI fallback)"
    return DoctorCheck(name="pywinauto_import", ok=ok, detail=detail, warn_only=not ok)


def check_directory_exists(path: Path, name: str) -> DoctorCheck:
    ok = path.exists() and path.is_dir()
    if name == "artifacts_dir":
        detail = f"Artifact root: {path}" + ("" if ok else " (auto-created on first run)")
    elif name == "results_dir":
        detail = f"Result root: {path}" + ("" if ok else " (auto-created on first run)")
    else:
        detail = f"Directory: {path}"
    # Missing data directories are not blockers: they are created on demand.
    return DoctorCheck(name=name, ok=ok, detail=detail, warn_only=not ok)


def check_portable_mode(config_path: Path | None = None) -> DoctorCheck:
    try:
        config = load_config(config_path)
    except FileNotFoundError:
        return DoctorCheck(name="portable_mode", ok=False, detail="Portable mode: config file not found")
    return DoctorCheck(name="portable_mode", ok=True, detail=f"Portable mode: {config.portable_mode}")


def run_doctor() -> list[DoctorCheck]:
    config_path = resolve_config_path()
    checks = [
        check_python_version(),
        check_config_exists(config_path),
        check_terminal_path(config_path),
        check_portable_mode(config_path),
        check_pywinauto_import(),
    ]

    try:
        config = load_config(config_path)
        checks.append(check_directory_exists(Path(config.artifacts_dir), "artifacts_dir"))
        checks.append(check_directory_exists(Path(config.results_dir), "results_dir"))
    except FileNotFoundError:
        checks.append(DoctorCheck(name="artifacts_dir", ok=False, detail="Config file not found"))
        checks.append(DoctorCheck(name="results_dir", ok=False, detail="Config file not found"))

    return checks


def has_hard_failure(checks: list[DoctorCheck]) -> bool:
    return any(not check.ok and not check.warn_only for check in checks)


def overall_status(checks: list[DoctorCheck]) -> str:
    if has_hard_failure(checks):
        return "FAIL"
    if any(not check.ok for check in checks):
        return "WARN"
    return "PASS"


def doctor_payload(checks: list[DoctorCheck]) -> dict[str, Any]:
    return {
        "ok": not has_hard_failure(checks),
        "overall_status": overall_status(checks),
        "checks": [
            {"name": check.name, "status": check.status, "ok": check.ok, "detail": check.detail}
            for check in checks
        ],
    }


def render_doctor_json(checks: list[DoctorCheck]) -> str:
    return json.dumps(doctor_payload(checks), indent=2)


def render_doctor_report(checks: list[DoctorCheck]) -> str:
    lines = [f"Config env var: {DEFAULT_CONFIG_ENV_VAR}"]
    for check in checks:
        lines.append(f"[{check.status}] {check.name}: {check.detail}")
    lines.append("")
    lines.append(f"Overall: {overall_status(checks)}")
    return "\n".join(lines)
