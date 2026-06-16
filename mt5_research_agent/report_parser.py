from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


PARSER_VERSION = "bg3f-1"

CORE_METRIC_FIELDS = (
    "net_profit",
    "gross_profit",
    "gross_loss",
    "profit_factor",
    "expected_payoff",
    "absolute_drawdown",
    "maximal_drawdown",
    "relative_drawdown_pct",
    "equity_drawdown_pct",
    "total_trades",
    "short_trades",
    "long_trades",
    "profit_trades",
    "loss_trades",
    "winrate_pct",
    "average_win",
    "average_loss",
)


@dataclass(slots=True)
class MetricSpec:
    aliases: tuple[str, ...]
    value_kind: str


@dataclass(slots=True)
class ParsedReport:
    source_report_path: str = ""
    parser_version: str = PARSER_VERSION
    raw_label_map: dict[str, list[str]] = field(default_factory=dict)
    parser_warnings: list[str] = field(default_factory=list)
    net_profit: float | None = None
    gross_profit: float | None = None
    gross_loss: float | None = None
    profit_factor: float | None = None
    expected_payoff: float | None = None
    absolute_drawdown: float | None = None
    maximal_drawdown: float | None = None
    relative_drawdown_pct: float | None = None
    equity_drawdown_pct: float | None = None
    total_trades: int | None = None
    short_trades: int | None = None
    long_trades: int | None = None
    profit_trades: int | None = None
    loss_trades: int | None = None
    winrate_pct: float | None = None
    average_win: float | None = None
    average_loss: float | None = None
    winning_trades: int | None = None
    losing_trades: int | None = None
    winrate: float | None = None


class TableExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._current_row: list[str] | None = None
        self._current_cell_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._current_row = []
        elif tag in {"td", "th"}:
            self._current_cell_parts = []
        elif tag == "br" and self._current_cell_parts is not None:
            self._current_cell_parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._current_cell_parts is not None:
            self._current_cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._current_row is not None and self._current_cell_parts is not None:
            text = normalize_line("".join(self._current_cell_parts))
            self._current_row.append(text)
            self._current_cell_parts = None
        elif tag == "tr" and self._current_row is not None:
            row = [cell for cell in self._current_row if cell]
            if row:
                self.rows.append(row)
            self._current_row = None


FIELD_SPECS: dict[str, MetricSpec] = {
    "net_profit": MetricSpec(
        aliases=("net profit", "cisty zisk celkem"),
        value_kind="number",
    ),
    "gross_profit": MetricSpec(
        aliases=("gross profit", "hruby zisk"),
        value_kind="number",
    ),
    "gross_loss": MetricSpec(
        aliases=("gross loss", "hruba ztrata"),
        value_kind="number",
    ),
    "profit_factor": MetricSpec(
        aliases=("profit factor", "ukazatel zisku"),
        value_kind="number",
    ),
    "expected_payoff": MetricSpec(
        aliases=("expected payoff", "prumerny vynos"),
        value_kind="number",
    ),
    "absolute_drawdown": MetricSpec(
        aliases=("absolute drawdown", "nejvetsi ztrata pod uvodni vklad"),
        value_kind="number",
    ),
    "maximal_drawdown": MetricSpec(
        aliases=(
            "maximal drawdown",
            "maximalni ztrata na zustatku od lokalniho maxima",
            "maximalni ztrata na majetku od lokalniho maxima",
        ),
        value_kind="leading_number",
    ),
    "relative_drawdown_pct": MetricSpec(
        aliases=(
            "relative drawdown",
            "equity drawdown relative",
            "equity dd %",
            "nejvetsi ztrata na zustatku od lokalniho maxima v %",
        ),
        value_kind="percent",
    ),
    "equity_drawdown_pct": MetricSpec(
        aliases=(
            "nejvetsi ztrata na majetku od lokalniho maxima v %",
            "equity drawdown relative",
            "relative drawdown",
        ),
        value_kind="percent",
    ),
    "total_trades": MetricSpec(
        aliases=("total trades", "celkem obchodu"),
        value_kind="int",
    ),
    "short_trades": MetricSpec(
        aliases=("short trades won %", "kratke pozice zisk %", "kratke pozice"),
        value_kind="count_percent_count",
    ),
    "long_trades": MetricSpec(
        aliases=("long trades won %", "dlouhe pozice vydelek %", "dlouhe pozice"),
        value_kind="count_percent_count",
    ),
    "profit_trades": MetricSpec(
        aliases=("profit trades % of total", "zisk z obchodu % celkem"),
        value_kind="count_percent_count",
    ),
    "loss_trades": MetricSpec(
        aliases=("loss trades % of total", "ztratove obchody % celkem"),
        value_kind="count_percent_count",
    ),
    "average_win": MetricSpec(
        aliases=("average profit trade", "prumerny ziskovy obchod"),
        value_kind="number",
    ),
    "average_loss": MetricSpec(
        aliases=("average loss trade", "prumerny ztratovy obchod"),
        value_kind="number",
    ),
}

