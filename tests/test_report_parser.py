from pathlib import Path

from mt5_research_agent.report_parser import parse_report_file


def test_parse_report_file_reads_expected_metrics() -> None:
    report = parse_report_file(Path("tests/fixtures/report_example.htm"))

    assert report.net_profit == 1234.56
    assert report.gross_profit == 2500.0
    assert report.gross_loss == -1265.44
    assert report.profit_factor == 1.98
    assert report.expected_payoff == 12.35
    assert report.absolute_drawdown == 100.0
    assert report.maximal_drawdown == 350.0
    assert report.relative_drawdown_pct == 12.5
    assert report.equity_drawdown_pct == 12.5
    assert report.total_trades == 140
    assert report.short_trades == 70
    assert report.long_trades == 70
    assert report.profit_trades == 81
    assert report.loss_trades == 59
    assert report.winrate_pct == 57.86
    assert report.average_win == 35.5
    assert report.average_loss == -21.45
    assert report.parser_warnings == []


def test_parse_czech_mt5_fixture_reads_variant_labels() -> None:
    report = parse_report_file(Path("tests/fixtures/report_mt5_cz_minimal.htm"))

    assert report.net_profit == -9.22
    assert report.profit_factor == 0.98
    assert report.maximal_drawdown == 189.67
    assert report.relative_drawdown_pct == 1.86
    assert report.equity_drawdown_pct == 1.86
    assert report.total_trades == 20
    assert report.profit_trades == 4
    assert report.loss_trades == 6
    assert report.winrate_pct == 40.0
    assert report.average_win == 90.15
    assert report.average_loss == -61.64


def test_parse_report_warns_when_required_metrics_are_missing() -> None:
    report = parse_report_file(Path("tests/fixtures/report_missing_metrics.htm"))

    assert report.net_profit == 10.0
    assert report.total_trades == 4
    assert "Metric not found: profit_factor" in report.parser_warnings
