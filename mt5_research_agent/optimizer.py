"""Phase 6 - Efficient optimization mode (MT5 optimizer fast-mode).

A single MT5 Strategy Tester launch can evaluate many input combinations when
``Optimization`` is enabled in the generated ``.ini`` and the ``.set`` file
declares parameter ranges (``name=value||start||step||stop||Y``). MT5 then writes
one optimization report (``.xml``) with a row per pass.

This module builds those files, counts the grid, launches the optimizer once,
discovers and parses the optimization report into ranked passes, and writes an
honest summary. Safety is unchanged: this is Strategy Tester only, there is no
``order_send`` and no live-trading path, every pass is preserved (never hidden),
and a pass that simply tops one criterion is reported as *UNVALIDATED* - it must
still survive split validation before anything is called a "best" candidate.

The deterministic logic (file generation, grid counting, XML parsing, ranking)
is unit-tested with the MT5 launch mocked, exactly like the rest of the project.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from mt5_research_agent.background_runner import (
    build_mt5_command,
    configured_artifacts_dir,
    discover_report,
    ensure_native_set_file,
    model_code,
    parse_utc_iso,
    render_mt5_command,
    utc_now_iso,
)
from mt5_research_agent.config import AppConfig, load_config
from mt5_research_agent.inspect import utc_timestamp
from mt5_research_agent.mt5_diagnostics import infer_expert_value
from mt5_research_agent.mt5_process import mt5_process_status_payload, stop_mt5_payload
from mt5_research_agent.report_parser import parse_number
from mt5_research_agent.result_store import get_results_dir
from mt5_research_agent.task import AcceptanceCriteria, ResearchTask


# MT5 [Tester] Optimization codes.
ALGORITHM_CODES: dict[str, int] = {
    "disabled": 0,
    "slow_complete": 1,
    "fast_genetic": 2,
    "all_symbols": 3,
}

# MT5 [Tester] OptimizationCriterion codes.
CRITERION_CODES: dict[str, int] = {
    "balance_max": 0,
    "balance_pf_max": 1,
    "balance_payoff_max": 2,
    "balance_dd_min": 3,
    "balance_recovery_max": 4,
    "balance_sharpe_max": 5,
    "custom_max": 6,
    "complex_max": 7,
}

# Above this slow-complete grid size, plan/run warn that the exhaustive grid is
# large and a fast genetic run is probably wiser. It never blocks the user.
LARGE_GRID_WARNING = 5000

# Canonical optimization-report metric columns (everything else is an input).
METRIC_FIELDS: tuple[str, ...] = (
    "result",
    "net_profit",
    "expected_payoff",
    "profit_factor",
    "recovery_factor",
    "sharpe_ratio",
    "custom",
    "equity_drawdown_pct",
    "total_trades",
)

_HEADER_FIELD_MAP: dict[str, str] = {
    "pass": "pass_number",
    "result": "result",
    "profit": "net_profit",
    "net profit": "net_profit",
    "expected payoff": "expected_payoff",
    "profit factor": "profit_factor",
    "recovery factor": "recovery_factor",
    "sharpe ratio": "sharpe_ratio",
    "custom": "custom",
    "custom max": "custom",
    "equity dd %": "equity_drawdown_pct",
    "equity dd": "equity_drawdown_pct",
    "equity drawdown": "equity_drawdown_pct",
    "equity drawdown %": "equity_drawdown_pct",
    "drawdown": "equity_drawdown_pct",
    "drawdown %": "equity_drawdown_pct",
    "trades": "total_trades",
    "total trades": "total_trades",
    "# trades": "total_trades",
}

_INT_METRICS = {"pass_number", "total_trades"}


@dataclass(slots=True)
class ParameterRange:
    name: str
    start: float
    step: float
    stop: float
    optimize: bool = True


@dataclass(slots=True)
class OptimizationSpec:
    test_id: str
    ea: str
    symbol: str
    timeframe: str
    period_from: str
    period_to: str
    deposit: float
    model: str
    algorithm: str
    criterion: str
    fixed_inputs: dict[str, str]
    ranges: list[ParameterRange]
    acceptance: dict[str, float] | None = None


@dataclass(slots=True)
class OptimizationPass:
    pass_number: int | None
    metrics: dict[str, float | None]
    inputs: dict[str, str]


@dataclass(slots=True)
class OptimizationReport:
    source_path: str
    columns: list[str]
    metric_columns: list[str]
    input_columns: list[str]
    passes: list[OptimizationPass]
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RankedPass:
    pass_number: int | None
    inputs: dict[str, str]
    metrics: dict[str, float | None]
    passes_filters: bool
    rejection_reasons: list[str]
    score: float


@dataclass(slots=True)
class LaunchOutcome:
    returncode: int | None
    stdout: str
    stderr: str
    started_at_iso: str
    timed_out: bool = False
    error: str = ""


@dataclass(slots=True)
class OptimizationRunResult:
    status: str
    test_id: str
    exit_code: int
    grid_combinations: int
    total_passes: int
    passed_filters: int
    command_line: str
    set_path: str = ""
    ini_path: str = ""
    raw_report_path: str = ""
    summary_path: str = ""
    passes_json_path: str = ""
    result_json_path: str = ""
    error: str = ""


# --------------------------------------------------------------------------- #
# Number / range helpers
# --------------------------------------------------------------------------- #
def format_number(value: float) -> str:
    """Compact, locale-free, never-scientific number formatting for MT5 files."""

    number = float(value)
    if number.is_integer():
        return str(int(number))
    text = f"{number:.10f}".rstrip("0").rstrip(".")
    return text or "0"


def range_value_count(parameter_range: ParameterRange) -> int:
    if not parameter_range.optimize:
        return 1
    if parameter_range.step <= 0:
        raise ValueError(f"Optimization range '{parameter_range.name}' must have a positive step.")
    if parameter_range.stop < parameter_range.start:
        raise ValueError(f"Optimization range '{parameter_range.name}' stop must be >= start.")
    return int((parameter_range.stop - parameter_range.start) / parameter_range.step + 1e-9) + 1


def grid_combination_count(spec: OptimizationSpec) -> int:
    """Exhaustive (slow-complete) grid size: the product of all range step counts."""

    total = 1
    for parameter_range in spec.ranges:
        total *= range_value_count(parameter_range)
    return total


# --------------------------------------------------------------------------- #
# Spec validation / loading
# --------------------------------------------------------------------------- #
def _require_non_empty_string(data: dict[str, Any], field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Field '{field_name}' must be a non-empty string.")
    return value.strip()


def _coerce_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Field '{field_name}' must be numeric.")
    return float(value)


def _validate_range(payload: dict[str, Any]) -> ParameterRange:
    if not isinstance(payload, dict):
        raise ValueError("Every entry in 'ranges' must be an object.")
    name = _require_non_empty_string(payload, "name")
    optimize = bool(payload.get("optimize", True))
    parameter_range = ParameterRange(
        name=name,
        start=_coerce_number(payload.get("start"), "start"),
        step=_coerce_number(payload.get("step", 1), "step"),
        stop=_coerce_number(payload.get("stop"), "stop"),
        optimize=optimize,
    )
    # Validate eagerly so a bad range is reported when the spec loads.
    range_value_count(parameter_range)
    return parameter_range


def _validate_fixed_inputs(payload: dict[str, Any]) -> dict[str, str]:
    value = payload.get("fixed_inputs", {})
    if not isinstance(value, dict):
        raise ValueError("Field 'fixed_inputs' must be an object.")
    normalized: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Every fixed input key must be a non-empty string.")
        normalized[key.strip()] = str(item)
    return normalized


def _validate_acceptance(payload: dict[str, Any]) -> dict[str, float] | None:
    value = payload.get("acceptance")
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("Field 'acceptance' must be an object when provided.")
    acceptance: dict[str, float] = {}
    for key in ("min_profit", "min_profit_factor", "max_equity_dd_pct", "min_trades"):
        if key in value and value[key] is not None:
            acceptance[key] = _coerce_number(value[key], f"acceptance.{key}")
    return acceptance or None


def validate_optimization_payload(payload: dict[str, Any]) -> OptimizationSpec:
    if not isinstance(payload, dict):
        raise ValueError("Optimization spec must be a JSON object.")

    algorithm = str(payload.get("algorithm", "fast_genetic")).strip()
    if algorithm not in ALGORITHM_CODES:
        raise ValueError(f"Field 'algorithm' must be one of {', '.join(sorted(ALGORITHM_CODES))}.")
    criterion = str(payload.get("criterion", "balance_max")).strip()
    if criterion not in CRITERION_CODES:
        raise ValueError(f"Field 'criterion' must be one of {', '.join(sorted(CRITERION_CODES))}.")

    raw_ranges = payload.get("ranges")
    if not isinstance(raw_ranges, list) or not raw_ranges:
        raise ValueError("Field 'ranges' must be a non-empty list.")
    ranges = [_validate_range(item) for item in raw_ranges]
    if not any(parameter_range.optimize for parameter_range in ranges):
        raise ValueError("At least one range must have optimize=true.")

    deposit = _coerce_number(payload.get("deposit", 10000), "deposit")

    return OptimizationSpec(
        test_id=_require_non_empty_string(payload, "test_id"),
        ea=_require_non_empty_string(payload, "ea"),
        symbol=_require_non_empty_string(payload, "symbol"),
        timeframe=_require_non_empty_string(payload, "timeframe"),
        period_from=_require_non_empty_string(payload, "period_from"),
        period_to=_require_non_empty_string(payload, "period_to"),
        deposit=deposit,
        model=str(payload.get("model", "Every tick based on real ticks")).strip(),
        algorithm=algorithm,
        criterion=criterion,
        fixed_inputs=_validate_fixed_inputs(payload),
        ranges=ranges,
        acceptance=_validate_acceptance(payload),
    )


def load_optimization_spec(spec_path: str | Path) -> OptimizationSpec:
    path = Path(spec_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return validate_optimization_payload(payload)


def spec_to_payload(spec: OptimizationSpec) -> dict[str, Any]:
    return asdict(spec)


# --------------------------------------------------------------------------- #
# .set / .ini generation
# --------------------------------------------------------------------------- #
def build_optimization_set_text(spec: OptimizationSpec) -> str:
    lines = ["; generated by mt5_research_agent optimizer"]
    for key, value in spec.fixed_inputs.items():
        lines.append(f"{key}={value}")
    for parameter_range in spec.ranges:
        flag = "Y" if parameter_range.optimize else "N"
        lines.append(
            f"{parameter_range.name}={format_number(parameter_range.start)}"
            f"||{format_number(parameter_range.start)}"
            f"||{format_number(parameter_range.step)}"
            f"||{format_number(parameter_range.stop)}"
            f"||{flag}"
        )
    return "\n".join(lines) + "\n"


def build_optimization_ini_text(
    spec: OptimizationSpec,
    config: AppConfig,
    set_value: str,
    report_value: str,
) -> str:
    resolved_expert_value, _ = infer_expert_value(spec.ea, config)
    lines = [
        "; generated by mt5_research_agent optimizer",
        "[Tester]",
        f"Expert={resolved_expert_value}",
        f"ExpertParameters={set_value}",
        f"Symbol={spec.symbol}",
        f"Period={spec.timeframe}",
        f"Model={model_code(spec.model)}",
        f"FromDate={spec.period_from}",
        f"ToDate={spec.period_to}",
        f"Deposit={format_number(spec.deposit)}",
        f"Optimization={ALGORITHM_CODES[spec.algorithm]}",
        f"OptimizationCriterion={CRITERION_CODES[spec.criterion]}",
        "ForwardMode=0",
        "Visual=0",
        f"Report={report_value}",
        "ReplaceReport=1",
        f"ShutdownTerminal={1 if config.shutdown_terminal_after_run else 0}",
        f"Portable={1 if config.portable_mode else 0}",
    ]
    return "\n".join(lines) + "\n"


def optimization_dir(test_id: str, config: AppConfig | None = None) -> Path:
    root = configured_artifacts_dir(config) / "optimizations" / test_id
    root.mkdir(parents=True, exist_ok=True)
    return root


def _spec_to_task(spec: OptimizationSpec) -> ResearchTask:
    acceptance = spec.acceptance or {}
    return ResearchTask(
        test_id=spec.test_id,
        name=spec.test_id.casefold().replace("_", "-"),
        ea=spec.ea,
        symbol=spec.symbol,
        timeframe=spec.timeframe,
        period_from=spec.period_from,
        period_to=spec.period_to,
        deposit=spec.deposit,
        model=spec.model,
        inputs=dict(spec.fixed_inputs),
        acceptance=AcceptanceCriteria(
            min_profit=float(acceptance.get("min_profit", -999999)),
            min_profit_factor=float(acceptance.get("min_profit_factor", 0)),
            max_equity_dd_pct=float(acceptance.get("max_equity_dd_pct", 100)),
            min_trades=int(acceptance.get("min_trades", 0)),
        ),
    )


# --------------------------------------------------------------------------- #
# Optimization-report (SpreadsheetML XML) parsing
# --------------------------------------------------------------------------- #
def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _extract_rows(root: ElementTree.Element) -> list[list[str]]:
    rows: list[list[str]] = []
    for element in root.iter():
        if _strip_ns(element.tag).casefold() != "row":
            continue
        cells: list[str] = []
        for cell in list(element):
            if _strip_ns(cell.tag).casefold() != "cell":
                continue
            text = ""
            for data in list(cell):
                if _strip_ns(data.tag).casefold() == "data":
                    text = (data.text or "").strip()
                    break
            else:
                text = (cell.text or "").strip()
            cells.append(text)
        if cells:
            rows.append(cells)
    return rows


def _normalize_header(name: str) -> str:
    return " ".join(name.replace("\xa0", " ").split()).casefold()


def _coerce_metric(field_name: str, raw: str) -> float | None:
    value = parse_number(raw)
    if value is None:
        return None
    if field_name in _INT_METRICS:
        return float(int(value))
    return value


def parse_optimization_report_xml(xml_text: str, *, source_path: str = "") -> OptimizationReport:
    warnings: list[str] = []
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        raise ValueError(f"Could not parse optimization report XML: {exc}") from exc

    rows = _extract_rows(root)
    if not rows:
        return OptimizationReport(
            source_path=source_path,
            columns=[],
            metric_columns=[],
            input_columns=[],
            passes=[],
            warnings=["No table rows were found in the optimization report."],
        )

    header = rows[0]
    field_for_column: list[str | None] = []
    metric_columns: list[str] = []
    input_columns: list[str] = []
    for column in header:
        field_name = _HEADER_FIELD_MAP.get(_normalize_header(column))
        field_for_column.append(field_name)
        if field_name == "pass_number":
            continue
        if field_name in METRIC_FIELDS:
            metric_columns.append(field_name)
        elif field_name is None:
            if not column.strip():
                warnings.append("An optimization-report column had an empty header and was skipped.")
            else:
                input_columns.append(column.strip())

    passes: list[OptimizationPass] = []
    for row in rows[1:]:
        if all(not cell.strip() for cell in row):
            continue
        pass_number: int | None = None
        metrics: dict[str, float | None] = {}
        inputs: dict[str, str] = {}
        for index, field_name in enumerate(field_for_column):
            raw = row[index] if index < len(row) else ""
            if field_name == "pass_number":
                parsed = parse_number(raw)
                pass_number = int(parsed) if parsed is not None else None
            elif field_name in METRIC_FIELDS:
                metrics[field_name] = _coerce_metric(field_name, raw)
            elif field_name is None and index < len(header) and header[index].strip():
                inputs[header[index].strip()] = raw.strip()
        passes.append(OptimizationPass(pass_number=pass_number, metrics=metrics, inputs=inputs))

    if not passes:
        warnings.append("The optimization report had a header but no pass rows.")

    return OptimizationReport(
        source_path=source_path,
        columns=[column.strip() for column in header],
        metric_columns=metric_columns,
        input_columns=input_columns,
        passes=passes,
        warnings=warnings,
    )


def parse_optimization_report_file(report_path: str | Path) -> OptimizationReport:
    path = Path(report_path)
    data = path.read_bytes()
    encodings = ["utf-16", "utf-8-sig", "utf-8", "cp1250", "latin-1"]
    if not data.startswith((b"\xff\xfe", b"\xfe\xff")) and b"\x00" not in data[:200]:
        encodings = ["utf-8-sig", "utf-8", "cp1250", "latin-1", "utf-16"]
    xml_text = ""
    for encoding in encodings:
        try:
            xml_text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if not xml_text:
        xml_text = data.decode("utf-8", errors="ignore")
    return parse_optimization_report_xml(xml_text, source_path=str(path.resolve()))


# --------------------------------------------------------------------------- #
# Ranking (robustness-aware, honest)
# --------------------------------------------------------------------------- #
def hard_filter_reasons(metrics: dict[str, float | None], acceptance: dict[str, float] | None) -> list[str]:
    if not acceptance:
        return []
    reasons: list[str] = []
    net_profit = metrics.get("net_profit")
    profit_factor = metrics.get("profit_factor")
    drawdown = metrics.get("equity_drawdown_pct")
    trades = metrics.get("total_trades")

    if "min_profit" in acceptance:
        if net_profit is None or net_profit < acceptance["min_profit"]:
            reasons.append("MIN_PROFIT")
    if "min_profit_factor" in acceptance:
        if profit_factor is None or profit_factor < acceptance["min_profit_factor"]:
            reasons.append("MIN_PROFIT_FACTOR")
    if "max_equity_dd_pct" in acceptance:
        if drawdown is None or drawdown > acceptance["max_equity_dd_pct"]:
            reasons.append("MAX_EQUITY_DD_PCT")
    if "min_trades" in acceptance:
        if trades is None or trades < acceptance["min_trades"]:
            reasons.append("MIN_TRADES")
    return reasons


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def pass_score(metrics: dict[str, float | None], acceptance: dict[str, float] | None) -> float:
    """Transparent 0-100 attractiveness score for a single optimization pass.

    This is intentionally *not* a robustness verdict - a single-period optimizer
    pass cannot prove robustness. The weights only help surface promising combos
    for the next step (split validation). Components: profit factor, drawdown
    headroom, trade count, and net profit.
    """

    profit_factor = metrics.get("profit_factor") or 0.0
    drawdown = metrics.get("equity_drawdown_pct")
    trades = metrics.get("total_trades") or 0.0
    net_profit = metrics.get("net_profit") or 0.0

    pf_target = (acceptance or {}).get("min_profit_factor", 1.5) or 1.5
    pf_component = _clamp01(profit_factor / (pf_target * 1.5)) if pf_target > 0 else 0.0

    dd_limit = (acceptance or {}).get("max_equity_dd_pct", 50.0) or 50.0
    if drawdown is None:
        dd_component = 0.0
    else:
        dd_component = _clamp01(1.0 - (drawdown / dd_limit)) if dd_limit > 0 else 0.0

    trades_target = (acceptance or {}).get("min_trades", 100.0) or 100.0
    trades_component = _clamp01(trades / trades_target) if trades_target > 0 else 0.0

    profit_component = _clamp01(net_profit / max(net_profit, 1.0)) if net_profit > 0 else 0.0

    return round(
        (pf_component * 40.0)
        + (dd_component * 30.0)
        + (trades_component * 20.0)
        + (profit_component * 10.0),
        4,
    )


def rank_passes(passes: list[OptimizationPass], acceptance: dict[str, float] | None) -> list[RankedPass]:
    ranked: list[RankedPass] = []
    for optimization_pass in passes:
        reasons = hard_filter_reasons(optimization_pass.metrics, acceptance)
        ranked.append(
            RankedPass(
                pass_number=optimization_pass.pass_number,
                inputs=optimization_pass.inputs,
                metrics=optimization_pass.metrics,
                passes_filters=not reasons,
                rejection_reasons=reasons,
                score=pass_score(optimization_pass.metrics, acceptance),
            )
        )
    ranked.sort(
        key=lambda item: (item.passes_filters, item.score, item.pass_number if item.pass_number is not None else -1),
        reverse=True,
    )
    return ranked


def select_top_combos(ranked: list[RankedPass], limit: int) -> list[dict[str, str]]:
    preferred = [item for item in ranked if item.passes_filters]
    pool = preferred or ranked
    return [item.inputs for item in pool[:limit]]


# --------------------------------------------------------------------------- #
# Output writers
# --------------------------------------------------------------------------- #
def ranked_pass_to_payload(item: RankedPass) -> dict[str, Any]:
    return {
        "pass_number": item.pass_number,
        "score": item.score,
        "passes_filters": item.passes_filters,
        "rejection_reasons": item.rejection_reasons,
        "metrics": item.metrics,
        "inputs": item.inputs,
    }


def write_passes_json(out_dir: Path, report: OptimizationReport, ranked: list[RankedPass]) -> Path:
    path = out_dir / "passes.json"
    payload = {
        "source_report_path": report.source_path,
        "columns": report.columns,
        "metric_columns": report.metric_columns,
        "input_columns": report.input_columns,
        "parser_warnings": report.warnings,
        "total_passes": len(ranked),
        "passes": [ranked_pass_to_payload(item) for item in ranked],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def render_optimization_summary(
    test_id: str,
    report: OptimizationReport,
    ranked: list[RankedPass],
    acceptance: dict[str, float] | None,
    *,
    grid_combinations: int | None = None,
    top: int = 10,
) -> str:
    passed = [item for item in ranked if item.passes_filters]
    lines = [
        f"# Optimization Summary {test_id}",
        "",
        f"- Source report: {report.source_path or '<in-memory>'}",
        f"- Total passes parsed: {len(ranked)}",
        f"- Passes within hard filters: {len(passed)}",
    ]
    if grid_combinations is not None:
        lines.append(f"- Slow-complete grid size: {grid_combinations}")
    if acceptance:
        lines.append(f"- Hard filters applied: {json.dumps(acceptance, sort_keys=True)}")
    else:
        lines.append("- Hard filters applied: none (ranking only)")
    if report.warnings:
        lines.append(f"- Parser warnings: {'; '.join(report.warnings)}")
    lines.extend(
        [
            "",
            "> These are single-period optimizer passes. They are UNVALIDATED and must survive",
            "> split validation before any of them can be called a robust or \"best\" candidate.",
            "",
            "## Top Passes",
            "",
            "| Rank | Pass | Score | Filters | Net Profit | PF | Equity DD % | Trades | Inputs |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    if ranked:
        for rank, item in enumerate(ranked[:top], start=1):
            metrics = item.metrics
            filters = "ok" if item.passes_filters else ", ".join(item.rejection_reasons)
            trades_value = metrics.get("total_trades")
            trades_text = str(int(trades_value)) if trades_value is not None else "-"
            lines.append(
                f"| {rank} | {item.pass_number if item.pass_number is not None else '-'} | {item.score} | {filters} | "
                f"{metrics.get('net_profit')} | {metrics.get('profit_factor')} | "
                f"{metrics.get('equity_drawdown_pct')} | "
                f"{trades_text} | "
                f"`{json.dumps(item.inputs, sort_keys=True)}` |"
            )
    else:
        lines.append("| - | - | - | - | - | - | - | - | No passes were parsed. |")
    lines.extend(
        [
            "",
            "## Next Step",
            "",
            "Validate the top combos with `split-validate` (or feed them into `run-batch`).",
            "Profit alone never qualifies a candidate.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_optimization_summary(
    out_dir: Path,
    test_id: str,
    report: OptimizationReport,
    ranked: list[RankedPass],
    acceptance: dict[str, float] | None,
    *,
    grid_combinations: int | None = None,
) -> Path:
    path = out_dir / "optimization_summary.md"
    path.write_text(
        render_optimization_summary(
            test_id,
            report,
            ranked,
            acceptance,
            grid_combinations=grid_combinations,
        ),
        encoding="utf-8",
    )
    # Mirror into results/ so it sits next to the other research summaries.
    results_copy = get_results_dir() / f"optimization_{test_id}.md"
    shutil.copy2(path, results_copy)
    return path


def write_result_json(out_dir: Path, result: OptimizationRunResult, extra: dict[str, Any] | None = None) -> Path:
    path = out_dir / "optimization_result.json"
    payload: dict[str, Any] = asdict(result)
    payload["timestamp"] = utc_timestamp()
    if extra:
        payload.update(extra)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# Single-launch optimizer run
# --------------------------------------------------------------------------- #
def launch_optimization_process(command: list[str], timeout_seconds: int) -> LaunchOutcome:
    """Launch MT5 once for the whole optimization. Mocked in tests."""

    started_at = utc_now_iso()
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        return LaunchOutcome(process.returncode, stdout, stderr, started_at)
    except subprocess.TimeoutExpired as exc:
        if process is not None:
            process.kill()
            stdout, stderr = process.communicate()
        else:
            stdout, stderr = "", ""
        return LaunchOutcome(
            process.returncode if process is not None else None,
            stdout,
            stderr,
            started_at,
            timed_out=True,
            error=str(exc),
        )


def _failed_result(
    out_dir: Path,
    spec: OptimizationSpec,
    status: str,
    error: str,
    *,
    grid: int,
    command_line: str,
    set_path: Path,
    ini_path: Path,
) -> OptimizationRunResult:
    result = OptimizationRunResult(
        status=status,
        test_id=spec.test_id,
        exit_code=1,
        grid_combinations=grid,
        total_passes=0,
        passed_filters=0,
        command_line=command_line,
        set_path=str(set_path),
        ini_path=str(ini_path),
        error=error,
    )
    result.result_json_path = str(write_result_json(out_dir, result))
    return result


def run_optimization(
    spec: OptimizationSpec,
    *,
    timeout_seconds: int = 3600,
    allow_stop_existing_terminal: bool = False,
    launch: bool = True,
    config: AppConfig | None = None,
) -> OptimizationRunResult:
    config = config or load_config()
    out_dir = optimization_dir(spec.test_id, config)
    set_path = out_dir / f"{spec.test_id}.set"
    ini_path = out_dir / f"{spec.test_id}.ini"
    report_stem = out_dir / spec.test_id
    expected_report = out_dir / f"{spec.test_id}.xml"
    grid = grid_combination_count(spec)

    set_path.write_text(build_optimization_set_text(spec), encoding="utf-8")
    task = _spec_to_task(spec)
    native_set_path = ensure_native_set_file(task, config, set_path)
    report_value = str(report_stem.resolve())
    ini_path.write_text(
        build_optimization_ini_text(spec, config, native_set_path.name, report_value),
        encoding="utf-8",
    )
    command = build_mt5_command(config, ini_path)
    command_line = render_mt5_command(command)

    if not launch:
        result = OptimizationRunResult(
            status="FILES_GENERATED",
            test_id=spec.test_id,
            exit_code=0,
            grid_combinations=grid,
            total_passes=0,
            passed_filters=0,
            command_line=command_line,
            set_path=str(set_path),
            ini_path=str(ini_path),
        )
        result.result_json_path = str(write_result_json(out_dir, result, {"native_set_path": str(native_set_path)}))
        return result

    terminal_path = Path(config.terminal_path).expanduser() if config.terminal_path else None
    if terminal_path is None or not terminal_path.exists():
        return _failed_result(
            out_dir, spec, "PROCESS_FAILED", "Configured terminal_path does not exist.",
            grid=grid, command_line=command_line, set_path=set_path, ini_path=ini_path,
        )

    process_status = mt5_process_status_payload(config)
    if process_status["matching_running"]:
        if allow_stop_existing_terminal or config.allow_stop_existing_terminal:
            stop_payload = stop_mt5_payload(confirm=True, all_processes=False, config=config)
            if not stop_payload.get("wait_succeeded", False):
                return _failed_result(
                    out_dir, spec, "PROCESS_FAILED",
                    "Configured terminal process did not exit after stop request.",
                    grid=grid, command_line=command_line, set_path=set_path, ini_path=ini_path,
                )
        else:
            return _failed_result(
                out_dir, spec, "TERMINAL_ALREADY_RUNNING",
                "Configured terminal_path is already running. Stop it before launching an optimization.",
                grid=grid, command_line=command_line, set_path=set_path, ini_path=ini_path,
            )

    outcome = launch_optimization_process(command, timeout_seconds)
    if outcome.timed_out or (outcome.returncode not in (0, None)):
        return _failed_result(
            out_dir, spec, "PROCESS_FAILED",
            outcome.error or "MT5 optimization process returned a non-zero exit code.",
            grid=grid, command_line=command_line, set_path=set_path, ini_path=ini_path,
        )

    discovery = discover_report(
        expected_report,
        parse_utc_iso(outcome.started_at_iso),
        config=config,
        explicit_expected_paths=[expected_report],
    )
    if discovery.discovered_path is None:
        return _failed_result(
            out_dir, spec, "REPORT_MISSING",
            "MT5 optimization finished but no optimization report (.xml) was discovered.",
            grid=grid, command_line=command_line, set_path=set_path, ini_path=ini_path,
        )

    raw_copy = out_dir / f"{spec.test_id}_optimization.xml"
    if discovery.discovered_path.resolve() != raw_copy.resolve():
        shutil.copy2(discovery.discovered_path, raw_copy)

    report = parse_optimization_report_file(raw_copy)
    ranked = rank_passes(report.passes, spec.acceptance)
    passes_json_path = write_passes_json(out_dir, report, ranked)
    summary_path = write_optimization_summary(
        out_dir, spec.test_id, report, ranked, spec.acceptance, grid_combinations=grid
    )

    result = OptimizationRunResult(
        status="OPTIMIZATION_PARSED",
        test_id=spec.test_id,
        exit_code=0,
        grid_combinations=grid,
        total_passes=len(ranked),
        passed_filters=len([item for item in ranked if item.passes_filters]),
        command_line=command_line,
        set_path=str(set_path),
        ini_path=str(ini_path),
        raw_report_path=str(raw_copy),
        summary_path=str(summary_path),
        passes_json_path=str(passes_json_path),
    )
    result.result_json_path = str(write_result_json(out_dir, result, {"native_set_path": str(native_set_path)}))
    return result


# --------------------------------------------------------------------------- #
# Research-request -> optimization spec derivation
# --------------------------------------------------------------------------- #
def _numeric_values(values: list[str]) -> list[float] | None:
    parsed: list[float] = []
    for value in values:
        number = parse_number(value)
        if number is None:
            return None
        parsed.append(number)
    return parsed


def _range_from_values(name: str, numbers: list[float]) -> ParameterRange:
    ordered = sorted(set(numbers))
    if len(ordered) == 1:
        return ParameterRange(name=name, start=ordered[0], step=1.0, stop=ordered[0], optimize=False)
    gaps = [round(b - a, 10) for a, b in zip(ordered, ordered[1:]) if b > a]
    step = min(gaps) if gaps else 1.0
    return ParameterRange(name=name, start=ordered[0], step=step, stop=ordered[-1], optimize=True)


def optimization_spec_from_request(
    request: Any,
    *,
    algorithm: str = "fast_genetic",
    criterion: str = "balance_max",
    test_id: str | None = None,
) -> tuple[OptimizationSpec, list[str]]:
    """Derive an optimization spec from a parsed research request.

    Only numeric parameter lists become MT5 ranges; non-numeric parameter lists
    (for example ``[ema, sma]`` or ``[true, false]``) cannot be expressed as a
    tester range, so their first value is pinned as a fixed input and a warning
    is returned. The caller decides what to do with the warnings.
    """

    warnings: list[str] = []
    fixed_inputs: dict[str, str] = dict(request.baseline_inputs)
    ranges: list[ParameterRange] = []
    for name, values in request.parameter_space.items():
        numbers = _numeric_values(values)
        if numbers is None:
            fixed_inputs[name] = values[0]
            warnings.append(
                f"Parameter '{name}' is non-numeric ({values}); pinned to '{values[0]}' "
                "because MT5 ranges require numeric start/step/stop."
            )
            continue
        ranges.append(_range_from_values(name, numbers))
        fixed_inputs.pop(name, None)

    if not any(parameter_range.optimize for parameter_range in ranges):
        warnings.append("No numeric parameter had more than one value, so there is nothing to optimize.")

    acceptance_payload = request.acceptance_payload or {}
    acceptance: dict[str, float] = {
        key: float(acceptance_payload[key])
        for key in ("min_profit", "min_profit_factor", "max_equity_dd_pct", "min_trades")
        if key in acceptance_payload
    }

    spec = OptimizationSpec(
        test_id=test_id or f"{request.slug}_opt".upper(),
        ea=request.ea,
        symbol=request.symbol,
        timeframe=request.timeframe,
        period_from=request.period_from,
        period_to=request.period_to,
        deposit=10000.0,
        model="Every tick based on real ticks",
        algorithm=algorithm,
        criterion=criterion,
        fixed_inputs=fixed_inputs,
        ranges=ranges,
        acceptance=acceptance or None,
    )
    return spec, warnings


# --------------------------------------------------------------------------- #
# CLI command entry points
# --------------------------------------------------------------------------- #
def run_optimization_spec_from_request_command(request_path: str, algorithm: str, criterion: str) -> int:
    from mt5_research_agent.research_workflow import parse_research_request

    try:
        request = parse_research_request(request_path)
    except Exception as exc:
        print(str(exc))
        return 1
    if request.todos:
        print("request is ambiguous; resolve TODOs before deriving an optimization spec.")
        for item in request.todos:
            print(f"- {item}")
        return 1
    if algorithm not in ALGORITHM_CODES:
        print(f"Unsupported algorithm: {algorithm}. Expected one of {', '.join(sorted(ALGORITHM_CODES))}.")
        return 2
    if criterion not in CRITERION_CODES:
        print(f"Unsupported criterion: {criterion}. Expected one of {', '.join(sorted(CRITERION_CODES))}.")
        return 2

    spec, warnings = optimization_spec_from_request(request, algorithm=algorithm, criterion=criterion)
    out_dir = optimization_dir(spec.test_id)
    spec_path = out_dir / f"{spec.test_id}_spec.json"
    spec_path.write_text(json.dumps(spec_to_payload(spec), indent=2), encoding="utf-8")

    print(f"optimization spec: {spec_path}")
    print(f"optimizable ranges: {len([r for r in spec.ranges if r.optimize])}")
    print(f"slow-complete grid size: {grid_combination_count(spec)}")
    for warning in warnings:
        print(f"warning: {warning}")
    print("next: review the spec, then run plan-optimization or run-optimization")
    return 0


def run_plan_optimization_command(spec_path: str) -> int:
    try:
        spec = load_optimization_spec(spec_path)
    except Exception as exc:
        print(str(exc))
        return 1

    result = run_optimization(spec, launch=False)
    grid = result.grid_combinations
    print(f"test_id: {spec.test_id}")
    print(f"algorithm: {spec.algorithm} (Optimization={ALGORITHM_CODES[spec.algorithm]})")
    print(f"criterion: {spec.criterion} (OptimizationCriterion={CRITERION_CODES[spec.criterion]})")
    print(f"optimizable ranges: {len([r for r in spec.ranges if r.optimize])}")
    print(f"slow-complete grid size: {grid}")
    if grid > LARGE_GRID_WARNING:
        print(f"warning: grid size {grid} is large; consider algorithm=fast_genetic to bound runtime.")
    print(f"set file: {result.set_path}")
    print(f"ini file: {result.ini_path}")
    print("")
    print("--- .set ---")
    print(build_optimization_set_text(spec).rstrip())
    print("--- .ini ---")
    print(Path(result.ini_path).read_text(encoding="utf-8").rstrip())
    return 0


def run_run_optimization_command(
    spec_path: str,
    *,
    run: bool,
    timeout_seconds: int,
    allow_stop_existing_terminal: bool,
) -> int:
    try:
        spec = load_optimization_spec(spec_path)
    except Exception as exc:
        print(str(exc))
        return 1

    result = run_optimization(
        spec,
        timeout_seconds=timeout_seconds,
        allow_stop_existing_terminal=allow_stop_existing_terminal,
        launch=run,
    )
    print(f"test_id: {result.test_id}")
    print(f"status: {result.status}")
    print(f"slow-complete grid size: {result.grid_combinations}")
    print(f"set file: {result.set_path}")
    print(f"ini file: {result.ini_path}")
    if not run:
        print("preview only (no MT5 launch). Re-run with --run to launch the optimizer once.")
        print(f"command: {result.command_line or '<no terminal_path configured>'}")
        print(f"result json: {result.result_json_path}")
        return 0
    if result.status == "TERMINAL_ALREADY_RUNNING":
        print(result.error)
        print("next command: python -m mt5_research_agent stop-mt5 --confirm")
        return 1
    if result.status != "OPTIMIZATION_PARSED":
        print(f"optimization did not complete: {result.error}")
        print(f"result json: {result.result_json_path}")
        return 1
    print(f"total passes: {result.total_passes}")
    print(f"passes within hard filters: {result.passed_filters}")
    print(f"raw report: {result.raw_report_path}")
    print(f"summary: {result.summary_path}")
    print(f"passes json: {result.passes_json_path}")
    return 0


def run_parse_optimization_command(
    report_path: str,
    *,
    limit: int,
    min_profit_factor: float | None,
    max_equity_dd_pct: float | None,
    min_trades: float | None,
) -> int:
    try:
        report = parse_optimization_report_file(report_path)
    except Exception as exc:
        print(str(exc))
        return 1

    acceptance: dict[str, float] = {}
    if min_profit_factor is not None:
        acceptance["min_profit_factor"] = min_profit_factor
    if max_equity_dd_pct is not None:
        acceptance["max_equity_dd_pct"] = max_equity_dd_pct
    if min_trades is not None:
        acceptance["min_trades"] = min_trades

    ranked = rank_passes(report.passes, acceptance or None)
    print(f"source: {report.source_path}")
    print(f"columns: {', '.join(report.columns) or '<none>'}")
    print(f"input columns: {', '.join(report.input_columns) or '<none>'}")
    print(f"total passes: {len(ranked)}")
    print(f"passes within hard filters: {len([item for item in ranked if item.passes_filters])}")
    for warning in report.warnings:
        print(f"warning: {warning}")
    print("")
    print(render_optimization_summary("parsed", report, ranked, acceptance or None, top=limit).rstrip())
    return 0


def run_optimization_status_command(test_id: str) -> int:
    out_dir = configured_artifacts_dir() / "optimizations" / test_id
    result_path = out_dir / "optimization_result.json"
    if not result_path.exists():
        print(f"No optimization result stored for: {test_id}")
        print(f"expected: {result_path}")
        return 1
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    print(f"test_id: {payload.get('test_id', test_id)}")
    print(f"status: {payload.get('status', '')}")
    print(f"slow-complete grid size: {payload.get('grid_combinations', 0)}")
    print(f"total passes: {payload.get('total_passes', 0)}")
    print(f"passes within hard filters: {payload.get('passed_filters', 0)}")
    print(f"set file: {payload.get('set_path', '')}")
    print(f"ini file: {payload.get('ini_path', '')}")
    if payload.get("summary_path"):
        print(f"summary: {payload['summary_path']}")
    if payload.get("raw_report_path"):
        print(f"raw report: {payload['raw_report_path']}")
    if payload.get("error"):
        print(f"error: {payload['error']}")
    return 0
