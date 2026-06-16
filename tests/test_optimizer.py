from __future__ import annotations

import json
from pathlib import Path

import mt5_research_agent.optimizer as optimizer
from mt5_research_agent.optimizer import (
    LaunchOutcome,
    ParameterRange,
    build_optimization_ini_text,
    build_optimization_set_text,
    format_number,
    grid_combination_count,
    hard_filter_reasons,
    load_optimization_spec,
    optimization_spec_from_request,
    parse_optimization_report_xml,
    range_value_count,
    rank_passes,
    run_optimization,
    run_parse_optimization_command,
    run_plan_optimization_command,
    run_run_optimization_command,
    select_top_combos,
    validate_optimization_payload,
)


# A realistic MT5 optimization report in SpreadsheetML 2003 format: a header row
# of metric columns plus two input columns (TP_R, ATR_Mult), then pass rows.
OPTIMIZATION_XML = """<?xml version="1.0"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
          xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Worksheet ss:Name="Tester">
  <Table>
   <Row>
    <Cell><Data ss:Type="String">Pass</Data></Cell>
    <Cell><Data ss:Type="String">Result</Data></Cell>
    <Cell><Data ss:Type="String">Profit</Data></Cell>
    <Cell><Data ss:Type="String">Expected Payoff</Data></Cell>
    <Cell><Data ss:Type="String">Profit Factor</Data></Cell>
    <Cell><Data ss:Type="String">Recovery Factor</Data></Cell>
    <Cell><Data ss:Type="String">Sharpe Ratio</Data></Cell>
    <Cell><Data ss:Type="String">Custom</Data></Cell>
    <Cell><Data ss:Type="String">Equity DD %</Data></Cell>
    <Cell><Data ss:Type="String">Trades</Data></Cell>
    <Cell><Data ss:Type="String">TP_R</Data></Cell>
    <Cell><Data ss:Type="String">ATR_Mult</Data></Cell>
   </Row>
   <Row>
    <Cell><Data ss:Type="Number">0</Data></Cell>
    <Cell><Data ss:Type="Number">12000</Data></Cell>
    <Cell><Data ss:Type="Number">12000</Data></Cell>
    <Cell><Data ss:Type="Number">40</Data></Cell>
    <Cell><Data ss:Type="Number">1.8</Data></Cell>
    <Cell><Data ss:Type="Number">3.1</Data></Cell>
    <Cell><Data ss:Type="Number">0.9</Data></Cell>
    <Cell><Data ss:Type="Number">0</Data></Cell>
    <Cell><Data ss:Type="Number">18.5</Data></Cell>
    <Cell><Data ss:Type="Number">300</Data></Cell>
    <Cell><Data ss:Type="Number">2.0</Data></Cell>
    <Cell><Data ss:Type="Number">1.5</Data></Cell>
   </Row>
   <Row>
    <Cell><Data ss:Type="Number">1</Data></Cell>
    <Cell><Data ss:Type="Number">25000</Data></Cell>
    <Cell><Data ss:Type="Number">25000</Data></Cell>
    <Cell><Data ss:Type="Number">90</Data></Cell>
    <Cell><Data ss:Type="Number">3.0</Data></Cell>
    <Cell><Data ss:Type="Number">5.0</Data></Cell>
    <Cell><Data ss:Type="Number">1.5</Data></Cell>
    <Cell><Data ss:Type="Number">0</Data></Cell>
    <Cell><Data ss:Type="Number">9.0</Data></Cell>
    <Cell><Data ss:Type="Number">8</Data></Cell>
    <Cell><Data ss:Type="Number">3.0</Data></Cell>
    <Cell><Data ss:Type="Number">2.0</Data></Cell>
   </Row>
   <Row>
    <Cell><Data ss:Type="Number">2</Data></Cell>
    <Cell><Data ss:Type="Number">5000</Data></Cell>
    <Cell><Data ss:Type="Number">5000</Data></Cell>
    <Cell><Data ss:Type="Number">10</Data></Cell>
    <Cell><Data ss:Type="Number">1.3</Data></Cell>
    <Cell><Data ss:Type="Number">1.5</Data></Cell>
    <Cell><Data ss:Type="Number">0.4</Data></Cell>
    <Cell><Data ss:Type="Number">0</Data></Cell>
    <Cell><Data ss:Type="Number">40.0</Data></Cell>
    <Cell><Data ss:Type="Number">500</Data></Cell>
    <Cell><Data ss:Type="Number">1.0</Data></Cell>
    <Cell><Data ss:Type="Number">3.0</Data></Cell>
   </Row>
  </Table>
 </Worksheet>
</Workbook>
"""


