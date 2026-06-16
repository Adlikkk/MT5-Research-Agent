# Example Gold Research Request

## Goal
Find a robust single-run parameter set for GoldEA on XAUUSD_DUKA that survives date splits.

## EA
GoldEA

## Symbol
XAUUSD_DUKA

## Timeframe
H1

## Date range
2020.01.01 -> 2026.06.01

## Baseline inputs
- ADX_Hard_Min: 18
- SL_ATR: 1.7
- TP_R: 2.2
- SessionStartHour: 10
- SessionEndHour: 18
- AllowWednesday: false

## Parameters allowed to change
- TP_R: [2.0, 2.1, 2.2, 2.3]
- SL_ATR: [1.6, 1.7, 1.8]
- ADX_Hard_Min: [17, 18, 19]

## Hard limits
- min_profit: 0
- min_profit_factor: 1.1
- max_equity_dd_pct: 18
- min_trades: 100
- max_tests: 36
- stop_after_failures: 10

## Splits required
- top_candidates: 2
- S1_2020_2021: 2020.01.01 -> 2021.12.31
- S2_2022_2023: 2022.01.01 -> 2023.12.31
- S3_2024_2026: 2024.01.01 -> 2026.06.01
- all_splits_profitable: true
- min_profit_factor_each_split: 1.05
- max_equity_dd_pct_each_split: 20
- min_trades_each_split: 50

## Stress tests required
- Weekend gap stress is still manual in this phase.
- Spread shock stress is still manual in this phase.

## Ranking rules
- all splits profitable
- PF stability
- max equity drawdown
- enough trades
- stress survival
- weak-period survival

## Stop rules
- stop_after_failures: 10
- stop_on_ui_failure: true
