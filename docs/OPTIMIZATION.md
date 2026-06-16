# Efficient Optimization Mode (Phase 6)

The default research loop runs **one MT5 launch per task**. That is robust and
fully traceable, but slow when you want to sweep many parameter combinations.

Optimization mode uses the MetaTrader 5 Strategy Tester *optimizer* so a
**single launch evaluates many combinations** and writes one optimization
report (`.xml`) with a row per pass. This module generates the optimizer files,
counts the grid, launches the optimizer once, then parses and ranks the passes.

## Safety (unchanged)

- Strategy Tester only. There is **no** `order_send` and no live-trading path.
- Every pass is preserved in `passes.json` — none are ever hidden.
- A pass that simply tops one criterion is reported as **UNVALIDATED**. Optimizer
  passes are single-period results; they must still survive `split-validate`
  before anything is called a robust or "best" candidate. Profit alone never
  qualifies a candidate.

## How it maps to MT5

The generated `.ini` adds two `[Tester]` keys on top of the normal backtest ini:

| Key | Meaning |
| --- | --- |
| `Optimization=` | `0` disabled, `1` slow/complete (full grid), `2` fast genetic, `3` all symbols |
| `OptimizationCriterion=` | `0` balance max, `1` balance+PF, `2` payoff, `3` min DD, `4` recovery, `5` Sharpe, `6` custom (`OnTester`), `7` complex |

Optimizable inputs in the generated `.set` use MT5 range syntax:

```text
TP_R=1||1||0.5||3||Y      ; value || start || step || stop || optimize(Y/N)
ATR_Mult=1||1||0.5||2.5||Y
MagicNumber=990001         ; fixed inputs are written normally
```

## Optimization spec

A spec is a small JSON file:

```json
{
  "test_id": "US30-OPT-0001",
  "ea": "Advisors\\US30_MultiStrategyLab_M15",
  "symbol": "US30",
  "timeframe": "M15",
  "period_from": "2020.01.01",
  "period_to": "2025.01.01",
  "deposit": 10000,
  "model": "Every tick based on real ticks",
  "algorithm": "fast_genetic",
  "criterion": "balance_pf_max",
  "fixed_inputs": { "MagicNumber": "990001" },
  "ranges": [
    { "name": "TP_R", "start": 1.0, "step": 0.5, "stop": 3.0 },
    { "name": "ATR_Mult", "start": 1.0, "step": 0.5, "stop": 2.5 }
  ],
  "acceptance": { "min_profit": 0, "min_profit_factor": 1.5, "max_equity_dd_pct": 25, "min_trades": 100 }
}
```

`acceptance` is optional. When present it is used as a **hard filter**: passes
that breach it (for example too few trades — the classic over-fit signature) are
kept and shown but ranked below every filter survivor.

## Workflow

```powershell
# 1) Derive a spec from an existing research request (numeric ranges only).
python -m mt5_research_agent optimization-spec-from-request research_requests/us30_goal.md

# 2) Preview the generated files and grid size without launching MT5.
python -m mt5_research_agent plan-optimization artifacts/optimizations/<id>/<id>_spec.json

# 3) Run the optimizer once (real terminal required).
python -m mt5_research_agent run-optimization <spec.json> --run --timeout-seconds 3600

# 4) Or parse an optimization .xml you already have.
python -m mt5_research_agent parse-optimization <report.xml> --min-profit-factor 1.5 --max-dd 25 --min-trades 100

# 5) Re-read the stored result later.
python -m mt5_research_agent optimization-status <id>
```

`optimization-spec-from-request` only turns **numeric** parameter lists into
ranges (`[1.0, 1.5, 2.0]` → start 1.0, step 0.5, stop 2.0). Non-numeric lists
(for example `[ema, sma]`) cannot be an MT5 range, so their first value is pinned
as a fixed input and a warning is printed.

## Outputs

`run-optimization --run` writes, under `artifacts/optimizations/<test_id>/`:

- `<test_id>.set` / `<test_id>.ini` — the generated optimizer files
- `<test_id>_optimization.xml` — the copied raw MT5 optimization report
- `passes.json` — **every** parsed pass, ranked, with filter status and reasons
- `optimization_summary.md` — the ranked top-passes table (mirrored into `results/`)
- `optimization_result.json` — machine-readable status for `optimization-status`

## Ranking

Each pass gets a transparent 0–100 attractiveness score from profit factor,
drawdown headroom, trade count, and net profit. Ranking is `(passes_filters,
score)` so a filter survivor always outranks a higher-scoring pass that breached
a hard limit. The score is **not** a robustness verdict — it only surfaces the
most promising combos to feed into `split-validate`.

## Limitations

- A live optimization run needs a real MT5 terminal; only that step can't be
  exercised in CI. All deterministic logic (file generation, grid counting, XML
  parsing, ranking) is unit-tested with the launch mocked.
- The fast genetic algorithm explores a subset of the grid, so the reported
  "slow-complete grid size" is the exhaustive upper bound, not the genetic pass
  count.
- Sparse `ss:Index` cells in exotic optimization XML exports are not
  reconstructed; standard MT5 tester exports are dense and parse correctly.