def _write_config(tmp_path: Path, monkeypatch, *, terminal_path: str = "") -> Path:
    config_path = tmp_path / "config.json"
    payload = {
        "terminal_path": terminal_path,
        "portable_mode": True,
        "mt5_window_title_contains": "MetaTrader",
        "artifacts_dir": str(tmp_path / "artifacts"),
        "results_dir": str(tmp_path / "results"),
        "default_timeout_seconds": 30,
        "shutdown_terminal_after_run": True,
        "report_path_strategy": "artifacts_absolute_current",
    }
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("MT5_AGENT_CONFIG", str(config_path))
    return config_path


def _spec_payload(test_id: str = "US30-OPT-0001") -> dict:
    return {
        "test_id": test_id,
        "ea": "Advisors\\US30_MultiStrategyLab_M15",
        "symbol": "US30",
        "timeframe": "M15",
        "period_from": "2020.01.01",
        "period_to": "2025.01.01",
        "deposit": 10000,
        "model": "Every tick based on real ticks",
        "algorithm": "fast_genetic",
        "criterion": "balance_max",
        "fixed_inputs": {"MagicNumber": "990001"},
        "ranges": [
            {"name": "TP_R", "start": 1.0, "step": 0.5, "stop": 3.0},
            {"name": "ATR_Mult", "start": 1.0, "step": 0.5, "stop": 2.0},
        ],
        "acceptance": {
            "min_profit": 0,
            "min_profit_factor": 1.5,
            "max_equity_dd_pct": 25,
            "min_trades": 100,
        },
    }


# --------------------------------------------------------------------------- #
# number / range helpers
# --------------------------------------------------------------------------- #
def test_format_number_is_compact_and_never_scientific() -> None:
    assert format_number(1.0) == "1"
    assert format_number(0.5) == "0.5"
    assert format_number(2.25) == "2.25"
    assert format_number(10000000.0) == "10000000"


def test_range_value_count_and_grid() -> None:
    assert range_value_count(ParameterRange("TP_R", 1.0, 0.5, 3.0)) == 5
    assert range_value_count(ParameterRange("Fixed", 2.0, 1.0, 2.0, optimize=False)) == 1
    spec = validate_optimization_payload(_spec_payload())
    # TP_R: 1.0..3.0 step .5 => 5 values; ATR_Mult 1.0..2.0 step .5 => 3 values.
    assert grid_combination_count(spec) == 15


def test_range_value_count_rejects_bad_step() -> None:
    try:
        range_value_count(ParameterRange("Bad", 1.0, 0.0, 3.0))
    except ValueError as exc:
        assert "positive step" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for zero step")


# --------------------------------------------------------------------------- #
# spec validation
# --------------------------------------------------------------------------- #
def test_validate_optimization_payload_requires_optimizable_range() -> None:
    payload = _spec_payload()
    payload["ranges"] = [{"name": "TP_R", "start": 2.0, "step": 1.0, "stop": 2.0, "optimize": False}]
    try:
        validate_optimization_payload(payload)
    except ValueError as exc:
        assert "optimize=true" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError when nothing is optimizable")


def test_validate_optimization_payload_rejects_unknown_algorithm() -> None:
    payload = _spec_payload()
    payload["algorithm"] = "magic"
    try:
        validate_optimization_payload(payload)
    except ValueError as exc:
        assert "algorithm" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for unknown algorithm")


def test_load_optimization_spec_roundtrip(tmp_path: Path) -> None:
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(_spec_payload()), encoding="utf-8")
    spec = load_optimization_spec(spec_path)
    assert spec.test_id == "US30-OPT-0001"
    assert len(spec.ranges) == 2
    assert spec.acceptance is not None and spec.acceptance["min_trades"] == 100


# --------------------------------------------------------------------------- #
# set / ini generation
# --------------------------------------------------------------------------- #
def test_build_set_text_has_range_syntax() -> None:
    spec = validate_optimization_payload(_spec_payload())
    text = build_optimization_set_text(spec)
    assert "MagicNumber=990001" in text
    assert "TP_R=1||1||0.5||3||Y" in text
    assert "ATR_Mult=1||1||0.5||2||Y" in text


