import json
from pathlib import Path

import mt5_research_agent.ea_lab as ea_lab
from mt5_research_agent.ea_lab import (
    create_ea_from_prompt,
    generate_ea_source,
    load_metadata,
    parse_ea_prompt,
    revert_ea,
    run_ea_version_history_command,
    run_improve_ea_command,
    run_smoke_test_ea_command,
)
from mt5_research_agent.goal_seeker import GoalSeekResult
from mt5_research_agent.run_task import RunTaskResult


def _write_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
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


def _write_prompt(tmp_path: Path) -> Path:
    prompt = tmp_path / "ea_prompt.md"
    prompt.write_text(
        "\n".join(
            [
                "## EA name",
                "US30 Breakout Lab",
                "## Symbol",
                "US30",
                "## Timeframe",
                "M15",
                "## Strategy",
                "Breakout with ATR stop and TP_R, session filter, max one position.",
            ]
        ),
        encoding="utf-8",
    )
    return prompt


def test_parse_ea_prompt_extracts_fields(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    spec = parse_ea_prompt(_write_prompt(tmp_path))
    assert spec.name == "US30_Breakout_Lab"
    assert spec.symbol == "US30"
    assert spec.timeframe == "M15"
    assert "InpTP_R" in spec.inputs


def test_generated_ea_has_safety_defaults(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    spec = parse_ea_prompt(_write_prompt(tmp_path))
    source = generate_ea_source(spec, 1)
    # Safety: single position guard, inputs, no martingale/grid language, CTrade.
    assert "input " in source
    assert "InpMaxPositions" in source
    assert "CountOwnPositions" in source
    assert "no martingale" in source
    assert "iATR" in source
    # No hidden network calls or credentials.
    assert "WebRequest" not in source
    assert "password" not in source.lower()


def test_create_ea_from_prompt_versions(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    prompt = _write_prompt(tmp_path)

    first = create_ea_from_prompt(prompt)
    second = create_ea_from_prompt(prompt)

    assert first["version"] == 1
    assert second["version"] == 2
    assert Path(first["version_source_path"]).exists()
    assert Path(second["version_source_path"]).exists()
    metadata = load_metadata("US30_Breakout_Lab")
    assert metadata is not None
    assert metadata["current_version"] == 2
    assert len(metadata["versions"]) == 2
    # No terminal configured, so EA stays artifact-only with a warning.
    assert any("Experts folder" in w for w in first["warnings"])


def test_revert_ea_restores_previous_source(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    prompt = _write_prompt(tmp_path)
    create_ea_from_prompt(prompt)
    create_ea_from_prompt(prompt)

    result = revert_ea("US30_Breakout_Lab", 1)
    assert result["reverted_to"] == 1
    metadata = load_metadata("US30_Breakout_Lab")
    assert metadata["current_version"] == 1
    active = Path(result["active_source_path"]).read_text(encoding="utf-8")
    v1_source = (tmp_path / "artifacts" / "ea_lab" / "US30_Breakout_Lab" / "versions" / "US30_Breakout_Lab_v1.mq5").read_text(encoding="utf-8")
    assert active == v1_source


def test_ea_version_history_command(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_config(tmp_path, monkeypatch)
    create_ea_from_prompt(_write_prompt(tmp_path))
    exit_code = run_ea_version_history_command("US30_Breakout_Lab")
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "v1" in output


def test_smoke_test_ea_dry_run(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_config(tmp_path, monkeypatch)
    create_ea_from_prompt(_write_prompt(tmp_path))

    exit_code = run_smoke_test_ea_command(
        "US30_Breakout_Lab",
        symbol="US30",
        timeframe="M15",
        period_from="2024.01.01",
        period_to="2024.02.01",
        deposit=10000,
        run=False,
        timeout_seconds=60,
    )
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Dry smoke complete" in output
    task_path = tmp_path / "artifacts" / "ea_lab" / "US30_Breakout_Lab" / "smoke_tests" / "US30_BREAKOUT_LAB-V1-SMOKE.json"
    assert task_path.exists()
    payload = json.loads(task_path.read_text(encoding="utf-8"))
    assert payload["ea"] == "US30_Breakout_Lab_v1"


def test_smoke_test_ea_run_records_metadata(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    create_ea_from_prompt(_write_prompt(tmp_path))

    monkeypatch.setattr(
        ea_lab,
        "run_task_cli",
        lambda task_path, timeout_seconds: RunTaskResult(0, "PASS", "US30_BREAKOUT_LAB-V1-SMOKE", "report.htm", "log.json", "", False),
    )

    exit_code = run_smoke_test_ea_command(
        "US30_Breakout_Lab",
        symbol="US30",
        timeframe="M15",
        period_from="2024.01.01",
        period_to="2024.02.01",
        deposit=10000,
        run=True,
        timeout_seconds=60,
    )
    assert exit_code == 0
    metadata = load_metadata("US30_Breakout_Lab")
    smoke = metadata["versions"][-1]["smoke"]
    assert smoke["status"] == "PASS"
    assert smoke["raw_report_path"] == "report.htm"


def test_improve_ea_records_history(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_config(tmp_path, monkeypatch)
    create_ea_from_prompt(_write_prompt(tmp_path))
    goal_path = tmp_path / "goal.md"
    goal_path.write_text("# goal", encoding="utf-8")

    import mt5_research_agent.goal_seeker as goal_seeker

    monkeypatch.setattr(
        goal_seeker,
        "run_goal_seek",
        lambda *args, **kwargs: GoalSeekResult(
            slug="us30",
            target_reached=False,
            best_robust_id="",
            closest_raw_id="GOAL-0001",
            tests_run=4,
            rounds=1,
            stop_reason="test budget exhausted",
            report_path=str(tmp_path / "final.md"),
        ),
    )

    exit_code = run_improve_ea_command(
        "US30_Breakout_Lab",
        goal_request=str(goal_path),
        max_rounds=1,
        allow_gui_clicks=False,
        timeout_seconds=60,
    )
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "target reached: False" in output
    metadata = load_metadata("US30_Breakout_Lab")
    assert metadata["improvement_history"]
    assert metadata["improvement_history"][-1]["action"] == "parameter_search"
