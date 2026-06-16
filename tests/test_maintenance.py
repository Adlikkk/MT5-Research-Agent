import json
import zipfile
from pathlib import Path

import mt5_research_agent.maintenance as maintenance
from mt5_research_agent.config import AppConfig
from mt5_research_agent.maintenance import (
    config_wizard_detection,
    plan_clean_artifacts,
    run_clean_artifacts_command,
    run_config_wizard_command,
    run_export_bundle_command,
)


def test_config_wizard_detection_returns_labeled_checks(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    config = AppConfig.from_dict({"terminal_path": "", "artifacts_dir": str(tmp_path / "a"), "results_dir": str(tmp_path / "r")})
    checks = config_wizard_detection(config)
    labels = {label for label, _ok, _detail in checks}
    assert "terminal data folder" in labels
    assert "MQL5\\Experts" in labels
    assert "report path writable" in labels
    assert "MetaEditor" in labels
    # Each check is (label, bool, detail) and never raises with no terminal set.
    for _label, ok, detail in checks:
        assert isinstance(ok, bool)
        assert isinstance(detail, str)


def test_config_wizard_command_prints_detection(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_config(tmp_path, monkeypatch)
    run_config_wizard_command(terminal_path=None, artifacts_dir=None, results_dir=None, portable=None)
    out = capsys.readouterr().out
    assert "detected MT5 environment:" in out
    assert "report path writable" in out


def _write_config(tmp_path: Path, monkeypatch) -> Path:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "terminal_path": "",
                "portable_mode": False,
                "mt5_window_title_contains": "MetaTrader",
                "artifacts_dir": str(tmp_path / "artifacts"),
                "results_dir": str(tmp_path / "results"),
                "default_timeout_seconds": 30,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MT5_AGENT_CONFIG", str(config_path))
    return config_path


def test_clean_artifacts_only_targets_scaffolding(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    artifacts = tmp_path / "artifacts"
    (artifacts / "generated_sets").mkdir(parents=True)
    (artifacts / "generated_ini").mkdir(parents=True)
    (artifacts / "raw_reports").mkdir(parents=True)
    (artifacts / "logs").mkdir(parents=True)
    (artifacts / "generated_sets" / "a.set").write_text("x", encoding="utf-8")
    (artifacts / "generated_ini" / "a.ini").write_text("x", encoding="utf-8")
    report = artifacts / "raw_reports" / "a.htm"
    report.write_text("<html></html>", encoding="utf-8")
    log = artifacts / "logs" / "a.json"
    log.write_text("{}", encoding="utf-8")

    removable = plan_clean_artifacts()
    assert len(removable) == 2

    exit_code = run_clean_artifacts_command(safe=True)

    assert exit_code == 0
    assert not (artifacts / "generated_sets" / "a.set").exists()
    assert not (artifacts / "generated_ini" / "a.ini").exists()
    # Reports and logs are preserved.
    assert report.exists()
    assert log.exists()


def test_clean_artifacts_preview_does_not_delete(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_config(tmp_path, monkeypatch)
    artifacts = tmp_path / "artifacts"
    (artifacts / "generated_sets").mkdir(parents=True)
    target = artifacts / "generated_sets" / "a.set"
    target.write_text("x", encoding="utf-8")

    exit_code = run_clean_artifacts_command(safe=False)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert target.exists()
    assert "preview" in output


def test_export_bundle_request_files(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    results = tmp_path / "results"
    results.mkdir(parents=True)
    (results / "research_myslug.md").write_text("# report", encoding="utf-8")
    (results / "final_report_myslug.md").write_text("# final", encoding="utf-8")

    output_path, written = maintenance.export_bundle("myslug")

    assert output_path.exists()
    assert written == 2
    with zipfile.ZipFile(output_path) as archive:
        names = archive.namelist()
        assert "research_myslug.md" in names
        assert "manifest.json" in names


def test_export_bundle_command_reports_empty(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_config(tmp_path, monkeypatch)
    exit_code = run_export_bundle_command("does-not-exist")
    output = capsys.readouterr().out
    assert exit_code == 1
    assert "no matching" in output


def test_config_wizard_writes_and_preserves(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"terminal_path": "", "report_path_strategy": "terminal_root_stem"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("MT5_AGENT_CONFIG", str(config_path))

    terminal = tmp_path / "terminal64.exe"
    terminal.write_text("", encoding="utf-8")

    exit_code = run_config_wizard_command(
        terminal_path=str(terminal),
        artifacts_dir=str(tmp_path / "artifacts"),
        results_dir=str(tmp_path / "results"),
        portable=None,
    )
    output = capsys.readouterr().out
    written = json.loads(config_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert written["terminal_path"] == str(terminal)
    # Preserves an existing non-default value.
    assert written["report_path_strategy"] == "terminal_root_stem"
    assert "config written" in output