def test_build_ini_text_enables_optimization(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    spec = validate_optimization_payload(_spec_payload())
    config = optimizer.load_config()
    text = build_optimization_ini_text(spec, config, "US30-OPT-0001.set", "C:/reports/opt")
    assert "Optimization=2" in text  # fast_genetic
    assert "OptimizationCriterion=0" in text  # balance_max
    assert "Visual=0" in text
    assert "Report=C:/reports/opt" in text
    # Safety: optimization is still Strategy Tester only - no trading directives.
    assert "order_send" not in text.lower()


# --------------------------------------------------------------------------- #
# XML parsing
# --------------------------------------------------------------------------- #
def test_parse_optimization_report_xml_extracts_passes_and_inputs() -> None:
    report = parse_optimization_report_xml(OPTIMIZATION_XML, source_path="opt.xml")
    assert len(report.passes) == 3
    assert report.input_columns == ["TP_R", "ATR_Mult"]
    assert "net_profit" in report.metric_columns
    assert not report.warnings

    first = report.passes[0]
    assert first.pass_number == 0
    assert first.metrics["net_profit"] == 12000
    assert first.metrics["profit_factor"] == 1.8
    assert first.metrics["equity_drawdown_pct"] == 18.5
    assert first.metrics["total_trades"] == 300
    assert first.inputs == {"TP_R": "2.0", "ATR_Mult": "1.5"}


def test_parse_optimization_report_xml_handles_no_rows() -> None:
    report = parse_optimization_report_xml("<Workbook></Workbook>")
    assert report.passes == []
    assert report.warnings


# --------------------------------------------------------------------------- #
# ranking
# --------------------------------------------------------------------------- #
def test_hard_filter_reasons_flags_breaches() -> None:
    acceptance = {"min_profit_factor": 1.5, "max_equity_dd_pct": 25, "min_trades": 100}
    # Pass 1 has great PF/DD but only 8 trades -> overfit-looking, must be filtered.
    metrics = {"profit_factor": 3.0, "equity_drawdown_pct": 9.0, "total_trades": 8.0, "net_profit": 25000.0}
    assert hard_filter_reasons(metrics, acceptance) == ["MIN_TRADES"]
    good = {"profit_factor": 1.8, "equity_drawdown_pct": 18.5, "total_trades": 300.0, "net_profit": 12000.0}
    assert hard_filter_reasons(good, acceptance) == []


def test_rank_passes_prefers_filter_survivors_over_raw_profit() -> None:
    report = parse_optimization_report_xml(OPTIMIZATION_XML)
    acceptance = {"min_profit_factor": 1.5, "max_equity_dd_pct": 25, "min_trades": 100}
    ranked = rank_passes(report.passes, acceptance)
    # Pass 1 has the highest raw profit (25000) but only 8 trades, so it must NOT
    # rank first - the filter survivor (pass 0) wins. No profit-only acceptance.
    assert ranked[0].pass_number == 0
    assert ranked[0].passes_filters is True
    top_combos = select_top_combos(ranked, limit=2)
    assert {"TP_R": "2.0", "ATR_Mult": "1.5"} in top_combos
    # The 8-trade pass is rejected for MIN_TRADES, never silently dropped.
    rejected = next(item for item in ranked if item.pass_number == 1)
    assert "MIN_TRADES" in rejected.rejection_reasons


# --------------------------------------------------------------------------- #
# request -> spec derivation
# --------------------------------------------------------------------------- #
class _FakeRequest:
    slug = "us30_demo"
    ea = "Advisors\\Demo"
    symbol = "US30"
    timeframe = "M15"
    period_from = "2020.01.01"
    period_to = "2025.01.01"
    baseline_inputs = {"MagicNumber": "1", "MA_Type": "ema"}
    parameter_space = {"TP_R": ["1.0", "1.5", "2.0"], "MA_Type": ["ema", "sma"]}
    acceptance_payload = {"min_profit": 0, "min_profit_factor": 1.2, "max_equity_dd_pct": 25, "min_trades": 250}


def test_optimization_spec_from_request_numeric_only() -> None:
    spec, warnings = optimization_spec_from_request(_FakeRequest())
    names = {parameter_range.name for parameter_range in spec.ranges}
    assert names == {"TP_R"}
    tp_range = spec.ranges[0]
    assert (tp_range.start, tp_range.step, tp_range.stop) == (1.0, 0.5, 2.0)
    # Non-numeric MA_Type cannot be a range; it is pinned and a warning is raised.
    assert spec.fixed_inputs["MA_Type"] == "ema"
    assert any("MA_Type" in warning for warning in warnings)
    assert spec.acceptance is not None and spec.acceptance["min_trades"] == 250


# --------------------------------------------------------------------------- #
# run_optimization with a mocked single MT5 launch
# --------------------------------------------------------------------------- #
def test_run_optimization_preview_only_does_not_launch(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)

    def fail_launch(*args, **kwargs):  # pragma: no cover - must not be called
        raise AssertionError("preview must not launch MT5")

    monkeypatch.setattr(optimizer, "launch_optimization_process", fail_launch)
    spec = validate_optimization_payload(_spec_payload())
    result = run_optimization(spec, launch=False)

    assert result.status == "FILES_GENERATED"
    assert result.grid_combinations == 15
    assert Path(result.set_path).exists()
    assert Path(result.ini_path).exists()
    assert "Optimization=2" in Path(result.ini_path).read_text(encoding="utf-8")


def test_run_optimization_parses_after_mocked_launch(tmp_path: Path, monkeypatch) -> None:
    terminal = tmp_path / "terminal64.exe"
    terminal.write_text("stub", encoding="utf-8")
    _write_config(tmp_path, monkeypatch, terminal_path=str(terminal))
    monkeypatch.setattr(optimizer, "mt5_process_status_payload", lambda config: {"matching_running": False})

    captured: dict[str, Path] = {}

    def fake_launch(command, timeout_seconds):
        # MT5 would write <stem>.xml next to the configured Report stem; emulate it.
        out_dir = tmp_path / "artifacts" / "optimizations" / "US30-OPT-0001"
        report = out_dir / "US30-OPT-0001.xml"
        report.write_text(OPTIMIZATION_XML, encoding="utf-8")
        captured["report"] = report
        return LaunchOutcome(returncode=0, stdout="", stderr="", started_at_iso="2026-01-01T00:00:00+00:00")

    monkeypatch.setattr(optimizer, "launch_optimization_process", fake_launch)

    spec = validate_optimization_payload(_spec_payload())
    result = run_optimization(spec, launch=True)

    assert result.status == "OPTIMIZATION_PARSED"
    assert result.total_passes == 3
    assert result.passed_filters == 1
    assert Path(result.summary_path).exists()
    assert Path(result.passes_json_path).exists()
    payload = json.loads(Path(result.passes_json_path).read_text(encoding="utf-8"))
    assert payload["total_passes"] == 3
    # The results/ mirror exists so the summary sits with the other reports.
    assert (tmp_path / "results" / "optimization_US30-OPT-0001.md").exists()


def test_run_optimization_blocks_when_terminal_already_running(tmp_path: Path, monkeypatch) -> None:
    terminal = tmp_path / "terminal64.exe"
    terminal.write_text("stub", encoding="utf-8")
    _write_config(tmp_path, monkeypatch, terminal_path=str(terminal))
    monkeypatch.setattr(optimizer, "mt5_process_status_payload", lambda config: {"matching_running": True})

    def fail_launch(*args, **kwargs):  # pragma: no cover - must not be called
        raise AssertionError("must not launch while terminal is running")

    monkeypatch.setattr(optimizer, "launch_optimization_process", fail_launch)
    spec = validate_optimization_payload(_spec_payload())
    result = run_optimization(spec, launch=True)

    assert result.status == "TERMINAL_ALREADY_RUNNING"
    assert result.exit_code == 1


# --------------------------------------------------------------------------- #
# command entry points
# --------------------------------------------------------------------------- #
def test_plan_optimization_command_prints_grid(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_config(tmp_path, monkeypatch)
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(_spec_payload()), encoding="utf-8")

    exit_code = run_plan_optimization_command(str(spec_path))
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "slow-complete grid size: 15" in output
    assert "TP_R=1||1||0.5||3||Y" in output
    assert "Optimization=2" in output


def test_run_optimization_command_preview(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_config(tmp_path, monkeypatch)
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(_spec_payload()), encoding="utf-8")

    exit_code = run_run_optimization_command(
        str(spec_path), run=False, timeout_seconds=10, allow_stop_existing_terminal=False
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "preview only" in output
    assert "FILES_GENERATED" in output


def test_parse_optimization_command_ranks(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_config(tmp_path, monkeypatch)
    report_path = tmp_path / "opt.xml"
    report_path.write_text(OPTIMIZATION_XML, encoding="utf-8")

    exit_code = run_parse_optimization_command(
        str(report_path), limit=5, min_profit_factor=1.5, max_equity_dd_pct=25, min_trades=100
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "total passes: 3" in output
    assert "passes within hard filters: 1" in output
    assert "UNVALIDATED" in output
