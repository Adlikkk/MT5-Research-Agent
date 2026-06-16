# Contributing

## Scope

This project automates MT5 Strategy Tester research. It does not trade live and does not provide financial advice.

Contributions should preserve the core safety model:

- Strategy Tester only
- no live trading
- no broker order placement
- no `MetaTrader5.order_send`
- stop on unexpected UI state
- log and screenshot before and after GUI-affecting actions

## Development Setup

1. Install Python 3.11+ on Windows.
2. Create a virtual environment.
3. Install dependencies:

```powershell
python -m pip install -e .[dev]
```

4. Copy `config.example.json` to `config.json` and adjust local paths.

## Required Checks

Run these before opening a pull request:

```powershell
python -m pytest
ruff check .
mypy mt5_research_agent
```

## Change Guidelines

- Keep changes small and checkpointable.
- Prefer deterministic behavior over heuristics.
- Document MT5 UI assumptions explicitly.
- Update `README.md` and relevant files under `docs/` when behavior changes.
- Add or update tests for parsing, planning, and storage changes.

## Pull Request Notes

Include:

- the phase or feature being changed
- safety impact
- verification commands
- known limitations or unsupported MT5 variants
