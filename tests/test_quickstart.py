from __future__ import annotations

import json
from pathlib import Path

import mt5_research_agent.background_runner as background_runner
import mt5_research_agent.quickstart as quickstart
from mt5_research_agent.doctor import (
    DoctorCheck,
    doctor_payload,
    has_hard_failure,
    overall_status,
    render_doctor_report,
)
from mt5_research_agent.quickstart import (
    run_examples_command,
    run_first_smoke_command,
    run_open_artifacts_command,
    run_open_report_command,
)


def _write_config(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "terminal_path": "",
                "portable_mode": True,
                "artifacts_dir": str(tmp_path / "artifacts"),
                "results_dir": str(tmp_path / "results"),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MT5_AGENT_CONFIG", str(config_path))


# --------------------------------------------------------------------------- #
# doctor PASS/WARN/FAIL
# --------------------------------------------------------------------------- #
def test_doctor_status_levels() -> None:
    assert DoctorCheck("a", True, "ok").status == "PASS"
    assert DoctorCheck("b", False, "advisory", warn_only=True).status == "WARN"
    assert DoctorCheck("c", False, "blocker").status == "FAIL"


def test_doctor_warn_only_is_not_hard_failure() -> None:
    checks = [
        DoctorCheck("python_version", True, "3.11"),
        DoctorCheck("terminal_path", False, "missing", warn_only=True),
    ]
    assert has_hard_failure(checks) is False
    assert overall_status(checks) == "WARN"
    report = render_doctor_report(checks)
    assert "[WARN] terminal_path" in report
    assert "Overall: WARN" in report


def test_doctor_hard_failure_detected() -> None:
    checks = [DoctorCheck("config_file", False, "missing config")]
    assert has_hard_failure(checks) is True
    assert overall_status(checks) == "FAIL"
    payload = doctor_payload(checks)
    assert payload["ok"] is False
    assert payload["overall_status"] == "FAIL"


# --------------------------------------------------------------------------- #
# examples
# --------------------------------------------------------------------------- #
def test_examples_text(capsys) -> None:
    assert run_examples_command() == 0
    out = capsys.readouterr().out
    assert "first-smoke" in out
    assert "Strategy Tester only" in out


def test_examples_json(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_config(tmp_path, monkeypatch)
    assert run_examples_command(as_json=True) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert "safety" in payload


# --------------------------------------------------------------------------- #
# open-report / open-artifacts
# --------------------------------------------------------------------------- #
def test_open_report_not_found_returns_1(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_config(tmp_path, monkeypatch)
    exit_code = run_open_report_command("NOPE-0001")
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "No report found" in out


def test_open_report_found_opens(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_config(tmp_path, monkeypatch)
    reports = tmp_path / "artifacts" / "raw_reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "DEMO-0001.htm").write_text("<html></html>", encoding="utf-8")
    opened: list[str] = []
    monkeypatch.setattr(quickstart, "_open_path", lambda path: opened.append(str(path)) or True)

    exit_code = run_open_report_command("DEMO-0001", as_json=True)
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["report_path"].endswith("DEMO-0001.htm")
    assert opened


def test_open_artifacts(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_config(tmp_path, monkeypatch)
    monkeypatch.setattr(quickstart, "_open_path", lambda path: True)
    exit_code = run_open_artifacts_command(as_json=True)
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["ok"] is True
    assert "artifacts" in payload["artifacts_dir"].lower()


# --------------------------------------------------------------------------- #
# first-smoke
# --------------------------------------------------------------------------- #
def test_first_smoke_preview_creates_task_without_launch(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_config(tmp_path, monkeypatch)
    calls: list[dict] = []

    def fake_smoke(**kwargs):
        calls.append(kwargs)
        return 0

    monkeypatch.setattr(background_runner, "run_smoke_cli_command", fake_smoke)

    exit_code = run_first_smoke_command(
        ea="MyUS30EA",
        symbol="US30",
        timeframe="M15",
        period_from="2024.01.01",
        period_to="2024.02.01",
        deposit=10000,
        run=False,
        timeout_seconds=900,
    )
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "first smoke test" in out.lower()
    assert calls and calls[0]["run"] is False
    # The smoke task json was written under generated_tasks.
    task = tmp_path / "artifacts" / "generated_tasks" / "FIRST-SMOKE-0001.json"
    assert task.exists()


def test_first_smoke_uses_fast_deterministic_model(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    monkeypatch.setattr(background_runner, "run_smoke_cli_command", lambda **kw: 0)
    run_first_smoke_command(
        ea="MyEA", symbol="US30", timeframe="M15",
        period_from="2024.01.01", period_to="2024.02.01", deposit=10000,
        run=False, timeout_seconds=900,
    )
    payload = json.loads((tmp_path / "artifacts" / "generated_tasks" / "FIRST-SMOKE-0001.json").read_text("utf-8"))
    # Smoke = infrastructure validation -> fast, deterministic model (not every-tick).
    assert payload["model"] == "1 minute OHLC"


def test_first_smoke_dry_run_does_not_launch(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_config(tmp_path, monkeypatch)

    def fail_smoke(**kwargs):  # pragma: no cover - must not be called
        raise AssertionError("dry-run must not launch MT5")

    monkeypatch.setattr(background_runner, "run_smoke_cli_command", fail_smoke)
    # --ea is optional now; dry-run works without it.
    exit_code = run_first_smoke_command(
        ea=None, symbol="US30", timeframe="M15",
        period_from="2024.01.01", period_to="2024.02.01", deposit=10000,
        run=False, dry_run=True, timeout_seconds=900,
    )
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "dry run" in out.lower()
    assert (tmp_path / "artifacts" / "generated_tasks" / "FIRST-SMOKE-0001.json").exists()
