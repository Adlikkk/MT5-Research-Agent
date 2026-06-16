import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from mt5_research_agent.background_runner import (
    build_find_reports_payload,
    build_task_status_payload,
    discover_report,
    generate_mt5_files,
    run_prepare_mt5_files_command,
    run_test_report_strategies_command,
    run_fix_smoke_task_command,
    run_create_smoke_task_command,
    run_preflight_task_command,
    run_print_ini_command,
    run_print_set_command,
    run_smoke_cli_command,
    run_task_cli,
    run_generate_mt5_files_command,
    write_ini_file,
    write_set_file,
)
from mt5_research_agent.config import load_config
from mt5_research_agent.mt5_diagnostics import compile_ea_payload, locate_ea_payload
from mt5_research_agent.result_store import fetch_run_attempts
from mt5_research_agent.task import load_task


def _write_config(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    config_path = tmp_path / "config.json"
    payload = {
        "terminal_path": "",
        "portable_mode": True,
        "mt5_window_title_contains": "MetaTrader",
        "artifacts_dir": str(tmp_path / "artifacts"),
        "results_dir": str(tmp_path / "results"),
        "default_timeout_seconds": 30,
        "shutdown_terminal_after_run": True,
        "report_path_strategy": "terminal_relative_reports",
    }
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("MT5_AGENT_CONFIG", str(config_path))
    return config_path


def _write_terminal_config(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    terminal_path = tmp_path / "terminal64.exe"
    terminal_path.write_text("", encoding="utf-8")
    config_path = tmp_path / "config.json"
    payload = {
        "terminal_path": str(terminal_path),
        "portable_mode": True,
        "mt5_window_title_contains": "MetaTrader",
        "artifacts_dir": str(tmp_path / "artifacts"),
        "results_dir": str(tmp_path / "results"),
        "default_timeout_seconds": 30,
        "shutdown_terminal_after_run": True,
        "report_path_strategy": "terminal_relative_reports",
    }
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("MT5_AGENT_CONFIG", str(config_path))
    return config_path


def _write_ea_files(tmp_path: Path, *, subdir: str = "", with_source: bool = True, with_binary: bool = True) -> tuple[Path | None, Path | None]:
    experts_dir = tmp_path / "MQL5" / "Experts"
    target_dir = experts_dir / subdir if subdir else experts_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    mq5_path = target_dir / "US30_MultiStrategyLab_M15.mq5" if with_source else None
    ex5_path = target_dir / "US30_MultiStrategyLab_M15.ex5" if with_binary else None
    if mq5_path is not None:
        mq5_path.write_text("// source", encoding="utf-8")
    if ex5_path is not None:
        ex5_path.write_text("binary", encoding="utf-8")
    return mq5_path, ex5_path


def _write_task(tmp_path: Path) -> Path:
    task_path = tmp_path / "GOLD-0001.json"
    task_path.write_text(
        json.dumps(
            {
                "test_id": "GOLD-0001",
                "name": "gold_single_test",
                "ea": "GoldEA",
                "symbol": "XAUUSD_DUKA",
                "timeframe": "H1",
                "period_from": "2020.01.01",
                "period_to": "2026.06.01",
                "deposit": 10000,
                "model": "Every tick based on real ticks",
                "inputs": {
                    "TP_R": "2.2",
                    "SL_ATR": "1.7",
                },
                "acceptance": {
                    "min_profit": 0,
                    "min_profit_factor": 1.1,
                    "max_equity_dd_pct": 18,
                    "min_trades": 100,
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return task_path


def test_task_loading_bg_fixture(tmp_path: Path) -> None:
    task = load_task(_write_task(tmp_path))

    assert task.test_id == "GOLD-0001"
    assert task.inputs["TP_R"] == "2.2"


def test_create_smoke_task_writes_relaxed_acceptance(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)

    exit_code = run_create_smoke_task_command(
        test_id="US30-SMOKE-0001",
        ea="US30_MultiStrategyLab_M15",
        symbol="US30",
        timeframe="M15",
        period_from="2024.01.01",
        period_to="2024.02.01",
        deposit=10000,
    )

    task = load_task(tmp_path / "artifacts" / "generated_tasks" / "US30-SMOKE-0001.json")

    assert exit_code == 0
    assert task.symbol == "US30"
    assert task.inputs == {}
    assert task.acceptance.min_profit == -999999
    assert task.acceptance.min_profit_factor == 0
    assert task.acceptance.max_equity_dd_pct == 100
    assert task.acceptance.min_trades == 0


def test_locate_ea_finds_mq5_and_ex5_in_fake_experts_folder(tmp_path: Path, monkeypatch) -> None:
    _write_terminal_config(tmp_path, monkeypatch)
    _write_ea_files(tmp_path, subdir="Strategies")

    payload = locate_ea_payload("US30_MultiStrategyLab_M15")

    assert payload["ex5_exists"] is True
    assert payload["found_mq5"]
    assert payload["found_ex5"]
    assert payload["recommended_expert_value"] == "Strategies\\US30_MultiStrategyLab_M15"


def test_locate_ea_warns_when_ex5_missing(tmp_path: Path, monkeypatch) -> None:
    _write_terminal_config(tmp_path, monkeypatch)
    _write_ea_files(tmp_path, with_binary=False)

    payload = locate_ea_payload("US30_MultiStrategyLab_M15")

    assert payload["ex5_exists"] is False
    assert any("compiled .ex5 is missing" in warning for warning in payload["warnings"])


def test_write_set_file_preserves_input_text(tmp_path: Path) -> None:
    task = load_task(_write_task(tmp_path))
    output_path = write_set_file(task, tmp_path / "generated.set")

    content = output_path.read_text(encoding="utf-8")

    assert "TP_R=2.2" in content
    assert "SL_ATR=1.7" in content


def test_write_ini_file_contains_expected_cli_fields(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    task = load_task(_write_task(tmp_path))
    config = load_config()
    output_path = write_ini_file(
        task,
        config,
        tmp_path / "generated.set",
        tmp_path / "report.htm",
        tmp_path / "generated.ini",
    )

    content = output_path.read_text(encoding="utf-8")

    assert "Expert=GoldEA" in content
    assert "ExpertParameters=generated.set" in content
    assert "Report=" in content
    assert "ReplaceReport=1" in content
    assert "ShutdownTerminal=1" in content
    assert "Portable=1" in content


def test_write_ini_file_keep_terminal_open_disables_shutdown(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    task = load_task(_write_task(tmp_path))
    config = load_config()
    output_path = write_ini_file(
        task,
        config,
        tmp_path / "generated.set",
        tmp_path / "report.htm",
        tmp_path / "generated.ini",
        keep_terminal_open=True,
    )

    content = output_path.read_text(encoding="utf-8")

    assert "ShutdownTerminal=0" in content


def test_generate_mt5_files_and_status_persistence(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    task_path = _write_task(tmp_path)

    exit_code = run_generate_mt5_files_command(str(task_path))
    files = generate_mt5_files(task_path)
    attempts = fetch_run_attempts("GOLD-0001")

    assert exit_code == 0
    assert files.set_path.exists()
    assert files.native_set_path.exists()
    assert files.ini_path.exists()
    assert any(attempt["run_status"] == "FILES_GENERATED" for attempt in attempts)


def test_native_set_is_copied_to_mql5_profiles_tester(tmp_path: Path, monkeypatch) -> None:
    _write_terminal_config(tmp_path, monkeypatch)
    task_path = _write_task(tmp_path)

    files = generate_mt5_files(task_path)

    assert files.native_set_path.exists()
    assert files.native_set_path.parent == tmp_path / "MQL5" / "Profiles" / "Tester"
    assert files.native_set_path.name == "GOLD-0001.set"


def test_terminal_relative_reports_strategy_generates_native_report_targets(tmp_path: Path, monkeypatch) -> None:
    _write_terminal_config(tmp_path, monkeypatch)
    task_path = _write_task(tmp_path)

    files = generate_mt5_files(task_path)
    content = files.ini_path.read_text(encoding="utf-8")

    assert files.report_path_strategy == "terminal_relative_reports"
    assert any(path.parent == tmp_path / "reports" for path in files.expected_native_report_paths[:3])
    assert "ExpertParameters=GOLD-0001.set" in content
    assert "Report=reports\\GOLD-0001" in content


def test_discover_report_finds_wildcard_fixture(tmp_path: Path) -> None:
    expected = tmp_path / "GOLD-0001.htm"
    actual = tmp_path / "GOLD-0001_report.html"
    fixture_path = Path(__file__).parent / "fixtures" / "report_example.htm"
    actual.write_text(fixture_path.read_text(encoding="utf-8"), encoding="utf-8")

    discovered = discover_report(expected)

    assert discovered.discovered_path == actual
    assert any(item["name"] == "GOLD-0001_report.html" for item in discovered.nearby_files)


def test_smoke_cli_dry_output(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_terminal_config(tmp_path, monkeypatch)
    task_path = _write_task(tmp_path)

    exit_code = run_smoke_cli_command(str(task_path), run=False, timeout_seconds=30)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "test_id: GOLD-0001" in output
    assert "command:" in output
    assert "terminal64.exe" in output
    assert "Dry smoke complete" in output


def test_print_ini_and_set_commands_emit_generated_content(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_terminal_config(tmp_path, monkeypatch)
    task_path = _write_task(tmp_path)

    ini_exit_code = run_print_ini_command(str(task_path))
    ini_output = capsys.readouterr().out
    set_exit_code = run_print_set_command(str(task_path))
    set_output = capsys.readouterr().out

    assert ini_exit_code == 0
    assert "[Tester]" in ini_output
    assert "Expert=GoldEA" in ini_output
    assert set_exit_code == 0
    assert "TP_R=2.2" in set_output


def test_compile_ea_handles_missing_metaeditor_path_cleanly(tmp_path: Path, monkeypatch) -> None:
    _write_terminal_config(tmp_path, monkeypatch)
    _write_ea_files(tmp_path)
    metaeditor = tmp_path / "MetaEditor64.exe"
    if metaeditor.exists():
        metaeditor.unlink()

    payload = compile_ea_payload("US30_MultiStrategyLab_M15")

    assert payload["ok"] is False
    assert "MetaEditor executable was not found" in payload["warnings"][0]


def test_run_task_cli_persists_process_metadata(tmp_path: Path, monkeypatch) -> None:
    _write_terminal_config(tmp_path, monkeypatch)
    task_path = _write_task(tmp_path)

    class FakeProcess:
        pid = 4242
        returncode = 0

        def communicate(self, timeout=None):
            return ("stdout ok", "")

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(
        "mt5_research_agent.background_runner.mt5_process_status_payload",
        lambda config: {
            "running": False,
            "matching_running": False,
            "configured_terminal_path": config.terminal_path,
            "processes": [],
            "recommended_action": "none",
        },
    )

    files = generate_mt5_files(task_path)
    fixture_path = Path(__file__).parent / "fixtures" / "report_example.htm"
    files.report_path.write_text(fixture_path.read_text(encoding="utf-8"), encoding="utf-8")

    result = run_task_cli(str(task_path), timeout_seconds=30)
    attempts = fetch_run_attempts("GOLD-0001")
    final_attempt = attempts[-1]

    assert result.status in {"PASS", "FAIL"}
    assert final_attempt["command_line"]
    assert final_attempt["expected_report_path"] == str(files.report_path)
    assert final_attempt["discovered_report_path"] == str(files.report_path)
    assert final_attempt["process_id"] == 4242
    assert final_attempt["process_exit_code"] == 0
    assert final_attempt["process_started_at"]
    assert final_attempt["process_ended_at"]
    assert final_attempt["duration_seconds"] is not None


def test_run_task_cli_logs_nearby_files_when_report_missing(tmp_path: Path, monkeypatch) -> None:
    _write_terminal_config(tmp_path, monkeypatch)
    task_path = _write_task(tmp_path)

    class FakeProcess:
        pid = 4243
        returncode = 0

        def communicate(self, timeout=None):
            return ("stdout ok", "")

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(
        "mt5_research_agent.background_runner.mt5_process_status_payload",
        lambda config: {
            "running": False,
            "matching_running": False,
            "configured_terminal_path": config.terminal_path,
            "processes": [],
            "recommended_action": "none",
        },
    )

    files = generate_mt5_files(task_path)
    unrelated_file = files.report_path.parent / "other.txt"
    unrelated_file.write_text("x", encoding="utf-8")

    result = run_task_cli(str(task_path), timeout_seconds=30)
    log_payload = json.loads(Path(result.log_path).read_text(encoding="utf-8"))

    assert result.status == "REPORT_MISSING"
    assert "nearby_report_files" in log_payload
    assert any(item["name"] == "other.txt" for item in log_payload["nearby_report_files"])
    assert "report_candidates" in log_payload
    assert log_payload["report_candidates"] == []


def test_discover_report_finds_newest_xml_candidate_after_process_start(tmp_path: Path) -> None:
    expected = tmp_path / "US30-SMOKE-0001.htm"
    xml_path = tmp_path / "strategy_result.xml"
    xml_path.write_text("<report />", encoding="utf-8")
    started_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    discovered = discover_report(expected, started_at)

    assert discovered.discovered_path == xml_path
    assert any(item["name"] == "strategy_result.xml" for item in discovered.report_candidates)


def test_find_reports_discovers_recent_terminal_folder_reports(tmp_path: Path, monkeypatch) -> None:
    _write_terminal_config(tmp_path, monkeypatch)
    terminal_data_root = Path(os.environ["APPDATA"]) / "MetaQuotes" / "Terminal" / "REPORTROOT"
    reports_dir = terminal_data_root / "Tester" / "cache"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "recent_report.htm").write_text("<html />", encoding="utf-8")
    (reports_dir / "recent_report.xml").write_text("<report />", encoding="utf-8")

    payload = build_find_reports_payload(60)

    names = {item["name"] for item in payload["candidates"]}
    assert "recent_report.htm" in names
    assert "recent_report.xml" in names


def test_discover_report_searches_terminal_data_folder_not_only_artifacts(tmp_path: Path, monkeypatch) -> None:
    _write_terminal_config(tmp_path, monkeypatch)
    expected = tmp_path / "artifacts" / "raw_reports" / "US30-SMOKE-0001.htm"
    expected.parent.mkdir(parents=True, exist_ok=True)
    terminal_data_root = Path(os.environ["APPDATA"]) / "MetaQuotes" / "Terminal" / "SEARCHROOT"
    reports_dir = terminal_data_root / "Tester" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    external_report = reports_dir / "US30-SMOKE-0001_report.htm"
    external_report.write_text("<html />", encoding="utf-8")

    discovered = discover_report(expected, datetime.now(timezone.utc) - timedelta(seconds=1), config=load_config())

    assert discovered.discovered_path == external_report


def test_discover_report_finds_native_report_and_copy_path_is_used(tmp_path: Path, monkeypatch) -> None:
    _write_terminal_config(tmp_path, monkeypatch)
    task_path = _write_task(tmp_path)

    class FakeProcess:
        pid = 4242
        returncode = 0

        def communicate(self, timeout=None):
            return ("stdout ok", "")

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(
        "mt5_research_agent.background_runner.mt5_process_status_payload",
        lambda config: {
            "running": False,
            "matching_running": False,
            "configured_terminal_path": config.terminal_path,
            "processes": [],
            "recommended_action": "none",
        },
    )

    files = generate_mt5_files(task_path)
    native_report = files.expected_native_report_paths[0].with_suffix(".xml")
    native_report.parent.mkdir(parents=True, exist_ok=True)
    native_report.write_text("<report />", encoding="utf-8")

    result = run_task_cli(str(task_path), timeout_seconds=30)
    log_payload = json.loads(Path(result.log_path).read_text(encoding="utf-8"))

    assert result.status in {"PASS", "FAIL", "PARSE_FAILED", "FAIL_WITH_MISSING_METRICS"}
    assert log_payload["discovered_report_path"] == str(native_report)
    assert log_payload["copied_artifact_report_path"].endswith("GOLD-0001.xml")
    assert Path(log_payload["copied_artifact_report_path"]).exists()


def test_build_task_status_payload_includes_likely_diagnosis(tmp_path: Path, monkeypatch) -> None:
    _write_terminal_config(tmp_path, monkeypatch)
    task_path = _write_task(tmp_path)

    class FakeProcess:
        pid = 4243
        returncode = 0

        def communicate(self, timeout=None):
            return ("stdout ok", "")

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(
        "mt5_research_agent.background_runner.mt5_process_status_payload",
        lambda config: {
            "running": False,
            "matching_running": False,
            "configured_terminal_path": config.terminal_path,
            "processes": [],
            "recommended_action": "none",
        },
    )

    result = run_task_cli(str(task_path), timeout_seconds=30)
    payload = build_task_status_payload("GOLD-0001")

    assert result.status == "REPORT_MISSING"
    assert payload["ok"] is True
    assert payload["latest_status"] == "REPORT_MISSING"
    assert "exited almost immediately" in payload["likely_diagnosis"]


def test_build_task_status_payload_includes_long_run_report_missing_diagnosis(tmp_path: Path, monkeypatch) -> None:
    _write_terminal_config(tmp_path, monkeypatch)
    task_path = _write_task(tmp_path)

    class FakeProcess:
        pid = 4243
        returncode = 0

        def communicate(self, timeout=None):
            return ("stdout ok", "")

    times = iter(
        [
            100.0,
            112.5,
        ]
    )
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(
        "mt5_research_agent.background_runner.mt5_process_status_payload",
        lambda config: {
            "running": False,
            "matching_running": False,
            "configured_terminal_path": config.terminal_path,
            "processes": [],
            "recommended_action": "none",
        },
    )
    monkeypatch.setattr("mt5_research_agent.background_runner.monotonic", lambda: next(times))

    result = run_task_cli(str(task_path), timeout_seconds=30)
    payload = build_task_status_payload("GOLD-0001")

    assert result.status == "REPORT_MISSING"
    assert "likely started but report discovery or tester config still failed" in payload["likely_diagnosis"]


def test_preflight_task_fails_when_ex5_is_missing(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_terminal_config(tmp_path, monkeypatch)
    _write_ea_files(tmp_path, with_binary=False)
    task_path = tmp_path / "US30-SMOKE-0001.json"
    task_path.write_text(
        json.dumps(
            {
                "test_id": "US30-SMOKE-0001",
                "name": "us30-smoke-0001",
                "ea": "US30_MultiStrategyLab_M15",
                "symbol": "US30",
                "timeframe": "M15",
                "period_from": "2024.01.01",
                "period_to": "2024.02.01",
                "deposit": 10000,
                "model": "Every tick based on real ticks",
                "inputs": {},
                "acceptance": {
                    "min_profit": -999999,
                    "min_profit_factor": 0,
                    "max_equity_dd_pct": 100,
                    "min_trades": 0,
                },
            }
        ),
        encoding="utf-8",
    )

    exit_code = run_preflight_task_command(str(task_path))
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "ea_ex5_exists: False" in output


def test_fix_smoke_task_creates_patched_task_with_inferred_expert_value(tmp_path: Path, monkeypatch) -> None:
    _write_terminal_config(tmp_path, monkeypatch)
    _write_ea_files(tmp_path, subdir="Strategies")
    task_path = _write_task(tmp_path)
    payload = json.loads(task_path.read_text(encoding="utf-8"))
    payload["test_id"] = "US30-SMOKE-0001"
    payload["name"] = "us30-smoke-0001"
    payload["ea"] = "US30_MultiStrategyLab_M15"
    payload["symbol"] = "US30"
    payload["timeframe"] = "M15"
    payload["period_from"] = "2024.01.01"
    payload["period_to"] = "2024.02.01"
    payload["inputs"] = {}
    task_path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = run_fix_smoke_task_command(str(task_path), in_place=False)
    fixed_task = load_task(tmp_path / "artifacts" / "generated_tasks" / "US30-SMOKE-0001-FIXED.json")

    assert exit_code == 0
    assert fixed_task.ea == "Strategies\\US30_MultiStrategyLab_M15"


def test_report_missing_diagnostics_include_terminal_log_candidates_when_present(tmp_path: Path, monkeypatch) -> None:
    _write_terminal_config(tmp_path, monkeypatch)
    _write_ea_files(tmp_path)
    task_path = _write_task(tmp_path)
    terminal_data_root = Path(os.environ["APPDATA"]) / "MetaQuotes" / "Terminal" / "TESTROOT"
    logs_dir = terminal_data_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    (terminal_data_root / "MQL5" / "Experts").mkdir(parents=True, exist_ok=True)

    class FakeProcess:
        pid = 4243
        returncode = 0

        def communicate(self, timeout=None):
            log_file = logs_dir / "20260612.log"
            log_file.write_text("line1\nTerminal\tterminal process already started\nline3", encoding="utf-8")
            return ("stdout ok", "")

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(
        "mt5_research_agent.background_runner.mt5_process_status_payload",
        lambda config: {
            "running": False,
            "matching_running": False,
            "configured_terminal_path": config.terminal_path,
            "processes": [],
            "recommended_action": "none",
        },
    )

    result = run_task_cli(str(task_path), timeout_seconds=30)
    log_payload = json.loads(Path(result.log_path).read_text(encoding="utf-8"))
    payload = build_task_status_payload("GOLD-0001")

    assert result.status == "REPORT_MISSING"
    assert "terminal_log_candidates" in log_payload
    assert log_payload["terminal_log_candidates"]
    assert "terminal process was already running" in payload["likely_diagnosis"]


def test_inspect_run_status_includes_report_and_tester_log_candidates(tmp_path: Path, monkeypatch) -> None:
    _write_terminal_config(tmp_path, monkeypatch)
    _write_ea_files(tmp_path)
    task_path = _write_task(tmp_path)
    terminal_data_root = Path(os.environ["APPDATA"]) / "MetaQuotes" / "Terminal" / "TESTERROOT"
    tester_logs_dir = terminal_data_root / "Tester" / "logs"
    tester_logs_dir.mkdir(parents=True, exist_ok=True)
    (terminal_data_root / "MQL5" / "Experts").mkdir(parents=True, exist_ok=True)

    class FakeProcess:
        pid = 4243
        returncode = 0

        def communicate(self, timeout=None):
            tester_log = tester_logs_dir / "tester.log"
            tester_log.write_text("header\ninitialization failed\nreport cannot be written", encoding="utf-8")
            return ("stdout ok", "")

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(
        "mt5_research_agent.background_runner.mt5_process_status_payload",
        lambda config: {
            "running": False,
            "matching_running": False,
            "configured_terminal_path": config.terminal_path,
            "processes": [],
            "recommended_action": "none",
        },
    )

    run_task_cli(str(task_path), timeout_seconds=30)
    payload = build_task_status_payload("GOLD-0001")

    assert payload["report_candidates"] == []
    assert payload["tester_log_candidates"]
    assert "generated_ini_shutdown_terminal_value" in payload
    assert "native_set_path" in payload
    assert "report_path_strategy" in payload
    assert "expected_native_report_paths" in payload


def test_run_task_returns_terminal_already_running_when_matching_process_exists(tmp_path: Path, monkeypatch) -> None:
    _write_terminal_config(tmp_path, monkeypatch)
    task_path = _write_task(tmp_path)

    monkeypatch.setattr(
        "mt5_research_agent.background_runner.mt5_process_status_payload",
        lambda config: {
            "running": True,
            "matching_running": True,
            "configured_terminal_path": config.terminal_path,
            "processes": [{"pid": 100, "path": config.terminal_path, "path_matches_config": True}],
            "recommended_action": "stop it",
        },
    )

    result = run_task_cli(str(task_path), timeout_seconds=30)
    log_payload = json.loads(Path(result.log_path).read_text(encoding="utf-8"))

    assert result.status == "TERMINAL_ALREADY_RUNNING"
    assert log_payload["status"] == "TERMINAL_ALREADY_RUNNING"


def test_allow_stop_existing_terminal_continues_after_stop_succeeds(tmp_path: Path, monkeypatch) -> None:
    _write_terminal_config(tmp_path, monkeypatch)
    task_path = _write_task(tmp_path)

    class FakeProcess:
        pid = 4242
        returncode = 0

        def communicate(self, timeout=None):
            return ("stdout ok", "")

    monkeypatch.setattr(
        "mt5_research_agent.background_runner.mt5_process_status_payload",
        lambda config: {
            "running": True,
            "matching_running": True,
            "configured_terminal_path": config.terminal_path,
            "processes": [{"pid": 100, "path": config.terminal_path, "path_matches_config": True}],
            "recommended_action": "stop it",
        },
    )
    monkeypatch.setattr(
        "mt5_research_agent.background_runner.stop_mt5_payload",
        lambda **kwargs: {
            "ok": True,
            "confirm": True,
            "all_processes": False,
            "configured_terminal_path": kwargs["config"].terminal_path,
            "targets": [{"pid": 100, "path": kwargs["config"].terminal_path}],
            "skipped": [],
            "stopped_pids": [100],
            "wait_succeeded": True,
            "log_path": str(tmp_path / "artifacts" / "logs" / "stop_mt5_test.json"),
            "recommended_action": "rerun",
        },
    )
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: FakeProcess())

    files = generate_mt5_files(task_path)
    fixture_path = Path(__file__).parent / "fixtures" / "report_example.htm"
    files.report_path.write_text(fixture_path.read_text(encoding="utf-8"), encoding="utf-8")

    result = run_task_cli(str(task_path), timeout_seconds=30, allow_stop_existing_terminal=True)

    assert result.status in {"PASS", "FAIL"}


def test_prepare_mt5_files_outputs_native_paths(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_terminal_config(tmp_path, monkeypatch)
    task_path = _write_task(tmp_path)

    exit_code = run_prepare_mt5_files_command(str(task_path))
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "native set:" in output
    assert "report path strategy: terminal_relative_reports" in output


def test_test_report_strategies_stops_on_first_success(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_terminal_config(tmp_path, monkeypatch)
    task_path = _write_task(tmp_path)
    calls: list[str] = []

    class Result:
        def __init__(self, status: str) -> None:
            self.exit_code = 0 if status in {"PASS", "FAIL", "PARSE_FAILED"} else 1
            self.status = status
            self.test_id = "GOLD-0001"
            self.raw_report_path = ""
            self.parsed_report_path = ""
            self.log_path = "log.json"
            self.process_id = None
            self.process_exit_code = None
            self.safety_ui_failure = False

    def fake_run_task_cli(task_path: str, timeout_seconds: int, **kwargs):
        strategy = kwargs["report_path_strategy"]
        calls.append(strategy)
        return Result("REPORT_MISSING" if strategy == "terminal_relative_reports" else "PARSE_FAILED")

    monkeypatch.setattr("mt5_research_agent.background_runner.run_task_cli", fake_run_task_cli)

    exit_code = run_test_report_strategies_command(str(task_path), timeout_seconds=30)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert calls == ["terminal_relative_reports", "terminal_root_stem"]
    assert "winning strategy: terminal_root_stem" in output
