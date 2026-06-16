# Research Workflow

## Prompt To Execution

1. Create a Markdown request in `research_requests/`.
2. Run:

```powershell
python -m mt5_research_agent plan-from-request research_requests/example_gold_request.md
```

3. Review generated files under `artifacts/research_plans/<slug>/`.
4. If the request is complete, run:

```powershell
python -m mt5_research_agent show-task artifacts/generated_tasks/GOLD-0001.json
python -m mt5_research_agent smoke-cli artifacts/generated_tasks/GOLD-0001.json
python -m mt5_research_agent run-task artifacts/generated_tasks/GOLD-0001.json --execution-mode cli
python -m mt5_research_agent run-research research_requests/example_gold_request.md
```

Background CLI mode is the default execution path. GUI automation remains available only as a fallback.

CLI mode is still one-shot by default. It launches MT5 with generated `.set` and `.ini` files, runs one tester configuration, then usually lets the terminal exit with `ShutdownTerminal=1`.

## Real Smoke Task

Before debugging a full experiment, create one short deterministic smoke task with the real EA and symbol:

```powershell
python -m mt5_research_agent create-smoke-task --test-id US30-SMOKE-0001 --ea US30_MultiStrategyLab_M15 --symbol US30 --timeframe M15 --period-from 2024.01.01 --period-to 2024.02.01 --deposit 10000
python -m mt5_research_agent print-ini artifacts/generated_tasks/US30-SMOKE-0001.json
python -m mt5_research_agent print-set artifacts/generated_tasks/US30-SMOKE-0001.json
python -m mt5_research_agent smoke-cli artifacts/generated_tasks/US30-SMOKE-0001.json --run --timeout-seconds 900
python -m mt5_research_agent inspect-run US30-SMOKE-0001
python -m mt5_research_agent print-terminal-folders
python -m mt5_research_agent find-reports --since-minutes 120
```

If you need the terminal to remain open after the smoke run for manual diagnosis, add `--keep-terminal-open`.

## Planner Loop

After a batch completes, generate the next explainable batch:

```powershell
python -m mt5_research_agent plan-next --request research_requests/example_gold_request.md
python -m mt5_research_agent run-planned artifacts/generated_experiments/experiment_<timestamp>.json
```

## Outputs

- SQLite results database
- CSV leaderboard
- split validation reports
- candidate summaries
- research report
- planner history

## Current Limitation

Stress tests can be requested and documented, but they are not automated yet.
