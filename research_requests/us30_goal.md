# US30 M15 Goal

## Goal
Use my US30 M15 EA. Reach or get as close as robustly possible to +250% over 5 years, keep drawdown under 25%, require enough trades, avoid overfitting, and validate the best candidates across date splits.

## Goal constraints
- target_total_return_pct: 250
- target_period_years: 5
- max_equity_drawdown_pct: 25
- min_profit_factor: 1.2
- min_trades: 250
- must_validate_splits: true
- max_tests: 50
- max_runtime_minutes: 360
- objective: maximize robust return under drawdown and validation constraints

## EA
Advisors\US30_MultiStrategyLab_M15

## Symbol
US30

## Timeframe
M15

## Date range
2020.01.01 -> 2025.01.01

## Baseline inputs
- TP_R: 2.0
- ATR_Mult: 2.0
- SessionFilter: 1

## Parameters allowed to change
- TP_R: [1.5, 2.0, 2.5]
- ATR_Mult: [1.5, 2.0, 3.0]

## Hard limits
- min_profit: 0
- min_profit_factor: 1.2
- max_equity_dd_pct: 25
- min_trades: 250
- max_tests: 50
- stop_after_failures: 10

## Splits required
- top_candidates: 2
- S1: 2020.01.01 -> 2022.06.30
- S2: 2022.07.01 -> 2025.01.01
- all_splits_profitable: true
- min_profit_factor_each_split: 1.1
- max_equity_dd_pct_each_split: 28
- min_trades_each_split: 60

## Stress tests required
- Weekend gap stress is still manual in this phase.

## Ranking rules
- all splits profitable
- PF stability
- max equity drawdown
- enough trades

## Stop rules
- stop_after_failures: 10
- stop_on_ui_failure: true