def normalize_line(text: str) -> str:
    cleaned = text.replace("\x00", "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", cleaned).strip()


def strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def normalize_label(text: str) -> str:
    normalized = strip_accents(normalize_line(text)).casefold()
    normalized = normalized.rstrip(":")
    normalized = normalized.replace("%", " % ")
    normalized = re.sub(r"[()]+", " ", normalized)
    normalized = re.sub(r"[^a-z0-9% ]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


LABEL_TO_FIELD: dict[str, str] = {
    normalize_label(alias): field_name
    for field_name, spec in FIELD_SPECS.items()
    for alias in spec.aliases
}


def parse_decimal_token(token: str) -> float | None:
    cleaned = token.replace("\xa0", " ").replace("−", "-").replace("–", "-").strip()
    if not cleaned:
        return None
    cleaned = cleaned.replace(" ", "")
    last_dot = cleaned.rfind(".")
    last_comma = cleaned.rfind(",")
    if last_dot != -1 and last_comma != -1:
        if last_dot > last_comma:
            cleaned = cleaned.replace(",", "")
        else:
            cleaned = cleaned.replace(".", "").replace(",", ".")
    elif last_comma != -1:
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_number_tokens(text: str) -> list[str]:
    return re.findall(r"[-+]?\d[\d\s.,]*", text.replace("\xa0", " "))


def parse_number(text: str) -> float | None:
    tokens = extract_number_tokens(text)
    for token in tokens:
        value = parse_decimal_token(token)
        if value is not None:
            return value
    return None


def parse_int(text: str) -> int | None:
    value = parse_number(text)
    return int(value) if value is not None else None


def parse_percent(text: str) -> float | None:
    match = re.search(r"([-+]?\d[\d\s.,]*)\s*%", text)
    if not match:
        return None
    return parse_decimal_token(match.group(1))


def parse_count_and_percent(text: str) -> tuple[int | None, float | None]:
    match = re.search(r"([-+]?\d+)\s*\(([-+]?\d[\d\s.,]*)%\)", text)
    if match:
        count = int(match.group(1))
        percent = parse_decimal_token(match.group(2))
        return count, percent
    return parse_int(text), parse_percent(text)


def parse_rows(html_text: str) -> list[list[str]]:
    parser = TableExtractor()
    parser.feed(html_text)
    return parser.rows


def collect_label_pairs(rows: list[list[str]]) -> tuple[dict[str, str], dict[str, list[str]]]:
    normalized_pairs: dict[str, str] = {}
    raw_label_map: dict[str, list[str]] = {}
    for row in rows:
        index = 0
        while index + 1 < len(row):
            raw_label = normalize_line(row[index])
            raw_value = normalize_line(row[index + 1])
            if raw_label and raw_value:
                normalized_label = normalize_label(raw_label)
                if normalized_label:
                    normalized_pairs[normalized_label] = raw_value
                    raw_label_map.setdefault(raw_label, []).append(raw_value)
            index += 2
    return normalized_pairs, raw_label_map


def metrics_drawdown_pct(metrics: dict[str, Any]) -> float | None:
    """Return the equity drawdown percent from a normalized metrics dict.

    Tolerates the canonical ``equity_drawdown_pct``, the legacy
    ``equity_drawdown_percent`` key used by some older fixtures, and falls back
    to ``relative_drawdown_pct`` so callers never silently read ``None`` when a
    drawdown value is actually present.
    """

    for key in ("equity_drawdown_pct", "equity_drawdown_percent", "relative_drawdown_pct"):
        value = metrics.get(key)
        if value is not None:
            return value
    return None


def normalized_metrics_payload(report: ParsedReport) -> dict[str, Any]:
    return {field_name: getattr(report, field_name) for field_name in CORE_METRIC_FIELDS}


def parsed_report_to_payload(report: ParsedReport) -> dict[str, Any]:
    payload = asdict(report)
    payload["normalized_metrics"] = normalized_metrics_payload(report)
    return payload


def _apply_metric(
    report: ParsedReport,
    field_name: str,
    raw_value: str,
    warnings: list[str],
) -> None:
    spec = FIELD_SPECS[field_name]
    if spec.value_kind == "number":
        parsed_value = parse_number(raw_value)
        if parsed_value is None:
            warnings.append(f"Could not parse numeric value for {field_name!s} from {raw_value!r}.")
            return
        setattr(report, field_name, parsed_value)
        return
    if spec.value_kind == "leading_number":
        parsed_value = parse_number(raw_value)
        if parsed_value is None:
            warnings.append(f"Could not parse leading numeric value for {field_name!s} from {raw_value!r}.")
            return
        setattr(report, field_name, parsed_value)
        return
    if spec.value_kind == "percent":
        parsed_value = parse_percent(raw_value)
        if parsed_value is None:
            warnings.append(f"Could not parse percent value for {field_name!s} from {raw_value!r}.")
            return
        setattr(report, field_name, parsed_value)
        return
    if spec.value_kind == "int":
        parsed_value = parse_int(raw_value)
        if parsed_value is None:
            warnings.append(f"Could not parse integer value for {field_name!s} from {raw_value!r}.")
            return
        setattr(report, field_name, parsed_value)
        return
    if spec.value_kind == "count_percent_count":
        count, percent = parse_count_and_percent(raw_value)
        if count is None:
            warnings.append(f"Could not parse trade count for {field_name!s} from {raw_value!r}.")
            return
        setattr(report, field_name, count)
        if field_name == "profit_trades" and percent is not None:
            report.winrate_pct = percent
        return
    warnings.append(f"Unsupported parser value kind {spec.value_kind!r} for {field_name!s}.")


def parse_report_html(html_text: str, *, source_report_path: str = "") -> ParsedReport:
    rows = parse_rows(html_text)
    normalized_pairs, raw_label_map = collect_label_pairs(rows)
    report = ParsedReport(
        source_report_path=source_report_path,
        raw_label_map=raw_label_map,
    )

    matched_fields: set[str] = set()
    warnings: list[str] = []
    for normalized_label, raw_value in normalized_pairs.items():
        field_name = LABEL_TO_FIELD.get(normalized_label)
        if field_name is None:
            continue
        matched_fields.add(field_name)
        _apply_metric(report, field_name, raw_value, warnings)

    if report.equity_drawdown_pct is None:
        fallback = normalized_pairs.get(normalize_label("Největší ztráta na majetku od lokálního maxima"))
        if fallback:
            report.equity_drawdown_pct = parse_percent(fallback)

    if report.relative_drawdown_pct is None:
        fallback = normalized_pairs.get(normalize_label("Maximal drawdown"))
        if fallback:
            report.relative_drawdown_pct = parse_percent(fallback)

    if report.relative_drawdown_pct is None and report.equity_drawdown_pct is not None:
        report.relative_drawdown_pct = report.equity_drawdown_pct
    if report.equity_drawdown_pct is None and report.relative_drawdown_pct is not None:
        report.equity_drawdown_pct = report.relative_drawdown_pct

    report.winning_trades = report.profit_trades
    report.losing_trades = report.loss_trades
    report.winrate = report.winrate_pct

    if report.winrate_pct is None and report.profit_trades is not None and report.total_trades:
        report.winrate_pct = round((report.profit_trades / report.total_trades) * 100, 2)
        report.winrate = report.winrate_pct

    if not matched_fields:
        warnings.append("No known MT5 metric labels were matched in the report.")

    for field_name in CORE_METRIC_FIELDS:
        if getattr(report, field_name) is None:
            warnings.append(f"Metric not found: {field_name}")

    report.parser_warnings = warnings
    return report


def parse_report_file(report_path: str | Path) -> ParsedReport:
    path = Path(report_path)
    data = path.read_bytes()
    encodings: list[str]
    if data.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in data[:200]:
        encodings = ["utf-16", "utf-8-sig", "utf-8", "cp1250", "latin-1"]
    else:
        encodings = ["utf-8-sig", "utf-8", "cp1250", "latin-1"]
    html_text = ""
    for encoding in encodings:
        try:
            html_text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if not html_text:
        html_text = data.decode("utf-8", errors="ignore")
    return parse_report_html(html_text, source_report_path=str(path.resolve()))


def save_parsed_report(parsed_report: ParsedReport, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(parsed_report_to_payload(parsed_report), indent=2), encoding="utf-8")
