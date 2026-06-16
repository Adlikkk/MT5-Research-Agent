# AGENTS.md

## Project

- Name: `MT5 Research Agent`
- Platform: local Windows-only tool
- Primary stack: Python
- Primary target: MetaTrader 5 Strategy Tester GUI automation

## Purpose

Build a deterministic local research automation tool that lets a user give Codex a research task or prompt, then uses MetaTrader 5 Strategy Tester automation to:

- run backtests
- change EA input values
- collect and parse results
- save every test as structured artifacts

This repository is for research automation only. It is not a trading bot.

## Non-Negotiable Safety Rules

1. No live trading.
2. No broker order placement.
3. Never use MetaTrader5 Python `order_send`.
4. Never click `Buy`/`Sell` or any live chart trading button.
5. Only operate inside Strategy Tester.
6. Always save logs and screenshots before and after GUI actions.
7. Every test must have a unique `test_id`.
8. Every test must save:
   - EA name
   - symbol
   - timeframe
   - date range
   - deposit
   - model
   - all input values
   - raw report path
   - parsed metrics
   - pass/fail decision
   - rejection reason if failed
9. Prefer deterministic UI automation with `pywinauto`.
10. GUI coordinate clicking is allowed only behind `--allow-gui-clicks` and only after calibration.
11. Stop immediately if the expected MT5 UI state is not found.
12. Do not optimize for profit alone. Rank by robustness using:
   - all splits profitable
   - PF stability
   - max equity drawdown
   - enough trades
   - stress survival
   - weak-period survival
13. Keep changes small and checkpointable.
14. After each phase, update `README.md` with current commands and limitations.

## Operational Boundaries

- MT5 Strategy Tester is the only allowed MT5 surface.
- Assume the tool runs on a local Windows workstation with MT5 installed.
- Prefer stable window/control discovery over timing-based or coordinate-based automation.
- If the UI cannot be verified deterministically, fail fast and preserve evidence.
- Do not silently continue after partial GUI failure.

## Required Evidence For GUI Actions

Before and after each significant GUI action, save:

- a timestamped log entry
- a screenshot
- the current `test_id` if a test is active
- the intended action
- the observed UI state

If an action fails, save failure evidence before exiting the step.

## Test Artifact Contract

Each Strategy Tester run must produce a unique `test_id` and save structured outputs for reproducibility and review.

Minimum required fields:

- `test_id`
- `ea_name`
- `symbol`
- `timeframe`
- `date_range`
- `deposit`
- `model`
- `inputs`
- `raw_report_path`
- `parsed_metrics`
- `decision`
- `rejection_reason`
- `artifacts`
  - screenshots
  - logs

Prefer machine-readable formats such as JSON for metadata and parsed metrics.

## Preferred Implementation Direction

Build the system incrementally. Do not attempt the full end-to-end system in one pass.

Recommended phase order:

1. Repository scaffolding
   - basic Python project structure
   - artifact directories
   - config model
   - logging
   - `README.md`
2. MT5 attachment and read-only UI inspection
   - locate Strategy Tester window
   - verify expected tester state
   - capture screenshots/logs
3. Deterministic tester navigation
   - select EA/symbol/timeframe/date range
   - read and validate visible state
4. Input management
   - set EA inputs deterministically
   - persist requested and observed values
5. Backtest execution
   - start tester run
   - wait for completion
   - fail safely on unexpected state
6. Report export and parsing
   - export raw report
   - parse key metrics
   - persist structured result files
7. Research orchestration
   - accept research tasks
   - generate parameter variants
   - score by robustness rules
8. Controlled fallback clicks
   - enable only behind calibrated `--allow-gui-clicks`
   - keep disabled by default

## Engineering Rules For Codex

- Make the smallest viable change for the current phase.
- Keep code modular and easy to inspect.
- Prefer explicit state machines over implicit flows.
- Prefer typed Python models for configs, run records, and parsed metrics.
- Write checkpoints so interrupted work can be resumed safely.
- Record assumptions in code or `README.md`.
- If `README.md` does not exist yet, create it in the first implementation phase and keep it current afterward.

## Disallowed Shortcuts

- No live terminal trading automation.
- No use of MT5 APIs for order placement.
- No unguarded coordinate clicking.
- No skipping screenshots/logs around GUI actions.
- No ranking strategies by profit alone.
- No large unreviewable refactors when a smaller phase change is sufficient.

## Definition Of Done For Any Phase

A phase is only complete when:

- the new behavior is limited to the intended phase scope
- safety constraints remain enforced
- artifacts/logging behavior is documented
- commands and current limitations are reflected in `README.md`
- the repo remains checkpointable for the next phase
